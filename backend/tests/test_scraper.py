import json

import pytest

import scraper


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = payload if isinstance(payload, str) else json.dumps(payload)

    def json(self):
        return self._payload if not isinstance(self._payload, str) else json.loads(self._payload)


@pytest.fixture(autouse=True)
def no_rate_limit(monkeypatch):
    monkeypatch.setattr(scraper, "RATE_LIMIT_SECONDS", 0)


def stub(monkeypatch, routes: dict):
    """Route URLs to canned responses; unknown URLs blow up loudly."""
    calls = []

    def fake_request(method, url, **kwargs):
        calls.append((method, url))
        for fragment, payload in routes.items():
            if fragment in url:
                return FakeResponse(payload)
        raise AssertionError(f"unexpected request to {url}")

    monkeypatch.setattr(scraper.requests, "request", fake_request)
    return calls


@pytest.mark.parametrize("text,expected", [
    ("The range is $150,000 - $180,000 per year", (150000, 180000)),
    ("Compensation: $120k–$160k", (120000, 160000)),
    ("Base pay of $145,000 annually", (145000, 145000)),
    ("Salary depends on experience", (None, None)),
    ("Coffee costs $5", (None, None)),
])
def test_parse_salary(text, expected):
    assert scraper.parse_salary(text) == expected


def test_greenhouse_adapter(monkeypatch):
    stub(monkeypatch, {"boards-api.greenhouse.io": {
        "meta": {"name": "Acme Corp"},
        "jobs": [{
            "id": 4242, "title": "Director of People Operations",
            "location": {"name": "Remote - US"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/4242",
            "content": "<p>Own people ops. Range $160,000 - $195,000.</p>",
            "updated_at": "2026-08-01T00:00:00Z",
            "departments": [{"name": "People"}],
        }],
    }})
    jobs = scraper.scrape_source({"kind": "greenhouse", "token": "acme", "name": "Acme"})
    assert len(jobs) == 1
    job = jobs[0]
    assert job["company"] == "Acme Corp"
    assert job["external_id"] == "greenhouse:acme:4242"
    assert job["remote"] is True
    assert (job["salary_min"], job["salary_max"]) == (160000, 195000)
    assert "<p>" not in job["description"]


def test_lever_adapter(monkeypatch):
    stub(monkeypatch, {"api.lever.co": [{
        "id": "abc-123", "text": "Head of Talent",
        "categories": {"location": "Portland, OR", "team": "People", "commitment": "Full-time"},
        "descriptionPlain": "Lead talent. Pay $150,000 to $170,000.",
        "additionalPlain": "Great benefits.",
        "hostedUrl": "https://jobs.lever.co/acme/abc-123",
        "createdAt": 1756000000000,
    }]})
    job = scraper.scrape_source({"kind": "lever", "token": "acme", "name": "Acme"})[0]
    assert job["title"] == "Head of Talent"
    assert job["remote"] is False
    assert (job["salary_min"], job["salary_max"]) == (150000, 170000)
    assert job["posted_at"].startswith("2025-")


def test_ashby_adapter_uses_structured_compensation(monkeypatch):
    stub(monkeypatch, {"api.ashbyhq.com": {"jobs": [{
        "id": "job-1", "title": "People Operations Manager", "location": "Remote",
        "isRemote": True, "jobUrl": "https://jobs.ashbyhq.com/acme/job-1",
        "descriptionPlain": "Run people ops.",
        "compensation": {"summaryComponents": [
            {"compensationType": "Salary", "interval": "1 YEAR", "minValue": 140000, "maxValue": 165000}]},
        "publishedAt": "2026-08-10T00:00:00Z",
    }]}})
    job = scraper.scrape_source({"kind": "ashby", "token": "acme"})[0]
    assert (job["salary_min"], job["salary_max"]) == (140000, 165000)
    assert job["remote"] is True


def test_smartrecruiters_pages_and_fetches_bodies(monkeypatch):
    stub(monkeypatch, {
        "postings?limit=100": {"totalFound": 1, "content": [{
            "id": "p1", "name": "Talent Partner",
            "location": {"city": "Seattle", "region": "WA", "country": "us"},
            "company": {"name": "Acme"}, "releasedDate": "2026-07-01T00:00:00Z",
            "department": {"label": "People"},
        }]},
        "postings/p1": {"jobAd": {"sections": {
            "jobDescription": {"title": "Job Description", "text": "<p>Hire people. $130,000 - $150,000</p>"}}}},
    })
    job = scraper.scrape_source({"kind": "smartrecruiters", "token": "acme"})[0]
    assert job["url"] == "https://jobs.smartrecruiters.com/acme/p1"
    assert job["location"] == "Seattle, WA, us"
    assert "Hire people" in job["description"]
    assert (job["salary_min"], job["salary_max"]) == (130000, 150000)


def test_workday_adapter_builds_public_urls(monkeypatch):
    stub(monkeypatch, {"wday/cxs": {"total": 1, "jobPostings": [{
        "title": "HR Business Partner", "externalPath": "/job/Portland/HR-Business-Partner_R-123",
        "locationsText": "Portland, OR", "bulletFields": ["R-123"], "postedOn": "Posted 3 Days Ago",
    }]}})
    job = scraper.scrape_source({
        "kind": "workday", "name": "Acme",
        "url": "https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/Careers/jobs",
    })[0]
    assert job["url"] == "https://acme.wd1.myworkdayjobs.com/Careers/job/Portland/HR-Business-Partner_R-123"
    assert job["external_id"].endswith("R-123")


def test_generic_adapter_finds_and_enriches_links(monkeypatch):
    listing = """
      <html><body>
        <a href="/careers/jobs/head-of-talent">Head of Talent</a>
        <a href="/about">About us</a>
        <a href="https://twitter.com/acme">Twitter</a>
      </body></html>
    """
    detail = "<html><body><nav>menu</nav><h1>Head of Talent</h1><p>Remote role. $150,000 - $170,000.</p></body></html>"
    stub(monkeypatch, {"/careers/jobs/head-of-talent": detail, "acme.example.com/careers": listing})
    jobs = scraper.scrape_source({"kind": "generic", "name": "Acme", "url": "https://acme.example.com/careers"})
    assert len(jobs) == 1
    job = jobs[0]
    assert job["url"] == "https://acme.example.com/careers/jobs/head-of-talent"
    assert "menu" not in job["description"]
    assert (job["salary_min"], job["salary_max"]) == (150000, 170000)
    assert job["remote"] is True


def test_unknown_source_kind_raises(monkeypatch):
    with pytest.raises(scraper.ScrapeError, match="unknown source kind"):
        scraper.scrape_source({"kind": "monster.com"})


def test_http_error_becomes_scrape_error(monkeypatch):
    def fake_request(method, url, **kwargs):
        return FakeResponse({}, status_code=404)
    monkeypatch.setattr(scraper.requests, "request", fake_request)
    with pytest.raises(scraper.ScrapeError, match="404"):
        scraper.scrape_source({"kind": "greenhouse", "token": "nope"})
