# Reviewer Issue Remediation Report

**Scope:** work done against `JMIR_Strict_Reviewer_Critical_Issues_Prioritized.docx`
and `JMIR_AI_Model_Reranking_Clarification_Questions.docx`
**Branch:** `model-finetuning`
**Date:** 2026-09-21, updated 2026-09-22
**Test suite at close:** 1319 passed, 4 skipped
**Artefact manifest:** 38 pinned artefacts, all matching

---

## Summary

`JMIR_Strict_Reviewer_Critical_Issues_Prioritized.docx` raises **12 issues**.
All 12 have a section below, in the document's own order and numbering. The
separate `JMIR_AI_Model_Reranking_Clarification_Questions.docx` raises 20
questions; those are audited in Appendix A, not numbered here.

| # | Issue | Priority | Status |
|---|---|---|---|
| 1 | Extraction too weak to allow unverified AI output into analytics | Critical | **Closed** — mandatory verification gate, enforced in code |
| 2 | Unbiased held-out evaluation unfinished | Critical | **Closed** — adjudicated 2026-09-22, 132/132 segments |
| 3 | Evaluation data does not match the intended input distribution | Critical | **Closed** — reframed as proxy/component evaluation |
| 4 | Reporting LLM failed its own governance contract | Critical | **Closed** — option (b): declared experimental, deterministic operational |
| 5 | Ethics/IRB must cover more than the public corpus | Critical | **Partially addressed** — overclaim corrected; determination external |
| 6 | 8 fields generated, only 5 evaluated | High | **Closed** — scope verified in code, pinned by tests, stated |
| 7 | Adequacy thresholds not clinically validated | High | **Closed** — relabelled prototype thresholds in four places |
| 8 | Gold-standard expert description needs detail | High | **Scaffolded** — coverage verified; credentials needed from you |
| 9 | Kitchen-sink paper — no single primary contribution | High | **Closed** — evaluation framework primary, throughout |
| 10 | No independent usability/workflow evaluation | Moderate | **Closed** (bounded) — benefits marked undemonstrated |
| 11 | Reproducibility and data-release details | Moderate | **Open** — needs release decisions from you |
| 12 | Generative-AI disclosure and citation audit | Moderate | **Partially drafted** — blocked on the reference list |

**8 closed, 2 partial, 1 scaffolded, 1 open.** Everything not closed is blocked
on something external to this repository — an IRB determination, your
annotators' credentials, or a release decision — not on work that could have
been done here.

Two problems were found during the work that the reviewer had not flagged, and
both are recorded in full: the missing frontend `lib/` directory (Issue 1 §a)
and an overclaim in the ethics section (Issue 5).

---

## Issue 1 — Unverified AI output reaching longitudinal analytics · **Closed**

### The defect

`analytics_service.get_current_version_records()` admitted records with status `VALIDATED`. That status is set **automatically** by the extraction pipeline on four of its five routing paths (`ACCEPT`, clarification-exhausted, clarification-no-question, `RETAIN_WITH_UNKNOWN`); only `INTERVENTIONIST_REVIEW` produced `PENDING`. AI-extracted records were therefore reaching longitudinal analytics without any human ever having read them.

Deterministic validation establishes that a record is *schema-conformant*. It cannot establish that the record is a correct reading of the source text — a wrong value drawn from the right enumeration is indistinguishable in form from a right one. At 43.1% mean categorical-field accuracy, that gap is not hypothetical.

### What changed

| File | Change |
|---|---|
| `src/backend/models/observation.py` | Added `RecordStatus.VERIFIED`; added `verified_by` (FK `users`) and `verified_at` columns |
| `src/backend/services/analytics_service.py` | Gate tightened to `status.in_([VERIFIED, CORRECTED])`; docstring corrected — it still said "validated or corrected" |
| `src/backend/services/observation_service.py` | New `verify_record()` |
| `src/backend/api/structured_records.py` | New `POST /records/{record_id}/verify` |
| `src/backend/schemas/api_schemas.py` | `verified_by`, `verified_at` on `RecordResponse` |
| `alembic/versions/004_add_verified_record_status.py` | New migration |

**Design decisions worth recording:**

- **Verification does not create a new version.** It changes review state, not content, and the immutability rule exists to protect content. Who verified and when are stored on the record; the act is written to the audit trail.
- **A `PENDING` record cannot be verified as written.** It was routed for review because the evidence was inadequate; accepting it unchanged would silently undo the abstention router's decision. It must be corrected or rejected.
- **Existing `VALIDATED` rows are deliberately not migrated to `VERIFIED`.** Nobody reviewed them. Migrating them would have manufactured the very approval the gate exists to require.
- **The audit entry records the record's real prior status.** It was initially hardcoded to `"validated"`, which would have been wrong on an idempotent re-verify.

### Frontend

- New `src/frontend/components/records/VerificationPanel.tsx` — "Review required" panel; offers **Verify as written** only when the record is `VALIDATED`, and correction-only for `PENDING`.
- `StructuredRecordView.tsx` — status colours corrected. `validated` previously rendered green/`success`; it now reads as a waiting state, and only `verified`/`corrected` read as settled. The provenance line shows `verified_by` / `verified_at`.
- Record detail page wires the panel in.

### Tests (15 added)

- `tests/phase3/test_structured_records.py` — 8 endpoint tests: happy path, audit content, 409 on a `PENDING` record, 404 on missing record and missing parent observation, contributor forbidden, unauthenticated, and child-authorization enforced (asserting the service is **not** called when authorization fails).
- `tests/phase3/test_observation_service.py` — 8 service tests: state transition, no new version written, idempotence for already-verified, corrected left alone, refusal parametrized across `PENDING`/`REJECTED`/`ABSTAINED`, unknown record.
- `tests/phase4/test_analytics_gate.py` *(new file, 7 tests)* — compiles the actual analytics query and asserts the admitted status set is exactly `{verified, corrected}`. Widening the gate is a one-word edit; this makes it a failing test.

### Documentation

- `docs/paper/figures/fig23_architecture_mars.png` regenerated: the live request path now draws seven stages instead of six, with the verification gate marked in red and captioned "only verified or corrected records are admitted to analytics".
- Manuscript: new Discussion subsection *"Consequences for the application: a mandatory verification gate"*.
- `docs/User_and_Demo_Manual.md`: record statuses rewritten with analytics-eligibility stated per status; new "The Verification Gate" section.

### (a) Found during this work — frontend `lib/` is missing

`.gitignore` line 17 carried an unanchored `lib/` from the standard Python template. It was silently ignoring `src/frontend/lib/` — the API client, hooks (`useRecords`), types, and formatters that **every** page and component imports. The directory is absent from git *and* from disk.

Fixed the pattern (`/lib/`, `/lib64/`) so the directory can be committed. **The directory itself still has to be restored — the frontend cannot build without it.** All frontend changes in this report follow existing import conventions but are **unverified**: `node_modules` is also absent, so vitest cannot run here.

---

## Issue 2 — The unbiased held-out evaluation is unfinished · **Closed** *(2026-09-22)*

The returned sheet `holdout_adjudication_sheet_completed.csv` was checked before import: 133 of 133 rows decided, no blanks, and no edits to `segment_id`, `field`, either annotator column, the transcript or the codebook rule. **All 132 segments entered gold — nothing was lost to an undecided row.**

### Pipeline run

```
import_adjudication_sheet  → holdout_adjudications.json   (133 decisions)
adjudicate                 → gold_holdout_labels.json     (132/132 segments)
score_against_gold         → scored_holdout.json          (4 generators)
holdout_metrics            → holdout_metrics.json         (batch vs held-out)
```

`gold_labels.json` was verified byte-identical before and after.

### Result: the selection effect, measured

Mean accuracy over the four categorical fields, same gold-building procedure, same scoring policy on both sides:

| Generator | Batch (n=330) | Held-out (n=132) | Change |
|---|---|---|---|
| llama3.2:latest | 30.8% | 26.5% | −4.3 |
| qwen2.5:3b | 20.4% | 12.5% | −8.0 |
| qwen2.5:7b | 43.1% | **38.8%** | −4.3 |
| qwen3:14b | 42.0% | 40.2% | −1.9 |

Every generator is worse on segments not selected for model tractability. Uniform direction across all four is what a selection effect predicts and a chance difference does not.

Unsupported assertion, by contrast, **does not improve**: 92.1% for qwen3:14b on held-out against 97.0% on the batch, still the highest in the roster. The paper's central safety finding survives the move to an unbiased sample — accuracy degrades when segments stop being easy, the propensity to assert unsupported values does not.

Whole-record: held-out best 4.5%, ceiling 6.1%, headroom 1.5 points (four-generator batch: 4.5% / 8.8% / 4.2%).

### A scoring-policy mismatch, caught before it reached the manuscript

The first held-out scoring run used the tool's default `--behavior-match overlap` (five fields). The published batch policy is `excluded` (four categorical fields). Mean accuracy over four fields and over five are different quantities, and subtracting one from the other yields a plausible number with no meaning — it would have understated the held-out side and **inflated the reported selection effect**. Nothing downstream would have revealed it.

Held-out was re-scored under the published policy, and `holdout_metrics.check_same_policy` now refuses the comparison outright when `scoring_fields`, `behavior_match` or `behavior_overlap_threshold` differ.

### Adjudication was not balanced on this round

| Rows | A adopted | B adopted | Exact binomial p |
|---|---|---|---|
| All 133 | 54 | 79 | 0.037 |
| 17 genuine categorical judgements | 4 | 13 | 0.049 |
| 14 codebook-settled | 5 | 9 | 0.424 |
| 102 behavior wording | 45 | 57 | 0.276 |

The main batch split 89/90. The claim that neither annotator dominated holds for the batch and **not** for the held-out round. With 17 decisions the second figure is fragile, but it is now stated in Limitations rather than omitted.

### Also changed

- `tests/eval/extraction/holdout_metrics.py` — new; pairs the two sides. Reuses `summarise_scored`, which was extracted from `paper_metrics.augmented_block` so the two report identical quantities and cannot drift.
- Manuscript — new Results subsection "Accuracy on the held-out set" (two tables); held-out findings added to the Abstract and Discussion; the "Not measured" entry deleted; the Limitations entry rewritten from "pending adjudication" to a measured margin; adjudication-balance limitation added.
- `TestHeldOutResultsAreReported` (5 tests) — the successor to `test_holdout_accuracy_is_not_claimed_without_gold`, which retired itself the moment gold appeared. The new class catches the opposite failure: gold exists, numbers exist, prose still says pending. It also re-derives every quoted delta from the artefact and fails if the deltas stop being uniformly negative, since that would falsify the sentence in the manuscript.
- Five new artefacts pinned by checksum (38 total).

---

## Issue 3 — Evaluation data does not match the intended input distribution · **Closed**

The manuscript now states the relationship explicitly in Methods rather than leaving it to a Limitations bullet. The evaluated data differs from the application's intended input in three respects, each of which could affect extraction:

- **Authorship** — a transcript records what was said, not what an observer chose to report.
- **Register** — a contributor writes retrospective prose about a child; a transcript is verbatim dialogue.
- **Provenance** — a contributor writes with a goal in mind; a transcript has no such framing.

Added: a Methods paragraph stating the proxy relationship and why these corpora were chosen (autism interaction data, permissive research access, enough structure to annotate consistently; no corpus of real intervention notes is publicly available); a statement that every extraction result is a component evaluation on proxy data; the sentence "**Extraction is not validated on real intervention notes**" in Limitations; matching qualifiers in the Abstract (Methods and Conclusions) and in the Discussion conclusions; a "Not measured" entry.

---

## Issue 4 — The reporting LLM failed its own governance contract · **Closed**

Option (b) was chosen: keep the generative layer experimental, make the deterministic reporter operational.

### The rationale

All 11 evaluated reports were structurally conformant and contained no prohibited diagnostic, treatment, causal or prognostic content — but **0 of 11 passed governance validation**, because analyses the adequacy router had withheld were not acknowledged as withheld. The model did not fabricate them; it silently omitted their absence. A reader cannot distinguish a deliberately withheld analysis from one never attempted.

A component that fails its own governance test does not belong in the operational path.

### What changed

- **`src/backend/config.py`** — new `reporting_mode: Literal["deterministic", "generative_experimental"] = "deterministic"`.
- **`src/backend/ml/reporting_client.py`** — `generate_report()` is now mode-aware. In the default mode the LLM is **never called**. The template builder was renamed throughout from `_build_fallback_sections` to `_build_deterministic_sections` (and its helpers `_fallback_*` → `_deterministic_*`): it is the operational reporter now, not only an error path.
- **Provenance changed** from `deterministic_fallback` / `deterministic_fallback_v1` to `deterministic` / `deterministic_reporter_v1`.
- **`src/backend/ml/schemas.py`** — `GeneratedReportData.is_experimental`.
- **`src/backend/schemas/api_schemas.py`** — `ReportResponse.is_experimental` as a `@computed_field` derived from the stored provider, so it cannot drift from what actually produced the prose. No new column, no migration.
- **`ReportViewer.tsx`** — the amber banner now reads "**Experimental AI Draft** … not an operational report", replacing "AI-Generated Draft", which reads as a routine provenance note rather than a warning.

A failed generative call still falls back to the deterministic reporter, and the result is then labelled **deterministic, not experimental** — because that is what produced it.

### Tests

- `tests/phase4/test_reporting_client.py` — new `TestOperationalReportingMode` (5 tests): default mode is deterministic; the default never awaits `_call_llm`; the deterministic reporter passes `validate_report()` (it names every withheld indicator — the check the generative layer failed); generative output is marked experimental; a failed generative call drops the marker.
- 28 existing tests updated — every test that exercises the LLM now has to ask for `mode="generative_experimental"` explicitly.

### Documentation

- `docs/lld/Reporting_Llm.md` — new "Reporting Modes" section; generation flow rewritten.
- `docs/lld/Reporting_Llm_Specs.md` — new **REPORT-005** (deterministic default) and **REPORT-006** (`is_experimental` marker); REPORT-011 updated.
- `docs/User_and_Demo_Manual.md` — the two paths reordered and relabelled; the "Report Generation Uses Fallback" troubleshooting entry rewritten, since deterministic output is now the expected default rather than a missing-API-key symptom.
- `tests/eval/reporting/groundedness.py` — accepts both provider strings so recorded runs still parse.
- Manuscript: the negative result **stands as reported**. The layer was not modified and re-evaluated; it was removed from the operational path. A new Limitations entry records that remediability was not tested.

---

## Issue 5 — Ethics/IRB status must cover more than the public corpus · **Partially addressed**

The determination itself is external and still outstanding. What could be done here was the wording, and it needed doing: the ethics section contained an overclaim.

The Ethical considerations section said:

> "No data was collected from human participants for this work, no participants were recruited or contacted…"

Two autism intervention specialists produced the annotations, and their agreement with one another — **including how it changed between rounds** — is analysed and reported. That is human-generated research data, and the sentence as written could be read as denying it. This sits directly under reviewer issue #5.

Corrected to "no **child** data was collected", with a new paragraph stating that the specialists' labels are research data about a coding scheme rather than about the annotators, that no individual annotator is identified or characterised by performance, and that whether this makes them research participants, expert consultants or neither is **a determination for the reviewing institution rather than for the authors** — put to the Board explicitly rather than assumed. The IRB placeholder now requires the determination to address all three categories separately: archival child corpora, specialist annotation and adjudication, and human involvement in application testing.

**Still required before submission:** the determination as issued, with institution, exact wording and protocol number, addressing all three categories separately — the archival child corpora, the specialist annotation and adjudication, and any human involvement in application testing. Also the licence terms of both corpora and the scope of depositor consent for secondary computational analysis.

---

## Issue 6 — Eight fields generated, five evaluated · **Closed**

### Verified before writing

The extractor is asked for eight fields. Five were scored against the adjudicated gold standard (`behavior`, `domain`, `modality`, `prompt_level`, `outcome`). Three have no reference standard in this study: `goal_context`, `prompt_context`, `duration_seconds`.

Checking the code rather than assuming: **the three unevaluated fields are read by no KPI, no adequacy check, and no deterministic report section.** `analytics_engine.py` uses the five; `adequacy_router.py` uses three of them; neither touches the unevaluated three. The reviewer's third option ("ensure they cannot influence analytics without explicit professional verification") is satisfied, and more strongly than asked.

### One exception, stated rather than papered over

`analytics_service._record_to_dict()` passes the **whole** `record_data` into the `EvidencePacket`. The three unevaluated fields therefore reach the reporting layer. The operational deterministic reporter never renders them — it builds prose from KPIs and packet-level counts — but the **experimental generative reporter can see them**. This is now stated in the manuscript as a further reason that path is not operational. Behaviour was left unchanged rather than silently stripping fields from the packet.

### What changed

- Manuscript: a paragraph opening "Extraction accuracy" stating 8 generated / 5 evaluated and that **the extractor as a whole is not evaluated**; a second paragraph confining the three; a Limitations entry; a "Not measured" entry.
- `tests/phase4/test_unevaluated_fields.py` *(new file, 20 tests)* — asserts no unevaluated field name appears in the source of `analytics_engine`, `adequacy_router`, `forecasting_engine`, `analytics_service` or `reporting_client`, and the converse for the five evaluated fields, so evaluation scope and analytics scope cannot drift apart.

---

## Issue 7 — Adequacy thresholds are not clinically validated · **Closed**

The claim attached to the thresholds is now that withholding is **deterministic, inspectable and auditable** — not that these are the numbers at which evidence becomes clinically sufficient. No expert-consensus procedure set them, no sensitivity analysis has been run, and no outcome has been measured against them.

Stated in four places, so the framing cannot be met in one and contradicted in another:

- Manuscript — new Discussion subsection *"The status of the governance thresholds"*, plus a Limitations entry and a "Not measured" entry for threshold sensitivity.
- `docs/lld/Adequacy_Router.md` — above the thresholds table.
- `src/backend/config.py` — at the point of definition.
- `docs/User_and_Demo_Manual.md` — where a reader first meets the adequacy levels.

---

## Issue 8 — Gold-standard expert description needs more detail · **Scaffolded**

New Methods section *"Annotators"* in two halves.

**What I need from you** (marked `[TO COMPLETE BEFORE SUBMISSION]`), per annotator: professional role and qualification; years of relevant experience; prior experience with structured behavioural coding; what preparation they received and from whom; any relationship to the study or authors bearing on independence.

**What the artefacts already establish** — verified against the files, not asserted:

| Claim | Verified |
|---|---|
| Both annotated the full main batch | `gold_annotator_a.json` 330, `gold_annotator_b.json` 330 |
| Both annotated the full held-out set | `gold_holdout_annotator_a.json` 132, `gold_holdout_annotator_b.json` 132 |
| Conflicts adjudicated jointly, 89/90 split | Already reported; neither annotator dominated |

The same pair helped identify the three underspecified definitions and then annotated under the codebook resolving them — recorded as a limitation, not presented as independence. Three tests read the counts from the artefacts and fail if the prose and the files disagree.

---

## Issue 9 — The manuscript risks becoming a 'kitchen-sink' paper · **Closed**

Per your decision, **the evaluation framework is the primary contribution.** The four elements are now enumerated in the Introduction, each tied to a question a conventional accuracy report leaves open:

1. **Explicit-null annotation** — without a gold null there is no opportunity against which to count an invented value.
2. **Controlled codebook revision** — an untreated control field separates the codebook's effect from the effect of re-annotating.
3. **Oracle-bounded selection analysis** — what *any* selector could have recovered, before what a particular selector did, plus a model-independent held-out set quantifying how far the batch was conditioned on model behaviour.
4. **Governance check separate from schema conformance** — prohibited content, numeric grounding, and preservation of abstention state.

Everything else is explicitly subordinated: the annotation scheme, the four generators, the reranking stage and the reporting layer are "**the objects measured, not parallel contributions**"; the application is the setting that motivates the measurements.

Carried through the Abstract conclusion, the Discussion, and the Conclusions ("The framework is the contribution; the pipeline is the specimen"). Conclusions now report failure at **three** layers rather than two, adding the reporting layer.

**Title changed** — flagged for your approval:

> *A Governance-Aware Evaluation Framework for Language-Model Extraction in Autism Intervention Monitoring: Annotation Reliability, Unsupported Inference, Multi-Model Selection, and Reporting Governance*

(previously "Governance-Aware Extraction of Structured Autism Observations: …"). Revert if you prefer the original.

---

## Issue 10 — No independent usability/workflow evaluation · **Closed** (bounded)

Searched for demonstrated-benefit language rather than assuming none existed: no such claim was present. Added explicitly:

- Limitations: no independent professional evaluated the integrated application; development testing shows it functions, not that interventionists can use it effectively, that it reduces review burden, or that it improves recognition of missing evidence rather than inducing automation bias. "Every benefit attributed to the workflow in this paper is **intended or potential, never demonstrated**."
- In the verification-gate subsection: the gate is a design property enforced in code, **not** a demonstration that interventionists catch model errors. Automation bias is named as the evaluation the gate most needs next.
- Two "Not measured" entries.
- A test fails if phrases like "reduces review burden" or "saves time" ever appear in the prose.

---

## Issue 11 — Reproducibility and data-release details · **Open**

Blocked on decisions only you can make: repository or archive URL, release tag, licence, and exactly which artefacts may be redistributed under TalkBank/ASDBank terms.

What exists already and does not need redoing: 61 artefacts recorded, 38 pinned by SHA-256 (`docs/paper/artifact_manifest.json`), a full reproduction sequence in `docs/paper/artifacts.md`, seeds and runtime versions documented in clarification answer Q20, and a stated reproducibility boundary — everything downstream of the recorded generator outputs is deterministic; regenerating those outputs is not, because no generation seed was set.

The `Data availability` section of the manuscript carries a `[TO COMPLETE BEFORE SUBMISSION]` marker naming exactly these decisions.

---

## Issue 12 — Generative-AI disclosure and citation audit · **Partially drafted**

The AI-use disclosure is written and is honest about the dual role: the extraction and judge models are the object of study, and AI assistance was also used for evaluation tooling and manuscript drafting. It states that no AI system authored, selected or altered a gold-standard value, an adjudication decision or a reported statistic — every annotation and adjudication is human, statistics are computed by code from recorded artefacts, and tests re-derive each reported number from its artefact.

**Blocked:** the citation audit cannot begin, because no reference list exists yet (see *Still open*). Author contributions and conflict-of-interest declarations are also unwritten.

**Note if a frontier arm is added:** benchmarking Claude models in a manuscript drafted with Claude Code has to be stated plainly in this section. It is not disqualifying; it has to be visible.

---

## Appendix A — Clarification-questions coverage audit *(2026-09-22)*

`JMIR_AI_Model_Reranking_Clarification_Questions.docx` asks 20 questions in five
sections. **All 20 are answered** in `docs/paper/clarification_answers.md`, and
a follow-up round of 8 is answered in `docs/paper/clarification_answers_round2.md`.

| Section | Questions | Status |
|---|---|---|
| A. Model use and inference configuration | 1–3 | Answered |
| B. Extraction prompt, schema, admission logic | 4–8 | Answered |
| C. MARS multi-judge reranking | 9–15 | Answered (Q15 premise corrected) |
| D. Reporting LLM and governance validation | 16–18 | Answered (Q16 status updated) |
| E. Learning boundary and reproducibility | 19–20 | Answered (Q20 refreshed) |

Three of the answers **correct the premise of the question** rather than
confirming it, which is the part most likely to matter to a reviewer:

- **Q15** asked us to confirm that all four generators are integrated into the
  application. They are not. The deployed default is one provider
  (`llama3.2:latest`), and the MARS composing provider is not reachable from the
  factory.
- **Round-2 Q6** asked whether the application runs a multi-candidate roster.
  It does not.
- **Round-2 Q7** asked about reporting remediation. None was performed; the
  negative result stands with no post-remediation counterpart.

### What this audit found: four answers had gone stale

The answer sheets are written prose, not generated from artefacts, so this
session's work invalidated claims in them without anything failing:

| Answer | Was | Now |
|---|---|---|
| Round-2 **Q3** | "Adjudication is not complete. No held-out gold standard exists" | Complete. Full results table, whole-record figures, and the adjudication-balance caveat |
| Round-2 **Q6** | Extraction path only | Adds the analytics verification gate and the deterministic reporting default |
| Round-2 **Q7** | "No remediation, no rerun" | Still true, plus: the layer was removed from the operational path — a *deployment decision, not a remediation*, and the distinction is stated |
| Round-1 **Q15** | "should be stated only if verified" | Resolved: not integrated, and a test now asserts it |
| Round-1 **Q16** | Reporting config | Status note: config unchanged, but the layer is no longer operational |
| Round-1 **Q20** | 51 artefacts, 33 pinned | 56 artefacts, 38 pinned; held-out paths added; commit provenance clarified |

Superseded text was **kept** under its own heading rather than overwritten,
because an answer given when a result did not exist is itself a record of what
was known when the question was asked.

### Guard added

`tests/eval/extraction/test_clarification_answers.py` (9 tests) checks that both
sheets answer every question, and that the claims they make about the running
system still hold: the deployed model name matches `settings.ollama_model`, the
reporting default matches `settings.reporting_mode`, the verification gate is
described, MARS is still stated as unreachable, and the held-out answer matches
whether `gold_holdout_labels.json` actually exists. The manifest counts quoted in
Q20 are re-derived from the manifest.

---

## Appendix B — Manuscript consistency tests

`tests/eval/extraction/test_manuscript_consistency.py` grew by 18 tests across four new classes, each guarding a claim that is a one-edit slip away from becoming false:

- `TestContributionHierarchy` (5) — the primary contribution is named, others subordinated, title and abstract agree, conclusions restate it.
- `TestGovernanceBoundaries` (4) — the gate is stated in prose **and** enforced in `analytics_service`; generative reporting declared experimental in prose **and** `reporting_mode` defaults to deterministic in config.
- `TestScopeOfTheClaims` (6) — proxy framing, no validation claim on intervention notes, the 8-vs-5 field count, thresholds not called clinical cutoffs, benefit claims marked undemonstrated, no bare benefit claim anywhere.
- `TestAnnotatorClaims` (3) — coverage counts re-derived from artefacts; the credentials gap is flagged rather than invented.

Two pre-existing failures in this file were also repaired: `TestDeploymentScope` asserted literal strings from a superseded draft ("evaluated offline", "offline experiment, not a deployed component") that no longer appeared in the manuscript. The assertions were re-pointed at the current, stronger wording ("MARS is an evaluation method, not a deployed component", "not intended for the application's request path"). **The manuscript's meaning was not weakened to make tests pass.**

---

## Still open

| # | Item | Blocked on |
|---|---|---|
| 5 | IRB determination | External. Must cover corpus, specialists, and application testers separately |
| 8 | Annotator credentials | You — five facts listed under Issue 8 |
| 11 | Repo URL, release tag, licence, TalkBank redistribution scope | Your decisions |
| — | "Comparison with prior work" | 14 claims need citation; section unwritten |
| 12 | Citation audit | Cannot start until References exists. The AI-use disclosure itself is drafted and honest |
| — | `src/frontend/lib/` | Must be restored before the frontend builds (Issue 1 §a) |

Six `[TO COMPLETE BEFORE SUBMISSION]` markers remain in `make_manuscript.py`: Annotators, Ethics/IRB, Comparison with prior work, Data availability, Author contributions/COI, References.

---

## Files changed

**New (4)**

```
alembic/versions/004_add_verified_record_status.py
src/frontend/components/records/VerificationPanel.tsx
tests/phase4/test_analytics_gate.py
tests/phase4/test_unevaluated_fields.py
```

**Modified (28)** — backend: `api/structured_records.py`, `config.py`, `ml/reporting_client.py`, `ml/schemas.py`, `models/observation.py`, `schemas/api_schemas.py`, `services/analytics_service.py`, `services/observation_service.py` · frontend: `ReportViewer.tsx`, `StructuredRecordView.tsx`, record detail page, 2 test files · tests: `phase3/conftest.py`, `phase3/test_observation_service.py`, `phase3/test_structured_records.py`, `phase4/test_reporting_client.py`, `eval/extraction/test_manuscript_consistency.py`, `eval/reporting/groundedness.py` · docs: `make_manuscript.py`, `make_figures.py`, `Manuscript_Working_Draft.docx`, `fig23_architecture_mars.png`, `User_and_Demo_Manual.md`, `lld/Adequacy_Router.md`, `lld/Reporting_Llm.md`, `lld/Reporting_Llm_Specs.md` · `.gitignore`

Net: **+1219 / −186** lines across 32 files.

---

## Verification

```
uv run pytest tests/ -q --ignore=tests/phase6/integration
# 1319 passed, 4 skipped

uv run python docs/paper/verify_artifacts.py
# Checked 38 pinned artefacts against docs/paper/artifact_manifest.json
# All pinned artefacts match the manifest.

uv run python docs/paper/make_manuscript.py
# Wrote docs/paper/Manuscript_Working_Draft.docx
```

`ruff` introduced no new findings: the changed files carry the same counts as at HEAD (the repository has 237 pre-existing style findings, untouched).

**Not verified:** all frontend changes. `src/frontend/lib/` and `node_modules` are both absent, so neither `tsc` nor `vitest` can run here.
