from conftest import sample_resume

from matcher import TfidfIndex, score_jobs, strip_html, title_similarity


def test_strip_html_removes_markup_and_scripts():
    html = "<div>Senior <b>Talent</b> Partner<script>bad()</script>&amp; more</div>"
    assert strip_html(html) == "Senior Talent Partner & more"


def test_relevant_job_outscores_irrelevant_one():
    resume = sample_resume()
    jobs = [
        {"id": 1, "title": "Director of People Operations", "company": "Acme",
         "location": "Portland, OR", "remote": False,
         "description": "Own people operations, talent acquisition and our Workday HRIS.",
         "salary_min": 150000, "salary_max": 180000},
        {"id": 2, "title": "Line Cook", "company": "Diner",
         "location": "Portland, OR", "remote": False,
         "description": "Prepare food on a busy line. No people operations involved.",
         "salary_min": 40000, "salary_max": 45000},
    ]
    by_id = {r["job_id"]: r for r in score_jobs(jobs, resume)}
    assert by_id[1]["score"] > by_id[2]["score"]
    assert by_id[1]["score"] >= 45
    assert "Workday".lower() in [s.lower() for s in by_id[1]["breakdown"]["matched_skills"]]


def test_excluded_keyword_collapses_score():
    resume = sample_resume()
    job = {"id": 3, "title": "Director of People Operations", "company": "Acme",
           "location": "Portland, OR", "remote": False,
           "description": "Unpaid people operations role working with Workday.",
           "salary_min": None, "salary_max": None}
    result = score_jobs([job], resume)[0]
    assert result["breakdown"]["excluded_by"] == ["unpaid"]
    assert result["breakdown"]["multipliers"]["exclusions"] == 0.25
    assert "excluded term" in result["breakdown"]["summary"]


def test_salary_below_floor_reduces_score():
    resume = sample_resume()
    base = {"id": 4, "title": "Head of Talent", "company": "Acme", "location": "Portland, OR",
            "remote": False, "description": "Lead talent acquisition and people analytics."}
    good = score_jobs([{**base, "salary_min": 150000, "salary_max": 190000}], resume)[0]
    low = score_jobs([{**base, "id": 5, "salary_min": 70000, "salary_max": 80000}], resume)[0]
    assert good["score"] > low["score"]
    assert low["breakdown"]["multipliers"]["salary"] < 1.0


def test_remote_only_preference_penalizes_onsite():
    resume = sample_resume()
    resume["preferences"]["remote_only"] = True
    job = {"id": 6, "title": "Head of Talent", "company": "Acme", "location": "Austin, TX",
           "remote": False, "description": "Onsite talent leadership role.",
           "salary_min": 160000, "salary_max": 190000}
    result = score_jobs([job], resume)[0]
    assert result["breakdown"]["multipliers"]["location"] < 0.5


def test_title_similarity_prefers_closest_target():
    ratio, matched = title_similarity("Director of People Operations", ["Head of Talent", "Director of People Operations"])
    assert matched == "Director of People Operations"
    assert ratio == 1.0


def test_tfidf_cosine_is_symmetric_and_bounded():
    index = TfidfIndex(["people operations workday", "line cook kitchen"])
    a, b = index.vector("people operations workday"), index.vector("workday people operations")
    assert 0.99 <= TfidfIndex.cosine(a, b) <= 1.0
    assert TfidfIndex.cosine(a, index.vector("line cook kitchen")) < 0.2
