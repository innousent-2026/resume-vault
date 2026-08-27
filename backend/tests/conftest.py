import os
import sys

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

import pytest  # noqa: E402

import database as db  # noqa: E402
from app import create_app  # noqa: E402


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "test.db")
    db.close_connection()
    db.init_db(path)
    yield path
    db.close_connection()


@pytest.fixture
def client(db_path, monkeypatch, tmp_path):
    import resume as resume_mod
    resume_file = tmp_path / "resume.json"
    monkeypatch.setattr(resume_mod, "DEFAULT_RESUME_PATH", str(resume_file))
    resume_mod.save_resume(sample_resume(), str(resume_file))
    app = create_app(db_path)
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def sample_resume() -> dict:
    return {
        "profile": {
            "first_name": "Jane", "last_name": "Doe", "email": "jane@example.com",
            "phone": "555-123-4567",
            "address": {"line1": "1 Main St", "city": "Portland", "state": "OR", "postal_code": "97201",
                        "country": "United States"},
            "links": {"linkedin": "https://linkedin.com/in/janedoe"},
            "work_authorization": {"authorized_to_work": "Yes", "requires_sponsorship": "No"},
        },
        "summary": "People operations leader focused on talent acquisition and HRIS.",
        "skills": ["Talent Acquisition", "Workday", "People Analytics", "SQL"],
        "experience": [{"company": "Northwind", "title": "Director of People Operations",
                        "start_date": "2021-03", "end_date": None,
                        "bullets": ["Rebuilt the hiring funnel", "Led a Workday migration"]}],
        "education": [{"school": "University of Oregon", "degree": "BS", "field": "Business",
                       "graduation_date": "2013-06"}],
        "preferences": {
            "titles": ["Director of People Operations", "Head of Talent"],
            "keywords": ["people operations", "workday"],
            "exclude_keywords": ["unpaid"],
            "min_salary": 140000,
            "locations": ["Portland, OR"],
            "desired_salary": "175000",
        },
        "eeo": {"gender": "Decline to self-identify"},
        "documents": {"resume_path": "~/resume.pdf"},
    }
