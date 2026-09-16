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
3. **Annotation frame.** The batch is frozen at this point and is not
   regenerated.

### Annotation design

Gold is authored **from the source, independent of any model**. Two annotators
each read all 330 transcript segments and record the field values the
transcript supports, with no model output shown. They do not judge candidates.

Three consequences follow, and they are the reason for the design:

- **One common reference.** All three generators are scored against the same
  gold, so per-generator accuracy and the oracle ceiling are computed over a
  common set. A fourth generator can be added later with no new annotation.
- **No anchoring.** An annotator shown a model's answer is more likely to
  accept it, which would make each generator's measured accuracy partly a
  function of how persuasive its output looked. Blindness here is structural:
  the annotation tool reads `chat_text` and never touches `candidates`.
- **A third of the human cost.** 330 segments per annotator rather than
  330 x 3 candidate judgements, with no loss to the three-model comparison or
  the ceiling.

Both annotators cover all 330 segments, so the double-annotated overlap is the
whole batch and reliability is estimated over it rather than a subset.

Nulls are recorded explicitly. A null is the claim "this transcript supports no
value for this field", which is what makes an unsupported model value
measurable as a hallucination rather than being scored as an ordinary miss.

**Deriving per-generator judgements.** Gold holds values; the metrics are
defined over judgements. The mapping is mechanical, with no further human step:

| gold | model | judgement |
|---|---|---|
| null | null | `correctly_null` |
| null | value | `hallucinated` |
| value | null | `missing` |
| value | equal value | `correct` |
| value | different value | `incorrect` |

**Free-text `behavior`.** Exact string match on prose understates agreement for
reasons of wording rather than substance, and would drag whole-record
correctness toward zero. Agreement for `behavior` is therefore reported
descriptively (exact-match and mean token overlap) and excluded from the mean
kappa; for scoring, the match rule is an explicit, recorded parameter
(`--behavior-match`, default token overlap at 0.5, with `exact` and `excluded`
available). **[REPORT the rule used and its threshold in Methods.]**

**Reliability statistics.** Cohen's kappa per field, over the value categories
(nulls included as a category). Interval estimates, the marginal-imposed
ceiling `kappa_max`, the two-round codebook protocol and the pre-registered
before/after comparison are set out in `results_reliability.md`. Kappa is deliberately **not** pooled across
fields by concatenating labels: the fields draw on different category sets, so
a pooled confusion matrix would treat `verbal`-the-modality and
`verbal`-the-prompt-level as one category and compute a chance correction over
a distribution no annotator ever drew from. The overall figures reported are
the mean of the per-field kappas across the four categorical fields, and a
record-level exact-agreement rate, each stating what it aggregates.

Reliability was established over two annotation rounds separated by a written
codebook; see `results_reliability.md` for the protocol and results.
Disagreements that survive are adjudicated. A segment left unresolved on any
field is **excluded** from the gold standard rather than resolved by rule -- every
tie-break rule invents a value, and accuracy computed against invented values
measures the rule.

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
| annotators | 2, both covering all 330 segments (source-level gold) |
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

MARS runs end-to-end against live judges, with generators **replayed** from
the frozen batch so it selects from exactly the candidates the annotators saw.
Results are in *MARS over the full batch* below.

`mars_evaluation` refuses to report below 95% outcome coverage unless
`--allow-partial` is passed. That guard exists because an earlier 3-segment
single-judge ablation, evaluated by mistake, produced a MARS accuracy of 0.000
and a capture rate of −3.0 against a best generator of 4.5% — figures that read
as findings and were artefacts of a 3-segment denominator.

The candidate set MARS is handed can be established without any judge, by
replaying the recorded generator responses through the production
`build_candidates` / `classify_branch` path under the MARS-029 runtime gate
(**Figure 9A**).

**Judge panel size is a reporting constraint, not a detail.** With a single
judge, top-choice support is 1.0 by construction: there is no second opinion
for the agreement gate to disagree with, so the gate cannot reject anything and
its threshold is inert at any setting. A single-judge run measures generation
plus a one-model ranking and **no agreement-gating claim can rest on it**; it
is reported as an ablation. Roughly three eligible judges are required before
the gate is reported on, and the local roster does not currently supply them
(below).

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


### The adjudicated gold standard

Conflicts surviving round 2 were adjudicated by the **two annotators working
jointly from the codebook** (consensus adjudication), recorded in
`gold_labels.json` as `consensus:annotator_a+annotator_b`. Each of the 503
conflicted fields was decided with a written rationale. The decisions split 89
to annotator A and 90 to annotator B across the categorical fields, so neither
annotator's readings dominated the consensus; three decisions adopted a value
neither had recorded, each of them a correct application of a codebook rule
that both annotators had missed.

**All 330 segments entered the gold standard** — 322 adjudicated, 8 agreed on
every field, none excluded. Every figure below is therefore over the full
batch, not a conditional subset.

**Table 5 — Gold standard composition**

| property | value |
|---|---|
| segments in gold | 330 of 330 (none excluded) |
| resolved by consensus of both annotators | 322 |
| agreed on every field without adjudication | 8 |
| adjudicated fields | 503 (78 settled by an existing codebook rule) |
| adjudicator | consensus of annotator_a and annotator_b |
| null values in gold | outcome 115, modality 77, domain 3, prompt_level 2 |

### Per-field extraction accuracy

**Table 6 — Acceptable extractions per field (n = 330; acceptable = correct or
correctly null)**

| generator | domain | modality | prompt_level | outcome |
|---|---:|---:|---:|---:|
| llama3.2 | 17.9% | 50.3% | 28.2% | 27.0% |
| qwen2.5:3b | 8.8% | 36.4% | 4.2% | 32.4% |
| qwen2.5:7b | **42.4%** | **67.9%** | 28.2% | **33.9%** |

`qwen2.5:7b` leads on every field, but no generator exceeds 68% on any field
and none exceeds 43% on `domain`, `prompt_level` or `outcome` (**Figure 16**).

**Accuracy and coverage must be read together.** `qwen2.5:3b`'s 32.4% on
`outcome` is largely abstention: 69 of its acceptable judgements are
`correctly_null` and it returns nothing at all on 114 segments. On
`prompt_level` it is silent on 277 of 330 segments (84%), which is why its 4.2%
is not comparable to the others' as a quality figure. A generator that rarely
answers is not thereby accurate.

### Unsupported extractions

Where the adjudicated gold records a null — the transcript supports no value
for that field — the generators assert one anyway (**Figure 17**).

**Table 7 — Values asserted against a null gold**

| generator | modality (n=77) | outcome (n=115) |
|---|---:|---:|
| llama3.2 | 72 (93.5%) | 87 (75.7%) |
| qwen2.5:3b | 15 (19.5%) | 46 (40.0%) |
| qwen2.5:7b | 31 (40.3%) | 78 (67.8%) |

`domain` and `prompt_level` are omitted: gold records only 3 and 2 nulls for
them respectively, which cannot support a rate.

This is the measurement the explicit null convention was designed to make
possible, and it bears directly on the system's safety requirement that the
extraction provider must not generate field values unsupported by the source
text. On `outcome`, `llama3.2` invents a value on 87 of the 115 segments where
the transcript supports none. `qwen2.5:3b`'s lower rate is again partly
abstention rather than restraint.

### Whole-record correctness and the ceiling available to selection

**Table 8 — Whole-record accuracy (all four categorical fields acceptable)**

| | accuracy |
|---|---:|
| qwen2.5:7b | 4.5% |
| llama3.2 | 1.5% |
| qwen2.5:3b | 0.3% |
| **oracle ceiling** (best candidate per segment) | **6.1%** |

The ceiling is the result that matters for the architecture (**Figure 18**).
Even a perfect selector — one that picks, for every segment, whichever of the
three candidates is correct whenever any of them is — would produce a fully
correct record on 6.1% of segments. The headroom available to any reranking
mechanism over the best single generator is therefore **1.5 percentage points**
— five segments of 330.

Selection cannot rescue this generator roster. The limiting factor is candidate
quality, not candidate choice, and that is an argument for a better extraction
model rather than a better selector.

### Free-text `behavior`

Exact and threshold matching on prose is uninformative here, and the reason is
visible in the human data: the two annotators describing the same segment reach
a median token overlap of **0.316** (mean 0.368), and only 24.2% of their pairs
reach the 0.5 threshold the scorer defaults to. A threshold neither annotator
clears against the other cannot separate models.

`behavior` is therefore reported as a distribution against that human reference
band rather than as an accuracy (**Figure 19**):

| | median overlap | mean |
|---|---:|---:|
| annotator vs annotator | **0.316** | 0.368 |
| qwen2.5:7b vs gold | 0.083 | 0.096 |
| llama3.2 vs gold | 0.071 | 0.088 |
| qwen2.5:3b vs gold | 0.071 | 0.090 |

The models sit roughly four times below the human band. The gap is large enough
that it does not depend on the matching rule, which is why it is reported as a
distribution and why whole-record correctness above is computed with `behavior`
excluded (`--behavior-match excluded`, recorded in the scoring output).

### MARS over the full batch

MARS was run over all 330 segments against live judges, generators replayed
from the frozen batch. The judge roster is the five locally served models;
eligibility (MARS-027) removes those that generated a candidate for the
segment, leaving **3 eligible judges on 124 rerank segments and 2 on the
remaining 41**. Adding `qwen3:14b` to the roster is what lifted every rerank
segment to at least two eligible judges; under the previous four-model roster
41 segments had only one and could not be gated at all.

**A judge that contributes nothing is not visible from the outcome.** The first
full run reported 205 successes and looked unremarkable. In fact `qwen3:14b`
was discarded as unparseable on 165 of 165 rerank segments: it is a reasoning
model, Ollama streams its chain of thought against the same token budget as the
answer, and a 256-token judge budget was exhausted before any answer appeared.
The panel was nominally three and effectively two. Raising the judge budget to
2048 tokens fixed it, and `run_mars` now reports a per-judge discard rate so
the failure cannot recur silently. All judges were discarded on ≤2% of
consultations in the reported run.

**Table 9 — MARS outcomes (n = 330)**

| outcome | n | share |
|---|---:|---:|
| record returned | 265 | 80.3% |
| abstained — `no_reviewable_candidate` | 42 | 12.7% |
| abstained — `judge_disagreement` | 21 | 6.4% |
| abstained — `insufficient_valid_judge_responses` | 2 | 0.6% |

Of the 265 returned, 123 were single-candidate short-circuits that consulted no
judge and 142 were judged. The agreement gate rejected 21 of the 165 rerank
segments (12.7%). On the judged segments top-choice support was 1.0 on 74 and
0.667 on 68 — i.e. unanimous on just over half, and a 2-of-3 majority on the
rest. The gate is stricter on the 41 two-judge segments than on the 124
three-judge ones: a 1–1 split is a modal tie, which abstains before the
threshold is consulted, so those segments effectively require unanimity. That
asymmetry follows from judge eligibility rather than from a calibration choice.

**Table 10 — MARS against the best single generator**

| | accuracy |
|---|---:|
| MARS, over the 265 records returned | 3.4% |
| MARS, over all 330 (abstentions counted as not correct) | 2.7% |
| `qwen2.5:7b`, over the same 265 segments | 4.5% |
| `qwen2.5:7b`, over all 330 | 4.5% |
| oracle ceiling | 6.1% |

**No improvement from reranking is observed, and none is excluded.** On the 265
segments MARS answered, it produced 9 fully correct records against the best
generator's 12. Paired over the same segments: 9 correct for both, **0 where
MARS was correct and the generator was not**, 3 the other way, 253 where
neither was. Exact McNemar on the 3 discordant pairs gives **p = 0.25** — no
evidence of a difference in either direction, and the study is underpowered to
find one. At a best-generator accuracy of 4.5% and a ceiling of 6.1%, the
entire quantity under test is 5 records out of 330.

The one unambiguous observation is that MARS never selected a correct record
the best generator had missed. Reranking did not recover any candidate that
picking `qwen2.5:7b` unconditionally would have lost.

The oracle capture rate is reported as −0.758 and should not be read as a
performance figure: with MARS below the best single generator the numerator is
negative, and a rate computed against 1.5 points of headroom is dominated by
its denominator. It is recorded for completeness rather than interpreted.

### Does reranking select better than not reranking?

Table 10 compares MARS to the best generator on whole-record accuracy over
every returned record, and finds nothing. That instrument is wrong for the
question in two ways. It includes the **123 single-candidate short-circuits**,
where one generator cleared admission, no judge was consulted, and MARS passed
the candidate through — selection quality cannot be measured where no selection
occurred. And whole-record accuracy fires on 4.5% of segments, too coarse to
resolve a selection effect at all.

Measuring selection where selection happened — the **142 judged segments** —
and field by field, resolves it (`mars_selection_analysis.py`, **Figure 21**).

**Table 11 — Per-field accuracy of three selection policies (142 judged segments)**

| selector | domain | modality | prompt_level | outcome | mean |
|---|---:|---:|---:|---:|---:|
| best generator (`qwen2.5:7b`) | 45.8% | 77.5% | 35.9% | 30.3% | **47.4%** |
| **MARS** | 33.1% | 74.7% | 33.8% | **32.4%** | **43.5%** |
| random candidate | 22.3% | 55.6% | 23.5% | 28.5% | **32.5%** |

**Table 12 — Paired differences, 10,000 bootstrap replicates over segments**

| field | MARS − random candidate | MARS − best generator |
|---|---|---|
| domain | +7.8 [−0.7, +16.2] | **−12.7 [−19.7, −6.3]** |
| modality | **+19.0 [+9.9, +28.2]** | −2.8 [−8.5, +2.8] |
| prompt_level | **+13.5 [+5.6, +21.8]** | −2.1 [−9.2, +4.2] |
| outcome | +5.7 [−1.4, +12.7] | +2.1 [−2.8, +7.0] |

Bold intervals exclude zero.

**Two findings, and they point in opposite directions.**

*Reranking carries real signal.* MARS selects better than a candidate chosen at
random on every field, significantly so on `modality` (+19.0) and
`prompt_level` (+13.5). The judges are not noise: given a set of candidates
they identify better ones more often than chance. This is the first evidence in
this study that the judging stage does anything at all, and it could not be
seen in the whole-record figure.

*Reranking does not beat the simplest informed policy.* Against always using
the strongest generator, MARS is 3.9 points worse on average, significantly so
on `domain` (−12.7) and indistinguishable on the other three. MARS sits between
the two baselines: better than no judgement, worse than one fixed good choice.

**Why `domain` is where it loses.** MARS selected `qwen2.5:7b` on 58% of judged
segments (llama3.2 on 37, qwen2.5:3b on 23, qwen2.5:7b on 82). On `domain` that
model leads the roster by 32 points (45.8% against 13.4% and 7.7%), so the 42%
of selections that go elsewhere carry an expected cost of roughly 14.7 points —
against an observed deficit of 12.7. The mechanism is not that the judges rank
badly; it is that they rank *candidates* while the accuracy difference lives in
*which model produced them*, and no per-candidate evidence reveals that
`qwen2.5:7b` is three times better at `domain` than its rivals.

This is a property of the roster, not a defect of reranking. Where the
generators are close — `outcome`, with a 5-point spread across the three — MARS
matches the best of them and is nominally ahead (+2.1). Where one generator
dominates, any selector that sometimes chooses another pays for it, and the
dominant-generator policy is unbeatable by construction. **Reranking should be
expected to pay off on a roster of comparable-strength generators and to lose
on one with a dominant model**; this roster is the second kind.

---

## Not yet measured

State of the evidence, recorded so that no reader infers more than exists:

| quantity | status | blocked on |
|---|---|---|
| per-generator field accuracy | **measured** (Table 6) | — |
| inter-rater reliability (κ) | **measured** — mean κ 0.610 pre-codebook, 0.801 post | — see `results_reliability.md` |
| adjudicated gold standard | **measured** — 330 of 330 segments (Table 5) | — |
| unsupported-extraction rate | **measured** (Table 7) | — |
| oracle candidate ceiling | **measured** — 6.1% (Table 8) | — |
| MARS accuracy / coverage / abstention profile | **measured** (Tables 9-10) | — |
| whether reranking beats no judgement | **measured** — yes, +19.0 / +13.5 points on 2 of 4 fields (Table 12) | — |
| whether reranking beats the best single generator | **measured** — no; −3.9 points on average, −12.7 on `domain` (Table 12) | — |
| whether reranking would pay on a balanced roster | not measured | a roster without a dominant generator |
| MARS agreement-gate behaviour | not reportable | a panel of ~3 eligible judges |
| frontier-model comparison | out of the primary experiment | corpus terms confirmation |

MARS coverage, abstention reason codes and selection behaviour are now
measurable — the pipeline runs — but are reported only from a run whose judge
panel is stated, and never from the single-judge ablation.

The evaluation harness for all of these already exists
(`tests/eval/extraction/mars_evaluation.py`) and reports single-best-generator
accuracy, MARS accuracy, the oracle ceiling and the capture rate together,
because any one alone is misleading: a gain from 75% to 82% does not say whether
reranking left six points on the table or almost none.

**Frontier comparator.** A `claude-*` generator can enter the batch through the
same `ExtractionProvider` contract as the local models. It is held **outside the
primary experiment** until the corpora's terms are confirmed to permit
transmitting segments to a third-party API (see the ethics section), and will
then be reported as a secondary frontier benchmark rather than folded into the
primary three-generator comparison.

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
- **Free-text fields.** `behavior` is compared by a stated rule rather than by
  meaning. Token overlap accepts rewording but cannot detect two descriptions
  that share words while describing different things, and `exact` understates
  agreement badly. The rule and threshold are recorded with every scored run.
- **Judge panel.** The five-model roster gives 3 eligible judges on 124 rerank
  segments and 2 on 41. The gate is therefore stricter on those 41, where a
  modal tie abstains and unanimity is effectively required. A sixth
  non-generator model would remove the asymmetry.
- **Whole-record MARS comparison is underpowered.** At 4.5% best-generator
  accuracy the whole-record comparison rests on 3 discordant segments and
  resolves nothing (Table 10). The per-field analysis on judged segments
  (Tables 11-12) is what carries the selection finding; the two measure
  different things and the whole-record figure remains what the system returns.
- **The selection finding is roster-conditional.** MARS losing to the
  best-generator policy follows from one generator dominating `domain` by 32
  points. On a roster of comparable-strength generators the same judges could
  plausibly win, and this study cannot say whether they would. The finding is
  "reranking loses to a dominant generator", not "reranking does not work".
- **Gold coverage.** Every segment was resolved: all 330 entered the gold
  standard and none was excluded, so accuracy is over the full batch rather
  than a conditional subset. The counts are recorded in `gold_labels.json`.
- **Consensus adjudication.** Conflicts were settled by the two annotators
  jointly rather than by an independent third party. This is standard practice
  and is recorded in the gold file, but the adjudicators are the same people
  whose disagreements they resolved, and an independent adjudicator might have
  settled some differently. The 89/90 split of decisions between the two
  annotators' values indicates neither dominated, which bounds but does not
  eliminate the concern.
- **Ceiling, not selector.** The 6.1% oracle ceiling is a property of this
  three-generator roster. It says reranking has 1.6 points of headroom *here*;
  it does not generalise to a roster with stronger or more diverse candidates.
- **Statuses are self-reported.** Table 2's status columns describe what the
  models claimed, which Figure 6 shows is a poor guide to what they produced.
- **No held-out research split yet.** The batch preserves real `child_id` on
  every candidate so a leakage-safe child-level split can be constructed
  downstream, but no such split has been frozen.
