"""Job/resume matching.

Deliberately dependency-light: a self-contained TF-IDF cosine similarity over
the corpus of scraped jobs, blended with explicit skill, title, location and
salary signals. Every score comes back with a breakdown so the dashboard can
say *why* something matched instead of showing an unexplained number.

To swap in embeddings later, implement ``semantic_similarity(a, b) -> float``
and pass it as ``similarity_fn`` to :func:`score_jobs`.
"""

import math
import re
from collections import Counter

from resume import resume_text

STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "than", "with", "without", "for", "to",
    "of", "in", "on", "at", "by", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "we", "our", "you", "your", "they", "their", "this", "that", "these", "those", "it", "its",
    "will", "would", "can", "could", "should", "may", "might", "must", "have", "has", "had",
    "do", "does", "did", "not", "no", "all", "any", "each", "more", "most", "other", "some",
    "such", "own", "same", "so", "up", "out", "about", "into", "over", "under", "who", "what",
    "when", "where", "how", "why", "job", "role", "position", "work", "team", "company",
    "experience", "years", "including", "etc", "us", "new", "help", "across", "within", "per",
}

WEIGHTS = {
    "content": 0.40,   # TF-IDF cosine over the whole posting
    "skills": 0.25,    # explicit skill overlap
    "title": 0.20,     # title vs. target titles
    "keywords": 0.15,  # preference keywords present in the posting
}

TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9+#.\-]{1,}")


def tokenize(text: str) -> list[str]:
    return [t for t in TOKEN_RE.findall((text or "").lower()) if t not in STOPWORDS and len(t) > 1]


def strip_html(text: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text or "", flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (text.replace("&amp;", "&").replace("&nbsp;", " ")
                .replace("&lt;", "<").replace("&gt;", ">").replace("&#39;", "'")
                .replace("&quot;", '"'))
    return re.sub(r"\s+", " ", text).strip()


class TfidfIndex:
    """Small TF-IDF vectorizer. Fit on the job corpus + the resume."""

    def __init__(self, documents: list[str]):
        self.docs = [Counter(tokenize(d)) for d in documents]
        n = max(len(self.docs), 1)
        df = Counter()
        for doc in self.docs:
            df.update(doc.keys())
        self.idf = {term: math.log((n + 1) / (count + 1)) + 1.0 for term, count in df.items()}

    def vector(self, text: str) -> dict[str, float]:
        counts = Counter(tokenize(text))
        if not counts:
            return {}
        max_tf = max(counts.values())
        vec = {
            term: (0.5 + 0.5 * tf / max_tf) * self.idf.get(term, 1.0)
            for term, tf in counts.items()
        }
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {term: v / norm for term, v in vec.items()}

    @staticmethod
    def cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        small, large = (a, b) if len(a) < len(b) else (b, a)
        return sum(v * large.get(term, 0.0) for term, v in small.items())


def normalize_skill(skill: str) -> str:
    return re.sub(r"[^a-z0-9+# ]", " ", str(skill).lower()).strip()


def skill_overlap(resume: dict, job_text: str) -> tuple[float, list[str], list[str]]:
    skills = [s for s in (normalize_skill(s) for s in resume.get("skills", [])) if s]
    if not skills:
        return 0.0, [], []
    haystack = " " + re.sub(r"[^a-z0-9+# ]", " ", job_text.lower()) + " "
    matched = [s for s in skills if f" {s} " in haystack]
    missing = [s for s in skills if s not in matched]
    return len(matched) / len(skills), matched, missing


def title_similarity(job_title: str, target_titles: list[str]) -> tuple[float, str | None]:
    job_tokens = set(tokenize(job_title))
    if not job_tokens or not target_titles:
        return 0.0, None
    best, best_title = 0.0, None
    for target in target_titles:
        target_tokens = set(tokenize(target))
        if not target_tokens:
            continue
        overlap = len(job_tokens & target_tokens) / len(job_tokens | target_tokens)
        if overlap > best:
            best, best_title = overlap, target
    return best, best_title


def keyword_hits(job_text: str, keywords: list[str]) -> tuple[float, list[str]]:
    if not keywords:
        return 0.0, []
    lowered = job_text.lower()
    hits = [k for k in keywords if k.lower() in lowered]
    return len(hits) / len(keywords), hits


def salary_fit(job: dict, min_salary) -> tuple[float, str]:
    """Returns a multiplier and an explanation. Unknown salary is never punished
    hard — most postings simply don't list one."""
    if not min_salary:
        return 1.0, "no salary floor set"
    top = job.get("salary_max") or job.get("salary_min")
    if not top:
        return 0.97, "salary not listed"
    if top >= min_salary:
        return 1.0, f"pays up to {top:,} (floor {min_salary:,})"
    shortfall = (min_salary - top) / min_salary
    return max(0.4, 1.0 - shortfall), f"below floor: tops out at {top:,} vs {min_salary:,}"


def location_fit(job: dict, prefs: dict) -> tuple[float, str]:
    if job.get("remote"):
        return 1.0, "remote"
    if prefs.get("remote_only"):
        return 0.35, "not remote, and remote_only is set"
    locations = [l for l in prefs.get("locations", []) if l]
    if not locations:
        return 1.0, "no location preference"
    job_loc = (job.get("location") or "").lower()
    if not job_loc:
        return 0.95, "location not listed"
    for pref in locations:
        city = pref.split(",")[0].strip().lower()
        if city and city in job_loc:
            return 1.0, f"matches preferred location ({pref})"
    return 0.6, f"outside preferred locations ({job.get('location')})"


def exclusion_hits(job_text: str, exclusions: list[str]) -> list[str]:
    lowered = job_text.lower()
    return [x for x in exclusions or [] if x and x.lower() in lowered]


def job_blob(job: dict) -> str:
    return strip_html(" ".join(str(job.get(k) or "") for k in ("title", "company", "location", "description")))


def score_jobs(jobs: list[dict], resume: dict, similarity_fn=None) -> list[dict]:
    """Score every job against the resume. Returns [{job_id, score, breakdown}]."""
    prefs = resume.get("preferences", {}) or {}
    blobs = [job_blob(j) for j in jobs]
    r_text = resume_text(resume)

    index = TfidfIndex(blobs + [r_text])
    resume_vec = index.vector(r_text)

    results = []
    for job, blob in zip(jobs, blobs):
        if similarity_fn is not None:
            content = float(similarity_fn(r_text, blob))
        else:
            content = TfidfIndex.cosine(resume_vec, index.vector(blob))
        # Cosine over long postings rarely exceeds ~0.45; rescale so the
        # component uses its full range instead of clustering near zero.
        content_scaled = min(1.0, content / 0.45)

        skills_ratio, matched_skills, missing_skills = skill_overlap(resume, blob)
        title_ratio, matched_title = title_similarity(job.get("title", ""), prefs.get("titles", []))
        kw_ratio, matched_keywords = keyword_hits(blob, prefs.get("keywords", []))

        base = (
            WEIGHTS["content"] * content_scaled
            + WEIGHTS["skills"] * skills_ratio
            + WEIGHTS["title"] * title_ratio
            + WEIGHTS["keywords"] * kw_ratio
        )
        sal_mult, sal_note = salary_fit(job, prefs.get("min_salary"))
        loc_mult, loc_note = location_fit(job, prefs)
        excluded = exclusion_hits(blob, prefs.get("exclude_keywords", []))
        excl_mult = 0.25 if excluded else 1.0

        score = round(100 * base * sal_mult * loc_mult * excl_mult, 1)
        results.append({
            "job_id": job.get("id"),
            "score": score,
            "breakdown": {
                "components": {
                    "content": round(content_scaled, 3),
                    "skills": round(skills_ratio, 3),
                    "title": round(title_ratio, 3),
                    "keywords": round(kw_ratio, 3),
                },
                "multipliers": {
                    "salary": round(sal_mult, 3),
                    "location": round(loc_mult, 3),
                    "exclusions": excl_mult,
                },
                "matched_skills": matched_skills[:15],
                "missing_skills": missing_skills[:15],
                "matched_title": matched_title,
                "matched_keywords": matched_keywords,
                "excluded_by": excluded,
                "notes": [n for n in (sal_note, loc_note) if n],
                "summary": explain(score, matched_skills, matched_title, excluded),
            },
        })
    return results


def explain(score: float, matched_skills: list[str], matched_title: str | None, excluded: list[str]) -> str:
    if excluded:
        return f"Filtered down — posting contains excluded term(s): {', '.join(excluded)}"
    band = ("Strong match" if score >= 70 else "Worth a look" if score >= 45 else "Weak match")
    bits = []
    if matched_title:
        bits.append(f"title lines up with '{matched_title}'")
    if matched_skills:
        count = len(matched_skills)
        bits.append(f"{count} of your skills appear{'s' if count == 1 else ''} in the posting")
    return band + (" — " + "; ".join(bits) if bits else "")
