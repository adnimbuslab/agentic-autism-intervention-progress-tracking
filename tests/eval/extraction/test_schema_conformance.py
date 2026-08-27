from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.backend.ml.extraction.prompts import PROMPT_VERSION
from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    ExtractionResult,
    SourceType,
)
from src.backend.ml.extraction.temporary_llm import TemporaryLLMExtractionProvider
from src.backend.schemas.observation_schema import (
    ContributorRole,
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    Setting,
    StructuredObservation,
)


def _make_request(**overrides: object) -> ExtractionRequest:
    defaults: dict[str, object] = dict(
        source_type=SourceType.CONVERSATIONAL,
        text="Child pointed to the toy and said 'want that' independently.",
        child_id="child_42",
        session_id="sess_007",
        contributor_role=ContributorRole.PARENT,
        observation_date=date(2024, 3, 10),
        setting=Setting.HOME,
    )
    defaults.update(overrides)
    return ExtractionRequest(**defaults)


def _mock_tool_response(**field_overrides: object) -> Mock:
    defaults = {
        "domain": "social_communication",
        "behavior": "Child pointed to toy and said 'want that'",
        "modality": "verbal",
        "prompt_level": "independent",
        "outcome": "correct",
        "confidence": 0.9,
        "goal_context": None,
        "prompt_context": None,
        "duration_seconds": None,
        "abstention_reason": None,
    }
    defaults.update(field_overrides)

    tool_block = Mock()
    tool_block.type = "tool_use"
    tool_block.name = "record_observation"
    tool_block.input = defaults

    response = Mock()
    response.content = [tool_block]
    response.usage = Mock(input_tokens=150, output_tokens=60)
    response.model_dump_json = Mock(return_value='{"mock": true}')
    return response


@pytest.mark.eval
class TestSchemaConformance:
    async def test_result_is_extraction_result(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=_mock_tool_response())

        result = await provider.extract(_make_request())
        assert isinstance(result, ExtractionResult)

    async def test_observations_are_structured(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=_mock_tool_response())

        result = await provider.extract(_make_request())
        assert len(result.observations) == 1
        assert isinstance(result.observations[0], StructuredObservation)

    # @spec EXTRACT-001
    async def test_app_known_fields_preserved(self) -> None:
        request = _make_request(
            child_id="test_child_99",
            session_id="test_sess_42",
            contributor_role=ContributorRole.TEACHER,
            observation_date=date(2025, 6, 1),
            setting=Setting.SCHOOL,
        )
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=_mock_tool_response())

        result = await provider.extract(request)
        obs = result.observations[0]
        assert obs.child_id == "test_child_99"
        assert obs.session_id == "test_sess_42"
        assert obs.contributor_role == ContributorRole.TEACHER
        assert obs.observation_date == date(2025, 6, 1)
        assert obs.setting == Setting.SCHOOL

    async def test_enum_values_valid(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=_mock_tool_response())

        result = await provider.extract(_make_request())
        obs = result.observations[0]
        assert isinstance(obs.domain, Domain)
        assert isinstance(obs.modality, Modality)
        assert isinstance(obs.prompt_level, PromptLevel)
        assert isinstance(obs.outcome, Outcome)

    async def test_provider_metadata_recorded(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=_mock_tool_response())

        result = await provider.extract(_make_request())
        assert result.provider == "temporary_llm_extraction"
        assert result.model == "claude-sonnet-4-20250514"
        assert result.prompt_version == PROMPT_VERSION

    async def test_token_usage_recorded(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=_mock_tool_response())

        result = await provider.extract(_make_request())
        assert result.token_usage is not None
        assert result.token_usage["input_tokens"] == 150
        assert result.token_usage["output_tokens"] == 60

    async def test_extraction_duration_recorded(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=_mock_tool_response())

        result = await provider.extract(_make_request())
        assert result.extraction_duration_ms is not None
        assert result.extraction_duration_ms >= 0

    async def test_raw_llm_response_stored(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=_mock_tool_response())

        result = await provider.extract(_make_request())
        assert result.raw_llm_response is not None

    # @spec EXTRACT-011
    async def test_conversational_source_type(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        mock_create = AsyncMock(return_value=_mock_tool_response())
        provider._client.messages.create = mock_create

        await provider.extract(_make_request(source_type=SourceType.CONVERSATIONAL))
        call_kwargs = mock_create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        user_content = messages[0]["content"]
        assert "contributor observation" in user_content.lower()

    # @spec EXTRACT-011
    async def test_chat_segment_source_type(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        mock_create = AsyncMock(return_value=_mock_tool_response())
        provider._client.messages.create = mock_create

        request = _make_request(
            source_type=SourceType.CHAT_SEGMENT,
            text="*CHI:\txxx .\n%spa:\t$NIA:RP:VNR\n*INV:\tyou want the toy ?",
        )
        await provider.extract(request)
        call_kwargs = mock_create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        user_content = messages[0]["content"]
        assert "CHAT" in user_content
