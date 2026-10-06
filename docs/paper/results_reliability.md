# Annotation reliability — manuscript section

Draft text, tables and figures for the inter-rater reliability portion of the
manuscript. Every number below was produced by a run recorded in this
repository and is reproducible from:

```
uv run python -m tests.eval.extraction.import_gold_sheet annotator_a --path <sheet>
uv run python -m tests.eval.extraction.agreement_report annotator_a_round1 annotator_b_round1
uv run python -m tests.eval.extraction.reliability_stats annotator_a annotator_b --round1
uv run python -m tests.eval.extraction.reissue_gold_sheet annotator_a annotator_b --report-only
uv run python -m tests.eval.extraction.import_gold_sheet annotator_a --path <round-2 sheet> --merge
uv run python -m tests.eval.extraction.round_comparison annotator_a annotator_b
uv run python -m tests.eval.extraction.reliability_stats annotator_a annotator_b
uv run python docs/paper/make_figures.py          # figures 10-13
```

Derivations and worked calculations for every estimator below are in
`reliability_mathematics.md`. The artefact list, checksums and full
reproduction sequence are in `artifacts.md`, generated from
`artifact_manifest.json`.

Figures 10-15 read `reliability_round1.json`, `reliability_current.json`,
`round_comparison.json`, `gold_annotator_{a,b}_round1.json` and
`reissue_round2_selection.json` directly, so they cannot drift from the
artefacts they describe. `test_manuscript_numbers.py` re-derives every cell of
every table below from those artefacts and fails if the prose and the data
disagree.

**Status: both rounds complete.** Round 2 was returned and merged on
2026-09-15. Adjudication of the residual conflicts has not been performed, so
no gold standard, accuracy or MARS number appears here. Section *Not yet
measured* states precisely what is outstanding.

---

## Methods

### Reliability statistics

Four quantities are computed per field, over the value categories with nulls
included as a category. Each is derived and then worked through on this
study's own data in `reliability_mathematics.md`; the summary follows.

**Cohen's kappa.** With `p_o` the observed agreement and `p_e` the agreement
predicted by the annotators' own marginals,

```
        p_o - p_e
kappa = ---------
         1 - p_e
```

Kappa is **not** pooled across fields by concatenating labels. The fields draw
on different category sets, so a pooled confusion matrix would treat
`verbal`-the-modality and `verbal`-the-prompt-level as one category and
chance-correct against a distribution no annotator ever drew from. The overall
figure reported is the mean of the per-field kappas, which states what it
aggregates.

**The ceiling the marginals allow.** Kappa is bounded above by how similarly
the two annotators used the category vocabulary, independently of how carefully
they read any segment. Observed agreement cannot exceed the overlap of the two
marginal distributions,

```
p_o_max   = sum_i min(p_i., p_.i)

            p_o_max - p_e
kappa_max = -------------
               1 - p_e
```

and `n (1 - p_o_max)` is the number of segments **forced** to disagree by the
marginals before a transcript is read. Where one annotator uses a category the
other never uses, those segments cannot agree at any level of care. Reporting
kappa alongside `kappa_max` separates two failures a bare kappa conflates: a
low kappa near its ceiling is a *definitional* problem, in which both
annotators applied a consistent but divergent reading of the scheme; a low
kappa far below its ceiling is a *judgement* problem on individual segments.
The distinction determines the remedy, and in this study it determined the
protocol change.

**Interval estimates.** Two estimators are computed and reported together.

1. *Percentile bootstrap* — 10,000 replicates resampling segments with
   replacement, 2.5th and 97.5th percentiles, seed 20260915. Replicates that
   collapse to a single category leave kappa undefined and are dropped and
   counted rather than scored as zero. This is the interval reported.
2. *Fleiss-Cohen-Everitt large-sample variance* (1969) —

```
var(kappa) = 1 / (n (1 - p_e)^4) * [ A + B - C ]

A = sum_i p_ii [ (1 - p_e) - (p_i. + p_.i)(1 - p_o) ]^2
B = (1 - p_o)^2 * sum_i sum_{j != i} p_ij (p_.i + p_j.)^2
C = ( p_o p_e - 2 p_e + p_o )^2
```

The bootstrap is the headline because it is assumption-light and survives the
sparse categories these fields actually have; the asymptotic estimator is
computed as a cross-check, on the reasoning that when an assumption-light and
an asymptotic estimator agree, neither is carrying a transcription error. They
agreed to within 0.005 on every bound of every field (Table R1), and all 10,000
replicates were valid for all four fields.

**Free-text `behavior`.** Exact match on prose understates agreement for
reasons of wording rather than substance. It is reported descriptively
(exact-match rate and mean token overlap) and excluded from the mean kappa;
whether two descriptions say the same thing is settled by a human at
adjudication.

### Two-round annotation protocol

Both annotators independently annotated all 330 segments from the transcript,
blind to model output and to each other (round 1). Analysis of the resulting
conflicts identified three field definitions that were underspecified in the
annotation instructions rather than genuinely contested:

1. whether `gestural` modality covers physical manipulation of objects or only
   communicative gestures;
2. whether `correct`/`incorrect` apply to ordinary conversational turns or only
   against an identifiable target;
3. whether an adult utterance preceding a child response constitutes a verbal
   prompt or the antecedent that creates the opportunity.

These were resolved in a written codebook (`docs/annotation_codebook.md`) that
states a rule, a decision test and worked examples for each (**Figure 15**),
and the affected segments were re-annotated (round 2). **Figure 14** accounts
for every segment through both rounds.

**Selection rule, fixed before round 2.** A segment was re-issued if at least
one of its conflicting fields was a value pair the codebook speaks to. The pair
table is enumerated in `reissue_gold_sheet.CODEBOOK_BOUNDARIES`, each pair
citing the rule that resolves it, and the realised selection is recorded in
`reissue_round2_selection.json`. Conflicts the codebook is silent on — `domain`
category judgements, and degree-of-completion calls such as correct-vs-partial
— were **not** re-issued and go to adjudication as they stand. Re-issuing them
would buy a reliability improvement the protocol did not earn.

**The codebook was not applied retroactively.** Rewriting round-1 values by
script to match the new rules would produce a gold standard containing values
no annotator chose, and a reliability figure describing the rewrite rule rather
than the annotators. The affected segments went back out blind instead.

**Blindness and independence in round 2.** Value columns were exported empty.
Neither annotator's round-1 values appear in the round-2 sheet, nor the other
annotator's, nor any indication of which field was in conflict — knowing that
a segment's `modality` was disputed is itself an anchor. Segments were
presented in a fresh per-annotator order under a seed distinct from round 1, so
neither annotator could pace off a familiar sequence, and all five fields were
re-annotated rather than only the conflicting ones: re-judging `outcome` while
looking at a `prompt_level` already committed to is not an independent
judgement. Round 1 was frozen to a separate artefact before round 2 could be
merged.

### Pre-registered before/after comparison

The comparison was specified before round 2 existed
(`tests/eval/extraction/round_comparison.py`).

**Estimand.** Per-field change in kappa over the 178 re-issued segments, round
1 against round 2, with a 95% interval from a **paired** bootstrap resampling
segments and recomputing both kappas on the same draw. The two rounds share
annotators and segments, so comparing two independent intervals by eye would
ignore the pairing and overstate the uncertainty on the difference.
Restricting to the re-issued segments is what makes the rounds comparable: the
remaining 152 carry round-1 values in both and would dilute any change by a
constant.

**Control field.** `domain` is re-annotated in round 2 along with everything
else, but no codebook rule touches it. It therefore carries the same practice,
fatigue and regression-to-the-mean effects as the treated fields and none of
the instruction. If `modality`, `prompt_level` and `outcome` improve while
`domain` does not, the improvement is attributable to the codebook; if `domain`
moves as much as the rest, the honest reading is that re-annotation rather than
the rules produced the change. This inference is the reason `domain` conflicts
were excluded from the re-issue rather than swept in for convenience.

---

## Results

### Round-1 reliability, and how much of it the marginals fixed

Both annotators completed all 330 segments, so the double-annotated overlap is
the whole batch. Agreement was substantial on `domain` and moderate on the
three other categorical fields (**Table R1**, **Figure 10**). Mean kappa across
the four categorical fields was 0.610. Whole-record exact agreement — all five
fields identical, `behavior` compared as a string — was 0.0182 (6 of 330), which
is a statement about free-text prose rather than about the categorical scheme.
`behavior` exact-match agreement was 0.0455 at a mean token overlap of 0.3978.

**Table R1 — Round-1 inter-annotator reliability (n = 330 segments)**

| field | categories used | p_o | p_e | kappa | 95% CI (bootstrap) | 95% CI (asymptotic) | SE | kappa_max | kappa / kappa_max |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| domain | 9 | 0.809 | 0.233 | 0.751 | [0.697, 0.803] | [0.698, 0.805] | 0.027 | 0.921 | 0.816 |
| modality | 6 | 0.724 | 0.359 | 0.570 | [0.517, 0.624] | [0.515, 0.625] | 0.028 | 0.622 | **0.916** |
| prompt_level | 7 | 0.749 | 0.379 | 0.595 | [0.516, 0.667] | [0.520, 0.670] | 0.038 | 0.839 | 0.709 |
| outcome | 7 | 0.642 | 0.249 | 0.524 | [0.458, 0.589] | [0.458, 0.589] | 0.034 | 0.758 | 0.691 |

Mean kappa across the four categorical fields: 0.610. Bootstrap: 10,000
replicates, all valid, seed 20260915. `behavior` excluded (free text).

The `kappa_max` column carries the substantive finding. `modality` has both the
lowest ceiling (0.622) and the highest ratio to it (0.916): the annotators were
operating at 92% of the agreement their own category usage permitted, and the
kappa of 0.570 is a near-direct readout of a vocabulary mismatch rather than of
inconsistent segment-level judgement. `outcome` and `prompt_level` sit further
below their ceilings (0.69 and 0.71), so part of their shortfall is genuine
per-segment disagreement. `domain`, with the highest kappa and a ceiling of
0.921, shows no marginal pathology.

**Table R2 — Disagreement forced by the marginals**

`n (1 - p_o_max)` is the number of segments that could not have agreed at the
observed marginals, whatever either annotator did on any individual transcript.

| field | observed disagreements | forced by marginals | share forced |
|---|---:|---:|---:|
| domain | 63 | 20 | 32% |
| modality | 91 | 80 | **88%** |
| prompt_level | 83 | 33 | 40% |
| outcome | 118 | 60 | 51% |

The driver on `modality` is a single category. Annotator A recorded `none` — no
communicative act in the segment — 75 times; annotator B recorded it **zero**
times, instead distributing those segments across `gestural` (81 uses against
A's 17) and `multimodal` (54 against 39). This is visible in **Figure 11** as an
entirely empty `none` column. The two annotators were not disagreeing about
what the children did; they were applying different readings of whether
handling an object is a communicative modality at all. A reliability figure
that reported only kappa would have recorded this as moderate annotator
agreement and given no indication that the remedy was a definition rather than
retraining.

### Conflicts decompose into a small set of definitional boundaries

Across the four categorical fields there were 355 field-level conflicts on 215
of 330 segments (the 324 segments carrying *any* disagreement include free-text
`behavior`, which disagrees almost everywhere by exact match and is excluded
here). **254 (71.5%)** of the 355 fall on one of the three boundaries the
codebook states; 101 (28.5%) do not (**Table R3**, **Figure 12**).

**Table R3 — Round-1 conflicts by cause**

| field | conflicts | on a codebook boundary | codebook silent |
|---|---:|---:|---:|
| domain | 63 | 0 | 63 |
| modality | 91 | 88 (97%) | 3 |
| prompt_level | 83 | 83 (100%) | 0 |
| outcome | 118 | 83 (70%) | 35 |
| **total** | **355** | **254 (71.5%)** | **101 (28.5%)** |

The concentration is field-specific and interpretable. Every `prompt_level`
conflict falls on a stated boundary, because the codebook fixes both the
antecedent/prompt distinction and a total ordering over the prompt levels, and
between them these bear on every value pair that occurred. `modality` is at 97%.
`outcome` is at 70%: the residual 35 are degree-of-completion judgements
(correct vs partial, approximation vs correct) that no definition settles.
`domain` is at 0% by construction — its conflicts are category judgements
(cognitive vs language, 12; play vs cognitive, 8) that the codebook does not
address, which is what qualifies it as the control field for the round-2
comparison.

178 of the 215 segments with a categorical conflict (82.8%), or 53.9% of the
full batch, carried at least one boundary conflict and were re-issued.

### Interpretation

The reliability that a naive reading of Table R1 would report — moderate
agreement on three of four fields — is substantially an artefact of an
underspecified annotation scheme rather than of annotator inconsistency. Two
independent lines of evidence support this: the ratio of kappa to its
marginal-imposed ceiling (0.92 on `modality`), and the concentration of
conflicts onto three enumerable definitional boundaries (71.5% of all field
conflicts). Both were computed from the round-1 data alone, before any protocol
change.

Whether the codebook in fact repairs the reliability is a separate empirical
question, and it is the one round 2 was designed to answer. It is answered
below.

### The codebook repairs the reliability; the control field is unmoved

Round 2 returned complete: both annotators re-annotated all 178 re-issued
segments, with no cell errors and no row identical to its round-1 counterpart
on all five fields. Over those segments, all three treated fields improved by a
margin whose 95% paired interval excludes zero, while the untreated control
field did not move (**Table R4**, **Figure 13**).

**Table R4 — Change in kappa over the 178 re-issued segments**

| field | arm | kappa round 1 | kappa round 2 | change | 95% CI (paired bootstrap) |
|---|---|---:|---:|---:|---|
| modality | treated | 0.385 | 0.866 | **+0.481** | [+0.397, +0.565] |
| outcome | treated | 0.284 | 0.628 | **+0.344** | [+0.217, +0.464] |
| prompt_level | treated | 0.281 | 0.574 | **+0.293** | [+0.137, +0.447] |
| domain | control | 0.732 | 0.691 | −0.041 | [−0.141, +0.052] |

Kappa on the re-issued segments is lower than on the full batch for every field
by construction: these are the segments the annotators disagreed on, so the
subset is the hard tail rather than a sample of the batch.

The control result is what licenses the causal reading. `domain` was
re-annotated in the same sitting, in the same fresh order, under the same
fatigue, by the same two annotators — and changed by −0.041 with an interval
spanning zero. Practice, regression to the mean and the mere act of seeing a
segment twice therefore do not account for the treated fields' gains of +0.29
to +0.48. The instruction does.

**The mechanism is visible in the ceilings.** `kappa_max` — the most the pair
could attain at their own marginals — rose sharply on exactly the treated
fields and fell slightly on the control:

| field | kappa_max round 1 | kappa_max merged | kappa round 1 | kappa merged |
|---|---:|---:|---:|---:|
| modality | 0.622 | 0.948 | 0.570 | 0.911 |
| prompt_level | 0.839 | 0.962 | 0.595 | 0.831 |
| outcome | 0.758 | 0.963 | 0.524 | 0.743 |
| domain (control) | 0.921 | 0.897 | 0.751 | 0.718 |

This is the predicted signature. The round-1 diagnosis was that the annotators
were applying divergent category vocabularies rather than judging segments
inconsistently; the remedy was therefore a definition, and what a definition
should do is align the marginals. It did: `modality`'s ceiling moved from 0.622
to 0.948, and annotator B, who recorded `none` zero times in round 1, used it
in round 2.

### Post-codebook reliability over the full batch

**Table R5 — Inter-annotator reliability after the codebook (n = 330 segments)**

| field | categories used | p_o | p_e | kappa | 95% CI (bootstrap) | 95% CI (asymptotic) | SE | kappa_max | kappa / kappa_max |
|---|---:|---:|---:|---:|---|---|---:|---:|---:|
| domain | 9 | 0.800 | 0.291 | 0.718 | [0.657, 0.774] | [0.659, 0.777] | 0.030 | 0.897 | 0.800 |
| modality | 6 | 0.949 | 0.420 | 0.911 | [0.869, 0.949] | [0.871, 0.952] | 0.021 | 0.948 | 0.961 |
| prompt_level | 6 | 0.891 | 0.355 | 0.831 | [0.777, 0.881] | [0.780, 0.882] | 0.026 | 0.962 | 0.863 |
| outcome | 7 | 0.809 | 0.258 | 0.743 | [0.684, 0.797] | [0.687, 0.799] | 0.029 | 0.963 | 0.771 |

Mean kappa across the four categorical fields rose from **0.610 to 0.801**.
Under the Landis and Koch bands, `modality` and `prompt_level` move from
moderate to almost perfect and `outcome` from moderate to substantial;
`domain`, untreated, remains substantial. Whole-record exact agreement is 0.0242
and `behavior` exact-match agreement 0.0273 at a mean token overlap of 0.3682,
both essentially unchanged — they are dominated by free-text prose, which the
codebook did not address. The two interval estimators again agree to within
0.005 on every bound, with all 10,000 replicates valid on every field.

This full-batch figure is computed over the **merged** gold, in which the 152
segments never in boundary conflict carry their round-1 values and the 178
re-issued segments carry round-2 values. It is the reliability of the gold
standard that will actually be adjudicated, and it is not a clean estimate of
what two annotators working under the codebook from the start would achieve —
that quantity was not measured and would require a fresh batch.

### Remaining disagreement

Categorical conflicts fell from 355 on 215 segments to **182 on 127 segments**,
a 49% reduction in adjudication load (**Figure 14**). What remains is concentrated where the
codebook is silent by design:

| field | conflicts round 1 | conflicts merged |
|---|---:|---:|
| domain | 63 | 66 |
| outcome | 118 | 63 |
| prompt_level | 83 | 36 |
| modality | 91 | 17 |
| **total** | **355** | **182** |

`domain` is now the largest single source of residual conflict (66 of 182),
still on the category judgements the codebook never addressed — `cognitive` vs
`language` (13), `language` vs `social_communication` (12), `language` vs `play`
(11). `outcome`'s residue is dominated by degree-of-completion calls
(`correct` vs `partial`, 13) and the target question in its harder form
(`correct` vs `none`, 13). These go to adjudication on the merits.

---

## Not yet measured

State of the evidence, recorded so that no reader infers more than exists.

| quantity | status | blocked on |
|---|---|---|
| round-1 inter-rater reliability | **measured** (Table R1) | — |
| marginal decomposition of round-1 disagreement | **measured** (Table R2) | — |
| conflict attribution to codebook boundaries | **measured** (Table R3) | — |
| change in kappa, treated fields | **measured** (Table R4) | — |
| change in kappa, control field (`domain`) | **measured** (Table R4) | — |
| post-codebook reliability, full batch | **measured** (Table R5) | — |
| adjudicated gold standard | not measured | adjudication of 182 residual conflicts |
| per-generator field accuracy | not measured | adjudicated gold |
| oracle candidate ceiling | not measured | adjudicated gold |
| MARS accuracy / capture rate | not measured | adjudicated gold |

The analysis code for every outstanding row exists and is tested
(`adjudicate.py`, `score_against_gold.py`, `mars_evaluation.py`). Adjudication
excludes any segment left unresolved on any field rather than breaking a tie by
rule, so the accuracy denominator will be the adjudicated subset and not the
full 330.

## Limitations

- **Two annotators, one pair.** Cohen's kappa describes this pair. With no
  third annotator there is no estimate of how much of the agreement is specific
  to these two readers, and the codebook rules were written after seeing where
  this particular pair diverged.
- **Agreement is not correctness.** Two annotators converging on a stated rule
  is reliability, not validity. A codebook that instructed both to record
  `gestural` everywhere would drive kappa to 1.0 and the gold standard to
  nonsense. Post-codebook reliability is a necessary condition for a usable
  gold standard, not a sufficient one; the defensibility of the rules
  themselves is argued in prose and settled at adjudication.
- **The codebook is derived from round-1 disagreement.** It was derived from
  the *pattern* of disagreement — which definitional boundaries proved
  ambiguous — and not from any ground-truth labels, which do not exist at this
  stage. The residual risk is that round-2 kappa improves through convergence
  by instruction rather than through better annotation. The `domain` control
  arm bounds that risk empirically: it moved by −0.041 with an interval
  spanning zero while the treated fields moved by +0.29 to +0.48, so the gains
  are not attributable to re-annotation as such. The risk the control cannot
  bound is convergence on a *wrong* rule, which is a validity question settled
  at adjudication rather than by any reliability statistic.
- **Reliability is not a clean between-subjects estimate.** The same two
  annotators produced both rounds, so round 2 is a within-annotator repeat
  under instruction, not an independent replication. Two annotators working
  under the codebook from the start might agree more or less; that quantity
  would require a fresh batch and was not measured.
- **Free-text `behavior` is outside the kappa.** Its reliability is reported
  descriptively and resolved by a human at adjudication, so no interval is
  available for it.
- **Kappa bands are conventional.** Landis and Koch labels are used for
  orientation only; nothing in the protocol depends on a threshold.
- **The re-issue set is not a random sample.** It is the segments where the
  annotators disagreed on a codebook boundary, so Table R4 describes the hard
  subset: its kappas are lower than the full-batch figures for every field by
  construction, and the changes in it are not estimates of what the codebook
  would do to a random segment. The full-batch figure (Table R5) is computed
  over the merged gold, in which 152 segments carry their round-1 values.
