# resume-vault

Website and digital product platform for the Resume Vault and Get Hired Faster Collection.

---

# Job Application Automation

Find roles worth applying to, understand *why* each one matched, fill the
application form from your resume, and keep a record of everything you sent.

Four parts:

| Part | What it does | Where |
| --- | --- | --- |
| **Backend** | Scrapes employer job boards, scores postings against your resume, maps form fields, stores applications | `backend/` (Flask + SQLite) |
| **Dashboard** | Browse matches, read the score breakdown, track applications, manage sources and preferences | `frontend/` (React + Vite) |
| **Extension** | Detects application forms, shows what it would type, fills only what you approve | `extension/` (Manifest V3) |
| **Resume data** | One JSON file that drives matching and autofill | `resume_data.json` |

## The one rule worth stating up front

**The extension never submits an application.** It fills fields and stops.
There is no code path that clicks a submit button or dispatches a submit event,
and the end-to-end test asserts it. You read the page and press Submit.

It also refuses to fill, by design:

- signature, initials, "I certify", SSN, date of birth, password fields;
- file uploads (browsers require a real user action, and you should check which
  resume version you're attaching anyway);
- demographic/EEO questions, unless you explicitly turn that on in Settings,
  and even then only from values you wrote in your resume file yourself.

## Setup

### 1. Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cp resume_data.example.json resume_data.json   # then edit it
python backend/app.py                          # http://127.0.0.1:5057
```

`resume_data.json` is gitignored — it holds your address and phone number.

Starting from a PDF instead:

```bash
python backend/manage.py import-resume ~/Documents/resume.pdf
# writes resume_data.draft.json — review it, then save it as resume_data.json
```

The parser is a first pass, not magic. Expect to fix section boundaries and
dates by hand.

### 2. Dashboard

```bash
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173, proxies /api to the backend
```

No data yet? `python backend/manage.py demo` seeds a handful of sample
postings so you can see the interface working.

### 3. Extension

1. Open `chrome://extensions` and turn on Developer mode.
2. "Load unpacked" → select the `extension/` directory.
3. Click the toolbar icon. It should say **Connected**. If it says the backend
   is offline, start `backend/app.py` or fix the backend URL in the popup.

Firefox: the manifest is MV3; load it via `about:debugging` → "Load Temporary
Add-on" → `extension/manifest.json`.

## Adding career sites

Most companies run one of a handful of applicant tracking systems, and each one
publishes its jobs as JSON. Those feeds are used directly — faster, more
reliable, and politer than scraping rendered HTML. Add sources in Settings, or
from the CLI:

```bash
python backend/manage.py add-source greenhouse      --token acme --name "Acme Corp"
python backend/manage.py add-source lever           --token acme
python backend/manage.py add-source ashby           --token acme
python backend/manage.py add-source smartrecruiters --token AcmeCorp
python backend/manage.py add-source workday --name Acme \
  --url https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/Careers/jobs
python backend/manage.py add-source generic --name Acme \
  --url https://acme.com/careers          # fallback: crawls a careers page for job links

python backend/manage.py scrape           # scrape everything, then rescore
python backend/manage.py jobs --min-score 60 --explain
```

Where to find each token:

| Kind | Token / URL |
| --- | --- |
| greenhouse | `boards.greenhouse.io/<token>` |
| lever | `jobs.lever.co/<slug>` |
| ashby | `jobs.ashbyhq.com/<slug>` |
| smartrecruiters | `careers.smartrecruiters.com/<company-id>` |
| workday | the `…/wday/cxs/<tenant>/<site>/jobs` endpoint (visible in devtools' network tab on their careers page) |
| generic | any careers page |

Requests are rate-limited to one per second per host.

## How matching works

Deliberately dependency-light — no model downloads. Each posting gets a 0–100
score from four weighted components:

| Component | Weight | Signal |
| --- | --- | --- |
| Posting overlap | 40% | TF-IDF cosine between your resume and the posting |
| Your skills | 25% | how many of your listed skills appear in the text |
| Title fit | 20% | token overlap against your target titles |
| Your keywords | 15% | how many of your keywords appear |

That base is then multiplied by salary fit, location fit, and an exclusion
penalty (a posting containing one of your excluded terms drops to a quarter of
its score). Every number, and the reason behind it, is shown on the job detail
page — a score you can't interrogate isn't worth having.

Want embeddings instead? Implement `similarity_fn(resume_text, job_text) ->
float` and pass it to `score_jobs`; nothing else changes.

## How the autofill works

1. The content script harvests every visible field with its label, ARIA text,
   `autocomplete` token, placeholder, and options. Labels are resolved the way
   real ATSes nest them (`label[for]`, `aria-labelledby`, wrapping labels, and
   Workday/SAP-style sibling wrappers).
2. The backend maps each field to a canonical resume field using ordered rules,
   scored by where the match came from — an `autocomplete="given-name"` is
   trusted far more than a match on a minified `name` attribute.
3. You get a panel listing every proposed value, its confidence, and why it was
   chosen. Edit anything, untick anything.
4. Values are written through the native setter and followed by `input`/`change`
   events, so React- and Angular-controlled inputs actually register them.
5. Anything unmapped can be mapped by hand. That correction is remembered for
   that site, so the same form fills itself properly next time.
6. "Log to dashboard" records the application and exactly which fields were
   filled.

**Quick Apply** (Settings) fills the high-confidence fields as soon as a form is
detected, for when you're doing a run of similar applications. It still doesn't
submit.

The extension only auto-runs on known ATS domains (see `content_scripts.matches`
in the manifest). On any other site, click the toolbar icon and press "Scan this
page" — that uses `activeTab`, so the extension gets access to that one page,
only when you ask.

## Tests

```bash
.venv/bin/python -m pytest backend/tests -q          # 46 tests: matcher, detector, scrapers, API
cd extension/e2e && npm install && ./run.sh          # loads the extension in real Chromium
```

The end-to-end run drives the real extension against a fixture application form
and checks that fields are detected and filled, that sensitive fields are left
alone, that a hand-mapped field is remembered, that the fill is logged — and
that the form was never submitted.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/health`, `/api/stats` | liveness, counts |
| GET/PUT | `/api/resume` | read/replace resume data |
| POST | `/api/resume/import-pdf` | draft a resume from a PDF (returns it, never saves) |
| GET/POST/DELETE | `/api/sources[/<id>]` | manage career sites |
| POST | `/api/scrape`, `/api/rescore` | run the pipeline |
| GET | `/api/jobs`, `/api/jobs/<id>`, `/api/jobs/lookup?url=` | browse matches |
| GET/POST/PATCH | `/api/applications[/<id>]` | track applications |
| POST | `/api/forms/analyze` | field descriptors → fill plan |
| POST | `/api/forms/learn` | remember a hand-mapped field |
| POST | `/api/forms/log` | record a filled form |
| GET/PUT | `/api/settings` | quick apply, EEO opt-in, score floor |

## Things worth knowing

- **Everything is local.** SQLite at `backend/data/jobs.db`, resume JSON on
  disk, no third-party services. Nothing is sent anywhere except the employer
  sites you visit yourself.
- **Cover letters** are templates: `{company}` and `{title}` resolve against the
  scraped job. If they can't be resolved, the field is left empty rather than
  filled with a letter that says "Dear {company}".
- **Scraping is polite but still scraping.** One request per second per host,
  identifying User-Agent. Some employers' terms prohibit automated access; that
  call is yours to make per site.
- **Volume isn't the goal.** The matcher is there so you apply to fewer, better
  fitting roles — a hundred autofilled applications to jobs you don't match is
  worse than ten good ones.
