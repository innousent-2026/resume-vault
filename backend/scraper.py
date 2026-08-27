"""Employer career-site scrapers.

Most companies run one of a handful of applicant tracking systems, and each of
those exposes a public job-board JSON feed. Using those feeds is faster, more
reliable and far politer than parsing rendered HTML, so every known ATS gets a
real adapter and only unknown/custom career pages fall back to HTML parsing.

Adding a company is one row in the ``sources`` table:

    kind=greenhouse       token=<board token from boards.greenhouse.io/<token>>
    kind=lever            token=<company slug from jobs.lever.co/<slug>>
    kind=ashby            token=<slug from jobs.ashbyhq.com/<slug>>
    kind=smartrecruiters  token=<company id from careers.smartrecruiters.com/<id>>
    kind=workday          url=https://<host>/wday/cxs/<tenant>/<site>/jobs
    kind=generic          url=https://example.com/careers
"""

import re
import time
from urllib.parse import urljoin, urlparse

import requests

from matcher import strip_html

USER_AGENT = "job-application-automation/1.0 (personal job search tool)"
TIMEOUT = 25
RATE_LIMIT_SECONDS = 1.0  # be a good citizen between requests to the same host

_last_request_at: dict[str, float] = {}


class ScrapeError(Exception):
    pass


def _get(url: str, method: str = "GET", **kwargs):
    host = urlparse(url).netloc
    elapsed = time.monotonic() - _last_request_at.get(host, 0.0)
    if elapsed < RATE_LIMIT_SECONDS:
        time.sleep(RATE_LIMIT_SECONDS - elapsed)
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/html;q=0.8"}
    headers.update(kwargs.pop("headers", {}))
    try:
        resp = requests.request(method, url, headers=headers, timeout=TIMEOUT, **kwargs)
    except requests.RequestException as exc:
        raise ScrapeError(f"request to {url} failed: {exc}") from exc
    finally:
        _last_request_at[host] = time.monotonic()
    if resp.status_code == 404:
        raise ScrapeError(f"{url} returned 404 — check the board token/slug")
    if resp.status_code >= 400:
        raise ScrapeError(f"{url} returned HTTP {resp.status_code}")
    return resp


SALARY_RE = re.compile(
    r"\$\s?(\d{2,3}(?:,\d{3})?(?:\.\d+)?)\s*(k\b)?\s*(?:-|–|—|to)\s*\$?\s?(\d{2,3}(?:,\d{3})?(?:\.\d+)?)\s*(k\b)?",
    re.I,
)
SINGLE_SALARY_RE = re.compile(r"\$\s?(\d{2,3}(?:,\d{3}))(?!\s*(?:-|–|to))", re.I)


def parse_salary(text: str) -> tuple[int | None, int | None]:
    """Pull a salary range out of free text. Returns (min, max), annualized."""
    if not text:
        return None, None
    plain = strip_html(text)
    m = SALARY_RE.search(plain)
    if m:
        lo = _to_amount(m.group(1), m.group(2))
        hi = _to_amount(m.group(3), m.group(4))
        if lo and hi and lo <= hi and lo >= 10000:
            return lo, hi
    m = SINGLE_SALARY_RE.search(plain)
    if m:
        amount = _to_amount(m.group(1), None)
        if amount and amount >= 10000:
            return amount, amount
    return None, None


def _to_amount(number: str, k_suffix: str | None) -> int | None:
    try:
        value = float(number.replace(",", ""))
    except ValueError:
        return None
    if k_suffix or value < 1000:
        value *= 1000
    return int(value)


REMOTE_RE = re.compile(r"\b(remote|work from home|distributed|anywhere)\b", re.I)


def looks_remote(*fields) -> bool:
    return any(REMOTE_RE.search(str(f)) for f in fields if f)


# --- adapters ---------------------------------------------------------------

def scrape_greenhouse(source: dict) -> list[dict]:
    token = source["token"]
    data = _get(f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true").json()
    company = (data.get("meta", {}) or {}).get("name") or source.get("name") or token
    jobs = []
    for item in data.get("jobs", []):
        description = strip_html(item.get("content", ""))
        location = (item.get("location") or {}).get("name")
        lo, hi = parse_salary(item.get("content", ""))
        jobs.append({
            "source_kind": "greenhouse",
            "external_id": f"greenhouse:{token}:{item['id']}",
            "company": company,
            "title": item.get("title", "").strip(),
            "location": location,
            "remote": looks_remote(location, item.get("title")),
            "url": item.get("absolute_url"),
            "description": description,
            "salary_min": lo,
            "salary_max": hi,
            "posted_at": item.get("updated_at"),
            "raw": {"departments": [d.get("name") for d in item.get("departments", [])]},
        })
    return jobs


def scrape_lever(source: dict) -> list[dict]:
    token = source["token"]
    data = _get(f"https://api.lever.co/v0/postings/{token}?mode=json").json()
    jobs = []
    for item in data:
        categories = item.get("categories", {}) or {}
        body = item.get("descriptionPlain") or strip_html(item.get("description", ""))
        full_text = " ".join(filter(None, [body, strip_html(item.get("additionalPlain", "") or "")]))
        lo, hi = parse_salary(full_text)
        location = categories.get("location")
        jobs.append({
            "source_kind": "lever",
            "external_id": f"lever:{token}:{item['id']}",
            "company": source.get("name") or token,
            "title": item.get("text", "").strip(),
            "location": location,
            "remote": looks_remote(location, categories.get("commitment"), item.get("workplaceType")),
            "url": item.get("hostedUrl"),
            "description": full_text,
            "salary_min": lo,
            "salary_max": hi,
            "posted_at": _epoch_ms_to_iso(item.get("createdAt")),
            "raw": {"team": categories.get("team"), "commitment": categories.get("commitment")},
        })
    return jobs


def scrape_ashby(source: dict) -> list[dict]:
    token = source["token"]
    url = f"https://api.ashbyhq.com/posting-api/job-board/{token}?includeCompensation=true"
    data = _get(url).json()
    company = source.get("name") or token
    jobs = []
    for item in data.get("jobs", []):
        description = item.get("descriptionPlain") or strip_html(item.get("descriptionHtml", ""))
        comp = item.get("compensation") or {}
        lo, hi = _ashby_salary(comp)
        if lo is None:
            lo, hi = parse_salary(description)
        jobs.append({
            "source_kind": "ashby",
            "external_id": f"ashby:{token}:{item.get('id')}",
            "company": item.get("companyName") or company,
            "title": (item.get("title") or "").strip(),
            "location": item.get("location"),
            "remote": bool(item.get("isRemote")) or looks_remote(item.get("location")),
            "url": item.get("jobUrl") or item.get("applyUrl"),
            "description": description,
            "salary_min": lo,
            "salary_max": hi,
            "posted_at": item.get("publishedAt"),
            "raw": {"department": item.get("department"), "team": item.get("team")},
        })
    return jobs


def _ashby_salary(comp: dict) -> tuple[int | None, int | None]:
    for component in (comp.get("summaryComponents") or []):
        if (component.get("compensationType") or "").lower() == "salary":
            lo, hi = component.get("minValue"), component.get("maxValue")
            interval = (component.get("interval") or "").lower()
            factor = {"1 hour": 2080, "1 month": 12, "1 week": 52}.get(interval, 1)
            if lo:
                return int(lo * factor), int((hi or lo) * factor)
    return None, None


def scrape_smartrecruiters(source: dict, detail_limit: int = 60) -> list[dict]:
    token = source["token"]
    jobs, offset = [], 0
    while True:
        url = f"https://api.smartrecruiters.com/v1/companies/{token}/postings?limit=100&offset={offset}"
        data = _get(url).json()
        content = data.get("content", [])
        for item in content:
            location = item.get("location", {}) or {}
            loc_str = ", ".join(filter(None, [location.get("city"), location.get("region"), location.get("country")]))
            posting_id = item.get("id")
            jobs.append({
                "source_kind": "smartrecruiters",
                "external_id": f"smartrecruiters:{token}:{posting_id}",
                "company": (item.get("company", {}) or {}).get("name") or source.get("name") or token,
                "title": (item.get("name") or "").strip(),
                "location": loc_str,
                "remote": bool(location.get("remote")) or looks_remote(loc_str),
                "url": f"https://jobs.smartrecruiters.com/{token}/{posting_id}",
                "description": "",
                "salary_min": None,
                "salary_max": None,
                "posted_at": item.get("releasedDate"),
                "raw": {"department": (item.get("department", {}) or {}).get("label"), "posting_id": posting_id},
            })
        offset += len(content)
        if len(content) < 100 or offset >= data.get("totalFound", 0):
            break

    # The list endpoint omits the ad body; pull it for the newest postings so
    # the matcher has something to work with.
    for job in jobs[:detail_limit]:
        posting_id = job["raw"]["posting_id"]
        try:
            detail = _get(f"https://api.smartrecruiters.com/v1/companies/{token}/postings/{posting_id}").json()
        except ScrapeError:
            continue
        job["description"] = _smartrecruiters_body(detail)
        job["salary_min"], job["salary_max"] = parse_salary(job["description"])
    return jobs


def _smartrecruiters_body(detail: dict) -> str:
    sections = ((detail.get("jobAd", {}) or {}).get("sections", {}) or {})
    chunks = []
    for section in sections.values():
        if isinstance(section, dict):
            chunks.append(section.get("title", ""))
            chunks.append(strip_html(section.get("text", "")))
    return re.sub(r"\s+", " ", " ".join(c for c in chunks if c)).strip()


def scrape_workday(source: dict) -> list[dict]:
    """Workday's cxs endpoint. ``url`` must be the jobs endpoint, e.g.
    https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/Careers/jobs
    """
    endpoint = source["url"].rstrip("/")
    site_base = endpoint.rsplit("/jobs", 1)[0]
    external_base = _workday_external_base(endpoint)
    jobs, offset = [], 0
    while offset < 500:
        payload = {"appliedFacets": {}, "limit": 20, "offset": offset, "searchText": ""}
        data = _get(endpoint, method="POST", json=payload,
                    headers={"Content-Type": "application/json"}).json()
        postings = data.get("jobPostings", [])
        for item in postings:
            path = item.get("externalPath", "")
            jobs.append({
                "source_kind": "workday",
                "external_id": f"workday:{urlparse(endpoint).netloc}:{item.get('bulletFields', [path])[0]}",
                "company": source.get("name") or urlparse(endpoint).netloc.split(".")[0],
                "title": (item.get("title") or "").strip(),
                "location": item.get("locationsText"),
                "remote": looks_remote(item.get("locationsText"), item.get("title")),
                "url": urljoin(external_base, path.lstrip("/")),
                "description": item.get("jobDescription") or "",
                "salary_min": None,
                "salary_max": None,
                "posted_at": item.get("postedOn"),
                "raw": {"site": site_base},
            })
        offset += len(postings)
        if len(postings) < 20 or offset >= data.get("total", 0):
            break
    return jobs


def _workday_external_base(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    parts = [p for p in parsed.path.split("/") if p]
    # /wday/cxs/<tenant>/<site>/jobs -> https://host/<site>/
    site = parts[-2] if len(parts) >= 2 else ""
    return f"{parsed.scheme}://{parsed.netloc}/{site}/"


JOB_LINK_RE = re.compile(r"/(jobs?|careers?|openings?|positions?|opportunit)", re.I)


def scrape_generic(source: dict) -> list[dict]:
    """Fallback for custom career pages: collect job-looking links.

    Deliberately shallow — it follows each discovered link once to grab a title
    and description. Anything it can't classify is left out rather than guessed.
    """
    from bs4 import BeautifulSoup

    base_url = source["url"]
    html = _get(base_url).text
    soup = BeautifulSoup(html, "html.parser")
    company = source.get("name") or urlparse(base_url).netloc

    seen, jobs = set(), []
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        absolute = urljoin(base_url, href)
        if urlparse(absolute).netloc != urlparse(base_url).netloc and "greenhouse" not in absolute and "lever" not in absolute:
            continue
        if not JOB_LINK_RE.search(urlparse(absolute).path):
            continue
        title = anchor.get_text(strip=True)
        if not title or len(title) < 3 or len(title) > 120:
            continue
        if absolute in seen or absolute.rstrip("/") == base_url.rstrip("/"):
            continue
        seen.add(absolute)
        jobs.append({
            "source_kind": "generic",
            "external_id": f"generic:{absolute}",
            "company": company,
            "title": title,
            "location": None,
            "remote": looks_remote(title),
            "url": absolute,
            "description": "",
            "salary_min": None,
            "salary_max": None,
            "posted_at": None,
            "raw": {"discovered_on": base_url},
        })
        if len(jobs) >= 100:
            break

    for job in jobs[:40]:
        try:
            detail = _get(job["url"]).text
        except ScrapeError:
            continue
        page = BeautifulSoup(detail, "html.parser")
        for tag in page(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = re.sub(r"\s+", " ", page.get_text(" ", strip=True))[:20000]
        job["description"] = text
        lo, hi = parse_salary(text)
        job["salary_min"], job["salary_max"] = lo, hi
        job["remote"] = job["remote"] or looks_remote(text[:2000])
    return jobs


ADAPTERS = {
    "greenhouse": scrape_greenhouse,
    "lever": scrape_lever,
    "ashby": scrape_ashby,
    "smartrecruiters": scrape_smartrecruiters,
    "workday": scrape_workday,
    "generic": scrape_generic,
}


def scrape_source(source: dict) -> list[dict]:
    adapter = ADAPTERS.get(source.get("kind"))
    if adapter is None:
        raise ScrapeError(f"unknown source kind '{source.get('kind')}' (have: {', '.join(sorted(ADAPTERS))})")
    jobs = adapter(source)
    return [j for j in jobs if j.get("title") and j.get("url")]


def _epoch_ms_to_iso(value) -> str | None:
    if not value:
        return None
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    except (ValueError, TypeError, OSError):
        return None
