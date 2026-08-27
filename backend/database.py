"""SQLite storage for jobs, applications and learned form mappings."""

import json
import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

DEFAULT_DB_PATH = os.environ.get(
    "JAA_DB_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "jobs.db")
)

_local = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS sources (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    kind          TEXT NOT NULL,              -- greenhouse | lever | ashby | smartrecruiters | workday | generic
    token         TEXT,                       -- board token / company slug
    url           TEXT,                       -- for generic + workday adapters
    enabled       INTEGER NOT NULL DEFAULT 1,
    last_scraped_at TEXT,
    last_error    TEXT,
    created_at    TEXT NOT NULL,
    UNIQUE(kind, token, url)
);

CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id     INTEGER REFERENCES sources(id) ON DELETE SET NULL,
    source_kind   TEXT NOT NULL,
    external_id   TEXT NOT NULL,
    company       TEXT NOT NULL,
    title         TEXT NOT NULL,
    location      TEXT,
    remote        INTEGER NOT NULL DEFAULT 0,
    url           TEXT NOT NULL,
    description   TEXT,
    salary_min    INTEGER,
    salary_max    INTEGER,
    posted_at     TEXT,
    first_seen_at TEXT NOT NULL,
    last_seen_at  TEXT NOT NULL,
    archived      INTEGER NOT NULL DEFAULT 0,
    raw           TEXT,
    UNIQUE(source_kind, external_id)
);
CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company);
CREATE INDEX IF NOT EXISTS idx_jobs_seen ON jobs(last_seen_at);

CREATE TABLE IF NOT EXISTS job_scores (
    job_id      INTEGER PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
    score       REAL NOT NULL,
    breakdown   TEXT NOT NULL,
    scored_at   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scores_score ON job_scores(score DESC);

CREATE TABLE IF NOT EXISTS applications (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id        INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
    company       TEXT NOT NULL,
    title         TEXT NOT NULL,
    url           TEXT,
    status        TEXT NOT NULL DEFAULT 'draft',  -- draft|applied|interviewing|offer|rejected|withdrawn
    method        TEXT,                            -- extension|manual
    applied_at    TEXT,
    notes         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_apps_status ON applications(status);

CREATE TABLE IF NOT EXISTS form_submissions (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    application_id INTEGER REFERENCES applications(id) ON DELETE CASCADE,
    url            TEXT NOT NULL,
    ats            TEXT,
    filled         TEXT NOT NULL,   -- JSON: [{field, canonical, value_preview}]
    skipped        TEXT NOT NULL,   -- JSON: [{field, reason}]
    submitted      INTEGER NOT NULL DEFAULT 0,
    created_at     TEXT NOT NULL
);

-- Signatures the user corrected by hand, so the detector gets better per-site.
CREATE TABLE IF NOT EXISTS field_mappings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ats         TEXT NOT NULL,
    host        TEXT NOT NULL DEFAULT '',
    signature   TEXT NOT NULL,
    canonical   TEXT NOT NULL,
    hits        INTEGER NOT NULL DEFAULT 1,
    updated_at  TEXT NOT NULL,
    UNIQUE(ats, host, signature)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    """One connection per thread; Flask's dev server is threaded."""
    path = db_path or DEFAULT_DB_PATH
    cached = getattr(_local, "conn", None)
    if cached is not None and getattr(_local, "path", None) == path:
        return cached
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    _local.conn = conn
    _local.path = path
    return conn


def close_connection() -> None:
    conn = getattr(_local, "conn", None)
    if conn is not None:
        conn.close()
        _local.conn = None
        _local.path = None


def init_db(db_path: str | None = None) -> sqlite3.Connection:
    conn = get_connection(db_path)
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


@contextmanager
def transaction(db_path: str | None = None):
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


# --- sources ---------------------------------------------------------------

def add_source(name, kind, token=None, url=None, enabled=True, db_path=None) -> int:
    with transaction(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO sources (name, kind, token, url, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(kind, token, url) DO UPDATE SET
                   name = excluded.name, enabled = excluded.enabled""",
            (name, kind, token, url, 1 if enabled else 0, utcnow()),
        )
        if cur.lastrowid:
            return cur.lastrowid
    row = get_connection(db_path).execute(
        "SELECT id FROM sources WHERE kind = ? AND token IS ? AND url IS ?", (kind, token, url)
    ).fetchone()
    return row["id"]


def list_sources(db_path=None, enabled_only=False) -> list[dict]:
    sql = "SELECT * FROM sources"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY name COLLATE NOCASE"
    return [dict(r) for r in get_connection(db_path).execute(sql)]


def delete_source(source_id: int, db_path=None) -> None:
    with transaction(db_path) as conn:
        conn.execute("DELETE FROM sources WHERE id = ?", (source_id,))


def mark_source_scraped(source_id: int, error: str | None = None, db_path=None) -> None:
    with transaction(db_path) as conn:
        conn.execute(
            "UPDATE sources SET last_scraped_at = ?, last_error = ? WHERE id = ?",
            (utcnow(), error, source_id),
        )


# --- jobs ------------------------------------------------------------------

def upsert_job(job: dict, source_id: int | None = None, db_path=None) -> tuple[int, bool]:
    """Insert or refresh a scraped job. Returns (job_id, is_new)."""
    now = utcnow()
    conn = get_connection(db_path)
    existing = conn.execute(
        "SELECT id FROM jobs WHERE source_kind = ? AND external_id = ?",
        (job["source_kind"], str(job["external_id"])),
    ).fetchone()
    payload = (
        source_id,
        job["source_kind"],
        str(job["external_id"]),
        job["company"],
        job["title"],
        job.get("location"),
        1 if job.get("remote") else 0,
        job["url"],
        job.get("description"),
        job.get("salary_min"),
        job.get("salary_max"),
        job.get("posted_at"),
        json.dumps(job.get("raw", {}))[:200000],
    )
    with transaction(db_path) as c:
        if existing:
            c.execute(
                """UPDATE jobs SET source_id=?, source_kind=?, external_id=?, company=?, title=?,
                       location=?, remote=?, url=?, description=?, salary_min=?, salary_max=?,
                       posted_at=?, raw=?, last_seen_at=?, archived=0
                   WHERE id=?""",
                payload + (now, existing["id"]),
            )
            return existing["id"], False
        cur = c.execute(
            """INSERT INTO jobs (source_id, source_kind, external_id, company, title, location,
                   remote, url, description, salary_min, salary_max, posted_at, raw,
                   first_seen_at, last_seen_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            payload + (now, now),
        )
        return cur.lastrowid, True


def set_score(job_id: int, score: float, breakdown: dict, db_path=None) -> None:
    with transaction(db_path) as conn:
        conn.execute(
            """INSERT INTO job_scores (job_id, score, breakdown, scored_at) VALUES (?,?,?,?)
               ON CONFLICT(job_id) DO UPDATE SET
                   score=excluded.score, breakdown=excluded.breakdown, scored_at=excluded.scored_at""",
            (job_id, float(score), json.dumps(breakdown), utcnow()),
        )


def query_jobs(db_path=None, min_score=0.0, q=None, company=None, remote=None,
               source_kind=None, applied=None, limit=50, offset=0, sort="score") -> list[dict]:
    where = ["j.archived = 0", "COALESCE(s.score, 0) >= ?"]
    args: list = [float(min_score)]
    if q:
        where.append("(j.title LIKE ? OR j.company LIKE ? OR j.description LIKE ?)")
        args += [f"%{q}%"] * 3
    if company:
        where.append("j.company LIKE ?")
        args.append(f"%{company}%")
    if remote is not None:
        where.append("j.remote = ?")
        args.append(1 if remote else 0)
    if source_kind:
        where.append("j.source_kind = ?")
        args.append(source_kind)
    if applied is True:
        where.append("a.id IS NOT NULL")
    elif applied is False:
        where.append("a.id IS NULL")

    order = {
        "score": "COALESCE(s.score, 0) DESC, j.last_seen_at DESC",
        "date": "COALESCE(j.posted_at, j.first_seen_at) DESC",
        "company": "j.company COLLATE NOCASE ASC",
    }.get(sort, "COALESCE(s.score, 0) DESC")

    sql = f"""
        SELECT j.*, COALESCE(s.score, 0) AS score, s.breakdown AS breakdown,
               a.id AS application_id, a.status AS application_status
        FROM jobs j
        LEFT JOIN job_scores s ON s.job_id = j.id
        LEFT JOIN applications a ON a.job_id = j.id
        WHERE {' AND '.join(where)}
        ORDER BY {order}
        LIMIT ? OFFSET ?
    """
    args += [int(limit), int(offset)]
    out = []
    for row in get_connection(db_path).execute(sql, args):
        d = dict(row)
        d["remote"] = bool(d["remote"])
        d["breakdown"] = json.loads(d["breakdown"]) if d.get("breakdown") else None
        d.pop("raw", None)
        out.append(d)
    return out


def get_job(job_id: int, db_path=None) -> dict | None:
    row = get_connection(db_path).execute(
        """SELECT j.*, COALESCE(s.score, 0) AS score, s.breakdown AS breakdown,
                  a.id AS application_id, a.status AS application_status
           FROM jobs j
           LEFT JOIN job_scores s ON s.job_id = j.id
           LEFT JOIN applications a ON a.job_id = j.id
           WHERE j.id = ?""",
        (job_id,),
    ).fetchone()
    if row is None:
        return None
    d = dict(row)
    d["remote"] = bool(d["remote"])
    d["breakdown"] = json.loads(d["breakdown"]) if d.get("breakdown") else None
    d["raw"] = json.loads(d["raw"]) if d.get("raw") else {}
    return d


def find_job_by_url(url: str, db_path=None) -> dict | None:
    """Exact match first, then a prefix match so tracking params don't break lookup."""
    conn = get_connection(db_path)
    row = conn.execute("SELECT * FROM jobs WHERE url = ?", (url,)).fetchone()
    if row is None:
        base = url.split("?")[0].rstrip("/")
        row = conn.execute(
            "SELECT * FROM jobs WHERE url LIKE ? ORDER BY last_seen_at DESC LIMIT 1", (base + "%",)
        ).fetchone()
    return row_to_dict(row)


def all_jobs_for_scoring(db_path=None) -> list[dict]:
    rows = get_connection(db_path).execute(
        "SELECT id, title, company, location, remote, description, salary_min, salary_max FROM jobs WHERE archived = 0"
    )
    return [dict(r) for r in rows]


# --- applications ----------------------------------------------------------

def create_application(company, title, job_id=None, url=None, status="applied",
                       method="extension", notes=None, applied_at=None, db_path=None) -> int:
    now = utcnow()
    with transaction(db_path) as conn:
        if job_id is not None:
            existing = conn.execute("SELECT id FROM applications WHERE job_id = ?", (job_id,)).fetchone()
            if existing:
                conn.execute(
                    "UPDATE applications SET status=?, method=?, applied_at=COALESCE(?, applied_at), updated_at=? WHERE id=?",
                    (status, method, applied_at or (now if status == "applied" else None), now, existing["id"]),
                )
                return existing["id"]
        cur = conn.execute(
            """INSERT INTO applications (job_id, company, title, url, status, method, applied_at,
                   notes, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (job_id, company, title, url, status, method,
             applied_at or (now if status == "applied" else None), notes, now, now),
        )
        return cur.lastrowid


def update_application(app_id: int, db_path=None, **fields) -> dict | None:
    allowed = {"status", "notes", "applied_at", "url", "company", "title", "method"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if updates:
        sets = ", ".join(f"{k} = ?" for k in updates)
        with transaction(db_path) as conn:
            conn.execute(
                f"UPDATE applications SET {sets}, updated_at = ? WHERE id = ?",
                list(updates.values()) + [utcnow(), app_id],
            )
    return get_application(app_id, db_path)


def get_application(app_id: int, db_path=None) -> dict | None:
    return row_to_dict(
        get_connection(db_path).execute("SELECT * FROM applications WHERE id = ?", (app_id,)).fetchone()
    )


def list_applications(status=None, limit=200, db_path=None) -> list[dict]:
    sql = """SELECT a.*, j.score AS score FROM applications a
             LEFT JOIN job_scores j ON j.job_id = a.job_id"""
    args: list = []
    if status:
        sql += " WHERE a.status = ?"
        args.append(status)
    sql += " ORDER BY COALESCE(a.applied_at, a.created_at) DESC LIMIT ?"
    args.append(int(limit))
    return [dict(r) for r in get_connection(db_path).execute(sql, args)]


def log_submission(url, filled, skipped, ats=None, application_id=None, submitted=False, db_path=None) -> int:
    with transaction(db_path) as conn:
        cur = conn.execute(
            """INSERT INTO form_submissions (application_id, url, ats, filled, skipped, submitted, created_at)
               VALUES (?,?,?,?,?,?,?)""",
            (application_id, url, ats, json.dumps(filled), json.dumps(skipped),
             1 if submitted else 0, utcnow()),
        )
        return cur.lastrowid


def submissions_for_application(app_id: int, db_path=None) -> list[dict]:
    rows = get_connection(db_path).execute(
        "SELECT * FROM form_submissions WHERE application_id = ? ORDER BY created_at DESC", (app_id,)
    )
    out = []
    for r in rows:
        d = dict(r)
        d["filled"] = json.loads(d["filled"])
        d["skipped"] = json.loads(d["skipped"])
        d["submitted"] = bool(d["submitted"])
        out.append(d)
    return out


# --- learned field mappings -------------------------------------------------

def learn_mapping(ats: str, signature: str, canonical: str, host: str = "", db_path=None) -> None:
    with transaction(db_path) as conn:
        conn.execute(
            """INSERT INTO field_mappings (ats, host, signature, canonical, hits, updated_at)
               VALUES (?,?,?,?,1,?)
               ON CONFLICT(ats, host, signature) DO UPDATE SET
                   canonical = excluded.canonical,
                   hits = field_mappings.hits + 1,
                   updated_at = excluded.updated_at""",
            (ats or "unknown", host or "", signature, canonical, utcnow()),
        )


def learned_mappings(ats: str | None = None, host: str = "", db_path=None) -> dict[str, str]:
    sql = "SELECT signature, canonical FROM field_mappings WHERE (host = ? OR host = '')"
    args: list = [host or ""]
    if ats:
        sql += " AND (ats = ? OR ats = 'unknown')"
        args.append(ats)
    sql += " ORDER BY (host = '') ASC, hits DESC"
    out: dict[str, str] = {}
    for row in get_connection(db_path).execute(sql, args):
        out.setdefault(row["signature"], row["canonical"])
    return out


# --- settings ---------------------------------------------------------------

def get_settings(db_path=None) -> dict:
    return {r["key"]: json.loads(r["value"]) for r in get_connection(db_path).execute("SELECT * FROM settings")}


def set_settings(values: dict, db_path=None) -> dict:
    with transaction(db_path) as conn:
        for key, value in values.items():
            conn.execute(
                """INSERT INTO settings (key, value) VALUES (?, ?)
                   ON CONFLICT(key) DO UPDATE SET value = excluded.value""",
                (key, json.dumps(value)),
            )
    return get_settings(db_path)


def stats(db_path=None) -> dict:
    conn = get_connection(db_path)
    one = lambda sql, *a: conn.execute(sql, a).fetchone()[0]  # noqa: E731
    by_status = {
        r["status"]: r["n"]
        for r in conn.execute("SELECT status, COUNT(*) AS n FROM applications GROUP BY status")
    }
    return {
        "jobs": one("SELECT COUNT(*) FROM jobs WHERE archived = 0"),
        "scored": one("SELECT COUNT(*) FROM job_scores"),
        "strong_matches": one("SELECT COUNT(*) FROM job_scores WHERE score >= 70"),
        "applications": one("SELECT COUNT(*) FROM applications"),
        "applications_by_status": by_status,
        "sources": one("SELECT COUNT(*) FROM sources WHERE enabled = 1"),
        "forms_filled": one("SELECT COUNT(*) FROM form_submissions"),
    }
