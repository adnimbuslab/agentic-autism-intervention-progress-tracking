"""The consolidated metrics must agree with the artefacts they are drawn from.

`paper_metrics.json` is a convenience view: it recomputes nothing, so any
disagreement with a source file means this view is stale, not that a result
changed. A stale convenience view is exactly the thing that reaches a
submission, because it is the file someone writes a table from.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

RESULTS = Path(__file__).parent / "results"
METRICS = RESULTS / "paper_metrics.json"


def _require(name: str) -> dict:
    path = RESULTS / name
    if not path.exists():
        pytest.skip(f"{name} not produced yet")
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def metrics() -> dict:
    return _require("paper_metrics.json")


class TestAgreesWithSources:
    def test_reliability_matches_both_rounds(self, metrics) -> None:
        r1, merged = _require("reliability_round1.json"), _require("reliability_current.json")
        assert metrics["annotation"]["reliability"]["round1"]["mean_kappa"] == r1["mean_kappa"]
        assert metrics["annotation"]["reliability"]["merged"]["mean_kappa"] == merged["mean_kappa"]
        for field, entry in metrics["annotation"]["reliability"]["round1"]["per_field"].items():
            assert entry["kappa"] == r1["fields"][field]["kappa"]
            assert entry["kappa_max"] == r1["fields"][field]["kappa_max"]

    def test_the_codebook_deltas_match(self, metrics) -> None:
        comparison = _require("round_comparison.json")
        for field, entry in metrics["annotation"]["codebook_intervention"]["per_field"].items():
            source = comparison["fields"][field]["delta"]
            assert entry["delta"] == source["delta"]
            assert entry["excludes_zero"] == source["excludes_zero"]
            assert entry["arm"] == comparison["fields"][field]["arm"]

    def test_the_gold_composition_matches(self, metrics) -> None:
        gold = _require("gold_labels.json")
        assert metrics["gold_standard"]["n_segments"] == gold["n_segments_in_gold"]
        assert metrics["gold_standard"]["composition"] == gold["counts"]
        assert metrics["gold_standard"]["adjudicator"] == gold["adjudicator"]

    def test_every_extraction_rate_has_its_denominator(self, metrics) -> None:
        scored = _require("scored_against_gold.json")
        for model, per_field in metrics["extraction"]["per_field_accuracy"].items():
            for field, entry in per_field.items():
                counts = scored["per_field_counts"][model]
                total = sum(v for k, v in counts.items() if k.startswith(f"{field}:"))
                assert entry["denominator"] == total
                assert entry["rate"] == pytest.approx(entry["n"] / total, abs=5e-5)

    def test_unsupported_denominators_equal_the_null_gold_counts(self, metrics) -> None:
        gold = _require("gold_labels.json")
        for field, n_null in metrics["gold_standard"]["nulls_per_field"].items():
            recomputed = sum(
                1 for v in gold["gold"].values() if v["field_values"][field] is None
            )
            assert n_null == recomputed
            for per_field in metrics["extraction"]["unsupported_extractions"].values():
                assert per_field[field]["denominator"] == n_null

    def test_the_mars_figures_match(self, metrics) -> None:
        mars = _require("mars_evaluation.json")
        outcomes = metrics["mars"]["outcomes"]
        assert outcomes["n_returned"] == mars["mars"]["n_returned"]
        assert outcomes["coverage"] == mars["mars"]["coverage"]
        assert metrics["mars"]["whole_record_accuracy"]["over_all"] == (
            mars["mars"]["accuracy_over_all"]
        )

    def test_the_selection_figures_match(self, metrics) -> None:
        selection = _require("mars_selection_analysis.json")
        block = metrics["mars"]["selection_quality"]
        assert block["n_judged_segments"] == selection["n_judged_segments"]
        assert block["mean_accuracy"] == selection["mean_accuracy"]
        for field, entry in block["per_field"].items():
            assert entry["vs_best"] == selection["per_field"][field]["vs_best_generator"]

    def test_the_headroom_is_the_stated_arithmetic(self, metrics) -> None:
        w = metrics["extraction"]["whole_record"]
        assert w["headroom"] == pytest.approx(
            w["oracle_ceiling"] - w["best_accuracy"], abs=5e-5
        )


class TestHonesty:
    def test_unmeasured_quantities_are_listed(self, metrics) -> None:
        listed = " ".join(metrics["not_measured"]).lower()
        for expected in ("frontier", "reporting-layer", "usability", "analytics"):
            assert expected in listed, expected

    def test_reporting_groundedness_is_no_longer_listed_as_unmeasured(
        self, metrics
    ) -> None:
        # It was unmeasured only because unconstrained decoding made every
        # generation fall back to the template. Under schema-constrained
        # decoding it is measured, and the list must not still claim otherwise.
        listed = " ".join(metrics["not_measured"]).lower()
        assert "no recorded evaluation artefact" not in listed

    def test_the_frontier_comparison_is_marked_blocked_not_omitted(
        self, metrics
    ) -> None:
        frontier = next(
            item for item in metrics["not_measured"] if "claude" in item.lower()
        )
        assert "blocked" in frontier.lower()
        assert "corpus terms" in frontier.lower() or "irb" in frontier.lower()

    def test_no_frontier_generator_is_present_in_the_results(self, metrics) -> None:
        # Until the corpus-terms question is settled, no claude-* result may
        # appear in the metrics at all.
        models = list(metrics["extraction"]["per_field_accuracy"])
        assert not any("claude" in m.lower() for m in models)

    def test_the_mars_run_was_not_degraded(self, metrics) -> None:
        config = metrics["mars"]["config"]
        assert config["single_judge_ablation"] is False
        assert config["max_judge_discard_rate"] <= 0.05
