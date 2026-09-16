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

# 5. adjudication -- one sheet, one decision-maker
uv run python -m tests.eval.extraction.export_adjudication_sheet annotator_a annotator_b
uv run python -m tests.eval.extraction.import_adjudication_sheet --path <returned sheet>
uv run python -m tests.eval.extraction.adjudicate annotator_a annotator_b \
    --decisions results/adjudications.json --adjudicator "<who, and how>"
uv run python -m tests.eval.extraction.score_against_gold --behavior-match excluded

# 6. statistics and figures
uv run python -m tests.eval.extraction.reliability_stats annotator_a annotator_b --round1
uv run python -m tests.eval.extraction.reliability_stats annotator_a annotator_b
uv run python -m tests.eval.extraction.round_comparison annotator_a annotator_b
uv run python -m tests.eval.extraction.mars_selection_analysis
uv run python -m tests.eval.reporting.groundedness
uv run python -m tests.eval.extraction.paper_metrics
uv run python docs/paper/make_manuscript.py
uv run python docs/paper/make_figures.py

# 7. check the prose against the data, and the data against the manifest
uv run pytest tests/eval/extraction/test_manuscript_numbers.py
uv run pytest tests/eval/extraction/test_extraction_results_numbers.py
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
| `tests/eval/extraction/results/annotation_sheets/adjudication_sheet_updated.csv` | Returned adjudication sheet: 503 decisions with rationales (primary data) | `adjudicator (consensus of both annotators)` | 272,213 | `0e2a38568659b73a...` |
| `tests/eval/extraction/results/adjudications.json` | Imported adjudication decisions | `import_adjudication_sheet` | 127,198 | `8f4a0790e9210290...` |
| `tests/eval/extraction/results/gold_labels.json` | Adjudicated gold standard: 330 of 330 segments (Table 5) | `adjudicate --decisions` | 121,469 | `32327d787648dac9...` |
| `tests/eval/extraction/results/scored_against_gold.json` | Per-generator judgements against gold, behavior excluded (Tables 6-8) | `score_against_gold --behavior-match excluded` | 215,465 | `593674e34bcb9470...` |
| `tests/eval/extraction/results/mars_outcomes.json` | MARS decisions over all 330 segments, 5-model judge roster | `run_mars` | 138,754 | `5310fdff92588266...` |
| `tests/eval/extraction/results/mars_run_summary.json` | MARS run configuration and per-judge discard rates | `run_mars` | 1,374 | `b9b66b921a6984ec...` |
| `tests/eval/extraction/results/mars_evaluation.json` | MARS accuracy, coverage, abstention profile, ceiling (Tables 9-10) | `mars_evaluation` | 1,190 | `0ca48149ada6eb78...` |
| `tests/eval/reporting/results/reporting_groundedness.json` | Reporting-layer groundedness run; records the 11/11 fallback finding | `tests.eval.reporting.groundedness` | 8,015 | `10023e0111262084...` |
| `tests/eval/extraction/results/paper_metrics.json` | Consolidated paper-ready metrics, derived from the artefacts above | `paper_metrics` | 10,904 | `897d7bc12379ad49...` |
| `tests/eval/extraction/results/mars_selection_analysis.json` | Per-field selection quality vs both baselines (Tables 11-12) | `mars_selection_analysis` | 2,675 | `639c663bd4f8adfb...` |
| `tests/eval/extraction/results/mars_branch_replay.json` | Candidate-stage branch distribution and judge-roster comparison | `mars_branch_replay` | 3,685 | `33466b195d7413d6...` |

## Prose and figures (listed, not pinned)

| artefact | what it is | produced by |
|---|---|---|
| `docs/annotation_codebook.md` | The three rules, with decision tests and worked examples | `written` |
| `docs/paper/results_reliability.md` | Manuscript section: reliability methods, results, limitations | `written` |
| `docs/paper/results_extraction.md` | Manuscript section: extraction/MARS methods and gold-standard results | `written` |
| `docs/paper/reliability_mathematics.md` | Derivations and worked calculations on the study's own data | `written` |
| `docs/paper/figures/fig10_reliability_round1.png` | Figure 10 - round-1 kappa against the marginal ceiling | `make_figures` |
| `docs/paper/figures/fig11_confusion_round1.png` | Figure 11 - annotator confusion, boundary cells outlined | `make_figures` |
| `docs/paper/figures/fig12_conflict_decomposition.png` | Figure 12 - conflicts by cause | `make_figures` |
| `docs/paper/figures/fig13_round_comparison.png` | Figure 13 - reliability before and after, with the control arm | `make_figures` |
| `docs/paper/figures/fig14_protocol.png` | Figure 14 - two-round protocol with realised counts | `make_figures` |
| `docs/paper/figures/fig15_codebook_rules.png` | Figure 15 - the three rules as decision tests | `make_figures` |
| `docs/paper/figures/fig16_field_accuracy.png` | Figure 16 - per-field extraction accuracy against gold | `make_figures` |
| `docs/paper/figures/fig17_unsupported.png` | Figure 17 - values asserted where the transcript supports none | `make_figures` |
| `docs/paper/figures/fig18_record_ceiling.png` | Figure 18 - whole-record accuracy and the selection ceiling | `make_figures` |
| `docs/paper/figures/fig19_behavior_overlap.png` | Figure 19 - free-text behavior against the human reference band | `make_figures` |
| `docs/paper/figures/fig20_mars_outcomes.png` | Figure 20 - MARS outcomes and comparison against the best generator | `make_figures` |
| `docs/paper/figures/fig21_selection.png` | Figure 21 - selection quality against both baselines | `make_figures` |
| `docs/paper/Manuscript_Working_Draft.docx` | Working-draft manuscript, assembled from the artefacts above | `make_manuscript` |
