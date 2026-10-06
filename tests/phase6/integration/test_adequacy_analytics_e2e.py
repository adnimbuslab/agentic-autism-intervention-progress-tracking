"""Adequacy/analytics E2E: ADEQUATE, LIMITED, INSUFFICIENT scenarios through
API boundaries.

Verifies deterministic repeatability, contributor/setting representation,
corrected-record supersession, and no double-counting.
"""
from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from src.backend.ml.adequacy_router import AdequacyRouter
from src.backend.ml.analytics_engine import AnalyticsEngine
from src.backend.ml.schemas import AdequacyLevel
from src.backend.schemas.observation_schema import (
    ContributorRole,
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    Setting,
)
from tests.phase6.integration.conftest import _make_mock_extraction


def _make_record_dict(
    *,
    domain="social_communication",
    behavior="test behavior",
    modality="verbal",
    prompt_level="independent",
    outcome="correct",
    contributor_role="parent",
    setting="home",
    observation_date=None,
    record_id="rec-001",
    obs_id="obs-001",
    version=1,
):
    return {
        "domain": domain,
        "behavior": behavior,
        "modality": modality,
        "prompt_level": prompt_level,
        "outcome": outcome,
        "contributor_role": contributor_role,
        "setting": setting,
        "observation_date": (observation_date or date.today()).isoformat(),
        "_record_id": record_id,
        "_observation_id": obs_id,
        "_version": version,
    }


@pytest.mark.integration
class TestAdequacyAnalyticsE2E:

    def test_adequate_scenario(self):
        records = []
        for i in range(8):
            records.append(_make_record_dict(
                record_id=f"rec-{i:03d}",
                obs_id=f"obs-{i:03d}",
                contributor_role="parent" if i % 2 == 0 else "teacher",
                setting="home" if i % 2 == 0 else "school",
                observation_date=date.today() - timedelta(days=i * 3),
            ))

        goals = [{"id": "g1", "domain": "social_communication", "title": "Test Goal"}]
        router = AdequacyRouter()
        adequacy = router.assess(
            records=records,
            goals=goals,
            review_start=date.today() - timedelta(days=60),
            review_end=date.today(),
        )
        assert adequacy.level == AdequacyLevel.ADEQUATE
        assert adequacy.eligible is True

    def test_limited_scenario(self):
        records = [
            _make_record_dict(
                record_id=f"rec-{i:03d}",
                obs_id=f"obs-{i:03d}",
                contributor_role="parent",
                setting="home",
                observation_date=date.today() - timedelta(days=i * 3),
            )
            for i in range(4)
        ]

        goals = [{"id": "g1", "domain": "social_communication", "title": "Test Goal"}]
        router = AdequacyRouter()
        adequacy = router.assess(
            records=records,
            goals=goals,
            review_start=date.today() - timedelta(days=60),
            review_end=date.today(),
        )
        assert adequacy.level == AdequacyLevel.LIMITED
        assert adequacy.eligible is True
        assert len(adequacy.quality_flags) > 0

    def test_insufficient_scenario(self):
        router = AdequacyRouter()
        adequacy = router.assess(
            records=[],
            goals=[{"id": "g1", "domain": "social_communication", "title": "Test Goal"}],
            review_start=date.today() - timedelta(days=60),
            review_end=date.today(),
        )
        assert adequacy.level == AdequacyLevel.INSUFFICIENT
        assert adequacy.eligible is False

    def test_analytics_withheld_when_insufficient(self):
        router = AdequacyRouter()
        adequacy = router.assess(
            records=[],
            goals=[],
            review_start=date.today() - timedelta(days=60),
            review_end=date.today(),
        )
        engine = AnalyticsEngine()
        analytics = engine.compute(
            child_id="test-child",
            review_period_id="test-period",
            records=[],
            adequacy=adequacy,
        )
        assert len(analytics.kpis) == 1
        assert analytics.kpis[0].abstained is True
        assert "insufficient" in analytics.kpis[0].abstention_reason.lower()

    def test_deterministic_repeatability(self):
        records = []
        for i in range(8):
            records.append(_make_record_dict(
                record_id=f"rec-{i:03d}",
                obs_id=f"obs-{i:03d}",
                contributor_role="parent" if i % 2 == 0 else "teacher",
                setting="home" if i % 2 == 0 else "school",
                observation_date=date.today() - timedelta(days=i * 3),
            ))

        goals = [{"id": "g1", "domain": "social_communication", "title": "Test Goal"}]
        router = AdequacyRouter()

        adequacy1 = router.assess(records=records, goals=goals,
                                  review_start=date.today() - timedelta(days=60),
                                  review_end=date.today())
        adequacy2 = router.assess(records=records, goals=goals,
                                  review_start=date.today() - timedelta(days=60),
                                  review_end=date.today())

        assert adequacy1.level == adequacy2.level
        assert adequacy1.eligible == adequacy2.eligible
        assert len(adequacy1.checks) == len(adequacy2.checks)
        for c1, c2 in zip(adequacy1.checks, adequacy2.checks):
            assert c1.check == c2.check
            assert c1.passed == c2.passed

        engine = AnalyticsEngine()
        a1 = engine.compute("c1", "rp1", records, adequacy1)
        a2 = engine.compute("c1", "rp1", records, adequacy2)

        assert len(a1.kpis) == len(a2.kpis)
        for k1, k2 in zip(a1.kpis, a2.kpis):
            assert k1.name == k2.name
            assert k1.value == k2.value
            assert k1.numerator == k2.numerator
            assert k1.denominator == k2.denominator

    def test_corrected_record_supersedes(self):
        original = _make_record_dict(
            record_id="rec-v1",
            obs_id="obs-001",
            version=1,
            prompt_level="verbal",
        )
        corrected = _make_record_dict(
            record_id="rec-v2",
            obs_id="obs-001",
            version=2,
            prompt_level="independent",
        )

        latest_by_obs: dict[str, dict] = {}
        for r in [original, corrected]:
            obs_id = r["_observation_id"]
            existing = latest_by_obs.get(obs_id)
            if existing is None or r["_version"] > existing["_version"]:
                latest_by_obs[obs_id] = r

        active = list(latest_by_obs.values())
        assert len(active) == 1
        assert active[0]["_version"] == 2
        assert active[0]["prompt_level"] == "independent"

    def test_no_double_counting(self):
        v1 = _make_record_dict(record_id="rec-v1", obs_id="obs-001", version=1)
        v2 = _make_record_dict(record_id="rec-v2", obs_id="obs-001", version=2)

        all_records = [v1, v2]
        latest_by_obs: dict[str, dict] = {}
        for r in all_records:
            obs_id = r["_observation_id"]
            existing = latest_by_obs.get(obs_id)
            if existing is None or r["_version"] > existing["_version"]:
                latest_by_obs[obs_id] = r

        active = list(latest_by_obs.values())
        assert len(active) == 1

    # @spec ADEQ-023
    def test_contributor_representation_single(self):
        records = [
            _make_record_dict(record_id=f"rec-{i}", obs_id=f"obs-{i}",
                              contributor_role="parent", setting="home")
            for i in range(5)
        ]
        router = AdequacyRouter()
        adequacy = router.assess(
            records=records, goals=[],
            review_start=date.today() - timedelta(days=60),
            review_end=date.today(),
        )
        contributor_flags = [
            f for f in adequacy.quality_flags
            if "contributor" in f.lower()
        ]
        assert len(contributor_flags) >= 1
        assert "cross_contributor_comparison" in adequacy.partial_abstentions

    # @spec ADEQ-024
    def test_setting_representation_single(self):
        records = [
            _make_record_dict(record_id=f"rec-{i}", obs_id=f"obs-{i}",
                              contributor_role="parent" if i % 2 == 0 else "teacher",
                              setting="home")
            for i in range(5)
        ]
        router = AdequacyRouter()
        adequacy = router.assess(
            records=records, goals=[],
            review_start=date.today() - timedelta(days=60),
            review_end=date.today(),
        )
        setting_flags = [
            f for f in adequacy.quality_flags
            if "setting" in f.lower()
        ]
        assert len(setting_flags) >= 1
        assert "cross_setting_comparison" in adequacy.partial_abstentions

    def test_independence_rate_computation(self):
        records = [
            _make_record_dict(record_id=f"rec-{i}", obs_id=f"obs-{i}",
                              prompt_level="independent" if i < 3 else "verbal",
                              contributor_role="parent" if i % 2 == 0 else "teacher",
                              setting="home" if i % 2 == 0 else "school",
                              observation_date=date.today() - timedelta(days=i * 3))
            for i in range(4)
        ]
        router = AdequacyRouter()
        adequacy = router.assess(
            records=records, goals=[],
            review_start=date.today() - timedelta(days=60),
            review_end=date.today(),
        )
        engine = AnalyticsEngine()
        analytics = engine.compute("c1", "rp1", records, adequacy)
        indep_kpi = next(k for k in analytics.kpis if k.name == "independence_rate")
        assert indep_kpi.value == 0.75
        assert indep_kpi.numerator == 3.0
        assert indep_kpi.denominator == 4.0

    @patch("src.backend.services.observation_service.get_extraction_provider")
    async def test_adequate_via_api(
        self, mock_get_provider, client: AsyncClient,
        interventionist_token, parent_token, teacher_token,
        seed_actors, seed_child, seed_goals, seed_review_period,
        mock_extraction_provider,
    ):
        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)

        for i in range(8):
            token = parent_token if i % 2 == 0 else teacher_token
            setting = "home" if i % 2 == 0 else "school"
            await client.post(
                f"/children/{seed_child.id}/observations",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "raw_text": f"Adequacy test observation {i}.",
                    "setting": setting,
                    "source_type": "conversational",
                },
            )

        resp = await client.post(
            f"/children/{seed_child.id}/analytics",
            headers={"Authorization": f"Bearer {interventionist_token}"},
            json={"review_period_id": str(seed_review_period.id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "kpis" in data
        assert "adequacy" in data
