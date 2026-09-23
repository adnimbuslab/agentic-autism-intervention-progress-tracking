"""Pin the study's data artefacts by checksum, and verify them later.

Every number in `results_reliability.md` and `reliability_mathematics.md` is
derived from a file in this manifest. Recording their hashes makes two failures
loud that are otherwise silent:

  - an analysis re-run under a changed seed, threshold or input, which produces
    a plausible new number under an old filename;
  - an edit to a returned annotation sheet after import, which would change the
    primary human data behind an already-reported kappa.

**What is pinned and what is not.** Data artefacts -- the returned sheets, the
gold files, the computed statistics -- are hashed, because they are evidence
and must not move without someone deciding they should. Prose and figures are
listed for completeness but not hashed: they are *rewritten* whenever a number
is added to the manuscript or a label is nudged in a plot, and a checksum that
fails on every honest edit is noise that trains its reader to ignore it.

The manifest is regenerated deliberately, never automatically:

    uv run python docs/paper/verify_artifacts.py --record     # after a re-run
    uv run python docs/paper/verify_artifacts.py              # check
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "tests/eval/extraction/results"
REPORTING = ROOT / "tests/eval/reporting/results"
SHEETS = RESULTS / "annotation_sheets"
MANIFEST = Path(__file__).parent / "artifact_manifest.json"

# (path relative to repo root, what it is, what produced it, pinned?)
ARTEFACTS: list[tuple[Path, str, str, bool]] = [
    (RESULTS / "annotation_batch.json",
     "Frozen annotation batch: 330 segments, 11 children, 3 generators",
     "build_annotation_batch", True),

    (SHEETS / "gold_sheet_annotator_a_updated.csv",
     "Annotator A, round 1, returned sheet (primary data)",
     "annotator", True),
    (SHEETS / "gold_sheet_annotator_b_updated.csv",
     "Annotator B, round 1, returned sheet (primary data)",
     "annotator", True),
    (SHEETS / "gold_sheet_annotator_a_round2_updated.csv",
     "Annotator A, round 2, returned sheet (primary data)",
     "annotator", True),
    (SHEETS / "gold_sheet_annotator_b_round2_updated.csv",
     "Annotator B, round 2, returned sheet (primary data)",
     "annotator", True),

    (RESULTS / "gold_annotator_a_round1.json",
     "Annotator A gold values, round 1, frozen before the round-2 merge",
     "import_gold_sheet + reissue_gold_sheet freeze", True),
    (RESULTS / "gold_annotator_b_round1.json",
     "Annotator B gold values, round 1, frozen before the round-2 merge",
     "import_gold_sheet + reissue_gold_sheet freeze", True),
    (RESULTS / "gold_annotator_a.json",
     "Annotator A gold values, merged (152 round-1 + 178 round-2)",
     "import_gold_sheet --merge", True),
    (RESULTS / "gold_annotator_b.json",
     "Annotator B gold values, merged (152 round-1 + 178 round-2)",
     "import_gold_sheet --merge", True),

    (RESULTS / "reissue_round2_selection.json",
     "Round-2 selection: which conflicts sit on a codebook boundary, and why",
     "reissue_gold_sheet", True),
    (RESULTS / "agreement_annotator_a_round1_annotator_b_round1.json",
     "Round-1 agreement report (kappa per field)",
     "agreement_report", True),
    (RESULTS / "agreement_annotator_a_annotator_b.json",
     "Post-codebook agreement report (kappa per field)",
     "agreement_report", True),
    (RESULTS / "reliability_round1.json",
     "Round-1 reliability: kappa, kappa_max, both intervals (Table R1)",
     "reliability_stats --round1", True),
    (RESULTS / "reliability_current.json",
     "Post-codebook reliability over the merged gold (Table R5)",
     "reliability_stats", True),
    (RESULTS / "round_comparison.json",
     "Pre-registered before/after comparison, treated vs control (Table R4)",
     "round_comparison", True),

    (SHEETS / "adjudication_sheet_updated.csv",
     "Returned adjudication sheet: 503 decisions with rationales (primary data)",
     "adjudicator (consensus of both annotators)", True),
    (RESULTS / "adjudications.json",
     "Imported adjudication decisions",
     "import_adjudication_sheet", True),
    (RESULTS / "gold_labels.json",
     "Adjudicated gold standard: 330 of 330 segments (Table 5)",
     "adjudicate --decisions", True),
    (RESULTS / "scored_against_gold.json",
     "Per-generator judgements against gold, behavior excluded (Tables 6a-8)",
     "score_against_gold --behavior-match excluded", True),
    (RESULTS / "mars_outcomes.json",
     "MARS decisions over all 330 segments, 5-model judge roster",
     "run_mars", True),
    (RESULTS / "mars_run_summary.json",
     "MARS run configuration and per-judge discard rates",
     "run_mars", True),
    (RESULTS / "mars_evaluation.json",
     "MARS accuracy, coverage, abstention profile, ceiling (Tables 9-10)",
     "mars_evaluation", True),
    (REPORTING / "reporting_groundedness.json",
     "Reporting-layer groundedness run; records the 11/11 fallback finding",
     "tests.eval.reporting.groundedness", True),
    (RESULTS / "annotation_batch_augmented.json",
     "Frozen batch plus a generator added after annotation (qwen3:14b)",
     "add_generator", True),
    (RESULTS / "scored_against_gold_augmented.json",
     "Four-generator judgements against the same gold",
     "score_against_gold --batch annotation_batch_augmented.json", True),
    (RESULTS / "holdout_set.json",
     "Model-independent held-out set: 132 segments, frozen before generation",
     "build_holdout_set", True),
    (RESULTS / "holdout_batch.json",
     "Four generators over the held-out set; membership frozen before any ran",
     "add_generator --out holdout_batch.json", True),
    (RESULTS / "gold_holdout_annotator_a.json",
     "Annotator A values over the held-out set, codebook from the first segment",
     "import_gold_sheet --segments holdout_set.json", True),
    (RESULTS / "gold_holdout_annotator_b.json",
     "Annotator B values over the held-out set, codebook from the first segment",
     "import_gold_sheet --segments holdout_set.json", True),
    (RESULTS / "reliability_holdout.json",
     "Held-out first-pass reliability under the final protocol",
     "reliability_stats holdout_annotator_a holdout_annotator_b", True),
    (SHEETS / "holdout_adjudication_sheet_completed.csv",
     "Returned held-out adjudication sheet: 133 conflicted fields, all decided",
     "export_adjudication_sheet, completed by both annotators jointly", True),
    (RESULTS / "holdout_adjudications.json",
     "Held-out adjudication decisions imported from the returned sheet",
     "import_adjudication_sheet --path holdout_adjudication_sheet_completed.csv", True),
    (RESULTS / "gold_holdout_labels.json",
     "Held-out adjudicated reference standard: 132 of 132 segments, none lost",
     "adjudicate holdout_annotator_a holdout_annotator_b --out gold_holdout_labels.json", True),
    (RESULTS / "scored_holdout.json",
     "Four-generator judgements against held-out gold, behavior excluded",
     "score_against_gold --gold gold_holdout_labels.json --batch holdout_batch.json", True),
    (RESULTS / "holdout_metrics.json",
     "Batch vs held-out accuracy and unsupported assertion, same scoring policy",
     "holdout_metrics", True),
    (RESULTS / "paper_metrics.json",
     "Consolidated paper-ready metrics, derived from the artefacts above",
     "paper_metrics", True),
    (RESULTS / "mars_selection_analysis.json",
     "Per-field selection quality vs both baselines (Tables 11-12)",
     "mars_selection_analysis", True),
    (RESULTS / "mars_branch_replay.json",
     "Candidate-stage branch distribution and judge-roster comparison",
     "mars_branch_replay", True),

    (ROOT / "docs/annotation_codebook.md",
     "The three rules, with decision tests and worked examples",
     "written", False),
    (ROOT / "docs/paper/results_reliability.md",
     "Manuscript section: reliability methods, results, limitations",
     "written", False),
    (ROOT / "docs/paper/results_extraction.md",
     "Manuscript section: extraction/MARS methods and gold-standard results",
     "written", False),
    (ROOT / "docs/paper/reliability_mathematics.md",
     "Derivations and worked calculations on the study's own data",
     "written", False),
    (ROOT / "docs/paper/figures/fig10_reliability_round1.png",
     "Figure 10 - round-1 kappa against the marginal ceiling",
     "make_figures", False),
    (ROOT / "docs/paper/figures/fig11_confusion_round1.png",
     "Figure 11 - annotator confusion, boundary cells outlined",
     "make_figures", False),
    (ROOT / "docs/paper/figures/fig12_conflict_decomposition.png",
     "Figure 12 - conflicts by cause",
     "make_figures", False),
    (ROOT / "docs/paper/figures/fig13_round_comparison.png",
     "Figure 13 - reliability before and after, with the control arm",
     "make_figures", False),
    (ROOT / "docs/paper/figures/fig14_protocol.png",
     "Figure 14 - two-round protocol with realised counts",
     "make_figures", False),
    (ROOT / "docs/paper/figures/fig15_codebook_rules.png",
     "Figure 15 - the three rules as decision tests",
     "make_figures", False),
    (ROOT / "docs/paper/figures/fig16_field_accuracy.png",
     "Figure 16 - agreement with the reference standard, split by whether the "
     "standard records a value",
     "make_figures", False),
    (ROOT / "docs/paper/figures/fig17_unsupported.png",
     "Figure 17 - values asserted where the transcript supports none",
     "make_figures", False),
    (ROOT / "docs/paper/figures/fig18_record_ceiling.png",
     "Figure 18 - whole-record accuracy and the selection ceiling",
     "make_figures", False),
    (ROOT / "docs/paper/figures/fig19_behavior_overlap.png",
     "Figure 19 - free-text behavior against the human reference band",
     "make_figures", False),
    (ROOT / "docs/paper/figures/fig20_mars_outcomes.png",
     "Figure 20 - MARS outcomes and comparison against the best generator",
     "make_figures", False),
    (ROOT / "docs/paper/figures/fig21_selection.png",
     "Figure 21 - selection quality against both baselines",
     "make_figures", False),
    (ROOT / "docs/paper/figures/fig22_extended_roster.png",
     "Figure 22 - four-generator agreement and the abstention trade-off",
     "make_figures", False),
    (ROOT / "docs/paper/figures/response/r2_holdout_selection_effect.png",
     "Response figure - batch vs held-out agreement and unsupported assertion",
     "make_response_figures", False),
    (ROOT / "docs/paper/figures/response/r3_reporting_governance.png",
     "Response figure - what the reporting governance check found",
     "make_response_figures", False),
    (ROOT / "docs/paper/figures/response/r4_field_scope.png",
     "Response figure - evaluation scope against analytics scope",
     "make_response_figures", False),
    (ROOT / "docs/paper/figures/response/r5_contribution_hierarchy.png",
     "Response figure - the contribution hierarchy",
     "make_response_figures", False),
    (ROOT / "docs/paper/Reviewer_Response.docx",
     "Point-by-point response to the strict-reviewer assessment, all 12 issues",
     "make_reviewer_response", False),
    (ROOT / "docs/paper/Manuscript_Working_Draft.docx",
     "Working-draft manuscript, assembled from the artefacts above",
     "make_manuscript", False),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 16), b""):
            digest.update(block)
    return digest.hexdigest()


def survey() -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path, description, produced_by, pinned in ARTEFACTS:
        entry: dict[str, Any] = {
            "path": str(path.relative_to(ROOT)),
            "description": description,
            "produced_by": produced_by,
            "pinned": pinned,
            "present": path.exists(),
        }
        if path.exists():
            entry["bytes"] = path.stat().st_size
            if pinned:
                entry["sha256"] = sha256(path)
        entries.append(entry)
    return entries


def verify() -> tuple[list[str], list[str]]:
    """Return (problems, checked) against the recorded manifest."""
    if not MANIFEST.exists():
        return ([f"{MANIFEST.name} not found -- run with --record first"], [])

    recorded = {e["path"]: e for e in json.loads(MANIFEST.read_text())["artefacts"]}
    problems: list[str] = []
    checked: list[str] = []

    for entry in survey():
        path = entry["path"]
        if path not in recorded:
            problems.append(f"{path}: not in the manifest (added since it was recorded)")
            continue
        was = recorded[path]
        if not entry["present"]:
            problems.append(f"{path}: MISSING")
            continue
        if not entry["pinned"]:
            continue
        checked.append(path)
        if entry.get("sha256") != was.get("sha256"):
            problems.append(
                f"{path}: CHECKSUM CHANGED\n"
                f"    recorded {was.get('sha256', '?')[:16]}...  "
                f"({was.get('bytes')} bytes)\n"
                f"    now      {entry.get('sha256', '?')[:16]}...  "
                f"({entry.get('bytes')} bytes)"
            )

    for path in recorded:
        if path not in {e["path"] for e in survey()}:
            problems.append(f"{path}: in the manifest but no longer listed")
    return problems, checked


DOC_PATH = Path(__file__).parent / "artifacts.md"

DOC_HEADER = """# Artefacts and reproduction

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
uv run python -m tests.eval.extraction.adjudicate annotator_a annotator_b \\
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
"""


def write_doc() -> None:
    """Regenerate artifacts.md from the recorded manifest."""
    if not MANIFEST.exists():
        raise SystemExit(f"{MANIFEST.name} not found -- run with --record first.")
    entries = json.loads(MANIFEST.read_text())["artefacts"]

    lines = [DOC_HEADER, "\n## Pinned data artefacts\n",
             "| artefact | what it is | produced by | bytes | sha256 |",
             "|---|---|---|---:|---|"]
    for entry in entries:
        if not entry["pinned"]:
            continue
        digest = entry.get("sha256", "")
        lines.append(
            f"| `{entry['path']}` | {entry['description']} | "
            f"`{entry['produced_by']}` | {entry.get('bytes', 0):,} | "
            f"`{digest[:16]}...` |"
        )

    lines += ["\n## Prose and figures (listed, not pinned)\n",
              "| artefact | what it is | produced by |", "|---|---|---|"]
    for entry in entries:
        if entry["pinned"]:
            continue
        lines.append(
            f"| `{entry['path']}` | {entry['description']} | "
            f"`{entry['produced_by']}` |"
        )

    missing = [e["path"] for e in entries if not e["present"]]
    if missing:
        lines.append("\n## Not present at the time the manifest was recorded\n")
        lines += [f"- `{path}`" for path in missing]

    DOC_PATH.write_text("\n".join(lines) + "\n")
    print(f"Wrote {DOC_PATH.relative_to(ROOT)} "
          f"({sum(1 for e in entries if e['pinned'])} pinned, "
          f"{sum(1 for e in entries if not e['pinned'])} listed)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--record", action="store_true",
        help="Write the manifest from the current files. Deliberate act: do it "
             "only when a re-run was intended.",
    )
    parser.add_argument(
        "--write-doc", action="store_true",
        help="Regenerate docs/paper/artifacts.md from the manifest.",
    )
    args = parser.parse_args()

    if args.write_doc:
        write_doc()
        return

    if args.record:
        entries = survey()
        missing = [e["path"] for e in entries if not e["present"]]
        MANIFEST.write_text(json.dumps({"artefacts": entries}, indent=2) + "\n")
        pinned = sum(1 for e in entries if e["pinned"] and e["present"])
        print(f"Recorded {len(entries)} artefacts ({pinned} pinned by checksum) "
              f"to {MANIFEST.relative_to(ROOT)}")
        for path in missing:
            print(f"  ! not present: {path}")
        write_doc()
        return

    problems, checked = verify()
    print(f"Checked {len(checked)} pinned artefacts against "
          f"{MANIFEST.relative_to(ROOT)}")
    if not problems:
        print("All pinned artefacts match the manifest.")
        return
    print(f"\n{len(problems)} problem(s):")
    for problem in problems:
        print(f"  - {problem}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
