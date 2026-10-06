"""The manifest must hold, and the worked calculations must be the real ones.

`reliability_mathematics.md` walks through kappa on `modality` at round 1 with
numbers typed into prose. A worked example that has drifted from the data is
worse than none: it reads as a verification of the implementation while
actually verifying nothing. These tests recompute every step from the gold
files and check the document against them.

The manifest tests assert that the pinned data artefacts still hash to what was
recorded, which is what makes "every number traces to a recorded file" a
checkable claim rather than an assurance.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RESULTS = Path(__file__).parent / "results"
MATHS = ROOT / "docs/paper/reliability_mathematics.md"
MANIFEST = ROOT / "docs/paper/artifact_manifest.json"
ARTEFACTS_DOC = ROOT / "docs/paper/artifacts.md"
VERIFY = ROOT / "docs/paper/verify_artifacts.py"


def _require(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} not produced yet")
    return path


@pytest.fixture(scope="module")
def maths() -> str:
    return _require(MATHS).read_text()


@pytest.fixture(scope="module")
def modality_round1() -> list[tuple[str, str]]:
    """The exact pairs the worked example is computed over."""
    first = json.loads(_require(RESULTS / "gold_annotator_a_round1.json").read_text())
    second = json.loads(_require(RESULTS / "gold_annotator_b_round1.json").read_text())
    return [
        (
            first[s]["field_values"]["modality"] or "none",
            second[s]["field_values"]["modality"] or "none",
        )
        for s in sorted(set(first) & set(second))
    ]


def _contains(text: str, value: float, decimals: int) -> bool:
    """Is `value`, printed to `decimals` places, present in the document?"""
    return f"{value:.{decimals}f}" in text


class TestWorkedKappa:
    def test_the_confusion_counts_in_the_table_are_real(
        self, maths, modality_round1
    ) -> None:
        joint = Counter(modality_round1)
        # The cells the prose singles out, and the diagonal it sums.
        assert joint[("none", "gestural")] == 64
        assert joint[("verbal", "verbal")] == 184
        assert joint[("gestural", "gestural")] == 15
        assert sum(joint[(c, c)] for c in {v for p in modality_round1 for v in p}) == 239
        for claim in ("| 64 |", "**184**", "**15**", "239"):
            assert claim in maths, claim

    def test_annotator_b_never_used_none(self, maths, modality_round1) -> None:
        assert Counter(b for _, b in modality_round1)["none"] == 0
        assert "The `none` column is empty" in maths

    def test_observed_and_expected_agreement_match(
        self, maths, modality_round1
    ) -> None:
        n = len(modality_round1)
        joint = Counter(modality_round1)
        row = Counter(a for a, _ in modality_round1)
        col = Counter(b for _, b in modality_round1)
        categories = set(row) | set(col)
        p_o = sum(joint[(c, c)] for c in categories) / n
        p_e = sum((row[c] / n) * (col[c] / n) for c in categories)
        assert _contains(maths, p_o, 6), f"p_o {p_o:.6f}"
        assert _contains(maths, p_e, 6), f"p_e {p_e:.6f}"
        # The individual expected-agreement terms are written out; check the
        # dominant one rather than all six.
        assert _contains(maths, (row["verbal"] / n) * (col["verbal"] / n), 6)

    def test_kappa_matches(self, maths, modality_round1) -> None:
        from tests.eval.extraction.agreement_report import cohens_kappa

        kappa = cohens_kappa(modality_round1)
        assert _contains(maths, kappa, 6), f"kappa {kappa:.6f}"

    def test_the_ceiling_and_forced_disagreements_match(
        self, maths, modality_round1
    ) -> None:
        from tests.eval.extraction.reliability_stats import kappa_max

        n = len(modality_round1)
        row = Counter(a for a, _ in modality_round1)
        col = Counter(b for _, b in modality_round1)
        overlap = sum(min(row[c], col[c]) for c in set(row) | set(col))
        assert overlap == 250
        assert n - overlap == 80
        assert _contains(maths, overlap / n, 6), "p_o_max"
        assert _contains(maths, kappa_max(modality_round1), 6), "kappa_max"
        assert "330 - 250 = 80" in maths

    def test_the_variance_terms_match(self, maths, modality_round1) -> None:
        from tests.eval.extraction.agreement_report import (
            expected_agreement,
            observed_agreement,
        )
        from tests.eval.extraction.reliability_stats import asymptotic_variance

        n = len(modality_round1)
        p_o = observed_agreement(modality_round1)
        p_e = expected_agreement(modality_round1)
        joint = Counter(modality_round1)
        row = Counter(a for a, _ in modality_round1)
        col = Counter(b for _, b in modality_round1)
        categories = sorted(set(row) | set(col))
        p_row = {c: row[c] / n for c in categories}
        p_col = {c: col[c] / n for c in categories}

        term_a = sum(
            (joint[(c, c)] / n) * ((1 - p_e) - (p_row[c] + p_col[c]) * (1 - p_o)) ** 2
            for c in categories
        )
        term_b = (1 - p_o) ** 2 * sum(
            (count / n) * (p_col[i] + p_row[j]) ** 2
            for (i, j), count in joint.items()
            if i != j
        )
        term_c = (p_o * p_e - 2 * p_e + p_o) ** 2

        assert _contains(maths, term_a, 8), f"A {term_a:.8f}"
        assert _contains(maths, term_b, 8), f"B {term_b:.8f}"
        assert _contains(maths, term_c, 8), f"C {term_c:.8f}"

        variance = asymptotic_variance(modality_round1)
        assert _contains(maths, variance, 8), f"var {variance:.8f}"
        assert _contains(maths, math.sqrt(variance), 6), "SE"

    def test_the_pooled_kappa_counterexample_is_real(self, maths) -> None:
        from tests.eval.extraction.agreement_report import cohens_kappa

        first = json.loads((RESULTS / "gold_annotator_a_round1.json").read_text())
        second = json.loads((RESULTS / "gold_annotator_b_round1.json").read_text())
        segments = sorted(set(first) & set(second))
        fields = ["domain", "modality", "prompt_level", "outcome"]
        pooled = [
            (
                first[s]["field_values"][f] or "none",
                second[s]["field_values"][f] or "none",
            )
            for f in fields
            for s in segments
        ]
        per_field = [
            cohens_kappa(
                [
                    (
                        first[s]["field_values"][f] or "none",
                        second[s]["field_values"][f] or "none",
                    )
                    for s in segments
                ]
            )
            for f in fields
        ]
        pooled_kappa = cohens_kappa(pooled)
        mean_kappa = sum(per_field) / len(per_field)

        assert _contains(maths, pooled_kappa, 4), f"pooled {pooled_kappa:.4f}"
        assert _contains(maths, mean_kappa, 4), f"mean {mean_kappa:.4f}"
        assert f"+{pooled_kappa - mean_kappa:.4f}" in maths, "inflation"
        assert len(pooled) == 1320

    def test_the_shared_label_claim_holds(self, maths, modality_round1) -> None:
        # The argument against pooling rests on labels being shared between the
        # modality and prompt_level vocabularies. Check that they are.
        from src.backend.schemas.observation_schema import Modality, PromptLevel

        shared = {m.value for m in Modality} & {p.value for p in PromptLevel}
        assert {"gestural", "verbal"} <= shared
        for label in ("`gestural`", "`verbal`"):
            assert label in maths

    def test_the_post_codebook_contrast_matches(self, maths) -> None:
        first = json.loads((RESULTS / "gold_annotator_a.json").read_text())
        second = json.loads((RESULTS / "gold_annotator_b.json").read_text())
        segments = sorted(set(first) & set(second))
        pairs = [
            (
                first[s]["field_values"]["modality"] or "none",
                second[s]["field_values"]["modality"] or "none",
            )
            for s in segments
        ]
        row = Counter(a for a, _ in pairs)
        col = Counter(b for _, b in pairs)
        overlap = sum(min(row[c], col[c]) for c in set(row) | set(col))
        assert overlap == 320
        assert len(pairs) - overlap == 10
        assert "330 - 320 = 10" in maths


class TestManifest:
    def test_the_pinned_artefacts_still_match(self) -> None:
        _require(MANIFEST)
        result = subprocess.run(
            [sys.executable, str(VERIFY)], capture_output=True, text=True, cwd=ROOT
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_every_pinned_artefact_is_present(self) -> None:
        entries = json.loads(_require(MANIFEST).read_text())["artefacts"]
        missing = [e["path"] for e in entries if e["pinned"] and not e["present"]]
        assert not missing, f"pinned but absent: {missing}"

    def test_the_primary_annotation_sheets_are_pinned(self) -> None:
        # The returned sheets are the study's primary human data; an unpinned
        # one could be edited after import without leaving a trace.
        entries = json.loads(_require(MANIFEST).read_text())["artefacts"]
        pinned = {e["path"] for e in entries if e["pinned"]}
        for name in (
            "gold_sheet_annotator_a_updated.csv",
            "gold_sheet_annotator_b_updated.csv",
            "gold_sheet_annotator_a_round2_updated.csv",
            "gold_sheet_annotator_b_round2_updated.csv",
        ):
            assert any(p.endswith(name) for p in pinned), name

    def test_the_generated_doc_lists_every_manifest_entry(self) -> None:
        entries = json.loads(_require(MANIFEST).read_text())["artefacts"]
        doc = _require(ARTEFACTS_DOC).read_text()
        for entry in entries:
            assert f"`{entry['path']}`" in doc, entry["path"]

    def test_the_doc_carries_the_recorded_checksums(self) -> None:
        entries = json.loads(_require(MANIFEST).read_text())["artefacts"]
        doc = _require(ARTEFACTS_DOC).read_text()
        for entry in entries:
            if entry["pinned"] and entry["present"]:
                assert entry["sha256"][:16] in doc, entry["path"]

    def test_the_seeds_are_stated(self) -> None:
        doc = _require(ARTEFACTS_DOC).read_text()
        for seed in ("42", "4242", "20260915", "10,000"):
            assert seed in doc, seed
