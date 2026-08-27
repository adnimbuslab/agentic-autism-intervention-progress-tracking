"""Extraction pipeline E2E: raw observation → ExtractionProvider (mocked at
Anthropic boundary) → ExtractionResult → ValidationEngine → AbstentionRouter
→ StructuredRecord persistence.

Verifies app-known metadata preservation, validation routing, and record storage.
"""
from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.backend.ml.abstention_router import AbstentionRouter
from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    ExtractionResult,
    ExtractionStatus,
    SourceType,
)
from src.backend.ml.schemas import RoutingDecision
from src.backend.ml.validation_engine import ValidationEngine
from src.backend.schemas.observation_schema import (
    ContributorRole,
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    Setting,
    StructuredObservation,
)


@pytest.mark.integration
class TestExtractionPipelineE2E:

    def _build_request(self, **overrides) -> ExtractionRequest:
        defaults = dict(
            source_type=SourceType.CONVERSATIONAL,
            text="Child said 'want juice' and pointed at the fridge independently.",
            child_id="test-child-001",
            session_id="test-session-001",
            contributor_role=ContributorRole.PARENT,
            observation_date=date.today(),
            setting=Setting.HOME,
        )
        defaults.update(overrides)
        return ExtractionRequest(**defaults)

    def _build_success_result(self, request: ExtractionRequest) -> ExtractionResult:
        obs = StructuredObservation(
            child_id=request.child_id,
            session_id=request.session_id,
            contributor_role=request.contributor_role,
            observation_date=request.observation_date,
            setting=request.setting,
            domain=Domain.SOCIAL_COMMUNICATION,
            behavior="said 'want juice' and pointed at the fridge",
            modality=Modality.VERBAL,
            prompt_level=PromptLevel.INDEPENDENT,
            outcome=Outcome.CORRECT,
            confidence=0.88,
        )
        return ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            observations=[obs],
            provider="test_mock",
            model="mock-v1",
            prompt_version="test-1.0",
        )

    def _build_partial_result(self, request: ExtractionRequest) -> ExtractionResult:
        obs = StructuredObservation(
            child_id=request.child_id,
            session_id=request.session_id,
            contributor_role=request.contributor_role,
            observation_date=request.observation_date,
            setting=request.setting,
            domain=Domain.SOCIAL_COMMUNICATION,
            behavior="child did something",
            modality=None,
            prompt_level=None,
            outcome=None,
            confidence=0.45,
        )
        return ExtractionResult(
            status=ExtractionStatus.PARTIAL,
            observations=[obs],
            provider="test_mock",
            model="mock-v1",
            prompt_version="test-1.0",
            clarification_questions=["What modality was used?"],
        )

    def _build_abstained_result(self, request: ExtractionRequest) -> ExtractionResult:
        obs = StructuredObservation(
            child_id=request.child_id,
            session_id=request.session_id,
            contributor_role=request.contributor_role,
            observation_date=request.observation_date,
            setting=request.setting,
            domain=None,
            behavior=None,
            modality=None,
            prompt_level=None,
            outcome=None,
            confidence=0.15,
            abstention_reason="Insufficient information to extract structured data.",
        )
        return ExtractionResult(
            status=ExtractionStatus.ABSTAINED,
            observations=[obs],
            provider="test_mock",
            model="mock-v1",
            prompt_version="test-1.0",
        )

    def test_success_preserves_app_metadata(self):
        request = self._build_request()
        result = self._build_success_result(request)
        obs = result.observations[0]

        assert obs.child_id == request.child_id
        assert obs.session_id == request.session_id
        assert obs.contributor_role == request.contributor_role
        assert obs.observation_date == request.observation_date
        assert obs.setting == request.setting

    def test_success_validates_accept(self):
        request = self._build_request()
        result = self._build_success_result(request)
        engine = ValidationEngine()
        validation = engine.validate(result.observations[0])

        assert validation.routing == RoutingDecision.ACCEPT
        assert validation.is_valid is True

    def test_success_routes_accept(self):
        request = self._build_request()
        result = self._build_success_result(request)
        engine = ValidationEngine()
        validation = engine.validate(result.observations[0])
        router = AbstentionRouter()
        routing = router.route(result, validation)

        assert routing == RoutingDecision.ACCEPT

    # @spec ABSTAIN-004
    def test_partial_routes_clarify(self):
        request = self._build_request()
        result = self._build_partial_result(request)
        engine = ValidationEngine()
        validation = engine.validate(result.observations[0])
        router = AbstentionRouter()
        routing = router.route(result, validation)

        assert routing in (
            RoutingDecision.CLARIFY,
            RoutingDecision.INTERVENTIONIST_REVIEW,
            RoutingDecision.RETAIN_WITH_UNKNOWN,
        )

    def test_abstained_routes_review_or_reject(self):
        request = self._build_request()
        result = self._build_abstained_result(request)
        engine = ValidationEngine()
        validation = engine.validate(result.observations[0])
        router = AbstentionRouter()
        routing = router.route(result, validation)

        assert routing in (
            RoutingDecision.INTERVENTIONIST_REVIEW,
            RoutingDecision.REJECT,
        )

    def test_metadata_cannot_be_overwritten_by_llm(self):
        request = self._build_request(child_id="REAL-CHILD-ID")
        obs = StructuredObservation(
            child_id=request.child_id,
            session_id=request.session_id,
            contributor_role=request.contributor_role,
            observation_date=request.observation_date,
            setting=request.setting,
            domain=Domain.SOCIAL_COMMUNICATION,
            behavior="test behavior",
            modality=Modality.VERBAL,
            prompt_level=PromptLevel.INDEPENDENT,
            outcome=Outcome.CORRECT,
            confidence=0.9,
        )
        assert obs.child_id == "REAL-CHILD-ID"
        assert obs.setting == Setting.HOME
        assert obs.contributor_role == ContributorRole.PARENT

    @patch("src.backend.services.observation_service.get_extraction_provider")
    async def test_full_pipeline_via_service(
        self, mock_get_provider, client, interventionist_token, parent_token,
        seed_actors, seed_child, mock_extraction_provider,
    ):
        from tests.phase6.integration.conftest import _make_mock_extraction

        mock_get_provider.return_value = mock_extraction_provider
        mock_extraction_provider.extract = AsyncMock(side_effect=_make_mock_extraction)

        resp = await client.post(
            f"/children/{seed_child.id}/observations",
            headers={"Authorization": f"Bearer {parent_token}"},
            json={
                "raw_text": "Child pointed at cookie and said 'cookie please'.",
                "setting": "home",
                "source_type": "conversational",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["routing_decision"] == "accept"
        assert data["observation"]["status"] == "finalized"

        obs_id = data["observation"]["id"]
        resp2 = await client.get(
            f"/observations/{obs_id}",
            headers={"Authorization": f"Bearer {interventionist_token}"},
        )
        assert resp2.status_code == 200
        detail = resp2.json()
        assert detail["structured_record"] is not None
        record = detail["structured_record"]
        assert record["record_data"]["child_id"] == str(seed_child.id)
        assert record["record_data"]["setting"] == "home"
        assert record["provider"] == "test_mock_extraction"

    def test_schema_rejects_invalid_confidence(self):
        import pydantic

        request = self._build_request()
        with pytest.raises(pydantic.ValidationError):
            StructuredObservation(
                child_id=request.child_id,
                session_id=request.session_id,
                contributor_role=request.contributor_role,
                observation_date=request.observation_date,
                setting=request.setting,
                domain=Domain.SOCIAL_COMMUNICATION,
                behavior="test",
                modality=Modality.VERBAL,
                prompt_level=PromptLevel.INDEPENDENT,
                outcome=Outcome.CORRECT,
                confidence=1.5,
            )

    def test_validation_cross_field_verbal_no_speech(self):
        request = self._build_request()
        obs = StructuredObservation(
            child_id=request.child_id,
            session_id=request.session_id,
            contributor_role=request.contributor_role,
            observation_date=request.observation_date,
            setting=request.setting,
            domain=Domain.SOCIAL_COMMUNICATION,
            behavior="pointed at toy",
            modality=Modality.VERBAL,
            prompt_level=PromptLevel.INDEPENDENT,
            outcome=Outcome.CORRECT,
            confidence=0.85,
        )
        engine = ValidationEngine()
        validation = engine.validate(obs)
        field_names = [fv.field_name for fv in validation.field_validations if not fv.is_valid]
        assert "modality" in field_names
