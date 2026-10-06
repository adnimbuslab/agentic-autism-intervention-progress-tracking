# Reliability mathematics — derivations and worked calculations

Every estimator used in `results_reliability.md`, derived and then worked
through on the study's own data rather than on a textbook example. The worked
field throughout is `modality` at round 1: it carries the paper's central
diagnostic result, and it is the field where a bare kappa is most misleading.

Implementation: `tests/eval/extraction/reliability_stats.py`.
Tests: `test_reliability_stats.py` (estimator properties),
`test_manuscript_numbers.py` (these numbers against the recorded artefacts).

## Notation

Two annotators label the same `n` items with categories from a set `K`.

```
n_ij   items annotator A put in category i and annotator B in category j
p_ij   n_ij / n
p_i.   sum_j p_ij      A's marginal (row)
p_.j   sum_i p_ij      B's marginal (column)
```

Nulls are a category, not missing data: a recorded null is the substantive
claim "this transcript supports no value here", and treating it as absence
would delete the study's hallucination measure.

## Worked data: `modality`, round 1, n = 330

Counts `n_ij`, annotator A down the side, annotator B across the top.

| A \ B | gestural | multimodal | none | unknown | verbal | written | **p_i. × n** |
|---|---:|---:|---:|---:|---:|---:|---:|
| gestural | **15** | 2 | 0 | 0 | 0 | 0 | 17 |
| multimodal | 2 | **35** | 0 | 0 | 2 | 0 | 39 |
| none | 64 | 9 | **0** | 1 | 0 | 1 | 75 |
| unknown | 0 | 3 | 0 | **5** | 1 | 0 | 9 |
| verbal | 0 | 5 | 0 | 1 | **184** | 0 | 190 |
| written | 0 | 0 | 0 | 0 | 0 | **0** | 0 |
| **p_.j × n** | 81 | 54 | **0** | 7 | 187 | 1 | 330 |

The `none` column is empty: annotator B never once used the category annotator
A used 75 times. Everything below follows from that.

---

## 1. Observed agreement, expected agreement, kappa

```
p_o = sum_i p_ii                          observed agreement
p_e = sum_i p_i. * p_.i                   agreement predicted by the marginals

        p_o - p_e
kappa = ---------
         1 - p_e
```

`p_e` is the agreement two annotators would reach if each drew independently
from their own observed marginal. Kappa is the fraction of the room above that
baseline which they actually closed.

**Worked.** The diagonal sums to 15 + 35 + 0 + 5 + 184 + 0 = 239.

```
p_o = 239 / 330 = 0.724242
```

The expected term, category by category (terms with a zero marginal vanish):

```
gestural     (17/330)(81/330)  = 0.012645
multimodal   (39/330)(54/330)  = 0.019339
none         (75/330)(0/330)   = 0
unknown      ( 9/330)( 7/330)  = 0.000579
verbal      (190/330)(187/330) = 0.326263
written      ( 0/330)( 1/330)  = 0
                                ----------
p_e                             = 0.358825
```

```
        0.724242 - 0.358825     0.365417
kappa = -------------------  =  --------  =  0.569919
          1 - 0.358825          0.641175
```

Reported as **0.570**.

## 2. The ceiling the marginals allow

Kappa is bounded above by how similarly the two annotators used the vocabulary,
independently of their judgement on any item. Observed agreement cannot exceed
the overlap of the two marginals, because agreement on category `i` requires
both a row-`i` and a column-`i` item:

```
p_o_max = sum_i min(p_i., p_.i)

            p_o_max - p_e
kappa_max = -------------
               1 - p_e

forced disagreements = n (1 - p_o_max) = n - sum_i min(n_i., n_.i)
```

**Worked.**

```
min(17,81) + min(39,54) + min(75,0) + min(9,7) + min(190,187) + min(0,1)
  = 17 + 39 + 0 + 7 + 187 + 0
  = 250

p_o_max = 250 / 330 = 0.757576

            0.757576 - 0.358825     0.398751
kappa_max = -------------------  =  --------  =  0.621907
              1 - 0.358825          0.641175

forced disagreements = 330 - 250 = 80
```

Reported as **kappa_max = 0.622**, with **80** of the 91 observed
disagreements (88%) unavoidable at these marginals.

**The ratio is the diagnostic.** `kappa / kappa_max = 0.570 / 0.622 = 0.916`.
The annotators closed 92% of the distance actually available to them. A reader
given only `kappa = 0.570` would conclude the annotators were inconsistent; the
ratio says they were nearly as consistent as their divergent category usage
permitted, and that the defect was in the scheme.

**The same field after the codebook** (n = 330, merged gold):

```
sum_i min(n_i., n_.i) = 320
forced disagreements  = 330 - 320 = 10          (was 80)
kappa_max             = 0.948                    (was 0.622)
kappa                 = 0.911                    (was 0.570)
```

The definition aligned the marginals, which is what a definition should do and
what the round-1 diagnosis predicted it would do.

## 3. Why kappa is not pooled across fields

A single kappa over all four fields can be computed by concatenating each
field's label pairs into one confusion matrix. It must not be reported, and the
size of the error is worth stating.

`modality` and `prompt_level` share three literal labels — `gestural`, `none`
and `verbal` — with entirely different meanings. Pooling merges
`verbal`-the-communication-channel with `verbal`-the-prompt-type into one
category and computes a chance correction against a distribution no annotator
ever drew from.

**Worked**, round 1, all four categorical fields, n = 4 × 330 = 1320:

```
pooled p_o   = 0.7311
pooled p_e   = 0.1203         <-- depressed: the pooled label space is larger
                                  than any single field's, so chance agreement
                                  looks far rarer than it is
pooled kappa = 0.6943

mean of per-field kappas = 0.6100
inflation from pooling   = +0.0843
```

The pooled figure is 0.084 higher, and the inflation is an artefact of the
pooled category count rather than a measurement. The mean of per-field kappas
is reported instead, which states plainly what it aggregates.

## 4. Large-sample variance (Fleiss, Cohen & Everitt, 1969)

```
var(kappa) = 1 / (n (1 - p_e)^4) * [ A + B - C ]

A = sum_i p_ii [ (1 - p_e) - (p_i. + p_.i)(1 - p_o) ]^2
B = (1 - p_o)^2 * sum_i sum_{j != i} p_ij (p_.i + p_j.)^2
C = ( p_o p_e - 2 p_e + p_o )^2
```

**Worked**, `modality` round 1:

```
A   = 0.11317203
B   = 0.00111972
C   = 0.07100584

A + B - C          = 0.04328591
n (1 - p_e)^4      = 330 * 0.641175^4 = 55.7726

var  = 0.04328591 / 55.7726 = 0.00077611
SE   = sqrt(0.00077611)     = 0.027859

95% CI = 0.569919 +/- 1.959964 * 0.027859 = [0.515316, 0.624521]
```

Reported as **SE 0.028**, CI **[0.515, 0.625]**.

**Degenerate case as a check.** Under perfect agreement `p_o = 1`, so
`p_ij = 0` for `i != j`, `p_ii = p_i. = p_.i`, and:

```
A = sum_i p_ii (1 - p_e)^2 = (1 - p_e)^2        since sum_i p_ii = 1
B = 0
C = (p_e - 2 p_e + 1)^2 = (1 - p_e)^2
var = [ (1-p_e)^2 - (1-p_e)^2 ] / (n (1-p_e)^4) = 0
```

A perfectly agreeing pair has zero variance, as it must. This identity is
asserted in `test_reliability_stats.py::test_perfect_agreement_has_zero_variance`.

## 5. Bootstrap interval (the one reported)

```
for r in 1..R:                       R = 10,000, seed 20260915
    draw n items from the n pairs, with replacement
    recompute kappa on the draw
    discard the draw if kappa is undefined (one category), and count it
CI = [ 2.5th percentile, 97.5th percentile ] of the retained replicates
```

The resampling unit is the **segment**, which is the unit of independent
observation. Resampling cells of the confusion matrix would treat the two
annotators' labels on the same transcript as separable, which they are not.

The bootstrap is reported rather than the asymptotic interval because the
asymptotic approximation degrades exactly where these fields live: `modality`
has categories with 1 and 0 observations. A replicate that collapses to a
single category leaves kappa undefined rather than zero — reporting 0.0 there
would state that the annotators agreed no better than chance, when in fact the
question could not be asked of that draw. Such replicates are dropped and
counted, so an interval resting on fewer than R replicates says so. All four
fields retained 10,000 of 10,000 in both rounds.

**Agreement between the two estimators.** They are computed together on the
reasoning that an assumption-light and an asymptotic estimator agreeing is
strong evidence neither carries a transcription error. Across all four fields
in both rounds, the two intervals differ by at most **0.005** on any bound —
`modality` round 1 gives bootstrap [0.517, 0.624] against asymptotic
[0.515, 0.625]. This agreement is asserted as a test, not merely observed.

## 6. Paired interval on the change

Round 1 and round 2 share both annotators and both segment sets, so the rounds
are paired and the interval belongs on the difference:

```
for r in 1..R:
    draw an index set I of size n from 1..n, with replacement
    kappa_1 = kappa over { before[i] : i in I }
    kappa_2 = kappa over { after[i]  : i in I }      <-- the SAME index set
    record kappa_2 - kappa_1
CI = [ 2.5th, 97.5th ] percentile of the recorded differences
```

Both kappas are recomputed on **the same draw**. Comparing two independently
constructed intervals by eye ignores the pairing and overstates the uncertainty
on the difference: segments that are hard in round 1 are hard in round 2, and
that correlation cancels in the difference but not in the separate intervals.

The estimand is restricted to the 178 re-issued segments. The other 152 carry
round-1 values in both rounds, so including them would add a constant of zero
change to both terms and shrink any measured difference toward zero.

**Result** (`round_comparison.json`, n = 178):

```
modality      0.385 -> 0.866    delta +0.481   95% CI [+0.397, +0.565]
outcome       0.284 -> 0.628    delta +0.344   95% CI [+0.217, +0.464]
prompt_level  0.281 -> 0.574    delta +0.293   95% CI [+0.137, +0.447]
domain        0.732 -> 0.691    delta -0.041   95% CI [-0.141, +0.052]   (control)
```

## 7. What the control arm licenses

`domain` is re-annotated in round 2 along with every other field, but no
codebook rule touches it. The comparison is therefore a difference in
differences in structure, though it is reported as two separate estimands
rather than as a single interaction term, because with four fields and one
control there is no useful power in the interaction.

```
treated fields:  delta in [+0.293, +0.481], every 95% CI excluding zero
control field:   delta = -0.041,            95% CI spanning zero
```

Re-annotation *as such* — practice, fatigue, regression to the mean, the mere
act of seeing a segment a second time — applies identically to both arms. The
control bounds that channel at −0.041 with an interval consistent with no
change. It cannot therefore account for gains of +0.29 to +0.48 in the treated
arm.

**What this does not license.** Two annotators converging on a stated rule is
reliability, not validity. A codebook instructing both to record `gestural`
everywhere would drive kappa to 1.0 and `kappa_max` to 1.0 and make the gold
standard worthless. The control arm bounds the practice-effect explanation; it
says nothing about whether the rules are *right*. That question is settled by
the defensibility of the rules as stated and by adjudication, neither of which
is a statistic.

A second limit: both rounds come from the same two annotators, so round 2 is a
within-annotator repeat under instruction rather than an independent
replication. What two fresh annotators working under the codebook from the
start would achieve was not measured.

## Reproduction

```
uv run python -m tests.eval.extraction.reliability_stats annotator_a annotator_b --round1
uv run python -m tests.eval.extraction.reliability_stats annotator_a annotator_b
uv run python -m tests.eval.extraction.round_comparison annotator_a annotator_b
uv run pytest tests/eval/extraction/test_reliability_stats.py
uv run pytest tests/eval/extraction/test_manuscript_numbers.py
```
