"""REST API for the job application dashboard and browser extension."""

import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, jsonify, request  # noqa: E402
from flask_cors import CORS  # noqa: E402

import database as db  # noqa: E402
import form_detector  # noqa: E402
import resume as resume_mod  # noqa: E402
from matcher import score_jobs  # noqa: E402
from scraper import ScrapeError, scrape_source  # noqa: E402

DEFAULT_SETTINGS = {
    "min_score": 45,
    "quick_apply": False,
    "include_eeo_answers": False,
    "auto_scrape_on_start": False,
}


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__)
    app.config["DB_PATH"] = db_path or db.DEFAULT_DB_PATH
    # The dashboard runs on localhost:5173 and the extension injects into
    # arbitrary employer sites, so both origins need to reach the API.
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    db.init_db(app.config["DB_PATH"])

    def path() -> str:
        return app.config["DB_PATH"]

    def load_resume_or_error():
        try:
            return resume_mod.load_resume(), None
        except resume_mod.ResumeError as exc:
            return None, (jsonify({"error": str(exc)}), 400)

    @app.errorhandler(Exception)
    def handle_error(exc):  # pragma: no cover - safety net
        app.logger.error("unhandled error: %s\n%s", exc, traceback.format_exc())
        return jsonify({"error": str(exc)}), 500

    # --- health / stats ----------------------------------------------------

    @app.get("/api/health")
    def health():
        return jsonify({"ok": True, "db": path()})

    @app.get("/api/stats")
    def get_stats():
        return jsonify(db.stats(path()))

    # --- resume ------------------------------------------------------------

    @app.get("/api/resume")
    def get_resume():
        data, error = load_resume_or_error()
        if error:
            return error
        return jsonify({"resume": data, "autofill_values": resume_mod.autofill_values(data)})

    @app.put("/api/resume")
    def put_resume():
        payload = request.get_json(force=True, silent=True) or {}
        problems = resume_mod.validate_resume(payload)
        if problems:
            return jsonify({"error": "invalid resume", "problems": problems}), 400
        resume_mod.save_resume(payload)
        return jsonify({"resume": payload, "autofill_values": resume_mod.autofill_values(payload)})

    @app.post("/api/resume/import-pdf")
    def import_pdf():
        payload = request.get_json(force=True, silent=True) or {}
        pdf_path = os.path.expanduser(payload.get("path", ""))
        if not pdf_path or not os.path.exists(pdf_path):
            return jsonify({"error": f"no PDF at '{pdf_path}'"}), 400
        try:
            parsed = resume_mod.parse_pdf(pdf_path)
        except resume_mod.ResumeError as exc:
            return jsonify({"error": str(exc)}), 400
        # Never written straight to disk — the parse is a draft for review.
        return jsonify({"draft": parsed, "problems": resume_mod.validate_resume(parsed)})

    # --- sources & scraping -------------------------------------------------

    @app.get("/api/sources")
    def get_sources():
        return jsonify({"sources": db.list_sources(path())})

    @app.post("/api/sources")
    def post_source():
        payload = request.get_json(force=True, silent=True) or {}
        kind = payload.get("kind")
        if kind not in ("greenhouse", "lever", "ashby", "smartrecruiters", "workday", "generic"):
            return jsonify({"error": f"unsupported source kind '{kind}'"}), 400
        if kind in ("workday", "generic") and not payload.get("url"):
            return jsonify({"error": f"'{kind}' sources need a url"}), 400
        if kind not in ("workday", "generic") and not payload.get("token"):
            return jsonify({"error": f"'{kind}' sources need a board token"}), 400
        source_id = db.add_source(
            name=payload.get("name") or payload.get("token") or payload.get("url"),
            kind=kind, token=payload.get("token"), url=payload.get("url"),
            enabled=payload.get("enabled", True), db_path=path(),
        )
        return jsonify({"id": source_id, "sources": db.list_sources(path())}), 201

    @app.delete("/api/sources/<int:source_id>")
    def remove_source(source_id):
        db.delete_source(source_id, path())
        return jsonify({"deleted": source_id})

    @app.post("/api/scrape")
    def run_scrape():
        payload = request.get_json(force=True, silent=True) or {}
        sources = db.list_sources(path(), enabled_only=True)
        if payload.get("source_id"):
            sources = [s for s in sources if s["id"] == payload["source_id"]]
        if not sources:
            return jsonify({"error": "no enabled sources configured"}), 400

        report = {"sources": [], "new": 0, "updated": 0, "errors": 0}
        for source in sources:
            try:
                jobs = scrape_source(source)
            except ScrapeError as exc:
                db.mark_source_scraped(source["id"], str(exc), path())
                report["sources"].append({"name": source["name"], "error": str(exc)})
                report["errors"] += 1
                continue
            new = updated = 0
            for job in jobs:
                _, is_new = db.upsert_job(job, source_id=source["id"], db_path=path())
                new += is_new
                updated += not is_new
            db.mark_source_scraped(source["id"], None, path())
            report["sources"].append({"name": source["name"], "found": len(jobs), "new": new, "updated": updated})
            report["new"] += new
            report["updated"] += updated

        scored = _rescore_all()
        report["scored"] = scored
        return jsonify(report)

    def _rescore_all() -> int:
        data, error = load_resume_or_error()
        if error:
            return 0
        jobs = db.all_jobs_for_scoring(path())
        for result in score_jobs(jobs, data):
            db.set_score(result["job_id"], result["score"], result["breakdown"], path())
        return len(jobs)

    @app.post("/api/rescore")
    def rescore():
        return jsonify({"scored": _rescore_all()})

    # --- jobs ---------------------------------------------------------------

    @app.get("/api/jobs")
    def get_jobs():
        args = request.args
        tri = lambda key: None if args.get(key) in (None, "", "any") else args.get(key) == "true"  # noqa: E731
        jobs = db.query_jobs(
            db_path=path(),
            min_score=args.get("min_score", 0, type=float),
            q=args.get("q"),
            company=args.get("company"),
            remote=tri("remote"),
            source_kind=args.get("source"),
            applied=tri("applied"),
            limit=min(args.get("limit", 50, type=int), 200),
            offset=args.get("offset", 0, type=int),
            sort=args.get("sort", "score"),
        )
        return jsonify({"jobs": jobs, "count": len(jobs)})

    @app.get("/api/jobs/<int:job_id>")
    def get_one_job(job_id):
        job = db.get_job(job_id, path())
        if job is None:
            return jsonify({"error": "job not found"}), 404
        return jsonify(job)

    @app.get("/api/jobs/lookup")
    def lookup_job():
        job = db.find_job_by_url(request.args.get("url", ""), path())
        return jsonify({"job": job})

    # --- applications -------------------------------------------------------

    @app.get("/api/applications")
    def get_applications():
        apps = db.list_applications(status=request.args.get("status"), db_path=path())
        for app_row in apps:
            app_row["submissions"] = db.submissions_for_application(app_row["id"], path())
        return jsonify({"applications": apps})

    @app.post("/api/applications")
    def post_application():
        payload = request.get_json(force=True, silent=True) or {}
        job_id = payload.get("job_id")
        company, title, url = payload.get("company"), payload.get("title"), payload.get("url")
        if job_id:
            job = db.get_job(job_id, path())
            if job is None:
                return jsonify({"error": "job not found"}), 404
            company, title, url = company or job["company"], title or job["title"], url or job["url"]
        if not company or not title:
            return jsonify({"error": "company and title are required"}), 400
        app_id = db.create_application(
            company=company, title=title, job_id=job_id, url=url,
            status=payload.get("status", "applied"), method=payload.get("method", "manual"),
            notes=payload.get("notes"), db_path=path(),
        )
        return jsonify(db.get_application(app_id, path())), 201

    @app.patch("/api/applications/<int:app_id>")
    def patch_application(app_id):
        payload = request.get_json(force=True, silent=True) or {}
        updated = db.update_application(app_id, db_path=path(), **payload)
        if updated is None:
            return jsonify({"error": "application not found"}), 404
        return jsonify(updated)

    # --- form autofill ------------------------------------------------------

    @app.post("/api/forms/analyze")
    def analyze():
        payload = request.get_json(force=True, silent=True) or {}
        fields = payload.get("fields") or []
        if not isinstance(fields, list):
            return jsonify({"error": "'fields' must be a list"}), 400
        data, error = load_resume_or_error()
        if error:
            return error

        url = payload.get("url", "")
        ats = form_detector.detect_ats(url)
        host = payload.get("host") or ""
        settings = {**DEFAULT_SETTINGS, **db.get_settings(path())}
        analysis = form_detector.analyze_form(
            fields=fields,
            values=resume_mod.autofill_values(data),
            url=url,
            learned=db.learned_mappings(ats, host, path()),
            include_sensitive=bool(settings.get("include_eeo_answers")),
        )
        analysis["job"] = db.find_job_by_url(url, path())
        analysis["quick_apply"] = bool(settings.get("quick_apply"))
        # Stated on every response so the client never has to assume otherwise.
        analysis["will_submit"] = False
        return jsonify(analysis)

    @app.post("/api/forms/learn")
    def learn():
        payload = request.get_json(force=True, silent=True) or {}
        signature, canonical = payload.get("signature"), payload.get("canonical")
        if not signature or canonical not in form_detector.CANONICAL_FIELDS:
            return jsonify({"error": "signature and a known canonical field are required",
                            "known_fields": form_detector.CANONICAL_FIELDS}), 400
        db.learn_mapping(payload.get("ats", "unknown"), signature, canonical,
                         payload.get("host", ""), path())
        return jsonify({"learned": {"signature": signature, "canonical": canonical}})

    @app.post("/api/forms/log")
    def log_form():
        payload = request.get_json(force=True, silent=True) or {}
        url = payload.get("url", "")
        job = db.find_job_by_url(url, path()) if url else None
        job_id = payload.get("job_id") or (job["id"] if job else None)
        company = payload.get("company") or (job["company"] if job else "Unknown company")
        title = payload.get("title") or (job["title"] if job else "Unknown role")

        app_id = db.create_application(
            company=company, title=title, job_id=job_id, url=url,
            status=payload.get("status", "draft"), method="extension", db_path=path(),
        )
        submission_id = db.log_submission(
            url=url,
            filled=payload.get("filled", []),
            skipped=payload.get("skipped", []),
            ats=payload.get("ats") or form_detector.detect_ats(url),
            application_id=app_id,
            submitted=False,   # the extension never submits; status is set by you
            db_path=path(),
        )
        return jsonify({"application_id": app_id, "submission_id": submission_id,
                        "application": db.get_application(app_id, path())}), 201

    @app.get("/api/forms/fields")
    def known_fields():
        return jsonify({"groups": form_detector.FIELD_GROUPS, "fields": form_detector.CANONICAL_FIELDS})

    # --- settings -----------------------------------------------------------

    @app.get("/api/settings")
    def get_settings():
        return jsonify({**DEFAULT_SETTINGS, **db.get_settings(path())})

    @app.put("/api/settings")
    def put_settings():
        payload = request.get_json(force=True, silent=True) or {}
        merged = db.set_settings(payload, path())
        return jsonify({**DEFAULT_SETTINGS, **merged})

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5057))
    app.run(host="127.0.0.1", port=port, debug=bool(os.environ.get("JAA_DEBUG")))
