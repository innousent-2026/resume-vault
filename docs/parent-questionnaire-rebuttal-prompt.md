# Feature Prompt — Parent Questionnaire: Rebuttal-Only Generation from the Factual Report

**How to use this file:** everything below the horizontal rule is the prompt. Paste it into
Replit Agent as one message. This preamble is notes for us, not for Replit.

**What this changes:** the questionnaire currently generated is a general intake instrument —
it collects the parent's whole story. The goal is narrower and sharper: every question must
exist to counteract a specific stated reason for removal, and must gather both the parent's
explanation and the proof that corroborates it. The `HOW TO RESOLVE EVERY ISSUE` and
`SUPPORTING DOCUMENTS FOR YOUR CASE` sections are working well and stay as they are.

**Read the "admission guard" section (§4) closely.** The current output contains several
questions whose honest answers would hand the agency evidence it otherwise has to prove.
That is the most important thing being fixed here.

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

## 1. What is wrong with the current output

Diagnose against the current generated questionnaire, which has 89 questions across 12
sections. Three problems, in order of severity:

**1. Some questions produce admissions against the parent.** The generated questionnaire asks
the parent to "describe what, if anything, you told the children about what to say or not say
to workers or investigators" (targeting the coaching allegation), and to "describe any time
Donovan was left alone with Dereck Jackson, and how often this happened" (targeting the
access/opportunity element of the sexual-abuse risk allegation). A candid answer to either
supplies the agency with an element it would otherwise have to prove, in the parent's own
words, in a document headed "your answers may be used in a court filing." This must not
happen. See §4.

**2. Whole sections are untethered from any removal reason.** `SECTION 1 — TIMELINE OF THE
REMOVAL` (13 questions) and `FINAL SECTION — ANYTHING THE REPORT LEFT OUT` (4 questions)
collect narrative that serves no identified reason. Removal-day facts are relevant only where
they bear on a specific reason — a defective warrant, a missing notice, an alternative to
removal that was never offered — and they belong to that reason's section.

**3. Most questions gather rather than rebut.** "Tell me, in your own words, what you know
about how Londyn and Damarius were disciplined in your home" invites an open narrative on the
agency's own theory. A rebuttal question targets what the agency must establish and gives the
parent a place to contradict it, supply missing context, or show what they actually did.

## 2. Generation pipeline

### Step 1 — Extract the removal reasons

Parse the Factual Report into a structured list of every reason offered for removal. The
current report already yields these as R1–R11; preserve those identifiers so the questionnaire,
the resolve-issues table, and the report stay cross-referenced.

```
removal_reason
  id, case_id, reason_code,        # R1, R2, …
  reason_text,                     # the allegation as the report states it
  source_page, source_paragraph,
  reason_type,                     # allegation | agency_conclusion | court_finding
  legal_basis,                     # e.g. WIC 300(b), 300(d), 300(j), where stated
  elements,                        # jsonb: the propositions that must be true for
                                   # this reason to hold — see Step 2
  evidence_cited,                  # what the report relies on for this reason
  evidence_gaps                    # what the report asserts without support
```

`reason_type` matters because the three types are answerable in different ways:

- **allegation** — a factual claim about what happened or what the parent knew. The parent can
  contradict it, contextualize it, or show it is unsupported.
- **agency_conclusion** — a judgment built on the allegations, e.g. "no reasonable means to
  protect the children in the home." The parent counters by showing what was never considered.
- **court_finding** — a ruling. A parent's narrative cannot make a finding untrue. These are
  answered procedurally: what was presented, what the parent was able to respond to, what the
  record contains. Keep these questions but mark them clearly as record-preservation, not
  factual rebuttal.

### Step 2 — Decompose each reason into its elements

This is the step that makes the questions targeted instead of general. For each reason, list
the discrete propositions that must hold for it to stand.

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

For each proposition, state what the report offers in support of it, and whether the
report supports it at all or merely asserts it. A proposition asserted without support
is the most productive thing in this list — mark it.
```

Unsupported propositions are where a rebuttal has the most leverage, and they drive the
best questions. Note in the example that (e) is about the specific child before the court —
reasons that reason from a sibling's harm to this child's risk usually have their weakest
proposition there.

### Step 3 — Generate questions against the elements

For each proposition, generate questions **only** where the parent can speak from personal
knowledge and where an answer would weaken it. Not every proposition yields a question — if
the parent has nothing to offer against it, generate nothing and do not pad.

Every question must be one of these six types. Tag each with its type and the proposition it
targets; a question that fits none of these types does not belong in the questionnaire.

| Type | What it does |
|---|---|
| `contradiction` | The report asserts something the parent knows to be untrue |
| `missing_context` | The event happened, but the report omits circumstances that change its meaning |
| `attribution` | The report attributes knowledge, action, or capacity to the parent that was not theirs |
| `protective_action` | What the parent actually did to protect the child — the direct answer to "failure to protect" |
| `alternative_available` | In-home options that existed and were never offered — the answer to "no reasonable means" |
| `procedural` | Whether required process happened — for `court_finding` reasons and threshold requirements |

**The generation test, applied to every question before it ships:**

> If the parent answers this question fully and truthfully, does the answer weaken a specific
> stated reason for removal?

If the answer is no, cut the question. If the answer is "it depends what they say," see §4 —
that is usually the signature of an admission-generating question.

### Step 4 — Pair every question with its proof

The parent's explanation is worth much more when something corroborates it. Each question
carries three parts, and the answer is incomplete without the third:

```
Q23.  [targets R2, proposition (b) — that the mother knew or should have known]

      The report states you knew or should have known about the abuse of Remy before
      May 5, 2023. It does not say how you would have known.

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

`I have nothing that shows this` must always be an option. A parent who checks it has given
their attorney useful information, and the alternative is pressure to overstate.

Roll every proof item up into the existing `SUPPORTING DOCUMENTS FOR YOUR CASE` section
automatically, so the parent gets one consolidated list of what to gather.

## 3. Structure of the generated questionnaire

```
PARENT QUESTIONNAIRE
Case / child / prepared-for / date          (unchanged)
HOW TO COMPLETE THIS QUESTIONNAIRE          (unchanged — the guidance is good)

PART 1 — ANSWERING THE ALLEGATIONS
  One section per reason_type = allegation, in the report's own order.
    Section header names the reason and its code: "(Answers reason R2)"
    "What the report says:" — the allegation in plain language      (unchanged, works well)
    "What the report relies on:" — NEW: the evidence cited, and what is asserted
      without support. This tells the parent where their answer matters most.
    Questions, each tagged to a proposition, each with explanation + basis + proof
    Witnesses block                                                  (unchanged)

PART 2 — ANSWERING THE AGENCY'S CONCLUSIONS
  reason_type = agency_conclusion. Heavily weighted to `alternative_available`
  and `protective_action`.

PART 3 — THE RECORD OF THE COURT PROCEEDINGS
  reason_type = court_finding. Framed honestly: these questions preserve what
  happened procedurally for the attorney. Say so in the section note rather than
  implying the parent's answers can undo a finding.

DOCUMENTS CHECKLIST                          (unchanged, now auto-rolled-up)
HOW TO RESOLVE EVERY ISSUE                   (unchanged — keep exactly as is)
SUPPORTING DOCUMENTS FOR YOUR CASE           (unchanged — keep exactly as is)
```

**Removed:** `SECTION 1 — TIMELINE OF THE REMOVAL` and `FINAL SECTION — ANYTHING THE REPORT
LEFT OUT` as standalone sections. Timeline questions that bear on a reason move into that
reason's section. Keep exactly one open question at the end:

> Is there anything in the report you believe is inaccurate that this questionnaire did not
> ask you about? Name the part of the report and explain what is wrong with it.

That preserves the catch-all value while staying anchored to rebutting the report.

## 4. The admission guard — build this, do not treat it as advice

**Never generate a question whose truthful answer supplies an element the agency must
prove.** The parent is answering in writing, for a document that may be filed. A question
that invites them to narrate their own conduct on a contested point is a liability, not an
instrument.

Run every generated question through this check and regenerate any that fails:

```
This question will be answered in writing by a parent, and the answer may be filed in
court. The agency must prove the propositions listed for this reason.

Does a truthful, cooperative answer to this question tend to establish any of those
propositions?

If yes, the question is unsafe. Rewrite it to target one of these instead:
  - what the agency's claim is based on, and whether that basis exists
  - what the parent affirmatively did that cuts against the claim
  - who else witnessed the relevant events and what they would say
  - what the report leaves out that changes the meaning of what it reports
Never ask the parent to narrate conduct that is itself the alleged wrongdoing,
unless the question is framed as a direct denial with the parent's account of what
actually happened.
```

**Worked example — the coaching allegation (R7).**

Currently generated, unsafe:

> 57. Describe what, if anything, you told the children about what to say or not say to
> workers or investigators.

An honest answer establishes coaching. Even an innocent answer ("I told them to tell the
truth") is a written admission that the parent discussed the interviews with the children
beforehand, which is the factual predicate the characterization rests on.

Regenerated, safe — same allegation, aimed at the agency's basis and the parent's account:

> 57. The report describes the children as appearing "coached." Were you ever told what
>     specifically the workers observed that led to this description? If so, who told you,
>     and what did they say?
> 58. Were you present during any interview of your children? If yes, describe what you
>     observed.
> 59. Did any worker or investigator ever ask you whether you had discussed the
>     investigation with your children? If yes, what did you tell them at the time?
> 60. Is there anyone outside your family — a teacher, doctor, counselor, coach — who could
>     describe how your children normally talk about difficult subjects?
> 61. The report describes your family as "enmeshed" and "acting in unison." In your own
>     words, is that accurate? Explain what you think the workers were reacting to.

Same target, no manufactured admission, and question 60 opens an evidentiary avenue the
original missed entirely.

Apply the same treatment to the access questions under R4 and R5. "Describe any time the
child was left alone with the father, and how often" becomes questions about what supervision
actually looked like, who else was present in the home, and whether anyone ever raised a
concern about this child specifically.

## 5. Additional generation rules

- **Personal knowledge only.** Every question must be answerable by this parent from what they
  saw, heard, did, or were told. Never ask them to characterize another adult's state of mind
  or to speculate about what an agency was thinking.
- **Distinguish firsthand from hearsay.** Keep the existing "how do you know this" pattern —
  it is doing real work — but attach it to each question rather than once per section.
- **This child, by name.** Reasons that reason from a sibling's harm to this child's risk are
  usually weakest on the child actually before the court. Generate at least one question per
  such reason directed at that gap.
- **Plain language.** No statutory citations in question text; the parent is answering, not
  briefing. Legal basis belongs in the section header and the resolve-issues table.
- **No leading questions.** Do not suggest the answer that helps. "The report is wrong that
  you refused services, isn't it?" produces worthless testimony and reads badly if filed.
  Ask what happened.
- **Length follows the report.** A reason with two supported propositions gets a few
  questions. Do not generate a fixed number per section. Total question count should fall
  well below the current 89 — the current count is inflated by untargeted narrative.
- **Preserve gaps honestly.** Where the report is illegible, redacted, or missing a source,
  carry the existing `[NEEDS SOURCE: …]` convention through rather than papering over it.

## 6. The "Update Questionnaire" button

Add an `UPDATE QUESTIONNAIRE FROM FACTUAL REPORT` button on the questionnaire view. It
regenerates the questionnaire against the current Factual Report.

**The hard requirement: regenerating must never destroy answers the parent has already
written.** Assume every regeneration happens after the parent has done hours of work.

Diff by reason and proposition, not by question number:

| Situation | Behavior |
|---|---|
| Reason unchanged, question unchanged | Keep question and its answer untouched |
| Reason unchanged, question reworded | Keep the answer, attach it to the reworded question, flag `review wording` |
| New reason in the report | Add its section, mark every question `new` |
| Reason removed from the report | Move its section to `Retired`, keep answers, never delete |
| Question removed but answered | Retain under `Retired`, visible and exportable |

After regeneration, show a summary before anything is committed:

```
Updated from Factual Report (revised Aug 19, 2026)

  + 1 new reason              R12 — failure to complete case plan services
  + 6 new questions           unanswered
  ~ 3 questions reworded      your answers were kept
  - 1 reason retired          R6 — your 4 answers are saved under Retired
    82 questions unchanged
```

Give the user `Apply` and `Discard` — never apply silently. Version the questionnaire on each
apply and allow restoring a prior version.

Button states: disabled with an explanatory note if no Factual Report is on file; `UPDATING…`
while running; if the report has not changed since the last generation, say so and offer
`Regenerate anyway`.

## 7. Data model additions

```
questionnaire
  id, case_id, version, generated_at, factual_report_version, status

questionnaire_question
  id, questionnaire_id, removal_reason_id,
  proposition_ref,            # which element of the reason this targets
  question_type,              # contradiction | missing_context | attribution |
                              # protective_action | alternative_available | procedural
  part,                       # 1 allegations | 2 conclusions | 3 court record
  order_index, question_text, context_text,
  proof_options,              # jsonb: the checklist under part (c)
  admission_check_passed,     # bool — §4 gate; false blocks publication
  state                       # active | reworded | new | retired

questionnaire_answer
  id, question_id, answer_text, basis_text,   # basis = how the parent knows
  proof_selected, proof_notes,
  answered_at, updated_at, retired_with_question
```

## 8. Acceptance criteria

1. Every generated question carries a `removal_reason_id` and a `proposition_ref`. A question
   that traces to no reason cannot be generated — enforce in code, not only in the prompt.
2. No standalone timeline or general-background section appears in the output.
3. Every question passes the §4 admission check before publication, with a test that feeds in
   the current unsafe question 57 and asserts it is rejected and rewritten.
4. Every question offers explanation, basis, and proof, and the proof list always includes
   "I have nothing that shows this."
5. `HOW TO RESOLVE EVERY ISSUE` and `SUPPORTING DOCUMENTS FOR YOUR CASE` render exactly as
   they do today, with the documents list now aggregated from per-question proof items.
6. Court-finding reasons are presented as record preservation, not as factual rebuttal.
7. `UPDATE QUESTIONNAIRE` preserves every existing answer across a regeneration in which
   reasons are added, reworded, and removed — verified by a test that answers all questions,
   changes the report, regenerates, and asserts no answer text is lost.
8. The update summary appears before changes are applied, and the prior version is
   restorable.
