# Feature Prompt — Section Drafter: Whole-Document Expert Claim Mapping (v2)

**How to use this file:** everything below the horizontal rule is the prompt. Paste it into
Replit Agent as one message. This preamble is notes for us, not for Replit.

**What changed from v1:** literal prompt text for each agent pass (this feature's quality is
almost entirely in those prompts, so they shouldn't be left to Replit to invent); a document
taxonomy that distinguishes fact sources from legal-authority sources; a routing table so
each section draws on the *right* record document instead of all of them; an explicit token
strategy so the whole Expert Claim isn't re-sent on every draft call; concrete API surface
and build order.

---

# BUILD: Expert Claim as a whole-document structural model for the Section Drafter

## 0. What you are building

Today the Section Drafter asks the user to upload a separate model snippet for each section
(the `MODEL SAMPLE` card with "Upload a section from the filed complaint to use as a
structural template"). Replace that entirely.

The user uploads **one** document — the full **Expert Claim**, a complaint already filed in
a comparable case — and the app derives the whole architecture of the new claim from it. The
new claim gets the same sections, in the same order, doing the same jobs, at the same depth.
But every section is *titled and written for the new case*, using the new case's own record.

When the user drafts section 7, the agent reads the entire Expert Claim, finds the section
inside it that does section 7's job, and models the draft on that section alone.

## 1. Read this before you design anything

The hard part of this feature is a matching problem, and the obvious solution is wrong.

Section titles in the new claim **will not match** the Expert Claim's titles. That is the
point of the feature — the new titles come from a different family, a different facility,
different dates, a different set of claim theories. So **you cannot map sections by title
similarity, keyword overlap, or embedding distance between headings.** That approach will
look like it works on the first test document and silently mis-map in production.

Map on two properties that survive the rename:

1. **Ordinal position** in the document.
2. **Rhetorical function** — the job the section does in the argument (establish
   jurisdiction, identify parties, lay the chronology, state the legal standard, apply
   elements to facts, establish damages, request relief).

Extract the rhetorical function once, at upload time, and store it. Match on it forever
after. Position proposes; function verifies.

## 2. Document taxonomy

The `DOCUMENTS ON FILE` panel currently mixes two kinds of document behind two badge styles.
Formalize three roles, because the agent must treat them differently:

| Role | Badge | Documents | What the agent may take from it |
|---|---|---|---|
| **STRUCTURE** | `MODEL` (new) | Expert Claim Sample | Architecture, ordering, register, citation density, paragraph rhythm. **Never facts.** |
| **RECORD** | `RECORD` (existing green) | Detention Report, Factual Report, Parent Response Questionnaire | Every fact, name, date, place, and quotation in the new claim. |
| **REFERENCE** | `REFERENCE` (existing blue) | Due-Process Rights Reference | Legal standards, rights framework, authority the new claim asserts. |

This taxonomy is the enforcement boundary for the fact-bleed guardrail in §7. A STRUCTURE
document is a shape, not a source. Encode that as a hard rule, not a suggestion in a prompt.

### Which record feeds which section

Do not hand all four documents to every drafting call. Route by the section's extracted
`rhetorical_function`:

| Section function | Primary source | Secondary |
|---|---|---|
| Party identification, jurisdiction, venue | Factual Report | Detention Report |
| Chronological narrative, custody timeline | Detention Report | Factual Report |
| Conditions of confinement, treatment | Detention Report | Parent Response Questionnaire |
| Harm, trauma, family impact, damages | Parent Response Questionnaire | Factual Report |
| Legal standard, rights framework | Due-Process Rights Reference | — |
| Element-by-element application | Due-Process Rights Reference | Factual + Detention Report |
| Relief requested | Factual Report | Parent Response Questionnaire |

Routing keeps each call focused and makes it obvious in the UI which upload is blocking
which section. Two qualifications:

- **The Due-Process Rights Reference is available to every section**, not only the two rows
  that name it. Legal framing runs through the whole claim.
- **Routing is a default, not a cage.** If a section needs a fact the routed documents do
  not contain, the agent may query the fact index (below) across all records rather than
  emitting a placeholder. Placeholders are for facts that exist nowhere in the record.

### Getting facts out of the records

Routing alone is not enough. Handing a drafting call a 40-page Factual Report and expecting
it to locate the three relevant paragraphs mid-draft is where facts get blurred, conflated,
or quietly dropped. Extract first, then draft against the extraction.

On upload of any RECORD or REFERENCE document, run a **fact-extraction pass** that decomposes
it into atomic, individually-sourced units:

```
record_document
  id, case_id, doc_type,            # detention_report | factual_report |
                                    # parent_questionnaire | due_process_reference
  filename, mime_type, storage_key,
  raw_text, page_count, extract_status, extract_error, uploaded_at

fact_atom
  id, case_id, record_document_id,
  fact_type,                        # person | date | location | agency | event |
                                    # condition | statement | harm | legal_standard
  text,                             # the assertion, in the record's own words where possible
  verbatim_quote,                   # exact source language, when quotable
  normalized_value,                 # ISO date, canonical facility name, etc.
  page, paragraph, char_start, char_end,
  entity_tags,                      # jsonb: who/what this fact attaches to
  section_functions                 # jsonb: which rhetorical functions this fact serves
```

The extraction prompt:

```
Extract every discrete factual assertion from this case record as an atomic fact.

For each: the assertion itself; the exact source language where it is quotable; a
normalized value for dates, names, and places; its page and paragraph; and which
sections of a legal claim it would support (chronology, conditions, harm, party
identification, relief).

Extract only what the document states. Do not infer, combine, or resolve
contradictions between facts — if the record says two different things, extract both
and flag the conflict. Where the record is vague ("sometime in the spring"), preserve
the vagueness exactly rather than sharpening it.
```

The `parent_questionnaire` needs one special rule: it is a first-person account, and the
parent's own language carries evidentiary weight a paraphrase does not. Preserve
`verbatim_quote` on every fact drawn from it, and prefer quoting over summarizing when that
fact reaches a draft.

Pass 3 then receives **the fact atoms whose `section_functions` match the section being
drafted**, plus the ability to query the full index — not four whole documents.

### Provenance

Every factual assertion in a generated draft carries a citation to the `fact_atom` that
produced it: document, page, paragraph. Surface these in the drafting view as inline markers
that expand to the source language, so the user can check any sentence against the record in
one click.

Provenance is also the real anti-fabrication mechanism. An instruction not to invent facts is
a request; requiring every assertion to name a source atom is a constraint. Any sentence in a
draft that asserts a fact with no atom behind it is flagged before the user ever sees it —
treat an unsourced assertion the same way you treat expert-case fact bleed.

### Cross-section consistency

Facts asserted in section 3 must not contradict section 9 — a filed document with an internal
date conflict is worse than one with a visible gap. Because every assertion resolves to a
`fact_atom`, run a consistency check across all drafted sections: the same atom must
normalize identically everywhere it appears, and conflicting atoms flagged at extraction must
never both be asserted. Report conflicts on the Structure Map, not silently.

## 3. UI changes

### 3a. `DOCUMENTS ON FILE` panel

Add one row **above** the existing four:

```
[MODEL]  Expert Claim Sample          missing | parsing… | 14 sections
```

- Style the `MODEL` badge as a third variant, visually distinct from the green `RECORD` and
  blue `REFERENCE` badges (suggest amber/neutral) — it is a different kind of thing.
- Accepts PDF, DOCX, TXT. One per case. Max 50 MB.
- On upload, run **Pass 1** immediately and show live progress on the row itself.
- The row is clickable once parsed and opens the **Structure Map** (§3b).
- Re-uploading replaces the model and invalidates the derived structure map — warn the user
  first if any sections are already drafted, since their titles and mappings will be
  regenerated.

**Delete the `MODEL SAMPLE` card** below the panel, along with its `UPLOAD MODEL` action and
the per-section upload control on each Section Drafter card. If any per-section model
uploads already exist in the database, keep them readable but stop offering new ones and
show a one-time notice that the model is now set at the case level.

### 3b. Structure Map screen (new)

A verification step between "model uploaded" and "start drafting." The user should never
draft fourteen sections on top of a mapping they never saw.

Two-column table, one row per section:

```
#   EXPERT CLAIM (model)                 YOUR CLAIM (generated)              STATUS
1   "I. PRELIMINARY STATEMENT"           "I. Preliminary Statement"          mapped
2   "II. JURISDICTION AND VENUE"         "II. Jurisdiction and Venue"        mapped
3   "III. THE SEPARATION OF J.M. …"      "III. The Separation of [child] …"  needs input
```

Each row expands to show: the model section's function summary, the rationale for the
generated title, and which record document supplied it. Titles are editable inline; an
edited title is marked **user-locked** and survives regeneration. Every row links straight
into drafting that section. A `Regenerate titles` action reruns Pass 2 after new records are
uploaded, preserving locked titles.

### 3c. Section Drafter cards — and the button that is the whole point of this feature

**The core interaction: every section card has a primary action button that writes that
section.** Label it `WRITE THIS SECTION` (`REWRITE` once a draft exists). One click, no
configuration, no per-section uploads, no prompt to compose. This button is the feature —
build the card around it.

Each card shows:
- the generated title for the new case (not the expert's),
- the `WRITE THIS SECTION` button as the card's primary action,
- a reference line: `Modeled on §{n} of Expert Claim — "{source_title}"`, expandable into a
  side-by-side view of the model section next to the working draft,
- the status chip,
- a checklist of any bracketed placeholders the draft is waiting on, each naming the
  specific missing fact and which document should supply it.

**Button states:**

| State | Button | Card |
|---|---|---|
| Records + model on file | `WRITE THIS SECTION`, enabled | — |
| Running | `WRITING…` with live phase text | streams the draft in as it is written |
| Draft exists, untouched | `REWRITE` | draft shown with provenance markers |
| Draft exists, user-edited | `REWRITE` | confirm first — see below |
| Model missing | disabled | "Upload the Expert Claim Sample to enable drafting" |
| Routed record missing | disabled | names the missing document specifically |

Drafting a section takes tens of seconds. Stream the output into the card as it generates,
and show the phase in the button (`Reading the Expert Claim…` → `Gathering facts…` →
`Writing…`) so the wait is legible rather than a spinner.

**Rewrite semantics.** If the user has edited a draft by hand, `REWRITE` must confirm before
overwriting and must preserve the prior version — keep a per-section version history with
one-click restore. Never silently discard a user's writing.

Also provide a `Write all sections` action on the Structure Map that runs the sections in
order, so the user can generate a full first draft and then work through it — but the
per-section button remains the primary path.

## 4. Data model

```
model_document
  id, case_id, filename, mime_type, storage_key,
  raw_text, page_count, uploaded_at,
  parse_status,            # pending | parsing | parsed | failed
  parse_error,
  proper_noun_index        # jsonb: names, places, dates, docket ids extracted from the
                           # expert claim — used by the fact-bleed check in §7

expert_section             # one row per section found in the Expert Claim
  id, model_document_id, order_index, heading_level,
  source_title,            # verbatim heading from the Expert Claim
  char_start, char_end, page_start, page_end,
  rhetorical_function,     # controlled vocabulary — see §2 routing table
  function_summary,        # fact-agnostic: what job this section does
  legal_elements,          # jsonb array: what it must establish
  evidence_types,          # jsonb array: what kinds of proof it leans on
  word_count, paragraph_count, citation_count, tone_notes

case_section               # 1:1 with expert_section, same order_index
  id, case_id, expert_section_id, order_index,
  drafted_title,
  title_rationale,
  title_locked,            # bool — user edited it; Pass 2 must not overwrite
  source_documents,        # jsonb: which records fed this section
  status,                  # not_started | mapped | drafting | drafted | needs_input | blocked
  draft_body, placeholders, last_drafted_at
```

**Invariant, enforced in code and covered by a test:**
`count(case_section) == count(expert_section)`, with identical `order_index` sequences and
`heading_level` values. If a user action breaks parity, show a persistent banner
(`Structure no longer matches model — 13 of 14 sections`) with a one-click repair.

## 5. The three passes

Use a long-context model for Pass 1. The prompts below are the deliverable — implement them
close to verbatim rather than paraphrasing.

### Pass 1 — Structure Extraction (once, on upload)

Input: full Expert Claim text. Output: the ordered `expert_section` rows.

Parse headings by numbering scheme, typography, *and* semantic breaks together — filed
complaints number inconsistently, and a single regex will fail on roman numerals mixed with
lettered subparts. Where detection is ambiguous, prefer more sections over fewer; the user
can merge in the Structure Map.

```
You are analyzing a filed legal complaint that will be used ONLY as a structural template
for a different case. Do not summarize its facts.

For each section, return:
  order_index, heading_level, source_title (verbatim),
  char_start, char_end,
  rhetorical_function — one of: preliminary_statement, jurisdiction_venue,
    party_identification, factual_chronology, conditions_of_confinement,
    legal_standard, element_application, harm_and_damages, relief_requested, other
  function_summary — 1-2 sentences describing WHAT JOB this section does in the
    argument, written so it would apply equally to any case using this structure.
    Name no party, place, date, or case-specific fact.
  legal_elements — what this section must establish for the complaint to succeed
  evidence_types — the kinds of proof it relies on
  word_count, paragraph_count, citation_count
  tone_notes — register, whether headings are assertions or labels, numbering
    convention, how authority is cited and where it sits in the paragraph

function_summary is the matching key used later against a different case. If it
mentions anything specific to THIS case, it is wrong — rewrite it.
```

### Pass 2 — Title Mapping (after Pass 1; rerun when records change)

Input: all `expert_section` rows + Factual Report + Detention Report. Output: a
`drafted_title` and `title_rationale` for every section, in order.

```
You are titling the sections of a new legal claim. The section STRUCTURE is fixed and
comes from a model complaint filed in a different case. Your job is to give each
section a title that belongs to THIS case.

For each section you receive its position, its rhetorical function, its function
summary, and the model's verbatim heading (for CONVENTION ONLY — numbering style,
capitalization, whether headings are assertions or bare labels).

Rules:
1. Preserve the section's function and its position in the argument.
2. Draw every specific term — parties, child, facility, agency, dates, claim
   theories — from the new case's Factual Report and Detention Report below.
3. Never carry a proper noun, date, docket number, or case-specific phrase from the
   model complaint into a title. Not one.
4. Match the model's heading conventions exactly while changing the words.
5. If the new case's record contains nothing supporting a section's function, still
   produce the section — structure parity is mandatory — but give it a neutral
   functional title, set status to needs_input, and name the exact missing fact and
   which document should contain it.

Return for each: drafted_title, title_rationale (which source facts drove it, citing
the document), status, missing_facts[].
```

### Pass 3 — Section Drafting (per section, fired by the button)

This is what `WRITE THIS SECTION` runs, and it is two steps, not one. The agent must work
out *what this section needs* before it goes looking for facts — otherwise retrieval is a
guess and the draft inherits whatever the guess missed.

**Step A — locate the model section.**

1. Select the mapped `expert_section` by `order_index`.
2. **Verify** the mapping: compare that section's `rhetorical_function` and
   `legal_elements` against what section N needs to accomplish. Do not compare titles.
3. If verification fails, search all `expert_section` rows for the best functional match,
   and **surface the re-mapping to the user** — never switch silently.
4. Load the model section's full text **plus its immediate neighbors**, so transitions and
   back-references read correctly.

**Step B — derive a fact requirements checklist, then satisfy it.**

Before writing a word, the agent reads the model section and produces an explicit list of
what this section must establish for the new case. Then each requirement is resolved against
the fact index by targeted query — not by hoping the right atoms were pre-tagged.

```
Below is one section of a complaint filed in a different case. It is the structural
model for the section now being drafted.

Read it and list what this section must ESTABLISH — not what it says. For each
requirement: what fact or showing is needed, why the section needs it, and what kind
of record document would ordinarily contain it.

Describe requirements generically, in terms that transfer to any case using this
structure. "The claimant's relationship to the detained child" is a requirement.
"That Ms. R. is J.M.'s mother" is not — that is the model's own case, and it is not
the case being drafted.
```

Each requirement is then resolved against the fact index (`GET /api/cases/:id/facts`),
querying across **all** record documents, with the §2 routing table ordering which to search
first rather than limiting what is reachable. Each requirement ends up in one of three
states: **satisfied** (atoms found), **partial** (some atoms, gaps named), or **unmet** (no
atom anywhere in the record).

Show this checklist in the card as the draft generates. It is the most useful thing on
screen — it tells the user exactly which document to go find, and it is why a section comes
back marked `needs_input` rather than quietly short.

**Worked example — "Parties and Background."** The user clicks `WRITE THIS SECTION`. The
agent locates §III of the Expert Claim, whose function is `party_identification`. It derives
requirements: identify the claimant and their standing; identify the detained child and the
relationship; identify the responsible agency and facility; establish the custody period;
establish residence and jurisdictional ties. It then queries the fact index for each:
claimant identity and relationship resolve from the **Factual Report**; agency, facility, and
custody dates from the **Detention Report**; the parent's account of the relationship and
separation from the **Parent Response Questionnaire**; the standing framework from the
**Due-Process Rights Reference**. Every requirement satisfied gets drafted in the model's
paragraph order and register, each sentence carrying its source citation. Anything unmet —
say the exact transfer date is nowhere in the record — becomes a bracketed placeholder and
sets the section to `needs_input`.

**Step C — draft.**

```
You are drafting section {N} of {TOTAL} of a new legal claim, titled
"{drafted_title}".

MODEL (structure only): the corresponding section of a complaint filed in a different
case, with its neighboring sections for context.
REQUIREMENTS: what this section must establish, derived in Step B, each marked
satisfied, partial, or unmet.
FACTS: the atoms resolved against those requirements, each with its source document,
page, and paragraph. You may query the full fact index for anything further.
REFERENCE (law): the Due-Process Rights Reference.

Work through the requirements in the order the model establishes them. Every
requirement marked satisfied must be addressed in the draft; every requirement marked
unmet becomes a bracketed placeholder in the position the model would have put it.

Mirror the model's structure: paragraph count and ordering, the sequence in which
elements are established, where and how authority is cited, sentence-level register,
and approximate length.

Build every factual assertion from the FACTS provided. Each assertion you make must
name the fact atom behind it — an assertion with no atom is not permitted, and will be
rejected before the user sees it. Where a fact came from the Parent Response
Questionnaire, prefer the parent's own words over your paraphrase.

Do not import any fact, name, date, place, condition, or holding from the model
complaint's own record. It belongs to another family's case.

Where no atom supports a fact the structure calls for, first query the fact index in
case it sits in an unrouted document. If it genuinely is not in the record, insert a
bracketed placeholder naming exactly what is needed and which document should contain
it — for example [DATE OF TRANSFER — not in Detention Report]. Never invent, estimate,
infer, or approximate a fact. An incomplete draft with honest gaps is correct; a
complete draft with invented facts is a serious failure.

Preserve any vagueness the record carries. If the record says "sometime in the
spring," the draft says so too — do not resolve it into a date.

Mark every legal citation you carry over from the model with a verify flag. Structure
may be borrowed; authority must be confirmed against this case's jurisdiction and
facts before it can stand.
```

## 6. Token and performance strategy

An expert complaint can run 60+ pages. Do not re-send it on every call.

- Pass 1 reads the full document **once** and persists everything downstream needs.
- Pass 2 sends only the section index (titles, functions, summaries) — never the body text.
- Pass 3 sends only the mapped section plus its two neighbors, sliced by the stored
  `char_start`/`char_end` — and **fact atoms, never whole record documents.** A section on
  conditions of confinement should receive forty relevant atoms, not a forty-page report.
- Fact extraction runs once per record document on upload; re-extract only on re-upload.
- Run Pass 1 as a background job with the row status reflecting real progress. A 60-page
  parse should not block the UI.
- If the Expert Claim exceeds the model's context window, chunk with overlap on detected
  heading boundaries and stitch the section index — never truncate silently.

## 7. Guardrails

These are correctness requirements, not polish. Build them with the feature, not after.

1. **Fact-bleed check — the single most important property here.** After each section
   drafts, scan the output against `model_document.proper_noun_index`. Any expert-case name,
   place, date, or docket number appearing in the new draft blocks the save and is
   highlighted for the user. Borrowing structure from a filed complaint makes it very easy
   to also borrow the other family's facts, and that failure is both invisible in review and
   seriously damaging.
2. **No fabrication, enforced by provenance.** Every factual assertion in a draft resolves to
   a `fact_atom` with a document, page, and paragraph. An unsourced assertion is flagged
   before the user sees it — same severity as expert-case fact bleed. Facts genuinely absent
   from the record become bracketed placeholders and `needs_input` status, surfaced as a
   visible checklist so gaps get filled rather than overlooked. Never a plausible-sounding
   invention.
3. **Citations carry a verify flag.** Authority from the model informs structure but is not
   asserted in the new claim until the user confirms it.
4. **Blocked states are explicit.** No Expert Claim → Section Drafter shows an empty state
   pointing at the upload. No Factual Report and no Detention Report → Pass 2 cannot run;
   say exactly that instead of generating generic titles. A section whose routed record is
   missing → `blocked`, naming the document it needs.
5. **This tool assists a person preparing their own claim.** Where the drafter is uncertain,
   it flags for human review rather than resolving on its own.

## 8. API surface

```
POST   /api/cases/:caseId/model-document        upload; kicks off Pass 1
GET    /api/cases/:caseId/model-document        status + section count
DELETE /api/cases/:caseId/model-document        invalidates structure map
POST   /api/cases/:caseId/records/:type         upload a record; kicks off fact extraction
GET    /api/cases/:caseId/facts                 fact index; filter by function, type, doc
GET    /api/cases/:caseId/facts/:id             single atom + source language
GET    /api/cases/:caseId/structure-map         joined expert_section + case_section
POST   /api/cases/:caseId/structure-map/titles  run/rerun Pass 2 (respects title_locked)
PATCH  /api/cases/:caseId/sections/:id          edit title (sets title_locked)
POST   /api/cases/:caseId/sections/:id/draft    run Pass 3; streams; what the button calls
GET    /api/cases/:caseId/sections/:id/requirements   Step B checklist + resolution state
GET    /api/cases/:caseId/sections/:id/model    model section text for side-by-side
GET    /api/cases/:caseId/sections/:id/versions  draft history for restore-after-rewrite
POST   /api/cases/:caseId/draft-all             run every section in order
```

## 9. Build order

1. Schema + migrations, with the parity invariant and its test.
2. Model upload row in `DOCUMENTS ON FILE`; remove the `MODEL SAMPLE` card and per-section
   uploads.
3. Pass 1 as a background job with live row status.
4. Structure Map screen, read-only.
5. Fact extraction over the record documents, with a browsable fact index.
6. Pass 2 + inline title editing and locking.
7. Pass 3 with routed fact atoms, provenance markers, and side-by-side model view.
8. Fact-bleed check, unsourced-assertion check, placeholder checklist, consistency check.

Ship 1–4 before starting 6 — the user must be able to see the extracted structure before any
generated title or draft is worth trusting. Step 5 can be built in parallel with 1–4; it
touches different documents and is the prerequisite for 7, not for 6.

## 10. Acceptance criteria

1. One Expert Claim upload produces a complete section-for-section structure map. No further
   uploads are needed to begin drafting.
2. Generated section count, order, and nesting match the Expert Claim exactly.
3. Every generated title reflects the new case's facts. No expert-case proper noun appears
   in any title or draft body — verified by the fact-bleed check, with a test that plants an
   expert-case name in a draft and asserts the save is blocked.
4. Drafting section N retrieves the structurally corresponding model section, matched by
   function rather than title text — verified by a test in which the new case's titles are
   deliberately unlike the model's.
5. Sections unsupported by the record are still created, marked `needs_input`, and list the
   specific missing facts and their source documents.
6. Replacing the Expert Claim regenerates the structure map while preserving user-locked
   titles.
7. A 60-page Expert Claim parses without blocking the UI, and drafting a single section does
   not re-send the full document.
8. Every factual assertion in a drafted section carries an inline citation to a fact atom
   that expands to its source language — verified by a test asserting that a draft
   containing an unsourced assertion is flagged rather than saved.
9. Facts drawn from the Parent Response Questionnaire appear in the parent's own words where
   the record supplies quotable language.
10. Drafting a section receives fact atoms, not whole record documents — verified by
    asserting the drafting call's payload excludes full document text.
11. The same fact normalizes identically across every section that asserts it, and
    contradictions flagged at extraction are never both asserted.
12. **The primary flow works end to end in one click.** With the Expert Claim and the four
    record documents on file, opening any section — "Parties and Background," say — and
    pressing `WRITE THIS SECTION` produces a drafted section that follows the model's
    structure, states this case's facts, cites each to its source document and page, and
    lists any facts the record does not contain. No further configuration, uploads, or
    prompt-writing by the user.
13. The requirements checklist is visible during and after drafting, and each item shows
    whether it was satisfied, partially satisfied, or unmet.
14. `REWRITE` on a hand-edited draft confirms before overwriting, and the prior version is
    restorable.

## 11. Out of scope

Multi-model blending (only one Expert Claim per case), automatic filing or export formatting,
and any change to how the four existing record documents are uploaded or displayed beyond the
badge taxonomy in §2.
