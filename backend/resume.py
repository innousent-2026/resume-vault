"""Resume loading, validation, and best-effort PDF import.

The canonical store is a JSON file (``resume_data.json`` at the repo root by
default) so it stays readable and hand-editable. Everything downstream — the
matcher, the form autofill, the dashboard — reads from here.
"""

import json
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_RESUME_PATH = os.environ.get("JAA_RESUME_PATH", os.path.join(REPO_ROOT, "resume_data.json"))
EXAMPLE_RESUME_PATH = os.path.join(REPO_ROOT, "resume_data.example.json")

REQUIRED_PROFILE_FIELDS = ["first_name", "last_name", "email"]


class ResumeError(Exception):
    pass


def load_resume(path: str | None = None) -> dict:
    path = path or DEFAULT_RESUME_PATH
    if not os.path.exists(path):
        if os.path.exists(EXAMPLE_RESUME_PATH):
            with open(EXAMPLE_RESUME_PATH) as fh:
                return json.load(fh)
        raise ResumeError(f"No resume found at {path}. Copy resume_data.example.json and fill it in.")
    with open(path) as fh:
        return json.load(fh)


def save_resume(data: dict, path: str | None = None) -> dict:
    path = path or DEFAULT_RESUME_PATH
    problems = validate_resume(data)
    if problems:
        raise ResumeError("; ".join(problems))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    return data


def validate_resume(data: dict) -> list[str]:
    problems = []
    if not isinstance(data, dict):
        return ["resume must be a JSON object"]
    profile = data.get("profile")
    if not isinstance(profile, dict):
        problems.append("missing 'profile' object")
    else:
        for field in REQUIRED_PROFILE_FIELDS:
            if not profile.get(field):
                problems.append(f"profile.{field} is required")
        email = profile.get("email", "")
        if email and "@" not in email:
            problems.append("profile.email does not look like an email address")
    for key in ("skills", "experience", "education"):
        if key in data and not isinstance(data[key], list):
            problems.append(f"'{key}' must be a list")
    return problems


def resume_text(resume: dict) -> str:
    """Flatten the resume into one blob for TF-IDF comparison."""
    parts = [resume.get("summary", "")]
    parts += [str(s) for s in resume.get("skills", [])]
    for job in resume.get("experience", []):
        parts += [job.get("title", ""), job.get("company", "")]
        parts += [str(b) for b in job.get("bullets", [])]
    for edu in resume.get("education", []):
        parts += [edu.get("degree", ""), edu.get("field", ""), edu.get("school", "")]
    parts += [str(c) for c in resume.get("certifications", [])]
    prefs = resume.get("preferences", {})
    parts += [str(t) for t in prefs.get("titles", [])]
    return "\n".join(p for p in parts if p)


def autofill_values(resume: dict) -> dict:
    """Canonical field name -> value, consumed by the extension."""
    p = resume.get("profile", {})
    addr = p.get("address", {}) or {}
    links = p.get("links", {}) or {}
    auth = p.get("work_authorization", {}) or {}
    experience = resume.get("experience", []) or []
    education = resume.get("education", []) or []
    latest_job = experience[0] if experience else {}
    latest_edu = education[0] if education else {}

    values = {
        "first_name": p.get("first_name"),
        "last_name": p.get("last_name"),
        "full_name": " ".join(x for x in [p.get("first_name"), p.get("last_name")] if x) or None,
        "preferred_name": p.get("preferred_name") or p.get("first_name"),
        "email": p.get("email"),
        "phone": p.get("phone"),
        "address_line1": addr.get("line1"),
        "address_line2": addr.get("line2"),
        "city": addr.get("city"),
        "state": addr.get("state"),
        "postal_code": addr.get("postal_code"),
        "country": addr.get("country"),
        "linkedin": links.get("linkedin"),
        "github": links.get("github"),
        "portfolio": links.get("portfolio") or links.get("website"),
        "current_company": latest_job.get("company"),
        "current_title": latest_job.get("title"),
        "years_experience": total_years_experience(resume),
        "school": latest_edu.get("school"),
        "degree": latest_edu.get("degree"),
        "field_of_study": latest_edu.get("field"),
        "graduation_year": str(latest_edu.get("graduation_date", ""))[:4] or None,
        "work_authorized": auth.get("authorized_to_work"),
        "requires_sponsorship": auth.get("requires_sponsorship"),
        "desired_salary": resume.get("preferences", {}).get("desired_salary"),
        "available_start_date": resume.get("preferences", {}).get("available_start_date"),
        "how_did_you_hear": resume.get("preferences", {}).get("how_did_you_hear"),
        "cover_letter": resume.get("documents", {}).get("cover_letter_template"),
        "resume_file": resume.get("documents", {}).get("resume_path"),
    }
    eeo = resume.get("eeo", {}) or {}
    for key in ("gender", "race", "veteran_status", "disability_status", "hispanic_latino"):
        if key in eeo:
            values[f"eeo_{key}"] = eeo[key]
    return {k: v for k, v in values.items() if v not in (None, "")}


def total_years_experience(resume: dict) -> int | None:
    """Sum of distinct years covered by listed roles (overlaps counted once)."""
    years: set[int] = set()
    for job in resume.get("experience", []) or []:
        start = _year(job.get("start_date"))
        if start is None:
            continue
        end = _year(job.get("end_date")) or _current_year()
        years.update(range(start, max(start, end) + 1))
    return len(years) or None


def _year(value) -> int | None:
    if not value:
        return None
    m = re.search(r"(19|20)\d{2}", str(value))
    return int(m.group(0)) if m else None


def _current_year() -> int:
    from datetime import date
    return date.today().year


# --- PDF import -------------------------------------------------------------

SECTION_PATTERNS = {
    "summary": r"^(professional\s+)?(summary|profile|objective)\b",
    "experience": r"^(work\s+|professional\s+)?experience\b|^employment\b",
    "education": r"^education\b",
    "skills": r"^(technical\s+)?skills\b|^core\s+competencies\b",
    "certifications": r"^certifications?\b|^licenses?\b",
}


def parse_pdf(path: str) -> dict:
    """Rough first pass at a resume PDF — always review the output by hand.

    Requires ``pypdf`` (in requirements.txt). Produces a partially-filled
    resume dict in the canonical schema; sections it can't classify land in
    ``_unparsed`` so nothing is silently dropped.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - depends on optional install
        raise ResumeError("pypdf is not installed; run: pip install -r backend/requirements.txt") from exc

    reader = PdfReader(path)
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    resume = {
        "profile": {"first_name": "", "last_name": "", "email": "", "phone": "", "links": {}},
        "summary": "",
        "skills": [],
        "experience": [],
        "education": [],
        "certifications": [],
        "_unparsed": [],
    }

    email = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
    if email:
        resume["profile"]["email"] = email.group(0)
    phone = re.search(r"(\+?\d{1,2}[\s.-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}", text)
    if phone:
        resume["profile"]["phone"] = phone.group(0).strip()
    for label, pattern in (("linkedin", r"linkedin\.com/[\w/-]+"), ("github", r"github\.com/[\w/-]+")):
        m = re.search(pattern, text, re.I)
        if m:
            resume["profile"]["links"][label] = "https://" + m.group(0).lstrip("https://")

    if lines:
        name_parts = lines[0].split()
        if 1 < len(name_parts) <= 4 and "@" not in lines[0]:
            resume["profile"]["first_name"] = name_parts[0]
            resume["profile"]["last_name"] = name_parts[-1]

    current = None
    buckets: dict[str, list[str]] = {}
    for line in lines:
        matched = next((sec for sec, pat in SECTION_PATTERNS.items() if re.search(pat, line, re.I)), None)
        if matched and len(line) < 60:
            current = matched
            buckets.setdefault(current, [])
            continue
        if current:
            buckets[current].append(line)
        else:
            resume["_unparsed"].append(line)

    resume["summary"] = " ".join(buckets.get("summary", []))[:1500]
    for line in buckets.get("skills", []):
        resume["skills"] += [s.strip() for s in re.split(r"[,;|•·]", line) if 1 < len(s.strip()) < 40]
    resume["certifications"] = buckets.get("certifications", [])
    resume["experience"] = _parse_experience(buckets.get("experience", []))
    resume["education"] = _parse_education(buckets.get("education", []))
    resume["_unparsed"] += buckets.get("experience", []) if not resume["experience"] else []
    return resume


DATE_RANGE = re.compile(
    r"((?:19|20)\d{2}|\w{3,9}\s+(?:19|20)\d{2})\s*[–—\-to]+\s*((?:19|20)\d{2}|present|current|\w{3,9}\s+(?:19|20)\d{2})",
    re.I,
)


def _parse_experience(lines: list[str]) -> list[dict]:
    roles: list[dict] = []
    current: dict | None = None
    for line in lines:
        dates = DATE_RANGE.search(line)
        bullet = line.lstrip().startswith(("•", "-", "*", "‣", "◦"))
        if dates and not bullet:
            header = DATE_RANGE.sub("", line).strip(" |,-–—")
            company, _, title = (header.partition(" - ") if " - " in header else ("", "", header))
            current = {
                "company": (company or header).strip(),
                "title": title.strip() or header.strip(),
                "start_date": dates.group(1),
                "end_date": None if dates.group(2).lower() in ("present", "current") else dates.group(2),
                "bullets": [],
            }
            roles.append(current)
        elif current is not None:
            current["bullets"].append(line.lstrip("•-*‣◦ ").strip())
    return roles


def _parse_education(lines: list[str]) -> list[dict]:
    entries = []
    for line in lines:
        if not line:
            continue
        year = _year(line)
        degree = re.search(r"(bachelor\w*|master\w*|associate\w*|ph\.?d|b\.?[sa]\.?|m\.?[sba]\.?)[^,|]*", line, re.I)
        entries.append({
            "school": re.split(r"[,|]", line)[0].strip(),
            "degree": degree.group(0).strip() if degree else "",
            "field": "",
            "graduation_date": str(year) if year else "",
        })
    return entries
