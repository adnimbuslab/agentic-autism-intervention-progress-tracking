from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest
from anthropic import APIError

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
        text="Something happened today.",
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


@pytest.mark.eval
class TestProviderAbstention:
    async def test_abstention_reason_preserved(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=_mock_response({
            "domain": None,
            "behavior": None,
            "modality": None,
            "prompt_level": None,
            "outcome": None,
            "confidence": 0.15,
            "abstention_reason": "Observation text lacks behavioral detail",
        }))

        result = await provider.extract(_make_request())
        assert result.observations[0].abstention_reason == "Observation text lacks behavioral detail"

    # @spec EXTRACT-013
    async def test_low_confidence_triggers_abstention_status(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=_mock_response({
            "domain": "language",
            "behavior": "maybe something",
            "modality": None,
            "prompt_level": None,
            "outcome": None,
            "confidence": 0.2,
        }))

        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.ABSTAINED

    async def test_abstained_still_returns_observation(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=_mock_response({
            "domain": "language",
            "behavior": "unclear",
            "modality": None,
            "prompt_level": None,
            "outcome": None,
            "confidence": 0.1,
        }))

        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.ABSTAINED
        assert len(result.observations) == 1

    # @spec EXTRACT-017
    async def test_api_error_returns_failed(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(
            side_effect=APIError(
                message="Rate limited",
                request=Mock(),
                body=None,
            ),
        )

        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.FAILED
        assert len(result.observations) == 0

    # @spec EXTRACT-018
    async def test_no_tool_use_block_returns_failed(self) -> None:
        response = Mock()
        text_block = Mock()
        text_block.type = "text"
        text_block.text = "I cannot extract this."
        response.content = [text_block]
        response.usage = Mock(input_tokens=100, output_tokens=50)
        response.model_dump_json = Mock(return_value='{}')

        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=response)

        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.FAILED
        assert len(result.observations) == 0
