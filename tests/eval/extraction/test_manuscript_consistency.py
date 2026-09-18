"""The manuscript must not contradict itself about what was completed.

A document assembled in sections drifts: a Methods paragraph written while an
experiment was pending survives into a build where the Results report that same
experiment as finished. That happened here -- Methods carried "annotation and
generator runs over it are not complete" in a build whose Results reported
mean kappa 0.910 over exactly those segments -- and a reviewer noticed before
any test did.

These checks derive the true state from the artefacts and assert the prose
agrees with it, across Methods, Results, Limitations and Not-measured together
rather than section by section.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RESULTS = Path(__file__).parent / "results"
MANUSCRIPT = ROOT / "docs/paper/Manuscript_Working_Draft.docx"


@pytest.fixture(scope="module")
def prose() -> str:
    if not MANUSCRIPT.exists():
        pytest.skip("manuscript not built")
    from docx import Document

    doc = Document(str(MANUSCRIPT))
    text = " ".join(p.text for p in doc.paragraphs)
    text += " " + " ".join(
        c.text for t in doc.tables for r in t.rows for c in r.cells
    )
    return re.sub(r"\s+", " ", text)


@pytest.fixture(scope="module")
def state() -> dict:
    """What the artefacts say actually happened."""
    holdout_batch = RESULTS / "holdout_batch.json"
    batch = json.loads(holdout_batch.read_text()) if holdout_batch.exists() else None
    generators_complete = []
    generators_partial = []
    if batch:
        total = len(batch["candidates"])
        for model in batch.get("models", []):
            n = sum(1 for e in batch["candidates"] if model in e["candidates"])
            (generators_complete if n == total else generators_partial).append(model)
    return {
        "holdout_frozen": (RESULTS / "holdout_set.json").exists(),
        "holdout_annotated": (RESULTS / "reliability_holdout.json").exists(),
        "holdout_gold": (RESULTS / "gold_holdout_labels.json").exists(),
        "generators_complete": generators_complete,
        "generators_partial": generators_partial,
        "main_gold": (RESULTS / "gold_labels.json").exists(),
    }


class TestHeldOutConsistency:
    def test_annotated_holdout_is_not_described_as_unannotated(
        self, prose, state
    ) -> None:
        if not state["holdout_annotated"]:
            pytest.skip("held-out round not annotated")
        for stale in (
            "annotation and generator runs over it are not complete",
            "held-out set is frozen (132 segments) but not yet annotated",
            "is not yet annotated",
        ):
            assert stale not in prose, f"stale claim survives: {stale!r}"

    def test_holdout_reliability_is_reported_when_measured(
        self, prose, state
    ) -> None:
        if not state["holdout_annotated"]:
            pytest.skip("held-out round not annotated")
        report = json.loads((RESULTS / "reliability_holdout.json").read_text())
        assert f"{report['mean_kappa']:.3f}" in prose

    def test_holdout_accuracy_is_not_claimed_without_gold(
        self, prose, state
    ) -> None:
        # Accuracy over the held-out sample requires an adjudicated reference.
        if state["holdout_gold"]:
            pytest.skip("held-out gold exists; accuracy may be reported")
        for forbidden in (
            "held-out accuracy",
            "accuracy on the held-out sample was",
            "unsupported-assertion rate on the held-out",
        ):
            assert forbidden.lower() not in prose.lower(), forbidden

    def test_generator_completion_is_described_accurately(
        self, prose, state
    ) -> None:
        if not state["generators_partial"]:
            pytest.skip("all held-out generator runs complete")
        # A partial run must be visible as partial somewhere in the prose.
        assert "in progress" in prose or "not complete" in prose

    def test_the_pending_marker_does_not_contradict_a_finished_experiment(
        self, prose, state
    ) -> None:
        if not state["holdout_annotated"]:
            pytest.skip("held-out round not annotated")
        # A [PENDING] tag adjacent to held-out text is the exact drift that
        # produced the contradiction a reviewer caught.
        for match in re.finditer(r"\[PENDING\][^.]*\.", prose):
            assert "held-out" not in match.group(0).lower(), match.group(0)


class TestClaimScope:
    def test_no_general_claim_about_model_size(self, prose) -> None:
        # Four local models, none at frontier scale, cannot support a general
        # claim that size does not explain the failure.
        for overreach in (
            "not attributable to model size",
            "not a consequence of model size",
            "model size does not",
        ):
            assert overreach not in prose.lower(), overreach

    def test_the_scoped_replacement_is_present(self, prose) -> None:
        assert "within the locally served models evaluated" in prose

    def test_no_causal_claim_from_the_uncontrolled_holdout_round(
        self, prose, state
    ) -> None:
        if not state["holdout_annotated"]:
            pytest.skip("held-out round not annotated")
        # The held-out round has no untreated control; its kappa must not be
        # presented as evidence the codebook caused the improvement.
        assert "no internal control" in prose
        assert "causal evidence for the codebook remains" in prose


class TestSubmissionGate:
    """The draft must not claim readiness it does not have."""

    def test_incomplete_sections_are_flagged_while_incomplete(self, prose) -> None:
        # References, prior-work comparison and the IRB determination are not
        # written; the draft must say so rather than read as finished.
        assert "TO COMPLETE BEFORE SUBMISSION" in prose

    def test_the_draft_declares_itself_not_submission_ready(self, prose) -> None:
        assert "NOT SUBMISSION READY" in prose
