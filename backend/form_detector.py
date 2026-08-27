"""Application-form field detection.

Given a list of field descriptors scraped from a page by the extension, work
out which canonical resume field each one wants. Rules are ordered and each
match carries a confidence, so the extension can show the user exactly what it
is about to type and where it is unsure.

Two things this module deliberately will not do:
  * guess at demographic / EEO answers — those come only from explicit values
    the user put in their resume file, and default to nothing;
  * touch signature, certification, or attestation fields — a human types those.
"""

import re
from urllib.parse import urlparse

# Canonical fields the autofill knows about, grouped for the review UI.
FIELD_GROUPS = {
    "identity": ["first_name", "last_name", "full_name", "preferred_name", "email", "phone"],
    "location": ["address_line1", "address_line2", "city", "state", "postal_code", "country"],
    "links": ["linkedin", "github", "portfolio"],
    "history": ["current_company", "current_title", "years_experience", "school", "degree",
                "field_of_study", "graduation_year"],
    "logistics": ["work_authorized", "requires_sponsorship", "desired_salary",
                  "available_start_date", "how_did_you_hear"],
    "documents": ["resume_file", "cover_letter"],
    "eeo": ["eeo_gender", "eeo_race", "eeo_veteran_status", "eeo_disability_status", "eeo_hispanic_latino"],
}
CANONICAL_FIELDS = [f for group in FIELD_GROUPS.values() for f in group]
SENSITIVE_FIELDS = set(FIELD_GROUPS["eeo"])

# Fields a human must handle themselves, whatever they look like.
NEVER_FILL = re.compile(
    r"signature|initials?\b|i\s*certify|certif(y|ication)\s+statement|attest|agree\s+to|"
    r"terms\s+and\s+conditions|acknowledg|password|ssn|social\s+security|date\s+of\s+birth|"
    r"security\s+(question|answer)|captcha|driver'?s?\s+licen[cs]e\s+number",
    re.I,
)

# HTML autocomplete tokens map cleanly onto canonical fields — highest confidence.
AUTOCOMPLETE_MAP = {
    "given-name": "first_name",
    "family-name": "last_name",
    "name": "full_name",
    "nickname": "preferred_name",
    "email": "email",
    "tel": "phone",
    "tel-national": "phone",
    "address-line1": "address_line1",
    "street-address": "address_line1",
    "address-line2": "address_line2",
    "address-level2": "city",
    "address-level1": "state",
    "postal-code": "postal_code",
    "country": "country",
    "country-name": "country",
    "organization": "current_company",
    "organization-title": "current_title",
    "url": "portfolio",
}

# Ordered: first pattern that matches wins, so put the specific ones first.
RULES: list[tuple[str, str]] = [
    ("first_name", r"\b(first[\s_-]*name|given[\s_-]*name|forename|fname)\b"),
    ("last_name", r"\b(last[\s_-]*name|family[\s_-]*name|surname|lname)\b"),
    ("preferred_name", r"\b(preferred[\s_-]*(first[\s_-]*)?name|nickname|goes?[\s_-]*by)\b"),
    ("full_name", r"\b(full[\s_-]*name|your[\s_-]*name|legal[\s_-]*name|applicant[\s_-]*name)\b|^name$"),
    ("email", r"\b(e[\s_-]*mail|email[\s_-]*address)\b"),
    ("phone", r"\b(phone|mobile|telephone|cell|contact[\s_-]*number)\b"),

    ("linkedin", r"\blinked[\s_-]*in\b"),
    ("github", r"\b(git[\s_-]*hub|gitlab)\b"),
    ("portfolio", r"\b(portfolio|personal[\s_-]*(web)?site|website|web[\s_-]*page|other[\s_-]*url|blog)\b"),

    ("address_line2", r"\b(address[\s_-]*(line[\s_-]*)?2|apt|apartment|suite|unit)\b"),
    ("address_line1", r"\b(street|address[\s_-]*(line[\s_-]*)?1?|mailing[\s_-]*address|home[\s_-]*address)\b"),
    ("city", r"\b(city|town|locality)\b"),
    ("state", r"\b(state|province|region|address[\s_-]*level[\s_-]*1)\b"),
    ("postal_code", r"\b(zip|postal[\s_-]*code|postcode)\b"),
    ("country", r"\b(country|nation)\b"),

    ("current_company", r"\b(current|present|most[\s_-]*recent)?[\s_-]*(employer|company|organization)\b"),
    ("current_title", r"\b(current|present|most[\s_-]*recent)?[\s_-]*(job[\s_-]*)?title\b|\bposition[\s_-]*held\b"),
    ("years_experience", r"\b(years?[\s_-]*(of[\s_-]*)?experience|yoe|experience[\s_-]*years?)\b"),

    ("school", r"\b(school|university|college|institution|alma[\s_-]*mater)\b"),
    ("degree", r"\b(degree|qualification|education[\s_-]*level)\b"),
    ("field_of_study", r"\b(major|discipline|field[\s_-]*of[\s_-]*study|concentration)\b"),
    ("graduation_year", r"\b(graduation|grad)[\s_-]*(year|date)\b|\byear[\s_-]*graduated\b"),

    ("requires_sponsorship", r"\b(sponsor(ship)?|visa[\s_-]*sponsor|require[\s_-]*sponsorship|h1b|h-1b)\b"),
    ("work_authorized", r"\b(legally[\s_-]*authorized|work[\s_-]*authoriz|authorized[\s_-]*to[\s_-]*work|"
                        r"eligible[\s_-]*to[\s_-]*work|right[\s_-]*to[\s_-]*work)\b"),
    ("desired_salary", r"\b(desired|expected|target|requested)[\s_-]*(salary|compensation|pay|rate)\b|"
                       r"\bsalary[\s_-]*(expectation|requirement)s?\b"),
    ("available_start_date", r"\b(start[\s_-]*date|available(ility)?[\s_-]*(date|to[\s_-]*start)?|notice[\s_-]*period)\b"),
    ("how_did_you_hear", r"\bhow[\s_-]*did[\s_-]*you[\s_-]*(hear|find)\b|\breferral[\s_-]*source\b|\bsource\b"),

    ("cover_letter", r"\bcover[\s_-]*letter\b|\bwhy[\s_-]*(do[\s_-]*you[\s_-]*want|are[\s_-]*you[\s_-]*interested)\b"),
    ("resume_file", r"\b(resume|cv|curriculum[\s_-]*vitae)\b"),

    ("eeo_hispanic_latino", r"\bhispanic|latino|latinx\b"),
    ("eeo_gender", r"\b(gender|sex)\b"),
    ("eeo_race", r"\b(race|ethnicity|ethnic[\s_-]*group)\b"),
    ("eeo_veteran_status", r"\bveteran|military\b"),
    ("eeo_disability_status", r"\bdisabilit(y|ies)\b"),
]
COMPILED_RULES = [(canonical, re.compile(pattern, re.I)) for canonical, pattern in RULES]

# Where the label text lives matters: a rule hit on the visible label is much
# more trustworthy than one on a minified `name` attribute.
SOURCE_CONFIDENCE = {
    "autocomplete": 0.99,
    "label": 0.92,
    "aria_label": 0.9,
    "name": 0.8,
    "id": 0.78,
    "placeholder": 0.7,
    "heading": 0.6,
}

ATS_HOSTS = {
    "greenhouse": ("greenhouse.io", "boards.greenhouse.io", "job-boards.greenhouse.io"),
    "lever": ("lever.co", "jobs.lever.co"),
    "ashby": ("ashbyhq.com", "jobs.ashbyhq.com"),
    "workday": ("myworkdayjobs.com", "workday.com"),
    "smartrecruiters": ("smartrecruiters.com",),
    "icims": ("icims.com",),
    "taleo": ("taleo.net",),
    "successfactors": ("successfactors.com", "sapsf.com", "jobs.sap.com"),
    "bamboohr": ("bamboohr.com",),
    "jobvite": ("jobvite.com",),
    "workable": ("workable.com",),
    "breezy": ("breezy.hr",),
    "recruitee": ("recruitee.com",),
}


def detect_ats(url: str) -> str:
    host = (urlparse(url or "").netloc or "").lower()
    for ats, domains in ATS_HOSTS.items():
        if any(host == d or host.endswith("." + d) or d in host for d in domains):
            return ats
    return "unknown"


def field_signature(field: dict) -> str:
    """Stable-ish identity for a field, used to key learned corrections."""
    parts = [
        (field.get("name") or "").strip().lower(),
        (field.get("id") or "").strip().lower(),
        normalize(field.get("label"))[:60],
        (field.get("type") or "").lower(),
    ]
    # Strip framework-generated numeric suffixes so signatures survive re-renders.
    parts = [re.sub(r"[-_:]?\d{3,}", "", p) for p in parts]
    return "|".join(parts)


def normalize(text) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s@/.-]", " ", str(text or ""))).strip().lower()


def classify_field(field: dict, learned: dict[str, str] | None = None) -> dict:
    """Return {canonical, confidence, matched_on, reason} for one field."""
    signature = field_signature(field)
    if learned and signature in learned:
        return {"canonical": learned[signature], "confidence": 1.0, "matched_on": "learned",
                "reason": "you mapped this field before"}

    haystacks = [
        ("autocomplete", (field.get("autocomplete") or "").strip().lower()),
        ("label", normalize(field.get("label"))),
        ("aria_label", normalize(field.get("aria_label"))),
        ("name", normalize(field.get("name"))),
        ("id", normalize(field.get("id"))),
        ("placeholder", normalize(field.get("placeholder"))),
        ("heading", normalize(field.get("section_heading"))),
    ]

    autocomplete = haystacks[0][1]
    if autocomplete in AUTOCOMPLETE_MAP:
        return {"canonical": AUTOCOMPLETE_MAP[autocomplete], "confidence": SOURCE_CONFIDENCE["autocomplete"],
                "matched_on": "autocomplete", "reason": f"autocomplete=\"{autocomplete}\""}

    combined = " ".join(text for _, text in haystacks if text)
    if NEVER_FILL.search(combined):
        return {"canonical": None, "confidence": 0.0, "matched_on": None,
                "reason": "left for you to complete by hand"}

    if (field.get("type") or "").lower() == "file":
        return {"canonical": "resume_file", "confidence": 0.75, "matched_on": "type",
                "reason": "file upload — browsers require you to pick the file yourself"}

    for source, text in haystacks[1:]:
        if not text:
            continue
        for canonical, pattern in COMPILED_RULES:
            if pattern.search(text):
                return {"canonical": canonical, "confidence": SOURCE_CONFIDENCE[source],
                        "matched_on": source, "reason": f"matched '{canonical}' on {source}: \"{text[:60]}\""}

    return {"canonical": None, "confidence": 0.0, "matched_on": None, "reason": "no rule matched"}


def choose_option(value, options: list) -> str | None:
    """Pick the option that best represents ``value`` for a select/radio group."""
    if not options:
        return None
    wanted = normalize(value)
    if not wanted:
        return None
    labels = [(normalize(o.get("label") if isinstance(o, dict) else o),
               (o.get("value") if isinstance(o, dict) else o)) for o in options]
    for label, raw in labels:                       # exact
        if label == wanted:
            return raw
    yes_no = {"yes": ("yes", "y", "true"), "no": ("no", "n", "false")}
    for key, variants in yes_no.items():
        if wanted in variants:
            for label, raw in labels:
                if label in variants or label.startswith(key):
                    return raw
    for label, raw in labels:                       # containment, longest first
        if label and (label in wanted or wanted in label):
            return raw
    return None


def analyze_form(fields: list[dict], values: dict, url: str = "",
                 learned: dict[str, str] | None = None, include_sensitive: bool = False,
                 unavailable: dict[str, str] | None = None) -> dict:
    """Map every field on a page and decide what (if anything) to type into it."""
    ats = detect_ats(url)
    plan, skipped = [], []

    for field in fields:
        result = classify_field(field, learned)
        canonical = result["canonical"]
        entry = {
            "field_id": field.get("field_id"),
            "selector": field.get("selector"),
            "label": field.get("label") or field.get("name") or field.get("id"),
            "type": field.get("type"),
            "required": bool(field.get("required")),
            "signature": field_signature(field),
            "canonical": canonical,
            "confidence": result["confidence"],
            "reason": result["reason"],
        }

        if canonical is None:
            skipped.append({**entry, "skip_reason": result["reason"]})
            continue
        if canonical in SENSITIVE_FIELDS and not include_sensitive:
            skipped.append({**entry, "skip_reason": "demographic question — answer it yourself"})
            continue
        if canonical == "resume_file":
            skipped.append({**entry, "skip_reason": "file uploads must be attached manually"})
            continue

        value = values.get(canonical)
        if value in (None, ""):
            reason = (unavailable or {}).get(canonical) or f"nothing in your resume for '{canonical}'"
            skipped.append({**entry, "skip_reason": reason})
            continue

        options = field.get("options") or []
        if options:
            chosen = choose_option(value, options)
            if chosen is None:
                skipped.append({**entry, "skip_reason": f"no option matches '{value}'"})
                continue
            entry["value"] = chosen
            entry["display_value"] = str(chosen)
        else:
            entry["value"] = str(value)
            entry["display_value"] = str(value)[:120]

        entry["autofill"] = entry["confidence"] >= 0.75
        plan.append(entry)

    return {
        "ats": ats,
        "url": url,
        "fields_seen": len(fields),
        "plan": plan,
        "skipped": skipped,
        "high_confidence": sum(1 for p in plan if p["autofill"]),
        "needs_review": [p for p in plan if not p["autofill"]],
    }
