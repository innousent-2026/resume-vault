# Feature Prompt — Section Drafter: Whole-Document Expert Claim Mapping

Paste the block below into Replit as a single feature request. Everything above the
horizontal rule is context for us, not for Replit.

**What this changes, in one sentence:** instead of uploading a separate model snippet for
every section, the user uploads the *entire* Expert Claim once, and the drafting agent
mirrors that document's structure exactly while renaming every section to fit the new
case's own facts.

---

## FEATURE REQUEST: Expert Claim as a whole-document structural model

### Background

The Section Drafter currently expects a model sample to be uploaded per section ("UPLOAD
MODEL" inside each section card). That is the wrong unit of work. The user works from a
single filed complaint — the **Expert Claim** — and wants the new claim to follow that
document's architecture end to end.

Two things have to be true at the same time:

1. **Structure matches the Expert Claim exactly.** Same number of sections, same order,
   same nesting depth, same rhetorical job per section, comparable length and citation
   density.
2. **Section titles belong to the new case.** Titles are regenerated from the new case's
   own record — the Factual Report and the Detention Report — so they name the new
   claimant, facility, dates, and claim theories. The Expert Claim's proper nouns never
   appear in the new claim.

The agent must therefore analyze the *whole* Expert Claim and, for whatever section the
user is drafting, locate the structurally corresponding section inside it — matching on
function and position, not on title text, because the titles will deliberately differ.

---

### 1. Documents On File — add a Model Document slot

Replace the per-section "UPLOAD MODEL" affordance with one case-level upload.

In the `DOCUMENTS ON FILE` panel, keep the existing rows and add a new row above them:

| Badge | Label | Status |
|---|---|---|
| `MODEL` | Expert Claim Sample | `missing` / `parsed` / `N sections` |

Behavior:

- Accepts PDF, DOCX, TXT (single file, up to 50 MB). One model document per case;
  re-uploading replaces it and invalidates the derived structure map.
- On upload, immediately run **Pass 1 (Structure Extraction)** below and show progress
  inline on the row (`Parsing… → 14 sections found`).
- The row is clickable and opens the **Structure Map** review screen (section 4).
- The `MODEL SAMPLE` card that currently sits below `DOCUMENTS ON FILE` — the one that says
  "Upload a section from the filed complaint to use as a structural template" — is removed.
  Its per-section upload is superseded by this single upload.
- Existing per-section model uploads, if any are already stored, remain readable but the
  UI no longer offers new ones.

The other four rows (`Detention Report`, `Factual Report`, `Parent Response Questionnaire`,
`Due-Process Rights Reference`) keep their current badge styling and `missing` states.

### 2. Data model

Add three tables/collections:

```
model_document
  id, case_id, filename, mime_type, storage_key,
  raw_text, page_count, uploaded_at, parse_status, parse_error

expert_section            # one row per section found in the Expert Claim
  id, model_document_id, order_index, heading_level,
  source_title,           # verbatim heading from the Expert Claim
  char_start, char_end, page_start, page_end,
  rhetorical_function,    # e.g. "jurisdictional basis", "party identification",
                          #      "chronological fact narrative", "legal standard",
                          #      "element-by-element application", "damages", "relief"
  legal_elements[],       # what this section must establish to do its job
  evidence_types[],       # e.g. ["intake records","witness declaration","policy citation"]
  word_count, citation_count, tone_notes

case_section              # 1:1 with expert_section, same order_index
  id, case_id, expert_section_id, order_index,
  drafted_title,          # generated from the new case's record
  title_rationale,        # why this title, which source facts drove it
  status,                 # not_started | mapped | drafting | drafted | needs_input
  draft_body, last_drafted_at
```

Invariant to enforce in code and in a test: `count(case_section) == count(expert_section)`
and the `order_index` sequences are identical. The user may edit a `drafted_title` or
reorder, but any deviation from the Expert Claim's structure is surfaced as a warning
banner ("Structure no longer matches model: 13 of 14 sections").

### 3. Three-pass agent design

**Pass 1 — Structure Extraction.** Runs once, on Expert Claim upload. Input: the full
Expert Claim text. Output: the ordered `expert_section` rows above. Detect headings by
numbering scheme, typography, and semantic breaks — do not rely on a single regex, filed
complaints number sections inconsistently. For each section, summarize *what job it does
in the argument*, not what it says about the expert case's facts. This summary is the
matching key later, so it must be fact-agnostic and portable.

**Pass 2 — Title Mapping.** Runs after Pass 1 completes and whenever the Factual Report or
Detention Report changes. Input: all `expert_section` rows + the new case's Factual Report
and Detention Report. Output: a `drafted_title` for every section, in order.

Rules for generated titles:
- Preserve the section's rhetorical function and its position in the argument.
- Use the new case's parties, facility, agency, dates, and claim theories — pulled from the
  Factual Report and Detention Report only.
- Never carry over a proper noun, docket number, date, or case-specific phrase from the
  Expert Claim.
- Match the Expert Claim's *heading conventions* (numbering style, capitalization, whether
  headings are assertions or labels) even while the words change.
- If the new case's record contains no facts supporting a section's function, still create
  the section (structure must match) but title it neutrally and set
  `status = needs_input` with a note naming the missing fact.

**Pass 3 — Section Drafting.** Runs per section, on demand, when the user opens a section
in the Section Drafter. This is the pass that must read the whole Expert Claim.

Retrieval for a section with `order_index = N`:
1. Load the full Expert Claim text.
2. Select the mapped `expert_section` by `order_index`, then *verify* the mapping by
   comparing the section's `rhetorical_function` and `legal_elements` against what the
   current section is supposed to accomplish. Do not match on title similarity — titles
   diverge by design.
3. If verification fails (the mapped section does not do the job the current section
   needs), search the whole document for the section whose function best matches, and
   surface the re-mapping to the user rather than silently switching.
4. Pass the model section's full text **plus the preceding and following section** as
   context, so transitions and cross-references read correctly.

Drafting instruction to the model, per section:

> You are drafting section {N} of {TOTAL}, titled "{drafted_title}", for the new claim.
> The corresponding section of the Expert Claim is provided in full, along with its
> neighbors. Mirror its structure: paragraph count and ordering, the sequence in which
> elements are established, how authority is cited and where, sentence-level register, and
> approximate length. Replace every fact with the corresponding fact from the new case's
> Factual Report and Detention Report. Do not import any fact, name, date, place, or
> holding from the Expert Claim's own record. Where the new case's record does not supply
> a fact the structure calls for, insert a bracketed placeholder naming exactly what is
> needed — never invent, estimate, or infer a fact.

### 4. Structure Map screen

Clicking the `MODEL` row opens a two-column review table so the user can verify the
mapping before drafting anything:

| # | Expert Claim section (model) | Your claim section (generated) | Status |
|---|---|---|---|
| 1 | *verbatim expert heading* | *generated title* | mapped |
| 2 | … | … | needs input |

Per row: expand to see the expert section's function summary and the rationale for the
generated title; edit the generated title inline; jump straight to drafting that section.
A "Regenerate titles" action reruns Pass 2 after new documents are uploaded, preserving any
titles the user has manually edited (flag them as user-locked).

### 5. Section Drafter card changes

Each section card in the Section Drafter shows:
- the generated title (the new case's title, not the expert's),
- a subtle reference line: `Modeled on §{order_index} of Expert Claim — "{source_title}"`,
  which expands to show that model section's text side by side with the draft,
- the section's status chip, and any bracketed placeholders surfaced as a checklist of
  missing facts.

Remove the per-section upload control entirely.

### 6. Guardrails

- **No fact bleed.** After each section drafts, run a check against the Expert Claim's
  extracted proper nouns, dates, and docket identifiers; flag any that appear in the new
  draft and block save until cleared. This is the single most important correctness
  property of the feature.
- **No fabrication.** Missing facts become bracketed placeholders and `needs_input`, never
  invented content.
- **Citations are not copied as authority.** Legal citations from the Expert Claim may
  inform structure, but each carries a `verify` flag in the new draft until the user
  confirms it applies to the new case's jurisdiction and facts.
- **Blocked states.** If the Expert Claim is missing, the Section Drafter shows an empty
  state pointing to the upload. If the Factual Report and Detention Report are both
  missing, Pass 2 cannot run — say so explicitly rather than generating generic titles.

### 7. Acceptance criteria

1. Uploading one Expert Claim produces a section-for-section structure map with no further
   uploads required.
2. Generated section count, order, and nesting match the Expert Claim exactly.
3. Every generated title reflects the new case's facts; no Expert Claim proper noun appears
   in any title or draft body.
4. Drafting section N retrieves and cites the structurally corresponding Expert Claim
   section, verified by function rather than by title text.
5. Sections unsupported by the new case's record are still created, marked `needs_input`,
   and list the specific missing facts.
6. Replacing the Expert Claim invalidates and regenerates the structure map, keeping
   user-locked titles.
