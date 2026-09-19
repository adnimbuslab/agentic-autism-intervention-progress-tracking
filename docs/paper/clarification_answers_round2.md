# Answers: Follow-up Clarification Questions (round 2)

Same format as round 1 (`clarification_answers.md`): **Answer** with the
repository path, then **In plain terms**.

Recorded state: commit `6163d13`, 2026-09-19.

**Three answers correct a premise or report a negative rather than a fact.**
**Q3** — held-out adjudication is *not* complete, so no held-out results exist.
**Q6** — the application default is **one** generator, not four, and MARS is not
in the default path; this corrects the premise of round-1 Q15 as well.
**Q7** — the governance failure was **not** remediated and the experiment was
**not** rerun; the negative result stands as reported.

---

## Q1 — Exact extracted-field list

**Answer.** Three distinct field sets, defined in
`src/backend/schemas/observation_schema.py` and
`src/backend/ml/extraction/mars/safety.py`. The apparent mismatch between round-1
Q5 and Q8 is real and intentional: **8 fields exist in the schema; 5 are
annotated and scored.**

**`LLM_EXTRACTED_FIELDS` (8)** — everything the model is asked to produce, and
the exact set the deduplication fingerprint covers (`FINGERPRINT_FIELDS` is this
set, sorted):

| # | Field | Annotated & scored? |
|---|---|---|
| 1 | `behavior` | yes (free text) |
| 2 | `domain` | yes (categorical) |
| 3 | `duration_seconds` | **no** |
| 4 | `goal_context` | **no** |
| 5 | `modality` | yes (categorical) |
| 6 | `outcome` | yes (categorical) |
| 7 | `prompt_context` | **no** |
| 8 | `prompt_level` | yes (categorical) |

The three unscored fields — `goal_context`, `prompt_context`, `duration_seconds`
— were not recorded in the annotation batch and replay as `None` everywhere
downstream. **This has a consequence that is already reported in the
manuscript's limitations:** two responses differing *only* on an unrecorded
field fingerprint as identical, so `single_candidate` counts are an upper bound
and `rerank_required` counts a lower bound. Because every observed
short-circuit had multiplicity 1, this does not affect the finding that no two
generators ever produced an identical extraction.

**`APP_KNOWN_FIELDS` (5)** — passed into the request, never model-generated:
`child_id`, `contributor_role`, `observation_date`, `session_id`, `setting`.

**`MARS_INTEGRITY_FIELDS` (13)** — the union of the two sets above, sorted;
used by the integrity check to verify the returned record is one whole
candidate rather than a field-wise blend:

`behavior`, `child_id`, `contributor_role`, `domain`, `duration_seconds`,
`goal_context`, `modality`, `observation_date`, `outcome`, `prompt_context`,
`prompt_level`, `session_id`, `setting`

The integrity set is deliberately broader than the fingerprint set: dedup asks
"did two generators produce the same extracted content?", integrity asks "is
this one intact record?" — and a blend that preserved the extracted fields while
corrupting the identity fields would pass the first and must fail the second.

**In plain terms.** The model is asked for 8 things; the study grades 5 of them.
The other 3 were never collected, so they are blank everywhere. A separate,
longer list of 13 is used for a different purpose: checking that the record
handed back is one complete answer rather than pieces of several stitched
together — which needs to include who and when, not just what.

---

## Q2 — Canonical outcome label

**Answer.** The canonical value is **`partial`**. Not `partial_success`, not any
variant. Source of truth: `Outcome` in
`src/backend/schemas/observation_schema.py`.

Full enumeration, exactly as stored and scored:

`correct` · `incorrect` · `approximation` · `no_response` · `partial` · `unknown`

Plus JSON `null`, which is a distinct state meaning "the transcript supports no
value here" — not a member of the enum.

This is the string used in the database, in the annotation sheets
(`VALUE_REFERENCE.csv` is generated from the enum, not typed separately), in the
codebook, in the extraction tool schema, and in every scoring artefact. The
manuscript should use `partial` throughout.

**In plain terms.** One word, `partial`. The annotation sheets, the code, and
the answer key all get it from the same place, so they cannot drift apart. There
is no `partial_success` anywhere.

---

## Q3 — 132-segment held-out set

**Answer.** **Adjudication is not complete.** No held-out gold standard exists,
so none of the requested results — field-level accuracy, unsupported-assertion
rate, whole-record accuracy — can be reported.

What *is* complete:

- **Annotation:** both annotators, 132/132 segments, no empty cells, no cell
  errors. Artefacts `gold_holdout_annotator_{a,b}.json`.
- **Generator runs:** all four, 132/132 each, recorded in `holdout_batch.json`.
- **Reliability:** mean κ 0.910 (`reliability_holdout.json`).

What remains: **133 conflicting fields across 105 segments** await adjudication
(`annotation_sheets/holdout_adjudication_sheet.csv`). Of those, 102 are
free-text `behavior` wording differences, 14 are settled by an existing codebook
rule, and **17 are genuine judgement calls** — 12 `domain`, 2 `modality`,
2 `outcome`, 1 `prompt_level`.

**One held-out comparison is already available, because it needs no gold
standard** — generator admission rates on the model-conditioned batch versus the
unbiased sample:

| Generator | Admitted, batch (330) | Admitted, held-out (132) | Change |
|---|---:|---:|---:|
| llama3.2 | 40.3% | 31.8% | −8.5 |
| qwen2.5:3b | 30.6% | 16.7% | −13.9 |
| qwen2.5:7b | 78.8% | 78.0% | −0.8 |
| qwen3:14b | 98.5% | 98.5% | +0.0 |
| **All four jointly admissible** | **41/330 (12.4%)** | **3/132 (2.3%)** | **−10.2** |

That fivefold drop in joint admissibility is a direct measure of how much easier
the evaluated segments were.

**In plain terms.** The two annotators have finished; the models have all been
run; what is missing is one person settling 133 disagreements — of which only 17
need real thought. Until that happens there is no answer key for these segments,
so we cannot say how accurate the models were on them. We *can* already say the
unbiased segments are much harder: all four models manage a usable answer on
only 2.3% of them, against 12.4% of the original set.

---

## Q4 — AdequacyRouter rules

**Answer.** `src/backend/ml/adequacy_router.py`. Six deterministic checks run
on every review period; their results plus the record count determine one of
three levels.

**Configuration values** (`src/backend/config.py`):

| Setting | Value | Meaning |
|---|---|---|
| `adequacy_min_observations` | 5 | records required for `adequate` |
| `adequacy_limited_observations` | 3 | below this, a critical failure means `insufficient` |
| `adequacy_field_completeness_threshold` | 0.7 | required populated-field ratio |
| `adequacy_temporal_cluster_max_ratio` | 0.8 | above this share in one cluster, timeliness fails |

**The six checks:** coverage (record count against expected or the minimum),
temporal distribution (records not clustered in time; requires ≥2 records),
contributor representation (passes at ≥2 distinct contributor roles), setting
representation (passes at ≥2 distinct settings), goal coverage (passes at ≥0.5
of active goals observed), field completeness (against the 0.7 threshold).

**Level assignment** (`_compute_level`), evaluated in this order:

1. 0 records → `insufficient`.
2. A **critical** check failed — coverage or field completeness — and fewer than
   3 records → `insufficient`; otherwise → `limited`.
3. More than 2 checks failed → `limited`.
4. Fewer than 3 records → `limited`.
5. At least 5 records and **no** failed checks → `adequate`.
6. Otherwise → `limited`.

**Abstention consequences.** `eligible = level != insufficient`. At
`insufficient`, the AnalyticsEngine returns a single `all_analytics` KPI marked
abstained with the level as its reason — **full abstention**. At `adequate` or
`limited`, analytics run and individual KPIs abstain on their own prerequisites
— **partial abstention**. Every failed check is also recorded as a quality flag
carried in the evidence packet.

**In the 11-child reporting evaluation:** all 11 children were assessed
`limited` — driven by single-contributor and single-setting representation,
which follows from how the evaluation's app-known metadata was derived (one
corpus per child). Analytics therefore ran, with partial abstention.

**In plain terms.** Six automatic checks ask whether there is enough evidence,
spread over enough time, people and settings, with enough fields filled in. Two
of them are treated as critical. The result is one of three verdicts. "Not
enough" switches all statistics off; "limited" lets them run but individual
numbers can still be withheld. All eleven children in the reporting study came
out "limited".

---

## Q5 — AnalyticsEngine definitions

**Answer.** `src/backend/ml/analytics_engine.py`. Every KPI is computed by code,
never by a model. Each `KpiResult` carries `name`, `numerator`, `denominator`,
`value`, `prerequisites_met`, `display_eligible`, `abstained`,
`abstention_reason`.

**KPIs produced, and their status in the 11-child evaluation:**

| KPI | Computed / withheld (of 11) |
|---|---|
| `observation_count` | 11 / 0 |
| `domain_distribution` | 11 / 0 |
| `modality_distribution` | 11 / 0 |
| `prompt_level_distribution` | 11 / 0 |
| `outcome_distribution` | 11 / 0 |
| `contributor_distribution` | 11 / 0 |
| `setting_distribution` | 11 / 0 |
| `independence_rate` | 11 / 0 |
| `positive_outcome_rate` | 11 / 0 |
| `missing_data_rate` | 11 / 0 |
| `prompt_support_trend` | 11 / 0 |
| `outcome_trend` | 11 / 0 |
| **`cross_setting_comparison`** | **0 / 11 — withheld** |
| **`cross_contributor_comparison`** | **0 / 11 — withheld** |

**Key definitions.** `independence_rate` = records with
`prompt_level == "independent"` ÷ records with any `prompt_level`; records with
no `prompt_level` are excluded from the denominator rather than counted as
dependent. The trend KPIs split the dated records into first and second halves
of the review period and report the difference between halves. Distribution KPIs
count only non-null values.

**Missing-data handling.** Throughout, a field that is absent is excluded from
that KPI's denominator; it is never imputed and never treated as a negative
observation. `missing_data_rate` reports the absence itself as its own metric.

**Withholding.** A KPI abstains when its prerequisite is unmet — for the two
comparison KPIs, that prerequisite is more than one setting and more than one
contributor respectively. In the 11-child evaluation each child's records came
from a single corpus and therefore a single derived setting and contributor
role, so both comparisons were withheld for all 11.

**That is precisely the pair the reporting model failed to acknowledge**,
causing all 11 governance-validation failures reported in round-1 Q18. The
analytics engine withheld them correctly and said why; the reporting model
omitted any mention that they had been withheld.

**In plain terms.** Fourteen statistics, all computed by ordinary code so no
model can invent or alter them. Twelve were computed for every child. Two —
comparisons across settings and across contributors — were deliberately
suppressed for every child, because each child's data came from only one setting
and one contributor, so there was nothing to compare. Those are exactly the two
the report failed to mention were missing.

---

## Q6 — Current integrated application configuration

**Answer.** **No.** The application's current default extraction workflow uses a
**single generator**, and MARS is not in the default path.

Verified configuration (`src/backend/config.py`, resolved at runtime):

```
extraction_provider        = "ollama"
extraction_provider_kwargs = {"base_url": "http://127.0.0.1:11434/v1",
                              "api_key": "ollama",
                              "model": "llama3.2:latest"}
```

`ObservationService` (`src/backend/services/observation_service.py:86`) calls
`get_extraction_provider(settings.extraction_provider, **settings.extraction_provider_kwargs)`
— one provider, one model. The factory
(`src/backend/ml/extraction/__init__.py`) recognises `temporary_llm`, `ollama`
and `finetuned_model`; **the MARS composing provider is not reachable from it.**

So, precisely:

- All four generators are **runnable** through the shared `ExtractionProvider`
  interface, and all four have been **evaluated**.
- **None of the four is configured as a multi-candidate roster in the running
  application.** The default is `llama3.2:latest` alone.
- MARS exists, is tested, and was run as an offline experiment over the frozen
  batch. It is **not** wired into the default request path.
- Four-generator MARS has **never been run**, experimentally or in the
  application.

**This corrects the premise of round-1 Q15**, which asked us to confirm that all
four generators are integrated into the application. They are not. The
manuscript should describe MARS as an offline experiment over recorded generator
outputs, not as a deployed component.

**In plain terms.** The running app uses one small model and no referee system.
Everything else — four models, the referee experiment — was research run offline
against saved outputs. Saying the four are "integrated" would overstate what is
deployed.

---

## Q7 — Reporting remediation

**Answer.** **No remediation was made, and no rerun exists.** The negative
result stands exactly as reported: 0/11 reports passed governance validation
because withheld analytics were not acknowledged.

The timeline matters and should not be collapsed:

1. **Before** any governance result existed, the reporting call was changed from
   prompt-only formatting on the `/v1` endpoint to schema-constrained decoding on
   Ollama's native endpoint, and `reporting_num_ctx` was raised 4096 → 8192.
   Both changes addressed **structural conformance**, which had been 0/11.
2. The evaluation was then run under that configuration, producing the reported
   result: 11/11 structurally conformant; 0/11 passing governance validation.
3. **Nothing was changed afterwards.** The reporting system prompt, the report
   schema, and `validate_report()` are unmodified since that run. No second
   evaluation was performed.

So there is one pre-remediation and no post-remediation result, because no
remediation occurred. The prompt does already instruct the model to "Preserve all
abstention messages" and to state clearly when a metric was withheld — the
failure is that a correct instruction was not followed, not that the instruction
was absent. Adding emphasis and re-running would produce a second number that
invites exactly the silent replacement this question guards against; if it is
done, both results must be reported side by side with the change between them
stated.

**In plain terms.** We fixed the formatting problem *before* measuring
governance, then measured, then stopped. We did not go back and tune the prompt
to make the governance score look better. The instruction to mention withheld
numbers was already in the prompt — the model simply did not follow it.

---

## Q8 — Free-text `behavior` evaluation

**Answer.** `token_overlap()` in
`tests/eval/extraction/agreement_report.py`. The metric is **Jaccard similarity
over whitespace-delimited word sets**:

```
overlap(a, b) = |set(a.split()) ∩ set(b.split())|
                ────────────────────────────────
                |set(a.split()) ∪ set(b.split())|
```

No library; no stemming, lemmatisation, stop-word removal or embedding.
Normalisation is case folding and whitespace collapsing only
(`normalize()` in the same module). Both empty → 1.0; exactly one empty → 0.0.

**Measured values** (330 merged-gold segments; models against the adjudicated
gold):

| | median | mean |
|---|---:|---:|
| annotator vs annotator | 0.316 | 0.368 |
| qwen2.5:7b vs gold | 0.083 | 0.096 |
| llama3.2 vs gold | 0.071 | 0.088 |
| qwen2.5:3b vs gold | 0.071 | 0.090 |

**Why `behavior` is excluded from whole-record accuracy.** The scorer's default
rule for free text is token overlap at a 0.5 threshold. **Only 24.2% of
human–human pairs reach that threshold** — two expert annotators describing the
same event usually fall below it. A threshold neither annotator clears against
the other cannot separate models, and including it would fail almost every
record for reasons of wording rather than substance, driving whole-record
accuracy toward zero independently of extraction quality.

Whole-record accuracy is therefore computed over the four categorical fields
with `--behavior-match excluded`, and that policy is recorded in the scoring
output (`scored_against_gold.json`, `behavior_match: "excluded"`). `behavior` is
reported separately as a distribution against the human reference band.

**The gap is real, not an artefact of the strict threshold.** Models sit at
median 0.07–0.08 against humans at 0.316 — roughly fourfold — which is why it is
reported as a distribution rather than suppressed. What the threshold cannot
support is a binary pass/fail verdict.

**Stated limitation.** Jaccard word overlap accepts rewording but cannot detect
two descriptions that share vocabulary while describing different things, and
penalises correct paraphrase. It is a floor on semantic agreement, not a measure
of it. A semantic or human evaluation of `behavior` has not been performed.

**In plain terms.** We compare two descriptions by how many words they share,
divided by the total distinct words used — no clever language processing. Two
human experts describing the same moment share only about a third of their
words, so a "must share half" rule fails most human pairs too. Judging the
models by that rule would say everything is wrong for reasons of phrasing, so we
leave this field out of the strict scoring and report the raw similarity
instead. Even so, the models share about four times fewer words with the answer
key than the two humans share with each other.
