import json


def test_health_and_empty_stats(client):
    assert client.get("/api/health").get_json()["ok"] is True
    stats = client.get("/api/stats").get_json()
    assert stats["jobs"] == 0 and stats["applications"] == 0


def test_resume_round_trip_and_autofill_values(client):
    body = client.get("/api/resume").get_json()
    assert body["resume"]["profile"]["first_name"] == "Jane"
    values = body["autofill_values"]
    assert values["full_name"] == "Jane Doe"
    assert values["email"] == "jane@example.com"
    assert values["current_title"] == "Director of People Operations"
    assert "eeo_gender" in values


def test_resume_rejects_invalid_payload(client):
    resp = client.put("/api/resume", json={"profile": {"first_name": "Jane"}})
    assert resp.status_code == 400
    assert any("email" in p for p in resp.get_json()["problems"])


def test_source_validation(client):
    assert client.post("/api/sources", json={"kind": "nope"}).status_code == 400
    assert client.post("/api/sources", json={"kind": "greenhouse"}).status_code == 400
    assert client.post("/api/sources", json={"kind": "workday", "name": "Acme"}).status_code == 400
    created = client.post("/api/sources", json={"kind": "greenhouse", "name": "Acme", "token": "acme"})
    assert created.status_code == 201
    assert len(client.get("/api/sources").get_json()["sources"]) == 1


def test_jobs_scored_filtered_and_applied(client, db_path):
    import database as db
    db.upsert_job({
        "source_kind": "greenhouse", "external_id": "gh:1", "company": "Acme",
        "title": "Director of People Operations", "location": "Portland, OR", "remote": False,
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "description": "Lead people operations and our Workday HRIS.",
        "salary_min": 160000, "salary_max": 190000,
    }, db_path=db_path)
    db.upsert_job({
        "source_kind": "greenhouse", "external_id": "gh:2", "company": "Diner",
        "title": "Line Cook", "location": "Austin, TX", "remote": False,
        "url": "https://boards.greenhouse.io/diner/jobs/2", "description": "Cook food.",
    }, db_path=db_path)

    assert client.post("/api/rescore").get_json()["scored"] == 2
    jobs = client.get("/api/jobs?sort=score").get_json()["jobs"]
    assert jobs[0]["title"] == "Director of People Operations"
    assert jobs[0]["breakdown"]["summary"]

    strong = client.get("/api/jobs?min_score=40").get_json()["jobs"]
    assert [j["title"] for j in strong] == ["Director of People Operations"]

    top_id = jobs[0]["id"]
    created = client.post("/api/applications", json={"job_id": top_id, "status": "applied"})
    assert created.status_code == 201
    unapplied = client.get("/api/jobs?applied=false").get_json()["jobs"]
    assert top_id not in [j["id"] for j in unapplied]


def test_application_lifecycle(client):
    created = client.post("/api/applications", json={
        "company": "Acme", "title": "Head of Talent", "url": "https://acme.example/apply"}).get_json()
    assert created["status"] == "applied" and created["applied_at"]
    patched = client.patch(f"/api/applications/{created['id']}",
                           json={"status": "interviewing", "notes": "Phone screen Tuesday"}).get_json()
    assert patched["status"] == "interviewing"
    assert patched["notes"] == "Phone screen Tuesday"
    assert client.patch("/api/applications/999", json={"status": "rejected"}).status_code == 404


def test_form_analyze_plan_and_no_submit_flag(client):
    payload = {
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "host": "boards.greenhouse.io",
        "fields": [
            {"field_id": "1", "selector": "#fn", "label": "First Name", "name": "first_name", "type": "text"},
            {"field_id": "2", "selector": "#em", "label": "Email", "name": "email", "type": "email"},
            {"field_id": "3", "selector": "#sig", "label": "Electronic Signature", "type": "text"},
            {"field_id": "4", "selector": "#cv", "label": "Resume", "type": "file"},
        ],
    }
    body = client.post("/api/forms/analyze", json=payload).get_json()
    assert body["will_submit"] is False
    assert body["ats"] == "greenhouse"
    assert sorted(p["canonical"] for p in body["plan"]) == ["email", "first_name"]
    reasons = " ".join(s["skip_reason"] for s in body["skipped"])
    assert "by hand" in reasons and "manually" in reasons


def test_form_learning_changes_future_analysis(client):
    field = {"field_id": "9", "selector": "#q9", "label": "Q9", "name": "cand_q_00099", "type": "text"}
    payload = {"url": "https://careers.acme.com/apply", "host": "careers.acme.com", "fields": [field]}

    first = client.post("/api/forms/analyze", json=payload).get_json()
    assert first["plan"] == []
    signature = first["skipped"][0]["signature"]

    assert client.post("/api/forms/learn", json={
        "signature": signature, "canonical": "phone", "ats": "unknown", "host": "careers.acme.com",
    }).status_code == 200
    assert client.post("/api/forms/learn", json={"signature": signature, "canonical": "not_a_field"}).status_code == 400

    second = client.post("/api/forms/analyze", json=payload).get_json()
    assert second["plan"][0]["canonical"] == "phone"
    assert second["plan"][0]["value"] == "555-123-4567"


def test_form_log_creates_application_and_submission(client, db_path):
    import database as db
    db.upsert_job({
        "source_kind": "lever", "external_id": "lv:1", "company": "Acme", "title": "Head of Talent",
        "url": "https://jobs.lever.co/acme/abc", "description": "Talent leadership.",
    }, db_path=db_path)

    body = client.post("/api/forms/log", json={
        "url": "https://jobs.lever.co/acme/abc",
        "filled": [{"canonical": "email", "label": "Email", "value_preview": "jane@…"}],
        "skipped": [{"label": "Resume", "skip_reason": "file"}],
        "status": "applied",
    }).get_json()

    assert body["application"]["company"] == "Acme"
    assert body["application"]["status"] == "applied"
    apps = client.get("/api/applications").get_json()["applications"]
    assert apps[0]["submissions"][0]["submitted"] is False
    assert apps[0]["submissions"][0]["filled"][0]["canonical"] == "email"


def test_settings_defaults_and_updates(client):
    defaults = client.get("/api/settings").get_json()
    assert defaults["quick_apply"] is False and defaults["include_eeo_answers"] is False
    updated = client.put("/api/settings", json={"quick_apply": True, "min_score": 60}).get_json()
    assert updated["quick_apply"] is True and updated["min_score"] == 60
    assert client.get("/api/settings").get_json()["min_score"] == 60


def test_eeo_answers_only_after_opt_in(client):
    field = {"field_id": "g", "selector": "#g", "label": "Gender", "type": "select",
             "options": [{"label": "Decline to self-identify", "value": "d"}]}
    payload = {"url": "https://boards.greenhouse.io/acme", "fields": [field]}
    assert client.post("/api/forms/analyze", json=payload).get_json()["plan"] == []
    client.put("/api/settings", json={"include_eeo_answers": True})
    assert client.post("/api/forms/analyze", json=payload).get_json()["plan"][0]["value"] == "d"


def test_scrape_requires_sources(client):
    resp = client.post("/api/scrape", json={})
    assert resp.status_code == 400
    assert "no enabled sources" in resp.get_json()["error"]
