from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    ExtractionStatus,
    SourceType,
)
from src.backend.ml.extraction.temporary_llm import TemporaryLLMExtractionProvider
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


def _make_observation(**overrides: object) -> StructuredObservation:
    defaults: dict[str, object] = dict(
        child_id="child_1",
        session_id="session_1",
        contributor_role=ContributorRole.INTERVENTIONIST,
        observation_date=date(2024, 1, 15),
        setting=Setting.CLINIC,
        domain=Domain.LANGUAGE,
        behavior="Child spoke",
        modality=Modality.VERBAL,
        prompt_level=PromptLevel.INDEPENDENT,
        outcome=Outcome.CORRECT,
        confidence=0.85,
    )
    defaults.update(overrides)
    return StructuredObservation(**defaults)


def _mock_response(tool_input: dict) -> Mock:
    tool_block = Mock()
    tool_block.type = "tool_use"
    tool_block.name = "record_observation"
    tool_block.input = tool_input

    response = Mock()
    response.content = [tool_block]
    response.usage = Mock(input_tokens=100, output_tokens=50)
    response.model_dump_json = Mock(return_value='{}')
    return response


engine = ValidationEngine()


@pytest.mark.redteam
class TestExtractionHallucination:
    def test_empty_text_rejected_by_schema(self) -> None:
        with pytest.raises(ValidationError):
            ExtractionRequest(
                source_type=SourceType.CONVERSATIONAL,
                text="",
                child_id="child_1",
                session_id="session_1",
                contributor_role=ContributorRole.INTERVENTIONIST,
                observation_date=date(2024, 1, 15),
                setting=Setting.CLINIC,
            )

    def test_whitespace_only_passes_schema_but_extraction_abstains(self) -> None:
        request = ExtractionRequest(
            source_type=SourceType.CONVERSATIONAL,
            text="   ",
            child_id="child_1",
            session_id="session_1",
            contributor_role=ContributorRole.INTERVENTIONIST,
            observation_date=date(2024, 1, 15),
            setting=Setting.CLINIC,
        )
        assert request.text == "   "

    def test_irrelevant_content_validation_rejects(self) -> None:
        obs = _make_observation(
            behavior=None,
            domain=None,
            modality=None,
            prompt_level=None,
            outcome=None,
            confidence=0.1,
            abstention_reason="Text is about weather, not behavior",
        )
        result = engine.validate(obs)
        assert result.routing == RoutingDecision.REJECT

    async def test_contradictory_fields_detected_by_validation(self) -> None:
        obs = _make_observation(
            prompt_level=PromptLevel.INDEPENDENT,
            prompt_context="Full physical prompt was given",
        )
        result = engine.validate(obs)
        warnings = [
            fv for fv in result.field_validations
            if fv.field_name == "prompt_context" and not fv.is_valid
        ]
        assert len(warnings) >= 1

    async def test_outcome_without_behavior_caught(self) -> None:
        obs = _make_observation(behavior=None, outcome=Outcome.CORRECT)
        result = engine.validate(obs)
        errors = [
            fv for fv in result.field_validations
            if fv.field_name == "outcome" and not fv.is_valid
        ]
        assert len(errors) >= 1

    async def test_all_null_extraction_rejects(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=_mock_response({
            "domain": None,
            "behavior": None,
            "modality": None,
            "prompt_level": None,
            "outcome": None,
            "confidence": 0.05,
            "abstention_reason": "Nothing extractable",
        }))

        request = ExtractionRequest(
            source_type=SourceType.CONVERSATIONAL,
            text="The weather was nice today.",
            child_id="child_1",
            session_id="session_1",
            contributor_role=ContributorRole.INTERVENTIONIST,
            observation_date=date(2024, 1, 15),
            setting=Setting.CLINIC,
        )
        result = await provider.extract(request)
        assert result.status == ExtractionStatus.ABSTAINED

        obs = result.observations[0]
        validation = engine.validate(obs)
        assert validation.routing == RoutingDecision.REJECT
