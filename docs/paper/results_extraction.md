# Extraction evaluation — manuscript section

Draft text and tables for the extraction/MARS portion of the manuscript. Every
number below was produced by a run recorded in this repository and is
reproducible from two commands:

```
uv run python -m tests.eval.extraction.build_annotation_batch   # regenerates the batch (model calls)
uv run python -m tests.eval.extraction.mars_branch_replay        # candidate-stage replay (no model calls)
uv run python docs/paper/make_figures.py                         # figures 1-9 + tables 2-3
```

Figures 6-9 read `annotation_batch.json` and `mars_branch_replay.json` directly,
so they cannot drift from the artefacts they describe.

---

## Methods

### Corpus and sampling frame

Behavioural segments were derived from the Rollins (child–investigator) and
Flusberg (child–parent) ASDBank CHAT corpora: 11 children, 85 sessions, 75,003
utterances. After parsing, deidentification and episode segmentation, 2,442
behavioural segments were available, ranging from 162 to 273 per child
(**Figure 1**). Segments are short: median 8 utterance lines (mean 10.3, range
3–24), median 187 characters.

An earlier defect in child attribution (`chat_parser._match_child`) assigned
`child_id = "unknown"` to every segment. A pilot annotation set drawn before the
fix landed 28 of its 31 items on a single child and none on the Flusberg corpus;
its field accuracies are reported in **Figure 4** as motivation only and are
explicitly not treated as a baseline.

### Batch construction

The annotation batch is built in three stages. Stages 1 and 3 are deterministic;
only stage 2 calls models.

1. **Stratified pool.** 120 segments per child (4× the per-child target of 30,
   sized from the pilot yield), 1,320 segments in total, no child short of
   quota.
2. **Candidate generation.** Three local generators — `llama3.2`, `qwen2.5:3b`,
   `qwen2.5:7b` — each extract from every pooled segment. A segment is retained
   only where all three produced an admissible response (`require=all`), so
   every batch item carries a complete candidate set.
3. **Annotator assignment.** Two annotators, overlap 1.0: both judge all 330
   items, so inter-rater reliability is estimable over the whole batch rather
   than a subset.

### Admission policy

Two admission predicates are distinguished, and the distinction matters for
reading every table below.

- **`reviewable`** — provider status `SUCCESS` or `PARTIAL`. This is the MARS
  runtime gate (MARS-029) and is correct there: there is no sense reranking a
  candidate its own generator disowned.
- **`judgeable`** — any response carrying at least one populated extracted
  field, whatever status the provider assigned. The batch was built under this
  policy.

The annotation task has a different purpose from the runtime gate. It measures
how good extracted *values* are, and a response that filled every field while
self-reporting confidence 0.0 is something an annotator can judge. Admitting
only `reviewable` responses would retain the segments each model found easy and
report accuracy on those — a difficulty-biased sample rather than a corpus
estimate. Provider status is recorded per candidate either way, so accuracy
conditional on status remains analysable.

**Table 1 — Batch composition**

| property | value |
|---|---|
| children | 11 (5 Rollins, 6 Flusberg) |
| candidates | 330 (30 per child, no shortfall) |
| generators | llama3.2, qwen2.5:3b, qwen2.5:7b |
| segments attempted | 506 |
| joint yield (`require=all`, `admit=judgeable`) | 65.2% |
| annotators | 2, overlap 1.0 (660 candidate-set judgements) |
| sampling seed | 42 |

Pilot sizing held: a 60-segment pilot projected ~519 segments would be consumed
to reach 330 candidates; the realised run consumed 506 (**Figure 3**). The same
pilot caught two configuration errors before annotation effort was committed —
including `mistral` in the generator roster under `reviewable` admission gave a
joint yield of 1.67%, which would have required roughly 19,760 segments from a
pool of 1,320.

---

## Results

### Provider status does not gate provider output

Across 496 abstentions from the three generators, 494 (99.6%) still carried at
least one populated field (**Figure 6**). `llama3.2` self-reported `abstained`
on 197 of 330 segments while populating `domain` on 97.0% and `behavior` on
93.0% of them, at a mean self-reported confidence of 0.28. `qwen2.5:3b` shows
the opposite miscalibration: mean confidence 0.86 alongside the sparsest output
in the roster, populating `prompt_level` on only 15.5% of segments.

Self-reported status and confidence are therefore not usable as a proxy for
whether a model produced anything, and are reported here as model behaviour
rather than used as a filter.

**Table 2 — Per-generator status, confidence and field population (n = 330)**

| generator | success | partial | abstained | mean conf. | domain | behavior | modality | prompt_level | outcome |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| llama3.2 | 128 | 5 | 197 | 0.28 | 97.0% | 93.0% | 95.2% | 86.1% | 79.1% |
| qwen2.5:3b | 94 | 7 | 229 | 0.86 | 61.8% | 97.6% | 44.5% | 15.5% | 44.5% |
| qwen2.5:7b | 258 | 2 | 70 | 0.79 | 99.1% | 99.7% | 74.5% | 72.4% | 77.3% |

### Generators diverge almost everywhere

Exact-match agreement between generator pairs is low across all five fields
(**Table 3**). Unanimity across all three generators is rare: 4.5% of segments
on `domain`, 15.2% on `modality`, 12.1% on `outcome`, 6.1% on `prompt_level`
(**Figure 7**). `behavior` is free text, so its 2.7% unanimity and 4–7% pairwise
agreement are a floor on semantic agreement, not a measure of it; the
categorical fields carry the interpretable signal.

**Table 3 — Pairwise exact-match agreement, both generators populated**

| pair | domain | behavior | modality | prompt_level | outcome |
|---|---:|---:|---:|---:|---:|
| llama3.2 / qwen2.5:3b | 18% (n=196) | 7% (n=299) | 42% (n=141) | 48% (n=48) | 39% (n=119) |
| llama3.2 / qwen2.5:7b | 26% (n=317) | 5% (n=306) | 61% (n=235) | 25% (n=211) | 47% (n=208) |
| qwen2.5:3b / qwen2.5:7b | 24% (n=204) | 4% (n=321) | 47% (n=129) | 18% (n=45) | 36% (n=118) |

Divergence of this magnitude is what makes selection a live question rather than
a formality: on most segments the three generators propose materially different
records, and which one is returned is a decision the system makes.

### Coverage headroom available to selection

Taking the union across generators raises field population above the best single
generator by 16.1 points on `outcome`, 8.5 on `prompt_level` and 3.6 on
`modality`; `domain` and `behavior` are near-saturated by the best single model
and offer under a point (**Figure 8**). These are *populated*, not *correct* —
whether the additional values are supported by the transcript is precisely what
the annotation measures.

### MARS candidate stage

MARS has not been run end-to-end: no live `JudgeProvider` implementation exists
outside the unit-test stub, so no MARS accuracy, coverage or reason-code
distribution is reported. What can be established without a judge is the
candidate set MARS would be handed, obtained by replaying the recorded
generator responses through the production `build_candidates` / `classify_branch`
path under the MARS-029 runtime gate (**Figure 9A**).

**Table 4 — MARS candidate-stage branch distribution (n = 330)**

| branch | n | share | consequence |
|---|---:|---:|---|
| `no_reviewable_candidate` | 42 | 12.7% | abstains before any judge is consulted |
| `single_candidate` | 123 | 37.3% | short-circuits; no judging, no control confidence |
| `rerank_required` | 165 | 50.0% | a genuine ranking decision |

Two findings follow.

**No two generators ever produced an identical extraction.** The count of
distinct candidates equals the count of admitted generators at every level
(0→42, 1→123, 2→124, 3→41): deduplication merged nothing across all 330
segments, and all 123 short-circuits have multiplicity 1. The
`single_candidate` branch is therefore never reached by consensus in this
configuration — it is always the degenerate case where exactly one generator
cleared the runtime gate. Because MARS-032 forbids writing generator confidence
alone, those 37.3% of segments would return a record with
`control_confidence_state = not_available_short_circuit`, i.e. over a third of
MARS's output would arrive with no control confidence for downstream validation
to gate on.

**The local roster barely supports a judge panel.** Judge eligibility
(MARS-027) disqualifies only exact identities that generated a candidate. Over
the 165 rerank segments, a roster of all four locally served models yields 2
eligible judges on 124 segments and just 1 on the remaining 41. Any
`min_eligible_judges ≥ 2` configuration abstains on those 41 (12.4% of the
batch) for `insufficient_eligible_judges` before quality is considered.

### MARS versus single generators

On the one axis that does not require labels — how often a reviewable record
exists at all — the union of the three generators covers 87.3% of segments
against 78.8% for the best single generator (`qwen2.5:7b`), a headroom of 8.5
points (**Figure 9B**). This is a **ceiling on MARS coverage, not a measurement
of it**: within the 165 rerank segments the agreement gate and integrity check
can still abstain, and the eligibility shortfall above removes at least 41 more
under a two-judge policy.

Note that generator admission rates differ sharply between the two policies and
must not be compared across them: under `judgeable` admission over the 506
attempted segments, per-generator yield was 94.3% (`qwen2.5:7b`), 85.2%
(`llama3.2`) and 80.4% (`qwen2.5:3b`); under the MARS-029 `reviewable` gate over
the 330 retained segments it is 78.8%, 40.3% and 30.6% respectively.

---

## Not yet measured

State of the evidence, recorded so that no reader infers more than exists:

| quantity | status | blocked on |
|---|---|---|
| per-generator field accuracy | not measured | adjudicated labels |
| inter-rater reliability (κ) | not measured | both annotators' judgements |
| oracle candidate ceiling | not measured | adjudicated labels |
| MARS accuracy / capture rate | not measured | labels **and** a live `JudgeProvider` |
| MARS coverage, reason codes | not measured | a live `JudgeProvider` |

The evaluation harness for all of these already exists
(`tests/eval/extraction/mars_evaluation.py`) and reports single-best-generator
accuracy, MARS accuracy, the oracle ceiling and the capture rate together,
because any one alone is misleading: a gain from 75% to 82% does not say whether
reranking left six points on the table or almost none.

## Limitations

- **Candidate fields.** The batch recorded 5 of the 8 `LLM_EXTRACTED_FIELDS`;
  `goal_context`, `prompt_context` and `duration_seconds` replay as null. Two
  responses differing only on an unrecorded field fingerprint as one, so
  `single_candidate` counts are an upper bound and `rerank_required` a lower
  bound. As every short-circuit already has multiplicity 1, this does not affect
  the no-identical-extractions finding.
- **Generator roster.** Three small local models. Results characterise this
  roster, not extraction quality achievable in general, and the divergence rates
  in Table 3 would not transfer to a stronger or more homogeneous roster.
- **Free-text fields.** `behavior` agreement is exact-match and understates
  semantic agreement.
- **Statuses are self-reported.** Table 2's status columns describe what the
  models claimed, which Figure 6 shows is a poor guide to what they produced.
- **No held-out research split yet.** The batch preserves real `child_id` on
  every candidate so a leakage-safe child-level split can be constructed
  downstream, but no such split has been frozen.
