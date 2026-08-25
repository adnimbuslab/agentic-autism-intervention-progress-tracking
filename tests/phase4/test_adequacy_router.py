"""Tests for AdequacyRouter — deterministic evidence sufficiency checks."""

from __future__ import annotations

from datetime import date

import pytest

from src.backend.ml.adequacy_router import AdequacyRouter
from src.backend.ml.schemas import AdequacyLevel


@pytest.fixture
def router() -> AdequacyRouter:
    return AdequacyRouter()


def _records(n: int, **overrides) -> list[dict]:
    base = {
        "behavior": "said hello",
        "domain": "social_communication",
        "outcome": "correct",
        "modality": "verbal",
        "prompt_level": "independent",
        "setting": "home",
        "contributor_role": "parent",
        "observation_date": "2026-06-15",
    }
    results = []
    for i in range(n):
        rec = {**base, **overrides}
        rec["observation_date"] = f"2026-06-{(i % 28) + 1:02d}"
        results.append(rec)
    return results


class TestAdequacyLevel:
    def test_zero_records_insufficient(self, router: AdequacyRouter):
        result = router.assess([], [], date(2026, 6, 1), date(2026, 6, 30))
        assert result.level == AdequacyLevel.INSUFFICIENT
        assert not result.eligible

    def test_below_limited_threshold_insufficient_with_critical_fail(self, router: AdequacyRouter):
        recs = _records(2)
        result = router.assess(recs, [], date(2026, 6, 1), date(2026, 6, 30))
        assert result.level in (AdequacyLevel.INSUFFICIENT, AdequacyLevel.LIMITED)

    def test_five_records_diverse_adequate(self, router: AdequacyRouter):
        recs = _records(3, setting="home", contributor_role="parent")
        recs += _records(2, setting="school", contributor_role="teacher")
        goals = [{"domain": "social_communication"}]
        result = router.assess(recs, goals, date(2026, 6, 1), date(2026, 6, 30))
        assert result.level == AdequacyLevel.ADEQUATE
        assert result.eligible

    def test_single_contributor_limited(self, router: AdequacyRouter):
        recs = _records(5)
        result = router.assess(recs, [], date(2026, 6, 1), date(2026, 6, 30))
        assert "cross_contributor_comparison" in result.partial_abstentions

    def test_single_setting_partial_abstention(self, router: AdequacyRouter):
        recs = _records(5)
        result = router.assess(recs, [], date(2026, 6, 1), date(2026, 6, 30))
        assert "cross_setting_comparison" in result.partial_abstentions


class TestCoverageCheck:
    def test_passes_at_threshold(self, router: AdequacyRouter):
        recs = _records(5)
        result = router.assess(recs, [], date(2026, 6, 1), date(2026, 6, 30))
        coverage = next(c for c in result.checks if c.check.value == "coverage")
        assert coverage.passed

    def test_fails_below_threshold(self, router: AdequacyRouter):
        recs = _records(3)
        result = router.assess(recs, [], date(2026, 6, 1), date(2026, 6, 30))
        coverage = next(c for c in result.checks if c.check.value == "coverage")
        assert not coverage.passed


class TestTemporalDistribution:
    def test_clustered_fails(self, router: AdequacyRouter):
        recs = [
            {**_records(1)[0], "observation_date": "2026-06-15"}
            for _ in range(5)
        ]
        result = router.assess(recs, [], date(2026, 6, 1), date(2026, 6, 30))
        temporal = next(c for c in result.checks if c.check.value == "temporal_distribution")
        assert not temporal.passed

    def test_spread_passes(self, router: AdequacyRouter):
        recs = _records(5)
        result = router.assess(recs, [], date(2026, 6, 1), date(2026, 6, 30))
        temporal = next(c for c in result.checks if c.check.value == "temporal_distribution")
        assert temporal.passed


class TestGoalCoverage:
    def test_no_goals_passes(self, router: AdequacyRouter):
        recs = _records(5)
        result = router.assess(recs, [], date(2026, 6, 1), date(2026, 6, 30))
        goal_check = next(c for c in result.checks if c.check.value == "goal_coverage")
        assert goal_check.passed

    def test_uncovered_goal_domain_fails(self, router: AdequacyRouter):
        recs = _records(5, domain="social_communication")
        goals = [
            {"domain": "social_communication"},
            {"domain": "behavior_regulation"},
            {"domain": "play_skills"},
        ]
        result = router.assess(recs, goals, date(2026, 6, 1), date(2026, 6, 30))
        goal_check = next(c for c in result.checks if c.check.value == "goal_coverage")
        assert not goal_check.passed

    def test_majority_covered_passes(self, router: AdequacyRouter):
        recs = _records(3, domain="social_communication")
        recs += _records(2, domain="behavior_regulation")
        goals = [
            {"domain": "social_communication"},
            {"domain": "behavior_regulation"},
        ]
        result = router.assess(recs, goals, date(2026, 6, 1), date(2026, 6, 30))
        goal_check = next(c for c in result.checks if c.check.value == "goal_coverage")
        assert goal_check.passed


class TestFieldCompleteness:
    def test_complete_records_pass(self, router: AdequacyRouter):
        recs = _records(5)
        result = router.assess(recs, [], date(2026, 6, 1), date(2026, 6, 30))
        fc = next(c for c in result.checks if c.check.value == "field_completeness")
        assert fc.passed

    def test_missing_fields_fail(self, router: AdequacyRouter):
        recs = [{"observation_date": "2026-06-15"} for _ in range(5)]
        result = router.assess(recs, [], date(2026, 6, 1), date(2026, 6, 30))
        fc = next(c for c in result.checks if c.check.value == "field_completeness")
        assert not fc.passed


class TestQualityFlags:
    def test_quality_flags_populated_on_failure(self, router: AdequacyRouter):
        recs = _records(2)
        result = router.assess(recs, [], date(2026, 6, 1), date(2026, 6, 30))
        assert len(result.quality_flags) > 0

    def test_no_quality_flags_when_adequate(self, router: AdequacyRouter):
        recs = _records(3, setting="home", contributor_role="parent")
        recs += _records(2, setting="school", contributor_role="teacher")
        result = router.assess(recs, [], date(2026, 6, 1), date(2026, 6, 30))
        assert len(result.quality_flags) == 0
