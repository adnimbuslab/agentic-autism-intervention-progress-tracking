from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest

from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    ExtractionStatus,
    SourceType,
)
from src.backend.ml.extraction.temporary_llm import TemporaryLLMExtractionProvider
from src.backend.schemas.observation_schema import ContributorRole, Setting


def _make_request() -> ExtractionRequest:
    return ExtractionRequest(
        source_type=SourceType.CONVERSATIONAL,
        text="Child did something.",
        child_id="child_1",
        session_id="session_1",
        contributor_role=ContributorRole.INTERVENTIONIST,
        observation_date=date(2024, 1, 15),
        setting=Setting.CLINIC,
    )


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


def _provider_with_mock(tool_input: dict) -> TemporaryLLMExtractionProvider:
    provider = TemporaryLLMExtractionProvider(api_key="test")
    provider._client = Mock()
    provider._client.messages = Mock()
    provider._client.messages.create = AsyncMock(return_value=_mock_response(tool_input))
    return provider


@pytest.mark.eval
class TestUnsupportedFields:
    async def test_null_fields_not_invented(self) -> None:
        provider = _provider_with_mock({
            "domain": "language",
            "behavior": "Child babbled",
            "modality": None,
            "prompt_level": None,
            "outcome": None,
            "confidence": 0.6,
            "goal_context": None,
            "prompt_context": None,
            "duration_seconds": None,
            "abstention_reason": None,
        })
        result = await provider.extract(_make_request())
        obs = result.observations[0]
        assert obs.modality is None
        assert obs.prompt_level is None
        assert obs.outcome is None
        assert obs.goal_context is None
        assert obs.duration_seconds is None

    # @spec EXTRACT-016
    async def test_status_partial_when_critical_missing(self) -> None:
        provider = _provider_with_mock({
            "domain": "language",
            "behavior": None,
            "modality": "verbal",
            "prompt_level": "independent",
            "outcome": "correct",
            "confidence": 0.7,
        })
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.PARTIAL

    # @spec EXTRACT-015
    async def test_status_success_when_complete(self) -> None:
        provider = _provider_with_mock({
            "domain": "social_communication",
            "behavior": "Child pointed",
            "modality": "gestural",
            "prompt_level": "independent",
            "outcome": "correct",
            "confidence": 0.9,
        })
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.SUCCESS

    async def test_status_abstained_low_confidence(self) -> None:
        provider = _provider_with_mock({
            "domain": "language",
            "behavior": "unclear",
            "modality": None,
            "prompt_level": None,
            "outcome": None,
            "confidence": 0.1,
            "abstention_reason": "Text too vague",
        })
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.ABSTAINED

    # @spec EXTRACT-014
    async def test_status_abstained_many_nulls(self) -> None:
        provider = _provider_with_mock({
            "domain": None,
            "behavior": None,
            "modality": None,
            "prompt_level": None,
            "outcome": None,
            "confidence": 0.8,
            "goal_context": None,
            "prompt_context": None,
            "duration_seconds": None,
        })
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.ABSTAINED
