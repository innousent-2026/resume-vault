#!/usr/bin/env python3
"""CLI for the job pipeline — useful before the dashboard is running.

    python backend/manage.py add-source greenhouse --token acme --name "Acme Corp"
    python backend/manage.py scrape
    python backend/manage.py jobs --min-score 60
    python backend/manage.py import-resume ~/Documents/resume.pdf
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import database as db  # noqa: E402
import resume as resume_mod  # noqa: E402
from matcher import score_jobs  # noqa: E402
from scraper import ScrapeError, scrape_source  # noqa: E402


def cmd_add_source(args):
    source_id = db.add_source(name=args.name or args.token or args.url, kind=args.kind,
                              token=args.token, url=args.url)
    print(f"source #{source_id} added: {args.kind} {args.token or args.url}")


def cmd_list_sources(args):
    for source in db.list_sources():
        flag = "on " if source["enabled"] else "off"
        print(f"[{flag}] #{source['id']:>3} {source['kind']:<16} {source['name']:<28} "
              f"last={source['last_scraped_at'] or 'never'} {source['last_error'] or ''}")


def cmd_scrape(args):
    sources = db.list_sources(enabled_only=True)
    if args.source_id:
        sources = [s for s in sources if s["id"] == args.source_id]
    if not sources:
        sys.exit("no enabled sources — add one with: manage.py add-source")
    total_new = 0
    for source in sources:
        try:
            jobs = scrape_source(source)
        except ScrapeError as exc:
            db.mark_source_scraped(source["id"], str(exc))
            print(f"  ! {source['name']}: {exc}")
            continue
        new = sum(db.upsert_job(job, source_id=source["id"])[1] for job in jobs)
        db.mark_source_scraped(source["id"], None)
        total_new += new
        print(f"  ✓ {source['name']}: {len(jobs)} postings ({new} new)")
    print(f"{total_new} new postings")
    cmd_score(args)


def cmd_score(args):
    data = resume_mod.load_resume()
    jobs = db.all_jobs_for_scoring()
    for result in score_jobs(jobs, data):
        db.set_score(result["job_id"], result["score"], result["breakdown"])
    print(f"scored {len(jobs)} postings")


def cmd_jobs(args):
    for job in db.query_jobs(min_score=args.min_score, limit=args.limit):
        print(f"{job['score']:>5.1f}  {job['company'][:22]:<22} {job['title'][:44]:<44} {job['url']}")
        if args.explain and job.get("breakdown"):
            print(f"        {job['breakdown']['summary']}")


def cmd_applications(args):
    for row in db.list_applications():
        print(f"{row['status']:<12} {row['applied_at'] or row['created_at']:<22} "
              f"{row['company'][:24]:<24} {row['title']}")


def cmd_import_resume(args):
    draft = resume_mod.parse_pdf(os.path.expanduser(args.pdf))
    out = args.out or "resume_data.draft.json"
    with open(out, "w") as fh:
        json.dump(draft, fh, indent=2)
    problems = resume_mod.validate_resume(draft)
    print(f"wrote {out} — review it, fix {len(problems)} problem(s), then save as resume_data.json")
    for problem in problems:
        print(f"  - {problem}")


def cmd_stats(args):
    print(json.dumps(db.stats(), indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("add-source", help="register a career site to scrape")
    p.add_argument("kind", choices=["greenhouse", "lever", "ashby", "smartrecruiters", "workday", "generic"])
    p.add_argument("--token", help="board token / company slug")
    p.add_argument("--url", help="endpoint or careers page (workday, generic)")
    p.add_argument("--name", help="display name")
    p.set_defaults(func=cmd_add_source)

    sub.add_parser("sources", help="list configured sources").set_defaults(func=cmd_list_sources)

    p = sub.add_parser("scrape", help="scrape all enabled sources, then rescore")
    p.add_argument("--source-id", type=int)
    p.set_defaults(func=cmd_scrape)

    sub.add_parser("score", help="rescore every stored posting").set_defaults(func=cmd_score)

    p = sub.add_parser("jobs", help="list matched jobs")
    p.add_argument("--min-score", type=float, default=0)
    p.add_argument("--limit", type=int, default=25)
    p.add_argument("--explain", action="store_true")
    p.set_defaults(func=cmd_jobs)

    sub.add_parser("applications", help="list tracked applications").set_defaults(func=cmd_applications)

    p = sub.add_parser("import-resume", help="draft resume_data.json from a PDF")
    p.add_argument("pdf")
    p.add_argument("--out")
    p.set_defaults(func=cmd_import_resume)

    sub.add_parser("stats", help="pipeline counts").set_defaults(func=cmd_stats)

    args = parser.parse_args()
    db.init_db()
    args.func(args)


if __name__ == "__main__":
    main()
