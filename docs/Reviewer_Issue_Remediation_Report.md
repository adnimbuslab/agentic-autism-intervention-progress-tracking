# Reviewer Issue Remediation Report

**Scope:** work done against `JMIR_Strict_Reviewer_Critical_Issues_Prioritized.docx`
**Branch:** `model-finetuning`
**Date:** 2026-09-21
**Test suite at close:** 1306 passed, 3 skipped (66 tests added this round)
**Artefact manifest:** 33 pinned artefacts, all matching

---

## Summary

| # | Issue | Status | Where it was fixed |
|---|---|---|---|
| 1 | Unverified AI output reaching longitudinal analytics | **Closed** | Code + migration + figure + manuscript |
| 3 | ASDBank does not match the intended input distribution | **Closed** (reframed) | Manuscript |
| 4 | Reporting LLM failed its own governance contract | **Closed** (option b) | Code + docs + manuscript |
| 6 | 8 fields generated, only 5 evaluated | **Closed** | Verified in code, pinned by tests, stated in manuscript |
| 7 | Adequacy thresholds not clinically validated | **Closed** (relabelled) | Manuscript + LLD + config + manual |
| 9 | Kitchen-sink paper — no single primary contribution | **Closed** | Manuscript, title through conclusions |
| 10 | No independent usability/workflow evaluation | **Closed** (bounded) | Manuscript |
| 5 | Ethics/IRB determination | **Partially addressed** — wording corrected, determination still external |
| 8 | Annotator qualifications | **Scaffolded** — verifiable part done, credentials needed from you |
| 2 | Held-out adjudication unfinished | **Open** — needs your annotators |
| 11 | Reproducibility / release placeholders | **Open** — needs your decisions |
| 12 | Generative-AI disclosure and citation audit | **Partially drafted** — blocked on References |

Two problems were found during the work that the reviewer had not flagged. Both are recorded in full below (§1.1, §5.1).

---

## 1. Verification gate (Issue #1) — **Closed**

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

### 1.1 Found during this work — frontend `lib/` is missing

`.gitignore` line 17 carried an unanchored `lib/` from the standard Python template. It was silently ignoring `src/frontend/lib/` — the API client, hooks (`useRecords`), types, and formatters that **every** page and component imports. The directory is absent from git *and* from disk.

Fixed the pattern (`/lib/`, `/lib64/`) so the directory can be committed. **The directory itself still has to be restored — the frontend cannot build without it.** All frontend changes in this report follow existing import conventions but are **unverified**: `node_modules` is also absent, so vitest cannot run here.

---

## 2. Reporting layer declared experimental (Issue #4) — **Closed**

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

## 3. ASDBank reframed as proxy evaluation (Issue #3) — **Closed**

The manuscript now states the relationship explicitly in Methods rather than leaving it to a Limitations bullet. The evaluated data differs from the application's intended input in three respects, each of which could affect extraction:

- **Authorship** — a transcript records what was said, not what an observer chose to report.
- **Register** — a contributor writes retrospective prose about a child; a transcript is verbatim dialogue.
- **Provenance** — a contributor writes with a goal in mind; a transcript has no such framing.

Added: a Methods paragraph stating the proxy relationship and why these corpora were chosen (autism interaction data, permissive research access, enough structure to annotate consistently; no corpus of real intervention notes is publicly available); a statement that every extraction result is a component evaluation on proxy data; the sentence "**Extraction is not validated on real intervention notes**" in Limitations; matching qualifiers in the Abstract (Methods and Conclusions) and in the Discussion conclusions; a "Not measured" entry.

---

## 4. Five of eight fields (Issue #6) — **Closed**

### Verified before writing

The extractor is asked for eight fields. Five were scored against the adjudicated gold standard (`behavior`, `domain`, `modality`, `prompt_level`, `outcome`). Three have no reference standard in this study: `goal_context`, `prompt_context`, `duration_seconds`.

Checking the code rather than assuming: **the three unevaluated fields are read by no KPI, no adequacy check, and no deterministic report section.** `analytics_engine.py` uses the five; `adequacy_router.py` uses three of them; neither touches the unevaluated three. The reviewer's third option ("ensure they cannot influence analytics without explicit professional verification") is satisfied, and more strongly than asked.

### One exception, stated rather than papered over

`analytics_service._record_to_dict()` passes the **whole** `record_data` into the `EvidencePacket`. The three unevaluated fields therefore reach the reporting layer. The operational deterministic reporter never renders them — it builds prose from KPIs and packet-level counts — but the **experimental generative reporter can see them**. This is now stated in the manuscript as a further reason that path is not operational. Behaviour was left unchanged rather than silently stripping fields from the packet.

### What changed

- Manuscript: a paragraph opening "Extraction accuracy" stating 8 generated / 5 evaluated and that **the extractor as a whole is not evaluated**; a second paragraph confining the three; a Limitations entry; a "Not measured" entry.
- `tests/phase4/test_unevaluated_fields.py` *(new file, 20 tests)* — asserts no unevaluated field name appears in the source of `analytics_engine`, `adequacy_router`, `forecasting_engine`, `analytics_service` or `reporting_client`, and the converse for the five evaluated fields, so evaluation scope and analytics scope cannot drift apart.

---

## 5. Adequacy thresholds relabelled (Issue #7) — **Closed**

The claim attached to the thresholds is now that withholding is **deterministic, inspectable and auditable** — not that these are the numbers at which evidence becomes clinically sufficient. No expert-consensus procedure set them, no sensitivity analysis has been run, and no outcome has been measured against them.

Stated in four places, so the framing cannot be met in one and contradicted in another:

- Manuscript — new Discussion subsection *"The status of the governance thresholds"*, plus a Limitations entry and a "Not measured" entry for threshold sensitivity.
- `docs/lld/Adequacy_Router.md` — above the thresholds table.
- `src/backend/config.py` — at the point of definition.
- `docs/User_and_Demo_Manual.md` — where a reader first meets the adequacy levels.

### 5.1 Found during this work — an overclaim in the ethics section

The Ethical considerations section said:

> "No data was collected from human participants for this work, no participants were recruited or contacted…"

Two autism intervention specialists produced the annotations, and their agreement with one another — **including how it changed between rounds** — is analysed and reported. That is human-generated research data, and the sentence as written could be read as denying it. This sits directly under reviewer issue #5.

Corrected to "no **child** data was collected", with a new paragraph stating that the specialists' labels are research data about a coding scheme rather than about the annotators, that no individual annotator is identified or characterised by performance, and that whether this makes them research participants, expert consultants or neither is **a determination for the reviewing institution rather than for the authors** — put to the Board explicitly rather than assumed. The IRB placeholder now requires the determination to address all three categories separately: archival child corpora, specialist annotation and adjudication, and human involvement in application testing.

---

## 6. Contribution hierarchy (Issue #9) — **Closed**

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

## 7. Usability claims bounded (Issue #10) — **Closed**

Searched for demonstrated-benefit language rather than assuming none existed: no such claim was present. Added explicitly:

- Limitations: no independent professional evaluated the integrated application; development testing shows it functions, not that interventionists can use it effectively, that it reduces review burden, or that it improves recognition of missing evidence rather than inducing automation bias. "Every benefit attributed to the workflow in this paper is **intended or potential, never demonstrated**."
- In the verification-gate subsection: the gate is a design property enforced in code, **not** a demonstration that interventionists catch model errors. Automation bias is named as the evaluation the gate most needs next.
- Two "Not measured" entries.
- A test fails if phrases like "reduces review burden" or "saves time" ever appear in the prose.

---

## 8. Annotator qualifications (Issue #8) — **Scaffolded**

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

## Manuscript consistency tests

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
| 2 | Held-out adjudication — 133 conflicting fields | Your annotators. **Highest-value remaining item**: data and generator runs already exist |
| 5 | IRB determination | External. Must cover corpus, specialists, and application testers separately |
| 8 | Annotator credentials | You — five facts listed in §8 |
| 11 | Repo URL, release tag, licence, TalkBank redistribution scope | Your decisions |
| — | "Comparison with prior work" | 14 claims need citation; section unwritten |
| 12 | Citation audit | Cannot start until References exists. The AI-use disclosure itself is drafted and honest |
| — | `src/frontend/lib/` | Must be restored before the frontend builds (§1.1) |

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
# 1306 passed, 3 skipped

uv run python docs/paper/verify_artifacts.py
# Checked 33 pinned artefacts against docs/paper/artifact_manifest.json
# All pinned artefacts match the manifest.

uv run python docs/paper/make_manuscript.py
# Wrote docs/paper/Manuscript_Working_Draft.docx
```

`ruff` introduced no new findings: the changed files carry the same counts as at HEAD (the repository has 237 pre-existing style findings, untouched).

**Not verified:** all frontend changes. `src/frontend/lib/` and `node_modules` are both absent, so neither `tsc` nor `vitest` can run here.
