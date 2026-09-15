# Artefacts and reproduction

Every quantity reported in `results_reliability.md` and derived in
`reliability_mathematics.md` comes from a file listed below. This page is
generated from `artifact_manifest.json` by
`verify_artifacts.py --write-doc`; do not edit it by hand.

## Reproduction

The pipeline is deterministic from the frozen batch onward. Stage 1 calls
models; nothing after it does.

```
# 1. batch construction (model calls; the batch is frozen and not regenerated)
uv run python -m tests.eval.extraction.build_annotation_batch

# 2. round 1 -- export blind sheets, import what the annotators return
uv run python -m tests.eval.extraction.export_gold_sheet annotator_a annotator_b
uv run python -m tests.eval.extraction.import_gold_sheet annotator_a --path <sheet>
uv run python -m tests.eval.extraction.import_gold_sheet annotator_b --path <sheet>
uv run python -m tests.eval.extraction.agreement_report annotator_a annotator_b

# 3. codebook selection -- freezes round 1, issues round 2
uv run python -m tests.eval.extraction.reissue_gold_sheet annotator_a annotator_b

# 4. round 2 -- merge over the frozen round 1
uv run python -m tests.eval.extraction.import_gold_sheet annotator_a --path <sheet> --merge
uv run python -m tests.eval.extraction.import_gold_sheet annotator_b --path <sheet> --merge

# 5. statistics and figures
uv run python -m tests.eval.extraction.reliability_stats annotator_a annotator_b --round1
uv run python -m tests.eval.extraction.reliability_stats annotator_a annotator_b
uv run python -m tests.eval.extraction.round_comparison annotator_a annotator_b
uv run python docs/paper/make_figures.py

# 6. check the prose against the data, and the data against the manifest
uv run pytest tests/eval/extraction/test_manuscript_numbers.py
uv run python docs/paper/verify_artifacts.py
```

Seeds are fixed and recorded in the artefacts themselves: sheet ordering 42
(round 1) and 4242 (round 2), bootstrap 20260915 at 10,000 replicates.

## What is pinned

Data artefacts are hashed: they are evidence, and a re-run under a changed seed
or input would otherwise replace a reported number silently. Prose and figures
are listed but not hashed -- they are rewritten whenever a number is added or a
label is nudged, and a checksum failing on every honest edit teaches its reader
to ignore it.

`verify_artifacts.py` exits non-zero if a pinned file has moved. Re-record only
when a re-run was intended:

```
uv run python docs/paper/verify_artifacts.py --record
```


## Pinned data artefacts

| artefact | what it is | produced by | bytes | sha256 |
|---|---|---|---:|---|
| `tests/eval/extraction/results/annotation_batch.json` | Frozen annotation batch: 330 segments, 11 children, 3 generators | `build_annotation_batch` | 528,458 | `efd165f1c0dee0cb...` |
| `tests/eval/extraction/results/annotation_sheets/gold_sheet_annotator_a_updated.csv` | Annotator A, round 1, returned sheet (primary data) | `annotator` | 156,441 | `2618ccacb715a1e4...` |
| `tests/eval/extraction/results/annotation_sheets/gold_sheet_annotator_b_updated.csv` | Annotator B, round 1, returned sheet (primary data) | `annotator` | 152,567 | `d19b3c5e114f0ac3...` |
| `tests/eval/extraction/results/annotation_sheets/gold_sheet_annotator_a_round2_updated.csv` | Annotator A, round 2, returned sheet (primary data) | `annotator` | 91,877 | `803dc5b430556252...` |
| `tests/eval/extraction/results/annotation_sheets/gold_sheet_annotator_b_round2_updated.csv` | Annotator B, round 2, returned sheet (primary data) | `annotator` | 93,318 | `4a6ff5e43d39d1e4...` |
| `tests/eval/extraction/results/gold_annotator_a_round1.json` | Annotator A gold values, round 1, frozen before the round-2 merge | `import_gold_sheet + reissue_gold_sheet freeze` | 171,837 | `7950fcec0c87908e...` |
| `tests/eval/extraction/results/gold_annotator_b_round1.json` | Annotator B gold values, round 1, frozen before the round-2 merge | `import_gold_sheet + reissue_gold_sheet freeze` | 168,365 | `7b556f910ef86e6e...` |
| `tests/eval/extraction/results/gold_annotator_a.json` | Annotator A gold values, merged (152 round-1 + 178 round-2) | `import_gold_sheet --merge` | 174,992 | `778e93971ae46bc2...` |
| `tests/eval/extraction/results/gold_annotator_b.json` | Annotator B gold values, merged (152 round-1 + 178 round-2) | `import_gold_sheet --merge` | 174,986 | `e0abd2ff4fe1d130...` |
| `tests/eval/extraction/results/reissue_round2_selection.json` | Round-2 selection: which conflicts sit on a codebook boundary, and why | `reissue_gold_sheet` | 74,207 | `caae573037e4ba6d...` |
| `tests/eval/extraction/results/agreement_annotator_a_round1_annotator_b_round1.json` | Round-1 agreement report (kappa per field) | `agreement_report` | 17,638 | `e97c1918724bbb14...` |
| `tests/eval/extraction/results/agreement_annotator_a_annotator_b.json` | Post-codebook agreement report (kappa per field) | `agreement_report` | 17,547 | `cc51a86f6e16f67a...` |
| `tests/eval/extraction/results/reliability_round1.json` | Round-1 reliability: kappa, kappa_max, both intervals (Table R1) | `reliability_stats --round1` | 2,218 | `ae73f25f48737a5f...` |
| `tests/eval/extraction/results/reliability_current.json` | Post-codebook reliability over the merged gold (Table R5) | `reliability_stats` | 2,208 | `2840f188d023ff7f...` |
| `tests/eval/extraction/results/round_comparison.json` | Pre-registered before/after comparison, treated vs control (Table R4) | `round_comparison` | 5,499 | `e4f4ffa7e4eaf907...` |

## Prose and figures (listed, not pinned)

| artefact | what it is | produced by |
|---|---|---|
| `docs/annotation_codebook.md` | The three rules, with decision tests and worked examples | `written` |
| `docs/paper/results_reliability.md` | Manuscript section: methods, results, limitations | `written` |
| `docs/paper/reliability_mathematics.md` | Derivations and worked calculations on the study's own data | `written` |
| `docs/paper/figures/fig10_reliability_round1.png` | Figure 10 - round-1 kappa against the marginal ceiling | `make_figures` |
| `docs/paper/figures/fig11_confusion_round1.png` | Figure 11 - annotator confusion, boundary cells outlined | `make_figures` |
| `docs/paper/figures/fig12_conflict_decomposition.png` | Figure 12 - conflicts by cause | `make_figures` |
| `docs/paper/figures/fig13_round_comparison.png` | Figure 13 - reliability before and after, with the control arm | `make_figures` |
| `docs/paper/figures/fig14_protocol.png` | Figure 14 - two-round protocol with realised counts | `make_figures` |
| `docs/paper/figures/fig15_codebook_rules.png` | Figure 15 - the three rules as decision tests | `make_figures` |
