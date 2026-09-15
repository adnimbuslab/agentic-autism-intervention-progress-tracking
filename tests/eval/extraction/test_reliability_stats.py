"""Tests for the reliability interval estimates and marginal diagnostics.

The asymptotic variance is the piece most easily got wrong -- it is a long
expression transcribed from a 1969 paper, and a sign error in it produces a
plausible-looking standard error rather than a crash. It is therefore checked
three ways: against a case with an analytic answer, against the bootstrap on a
large sample where the two estimators must converge, and for the monotonicity
that any variance must show.
"""

from __future__ import annotations

import math
import random

import pytest

from tests.eval.extraction.agreement_report import cohens_kappa
from tests.eval.extraction.reliability_stats import (
    _percentile,
    asymptotic_variance,
    bootstrap_kappa,
    delta_kappa,
    field_statistics,
    kappa_max,
    mean_kappa,
)


def _pairs(spec: dict[tuple[str, str], int]) -> list[tuple[str, str]]:
    """Build a paired list from a confusion-matrix cell count spec."""
    out: list[tuple[str, str]] = []
    for (a, b), count in spec.items():
        out.extend([(a, b)] * count)
    return out


class TestKappaMax:
    def test_identical_marginals_permit_a_perfect_kappa(self) -> None:
        # Same marginals, disagreement only in how they are paired up.
        pairs = _pairs({("x", "y"): 10, ("y", "x"): 10})
        assert kappa_max(pairs) == pytest.approx(1.0)

    def test_a_category_one_annotator_never_used_caps_kappa(self) -> None:
        # A uses `none` 40 times; B never does. 40 items disagree by marginal
        # construction before a single transcript is read.
        pairs = _pairs({("none", "gestural"): 40, ("verbal", "verbal"): 60})
        ceiling = kappa_max(pairs)
        assert ceiling is not None and ceiling < 1.0

    def test_the_ceiling_is_never_below_the_estimate(self) -> None:
        rng = random.Random(7)
        values = ["a", "b", "c", "d"]
        for _ in range(50):
            pairs = [
                (rng.choice(values), rng.choice(values)) for _ in range(rng.randint(20, 200))
            ]
            kappa, ceiling = cohens_kappa(pairs), kappa_max(pairs)
            if kappa is not None and ceiling is not None:
                assert ceiling >= kappa - 1e-9

    def test_perfect_agreement_reaches_its_ceiling(self) -> None:
        pairs = _pairs({("a", "a"): 30, ("b", "b"): 20})
        assert kappa_max(pairs) == pytest.approx(1.0)
        assert cohens_kappa(pairs) == pytest.approx(1.0)


class TestAsymptoticVariance:
    def test_perfect_agreement_has_zero_variance(self) -> None:
        # Analytic: with p_o = 1 the bracketed terms cancel exactly.
        pairs = _pairs({("a", "a"): 40, ("b", "b"): 60})
        assert asymptotic_variance(pairs) == pytest.approx(0.0, abs=1e-12)

    def test_it_agrees_with_the_bootstrap_on_a_large_sample(self) -> None:
        # Where the asymptotic approximation is valid, the two estimators must
        # converge. Disagreement here means one of them is wrong.
        rng = random.Random(11)
        pairs: list[tuple[str, str]] = []
        for _ in range(4000):
            truth = rng.choice(["a", "b", "c"])
            first = truth if rng.random() < 0.8 else rng.choice(["a", "b", "c"])
            second = truth if rng.random() < 0.8 else rng.choice(["a", "b", "c"])
            pairs.append((first, second))

        analytic_se = math.sqrt(asymptotic_variance(pairs))
        boot = bootstrap_kappa(pairs, n_boot=600, seed=3)
        boot_se = (boot["upper"] - boot["lower"]) / (2 * 1.959963984540054)
        assert analytic_se == pytest.approx(boot_se, rel=0.15)

    def test_variance_falls_as_the_sample_grows(self) -> None:
        small = _pairs({("a", "a"): 30, ("b", "b"): 20, ("a", "b"): 10, ("b", "a"): 5})
        large = _pairs({("a", "a"): 300, ("b", "b"): 200, ("a", "b"): 100, ("b", "a"): 50})
        assert asymptotic_variance(large) < asymptotic_variance(small)

    def test_the_standard_error_scales_as_one_over_root_n(self) -> None:
        base = {("a", "a"): 30, ("b", "b"): 20, ("a", "b"): 10, ("b", "a"): 5}
        small = math.sqrt(asymptotic_variance(_pairs(base)))
        large = math.sqrt(
            asymptotic_variance(_pairs({k: v * 100 for k, v in base.items()}))
        )
        assert small / large == pytest.approx(10.0, rel=0.02)


class TestBootstrap:
    def test_the_interval_brackets_the_point_estimate(self) -> None:
        pairs = _pairs({("a", "a"): 60, ("b", "b"): 20, ("a", "b"): 15, ("b", "a"): 5})
        kappa = cohens_kappa(pairs)
        boot = bootstrap_kappa(pairs, n_boot=500, seed=1)
        assert boot["lower"] <= kappa <= boot["upper"]

    def test_it_is_reproducible_under_a_fixed_seed(self) -> None:
        pairs = _pairs({("a", "a"): 40, ("b", "b"): 40, ("a", "b"): 20})
        assert bootstrap_kappa(pairs, n_boot=300, seed=5) == bootstrap_kappa(
            pairs, n_boot=300, seed=5
        )

    def test_degenerate_replicates_are_dropped_and_counted(self) -> None:
        # Almost every item in one cell: many resamples collapse to a single
        # category, where kappa is undefined rather than zero.
        pairs = _pairs({("a", "a"): 99, ("a", "b"): 1})
        boot = bootstrap_kappa(pairs, n_boot=200, seed=2)
        assert boot["n_valid"] < boot["n_requested"]

    def test_an_empty_field_yields_no_interval_rather_than_zero(self) -> None:
        boot = bootstrap_kappa([], n_boot=100)
        assert boot["lower"] is None and boot["upper"] is None


class TestDeltaKappa:
    def test_a_round_that_does_not_exist_yields_none_not_a_number(self) -> None:
        before = _pairs({("a", "a"): 50, ("a", "b"): 50})
        assert delta_kappa(before, None) is None

    def test_mismatched_rounds_are_refused(self) -> None:
        before = _pairs({("a", "a"): 50})
        after = _pairs({("a", "a"): 40})
        with pytest.raises(ValueError, match="same items"):
            delta_kappa(before, after)

    def test_a_real_improvement_is_detected_with_an_interval_above_zero(self) -> None:
        before = _pairs({("a", "a"): 50, ("a", "b"): 50})       # kappa 0
        after = _pairs({("a", "a"): 50, ("b", "b"): 45, ("a", "b"): 5})
        result = delta_kappa(before, after, n_boot=400, seed=4)
        assert result["delta"] > 0
        assert result["excludes_zero"] is True

    def test_no_change_gives_an_interval_spanning_zero(self) -> None:
        pairs = _pairs({("a", "a"): 40, ("b", "b"): 30, ("a", "b"): 20, ("b", "a"): 10})
        result = delta_kappa(pairs, list(pairs), n_boot=400, seed=6)
        assert result["delta"] == pytest.approx(0.0)
        assert result["excludes_zero"] is False


class TestPercentile:
    def test_the_median_of_a_known_sequence(self) -> None:
        assert _percentile([1.0, 2.0, 3.0, 4.0, 5.0], 0.5) == pytest.approx(3.0)

    def test_it_interpolates_between_neighbours(self) -> None:
        assert _percentile([0.0, 10.0], 0.25) == pytest.approx(2.5)

    def test_the_extremes_are_the_extremes(self) -> None:
        values = [3.0, 1.0, 2.0]
        assert _percentile(values, 0.0) == 1.0
        assert _percentile(values, 1.0) == 3.0


class TestFieldStatistics:
    def test_it_reports_every_quantity_the_manuscript_table_needs(self) -> None:
        pairs = _pairs({("a", "a"): 60, ("b", "b"): 20, ("a", "b"): 15, ("b", "a"): 5})
        stats = field_statistics(pairs, n_boot=200, seed=1)
        for key in (
            "n", "observed_agreement", "expected_agreement", "kappa",
            "kappa_max", "kappa_over_kappa_max", "bootstrap_ci", "asymptotic_ci",
        ):
            assert stats[key] is not None, key

    def test_the_ratio_to_the_ceiling_is_at_most_one(self) -> None:
        pairs = _pairs({("none", "gestural"): 40, ("verbal", "verbal"): 60})
        stats = field_statistics(pairs, n_boot=100, seed=1)
        assert stats["kappa_over_kappa_max"] <= 1.0 + 1e-9


class TestMeanKappa:
    def test_undefined_fields_are_skipped_not_counted_as_zero(self) -> None:
        per_field = {
            "domain": {"kappa": 0.8},
            "modality": {"kappa": 0.6},
            "prompt_level": {"kappa": None},
            "outcome": {"kappa": 0.4},
        }
        assert mean_kappa(per_field) == pytest.approx(0.6)

    def test_no_defined_field_yields_none(self) -> None:
        assert mean_kappa({"domain": {"kappa": None}}) is None
