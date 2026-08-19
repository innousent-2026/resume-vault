# Feature Prompt — Parent Questionnaire: Rebuttal-Only Generation from the Factual Report

**How to use this file:** everything below the horizontal rule is the prompt. Paste it into
Replit Agent as one message. This preamble is notes for us, not for Replit.

**What this changes:** the questionnaire currently generated is a general intake instrument —
it collects the parent's whole story. The goal is narrower and sharper: every question must
exist to counteract a specific stated reason for removal, and must gather both the parent's
explanation and the proof that corroborates it. The `HOW TO RESOLVE EVERY ISSUE` and
`SUPPORTING DOCUMENTS FOR YOUR CASE` sections are working well and stay as they are.

**Two things to read closely.** §4 is the admission guard — the current output contains
questions whose honest answers would hand the agency evidence it otherwise has to prove. §3
is the verification chain — the machinery for attacking findings and allegations that rest on
unverified or false statements rather than on investigated fact.

---

# BUILD: Regenerate the Parent Questionnaire as a rebuttal instrument driven by the Factual Report

## 0. What this feature is for

The Factual Report identifies every reason the agency and the court gave for removing the
child. The Parent Questionnaire exists for exactly one purpose: **to let the parent answer
those reasons — each one, specifically — with their own account and with proof.**

It is not an intake form. It is not a place to collect the family's general history. Every
question must be traceable to a removal reason, and must be shaped to weaken that reason.

The finished questionnaire goes to an attorney and the answers may be used in a filing. That
raises the bar on both accuracy and safety: see §4.

## 1. The premise the design rests on

**A statement in a court report is not a verified fact, and a court finding is only as sound
as the material it was based on.**

Detention findings are typically made on a prima facie standard, in a short hearing, on the
agency's report — often before the parent has counsel, and usually without the parent
testifying. Whatever is in that report is what the court acts on. So a finding can be entered
on:

- a reporting party's claim recorded as established fact, never independently checked
- a professional opinion offered by someone who never examined the child or read the
  underlying records
- a summary of an interview that a worker did not conduct and did not listen to
- a statement attributed to the parent that the parent never made, or that is materially
  altered from what they said
- a description of an investigative step, home visit, service offer, or contact that did
  not occur
- exculpatory information known to the worker and left out of the report

None of these are exotic. They are the recurring factual basis of federal civil-rights claims
arising from dependency proceedings — claims that turn on false statements and material
omissions in the documents presented to the court.

**Design consequence:** the questionnaire must attack the *foundation* of every reason, not
only its conclusion. That applies to allegations, to agency conclusions, and to court
findings alike. There is no category of reason that gets only procedural treatment.

**A necessary discipline that comes with this.** The instrument captures discrepancies; it
does not coach accusations. Never generate a question that invites the parent to allege that
a worker lied, falsified, or committed perjury. Ask what the parent observed, what they
actually said, and what the report says — and let the gap between them stand on the record.
A questionnaire that records "the report states I refused services on March 14; no one
contacted me in March; my phone records show no calls from the agency that month" is far more
useful to an attorney, and far more credible in a filing, than one that records "the worker
lied." The parent supplies facts. Characterization is the attorney's work.

## 2. What is wrong with the current output

Diagnose against the current generated questionnaire, which has 89 questions across 12
sections. Four problems:

**1. Some questions produce admissions against the parent.** The generated questionnaire asks
the parent to "describe what, if anything, you told the children about what to say or not say
to workers or investigators" (targeting the coaching allegation), and to "describe any time
Donovan was left alone with Dereck Jackson, and how often this happened" (targeting the
access element of the sexual-abuse risk allegation). A candid answer to either supplies the
agency with an element it would otherwise have to prove, in the parent's own words, in a
document headed "your answers may be used in a court filing." See §4.

**2. Nothing tests where the report's assertions came from.** No question anywhere asks
whether an assertion was verified, who originally said it, whether the person who wrote it
had firsthand knowledge, or whether described events occurred at all. This is the largest
missed opportunity in the current instrument. See §3.

**3. Whole sections are untethered from any removal reason.** `SECTION 1 — TIMELINE OF THE
REMOVAL` (13 questions) and `FINAL SECTION — ANYTHING THE REPORT LEFT OUT` (4 questions)
collect narrative serving no identified reason. Removal-day facts are relevant where they
bear on a specific reason, and belong in that reason's section.

**4. Most questions gather rather than rebut.** "Tell me, in your own words, what you know
about how Londyn and Damarius were disciplined in your home" invites open narrative on the
agency's own theory.

## 3. Generation pipeline

### Step 1 — Extract the removal reasons

Parse the Factual Report into every reason offered for removal. The current report yields
these as R1–R11; preserve those identifiers so the questionnaire, the resolve-issues table,
and the report stay cross-referenced.

```
removal_reason
  id, case_id, reason_code,        # R1, R2, …
  reason_text,                     # the allegation as the report states it
  source_page, source_paragraph,
  reason_type,                     # allegation | agency_conclusion | court_finding
  legal_basis,                     # e.g. WIC 300(b), 300(d), 300(j), where stated
  propositions,                    # jsonb — Step 2
  evidence_cited,
  evidence_gaps
```

`reason_type` describes where a reason sits in the case, **not** how hard it may be
challenged. Every type gets full factual treatment.

### Step 2 — Decompose each reason into its propositions

```
Break this stated reason for removal into the specific propositions that must each be
true for the reason to hold. Number them.

Example — "Mother knew or should have known of father's sexual abuse of Remy and
continued to allow him access to the child" decomposes into:
  (a) the abuse of Remy occurred
  (b) the mother knew of it, or a reasonable parent would have
  (c) the mother had the ability to control the father's access to the child
  (d) she continued to allow that access after acquiring that knowledge
  (e) that access created a risk to THIS child specifically

For each proposition, state what the report offers in support, and whether the report
supports it at all or merely asserts it.
```

Reasons that argue from a sibling's harm to this child's risk are usually weakest on the
proposition about the child actually before the court. Mark that.

### Step 3 — Trace the verification chain for each proposition

**This step is what makes the instrument capable of reaching a falsified or unverified
foundation, and it runs on every reason regardless of type.**

For each proposition, trace backward through the report:

```
For this proposition, trace how it entered the record:

  ORIGIN     — who first asserted it? Named person, anonymous reporter, or unstated?
  CONVEYANCE — how did it reach the report's author? Did the author see or hear it
               firsthand, or are they repeating what someone else told them? Count the
               layers: a worker writing what a supervisor was told by a reporting party
               is three layers from the event.
  VERIFICATION — does the report show anyone independently checked it? An examination
               performed, a record pulled, a witness interviewed, a document reviewed?
               Or does the assertion simply appear, stated as fact?
  DOCUMENT   — is the underlying source attached, quoted, or merely referenced? A
               summary of a report that is not attached is not the report.
  ATTRIBUTION — does the report attribute a statement to the parent? Flag every one of
               these separately; they receive their own section of the questionnaire.

Then classify the chain:
  verified            — firsthand and independently corroborated in the report
  unverified_hearsay  — repeated from another source with no shown verification
  unsourced           — stated as fact with no origin given at all
  conclusory          — a characterization or opinion presented as observation
                        ("appeared coached", "enmeshed", "the home was unsafe")

Every proposition that is not `verified` is a place where the parent's firsthand
account may be the only contrary evidence in existence. Those generate questions
first.
```

The output of this step drives question generation and should also surface to the attorney as
a standalone view: which propositions in this case rest on nothing that was checked.

### Step 4 — Generate questions against propositions and chain breaks

Generate questions **only** where the parent can speak from personal knowledge and where an
answer would weaken the reason. Not every proposition yields a question. Do not pad.

Each question is tagged with its type, the proposition it targets, and the chain break it
exploits where applicable.

| Type | What it does |
|---|---|
| `contradiction` | The report asserts something the parent knows to be untrue |
| `missing_context` | The event happened, but the report omits circumstances that change its meaning |
| `attribution` | The report attributes knowledge, action, or capacity to the parent that was not theirs |
| `protective_action` | What the parent actually did to protect the child — the direct answer to "failure to protect" |
| `alternative_available` | In-home options that existed and were never offered — the answer to "no reasonable means" |
| `misquotation` | The report states the parent said something they did not say, or alters its meaning |
| `event_did_not_occur` | The report describes a visit, contact, interview, offer, or service that did not happen |
| `no_verification` | The parent knows the check the report implies was never made — no one called the doctor, pulled the school records, visited the home |
| `source_challenge` | The assertion traces to someone with no firsthand knowledge, or to a source the parent can identify and contextualize |
| `omission` | The worker knew something exculpatory and it does not appear in the report |
| `procedural` | Whether required process actually happened |

**The generation test, applied to every question before it ships:**

> If the parent answers this question fully and truthfully, does the answer weaken a specific
> stated reason for removal, or expose a break in how that reason entered the record?

If no, cut it. If "it depends what they say," see §4.

### Step 5 — Pair every question with its proof

Each question carries three parts, and the answer is incomplete without the third:

```
Q23.  [targets R2, proposition (b) — that the mother knew or should have known]
      [chain: unverified_hearsay — origin is the reporting party; no verification shown]

      The report states you knew or should have known about the abuse before May 5,
      2023. The report does not say how you would have known, and does not show that
      anyone checked this.

  a.  In your own words: what did you actually know, and when did you learn it?

  b.  How do you know this — did you see or hear it yourself, or did someone tell you?
      If someone told you, who, and when?

  c.  What could show this is accurate? Check any you have or can get:
      ☐ Text messages or emails from that period
      ☐ Someone who can confirm what you knew and when — name and contact
      ☐ A record showing where you were or what you were doing
      ☐ Something else: ______
      ☐ I have nothing that shows this
```

`I have nothing that shows this` must always be an option. Roll every proof item up into the
existing `SUPPORTING DOCUMENTS FOR YOUR CASE` section automatically.

## 4. The admission guard — build this, do not treat it as advice

**Never generate a question whose truthful answer supplies an element the agency must prove.**

Run every generated question through this check and regenerate any that fails:

```
This question will be answered in writing by a parent, and the answer may be filed in
court. The agency must prove the propositions listed for this reason.

Does a truthful, cooperative answer tend to establish any of those propositions?

If yes, the question is unsafe. Rewrite it to target one of these instead:
  - what the agency's claim is based on, and whether that basis was ever checked
  - what the parent affirmatively did that cuts against the claim
  - who else witnessed the relevant events and what they would say
  - what the report leaves out that changes the meaning of what it reports
Never ask the parent to narrate conduct that is itself the alleged wrongdoing, unless
the question is framed as a direct denial with the parent's account of what happened.
```

**Worked example — the coaching allegation (R7).**

Currently generated, unsafe:

> 57. Describe what, if anything, you told the children about what to say or not say to
> workers or investigators.

An honest answer establishes coaching. Even an innocent answer ("I told them to tell the
truth") is a written admission that the parent discussed the interviews with the children
beforehand — the factual predicate the characterization rests on.

Regenerated — same allegation, aimed at the basis of the claim and at the parent's account:

> 57. The report describes the children as appearing "coached." Were you ever told what
>     specifically the workers observed that led to this description? If so, who told you,
>     and what did they say?
> 58. Were you present during any interview of your children? If yes, describe what you
>     observed.
> 59. Was the "coaching" description based on anything written down at the time — notes, a
>     recording, a transcript — that you know of?
> 60. Is there anyone outside your family — a teacher, doctor, counselor, coach — who could
>     describe how your children normally talk about difficult subjects?
> 61. The report describes your family as "enmeshed" and "acting in unison." In your own
>     words, is that accurate? Explain what you think the workers were reacting to.

Same target, no manufactured admission, and 59 goes straight at a `conclusory` chain
classification — a characterization presented as observation, with no contemporaneous record
behind it.

Apply the same treatment to the access questions under R4 and R5.

## 5. Structure of the generated questionnaire

```
PARENT QUESTIONNAIRE
Case / child / prepared-for / date          (unchanged)
HOW TO COMPLETE THIS QUESTIONNAIRE          (unchanged — the guidance is good)

PART 1 — STATEMENTS THE REPORT ATTRIBUTES TO YOU                          NEW
  Every statement the report attributes to the parent, quoted verbatim with its page
  and paragraph, each with: Did you say this?  ☐ Yes, accurately
                                               ☐ Partly — it changes what I meant
                                               ☐ No, I never said this
                                               ☐ I don't remember
  followed by "If not accurate, what did you actually say?" and "Who else was present
  when you said it?" and "Was it recorded or written down at the time, that you know of?"

  This part goes first because it is mechanical, high-value, and something only the
  parent can supply. A statement the parent never made, sitting in a report the court
  relied on, is among the most consequential things this instrument can surface.

PART 2 — ANSWERING THE ALLEGATIONS
  One section per reason_type = allegation, in the report's order.
    Section header names the reason and its code: "(Answers reason R2)"
    "What the report says:"        — the allegation in plain language     (unchanged)
    "What the report relies on:"   — NEW: the evidence cited, and which propositions
                                     are asserted with nothing behind them, in plain
                                     language: "The report does not say who reported
                                     this or whether anyone checked it."
    Questions, each tagged to a proposition, each with explanation + basis + proof
    Witnesses block                                                        (unchanged)

PART 3 — ANSWERING THE AGENCY'S CONCLUSIONS
  reason_type = agency_conclusion. Weighted to `alternative_available`,
  `protective_action`, `event_did_not_occur`, and `no_verification`.

PART 4 — THE FINDINGS AND WHAT THEY WERE BASED ON
  reason_type = court_finding. Full factual treatment, not record preservation.
  Section note to the parent:

    "The court made these findings based on what was presented to it. These questions
     are about what was actually presented, whether it was accurate, and whether the
     things the report says were done were in fact done."

  Every finding generates questions in two directions:
    - the factual claims embedded in the finding. "Reasonable efforts were made to
      prevent removal" is a factual assertion about what the agency did. The parent
      knows what was and was not offered to them, and can contradict it directly.
    - what the court was and was not given. What the parent was able to say, whether
      they had counsel, what they tried to present, whether anything they said appears
      in the record at all.

DOCUMENTS CHECKLIST                          (unchanged, now auto-rolled-up)
HOW TO RESOLVE EVERY ISSUE                   (unchanged — keep exactly as is)
SUPPORTING DOCUMENTS FOR YOUR CASE           (unchanged — keep exactly as is)
```

**Removed:** `SECTION 1 — TIMELINE OF THE REMOVAL` and `FINAL SECTION — ANYTHING THE REPORT
LEFT OUT` as standalone sections. Timeline questions bearing on a reason move into that
reason's section. Keep one open question at the end:

> Is there anything in the report you believe is inaccurate that this questionnaire did not
> ask you about? Name the part of the report and explain what is wrong with it.

## 6. Additional generation rules

- **Personal knowledge only.** Every question must be answerable from what this parent saw,
  heard, did, or was told. Never ask them to characterize another adult's state of mind.
- **Distinguish firsthand from hearsay.** Keep the existing "how do you know this" pattern —
  it is doing real work — attached to each question rather than once per section.
- **Never solicit an accusation.** No question may ask whether a worker lied, falsified,
  fabricated, or acted in bad faith. Ask what happened, what was said, and what the report
  says. The discrepancy is the finding; the parent does not need to name it.
- **Dates and specifics for anything the parent says did not occur.** A claim that a visit
  never happened is only useful with a date attached and a reason the parent is sure —
  "I was at work; my timesheet shows it." Every `event_did_not_occur` and `no_verification`
  question must ask for the date and the basis for certainty.
- **This child, by name.** Reasons arguing from a sibling's harm get at least one question
  aimed at the gap regarding the child actually before the court.
- **Plain language.** No statutory citations in question text. Legal basis belongs in the
  section header and the resolve-issues table.
- **No leading questions.** Do not suggest the helpful answer. Ask what happened.
- **"I don't remember" is always acceptable and always offered.** A parent guessing at a date
  to be helpful damages their own credibility more than a blank does.
- **Length follows the report.** No fixed count per section. Total should fall well below the
  current 89 — that count is inflated by untargeted narrative, and Part 1 will absorb much of
  what remains.
- **Preserve gaps honestly.** Carry the existing `[NEEDS SOURCE: …]` convention through.

## 7. The "Update Questionnaire" button

Add an `UPDATE QUESTIONNAIRE FROM FACTUAL REPORT` button on the questionnaire view. It
regenerates against the current Factual Report.

**Hard requirement: regenerating must never destroy answers the parent has already written.**
Assume every regeneration lands after hours of work.

Diff by reason and proposition, not by question number:

| Situation | Behavior |
|---|---|
| Reason unchanged, question unchanged | Keep question and answer untouched |
| Reason unchanged, question reworded | Keep the answer, attach to the reworded question, flag `review wording` |
| New reason in the report | Add its section, mark every question `new` |
| Reason removed from the report | Move to `Retired`, keep answers, never delete |
| Question removed but answered | Retain under `Retired`, visible and exportable |

Show a summary before anything commits:

```
Updated from Factual Report (revised Aug 19, 2026)

  + 1 new reason              R12 — failure to complete case plan services
  + 6 new questions           unanswered
  ~ 3 questions reworded      your answers were kept
  - 1 reason retired          R6 — your 4 answers are saved under Retired
    82 questions unchanged
```

`Apply` and `Discard` — never silent. Version on each apply; allow restoring a prior version.
Button states: disabled with an explanation if no Factual Report is on file; `UPDATING…` while
running; if the report is unchanged since last generation, say so and offer `Regenerate
anyway`.

## 8. Data model additions

```
questionnaire
  id, case_id, version, generated_at, factual_report_version, status

proposition
  id, removal_reason_id, ref, text,
  chain_origin, chain_layers, chain_verification,
  chain_class,                # verified | unverified_hearsay | unsourced | conclusory
  supporting_document_attached

attributed_statement          # drives Part 1
  id, case_id, quoted_text, source_page, source_paragraph,
  attributed_to, context_text

questionnaire_question
  id, questionnaire_id, removal_reason_id, proposition_id,
  question_type,              # see §3 Step 4 table
  part,                       # 1 attributed | 2 allegations | 3 conclusions | 4 findings
  order_index, question_text, context_text,
  proof_options,
  admission_check_passed,     # bool — §4 gate; false blocks publication
  state                       # active | reworded | new | retired

questionnaire_answer
  id, question_id, answer_text, basis_text,
  certainty,                  # for event_did_not_occur: what makes the parent sure
  proof_selected, proof_notes,
  answered_at, updated_at, retired_with_question
```

## 9. Acceptance criteria

1. Every generated question carries a `removal_reason_id` and a `proposition_id`. A question
   tracing to no reason cannot be generated — enforced in code, not only in the prompt.
2. Every proposition carries a `chain_class`, and every proposition classified other than
   `verified` generates at least one question unless the parent has no possible personal
   knowledge of it.
3. Part 1 lists every statement the report attributes to the parent, quoted verbatim with
   page and paragraph, each with the four-way accuracy response.
4. Court findings receive factual questions, not only procedural ones — verified by a test
   asserting that a "reasonable efforts were made" finding generates at least one question
   asking what was actually offered to the parent.
5. No question asks the parent to allege that anyone lied, falsified, or acted in bad faith —
   verified by a screening test over generated question text.
6. Every question passes the §4 admission check before publication, with a test that feeds in
   the current unsafe question 57 and asserts it is rejected and rewritten.
7. Every question offers explanation, basis, and proof, and the proof list always includes
   "I have nothing that shows this."
8. `event_did_not_occur` and `no_verification` questions always request a date and the basis
   for the parent's certainty.
9. No standalone timeline or general-background section appears in the output.
10. `HOW TO RESOLVE EVERY ISSUE` and `SUPPORTING DOCUMENTS FOR YOUR CASE` render exactly as
    they do today, with documents now aggregated from per-question proof items.
11. `UPDATE QUESTIONNAIRE` preserves every existing answer across a regeneration in which
    reasons are added, reworded, and removed — verified by a test that answers all questions,
    changes the report, regenerates, and asserts no answer text is lost.
12. The update summary appears before changes are applied, and the prior version is
    restorable.
