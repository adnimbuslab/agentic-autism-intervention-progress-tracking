"""Tests for OllamaExtractionProvider -- OpenAI-compatible (Ollama) sibling
of TemporaryLLMExtractionProvider. Mirrors the Anthropic-backed provider's
existing test coverage, adapted to the OpenAI tool-call response shape."""

from __future__ import annotations

import json
from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest
from openai import APIError

from src.backend.ml.extraction.ollama_llm import OllamaExtractionProvider
from src.backend.ml.extraction.prompts import PROMPT_VERSION
from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    ExtractionResult,
    ExtractionStatus,
    SourceType,
)
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


def _mock_tool_call(name: str, arguments: dict) -> Mock:
    call = Mock()
    call.function = Mock()
    call.function.name = name
    call.function.arguments = json.dumps(arguments)
    return call


def _mock_response(tool_input: dict | None, tool_name: str = "record_observation") -> Mock:
    message = Mock()
    message.tool_calls = [_mock_tool_call(tool_name, tool_input)] if tool_input is not None else []

    choice = Mock()
    choice.message = message

    response = Mock()
    response.choices = [choice]
    response.usage = Mock(prompt_tokens=150, completion_tokens=60)
    response.model_dump_json = Mock(return_value='{"mock": true}')
    return response


def _provider_with_mock(tool_input: dict | None, tool_name: str = "record_observation") -> OllamaExtractionProvider:
    provider = OllamaExtractionProvider(base_url="http://127.0.0.1:11434/v1", api_key="ollama")
    provider._client = Mock()
    provider._client.chat = Mock()
    provider._client.chat.completions = Mock()
    provider._client.chat.completions.create = AsyncMock(return_value=_mock_response(tool_input, tool_name))
    return provider


_FULL_TOOL_INPUT = {
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


class TestSchemaConformance:
    async def test_result_is_extraction_result(self) -> None:
        provider = _provider_with_mock(_FULL_TOOL_INPUT)
        result = await provider.extract(_make_request())
        assert isinstance(result, ExtractionResult)
        assert len(result.observations) == 1
        assert isinstance(result.observations[0], StructuredObservation)

    async def test_app_known_fields_preserved(self) -> None:
        request = _make_request(
            child_id="test_child_99",
            session_id="test_sess_42",
            contributor_role=ContributorRole.TEACHER,
            observation_date=date(2025, 6, 1),
            setting=Setting.SCHOOL,
        )
        provider = _provider_with_mock(_FULL_TOOL_INPUT)
        result = await provider.extract(request)
        obs = result.observations[0]
        assert obs.child_id == "test_child_99"
        assert obs.session_id == "test_sess_42"
        assert obs.contributor_role == ContributorRole.TEACHER
        assert obs.observation_date == date(2025, 6, 1)
        assert obs.setting == Setting.SCHOOL

    async def test_enum_values_valid(self) -> None:
        provider = _provider_with_mock(_FULL_TOOL_INPUT)
        result = await provider.extract(_make_request())
        obs = result.observations[0]
        assert isinstance(obs.domain, Domain)
        assert isinstance(obs.modality, Modality)
        assert isinstance(obs.prompt_level, PromptLevel)
        assert isinstance(obs.outcome, Outcome)

    async def test_provider_metadata_recorded(self) -> None:
        provider = _provider_with_mock(_FULL_TOOL_INPUT)
        result = await provider.extract(_make_request())
        assert result.provider == "ollama_extraction"
        assert result.model == "llama3.2:latest"
        assert result.prompt_version == PROMPT_VERSION

    async def test_token_usage_recorded(self) -> None:
        provider = _provider_with_mock(_FULL_TOOL_INPUT)
        result = await provider.extract(_make_request())
        assert result.token_usage == {"input_tokens": 150, "output_tokens": 60}

    def test_get_info(self) -> None:
        provider = OllamaExtractionProvider(
            base_url="http://127.0.0.1:11434/v1", api_key="ollama", model="llama3.2:latest",
        )
        info = provider.get_info()
        assert info.name == "ollama_extraction"
        assert info.provider_type == "ollama"
        assert info.model_id == "llama3.2:latest"
        assert info.is_available is True


class TestStatusRules:
    async def test_status_success_when_complete(self) -> None:
        provider = _provider_with_mock(_FULL_TOOL_INPUT)
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.SUCCESS

    async def test_status_partial_when_critical_missing(self) -> None:
        tool_input = dict(_FULL_TOOL_INPUT, behavior=None)
        provider = _provider_with_mock(tool_input)
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.PARTIAL

    async def test_status_abstained_low_confidence(self) -> None:
        tool_input = dict(_FULL_TOOL_INPUT, confidence=0.1, abstention_reason="Too vague")
        provider = _provider_with_mock(tool_input)
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.ABSTAINED

    async def test_status_abstained_many_nulls(self) -> None:
        tool_input = {
            "domain": None, "behavior": None, "modality": None, "prompt_level": None,
            "outcome": None, "confidence": 0.8, "goal_context": None,
            "prompt_context": None, "duration_seconds": None,
        }
        provider = _provider_with_mock(tool_input)
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.ABSTAINED

    async def test_null_fields_not_invented(self) -> None:
        tool_input = dict(
            _FULL_TOOL_INPUT, modality=None, prompt_level=None, outcome=None,
        )
        provider = _provider_with_mock(tool_input)
        result = await provider.extract(_make_request())
        obs = result.observations[0]
        assert obs.modality is None
        assert obs.prompt_level is None
        assert obs.outcome is None


class TestFailureHandling:
    async def test_no_tool_call_returns_failed(self) -> None:
        provider = _provider_with_mock(None)
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.FAILED
        assert len(result.observations) == 0

    async def test_wrong_tool_name_returns_failed(self) -> None:
        provider = _provider_with_mock(_FULL_TOOL_INPUT, tool_name="some_other_tool")
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.FAILED

    async def test_api_error_returns_failed(self) -> None:
        provider = OllamaExtractionProvider(base_url="http://127.0.0.1:11434/v1", api_key="ollama")
        provider._client = Mock()
        provider._client.chat = Mock()
        provider._client.chat.completions = Mock()
        provider._client.chat.completions.create = AsyncMock(
            side_effect=APIError("Connection refused", request=Mock(), body=None),
        )
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.FAILED
        assert len(result.observations) == 0


class TestSmallModelSerializationQuirks:
    """Regression tests for real, live-observed behavior from llama3.2:latest
    via Ollama: numeric fields emitted as JSON strings, and "null" emitted
    as a literal string instead of JSON null -- both would otherwise crash
    or fail validation before reaching the abstention rules."""

    async def test_confidence_as_json_string_coerced(self) -> None:
        tool_input = dict(_FULL_TOOL_INPUT, confidence="1.0")
        provider = _provider_with_mock(tool_input)
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.SUCCESS
        assert result.observations[0].confidence == 1.0

    async def test_low_confidence_as_json_string_still_triggers_abstention(self) -> None:
        tool_input = dict(_FULL_TOOL_INPUT, confidence="0.1")
        provider = _provider_with_mock(tool_input)
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.ABSTAINED

    async def test_duration_seconds_null_string_normalized_to_none(self) -> None:
        tool_input = dict(_FULL_TOOL_INPUT, duration_seconds="null")
        provider = _provider_with_mock(tool_input)
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.SUCCESS
        assert result.observations[0].duration_seconds is None

    async def test_all_fields_null_string_triggers_null_threshold_abstention(self) -> None:
        tool_input = {
            "domain": "null", "behavior": "null", "modality": "null",
            "prompt_level": "null", "outcome": "null", "confidence": "0.8",
            "goal_context": "null", "prompt_context": "null", "duration_seconds": "null",
        }
        provider = _provider_with_mock(tool_input)
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.ABSTAINED

    async def test_unknown_extra_field_ignored(self) -> None:
        tool_input = dict(_FULL_TOOL_INPUT, prompts=" prompted")
        provider = _provider_with_mock(tool_input)
        result = await provider.extract(_make_request())
        assert result.status == ExtractionStatus.SUCCESS

    def test_content_fallback_parses_tool_call_json_from_content(self) -> None:
        """Some responses put the tool call JSON in message.content as text
        instead of populating message.tool_calls at all."""
        message = Mock()
        message.tool_calls = None
        message.content = json.dumps({"name": "record_observation", "parameters": _FULL_TOOL_INPUT})
        choice = Mock()
        choice.message = message
        response = Mock()
        response.choices = [choice]

        provider = OllamaExtractionProvider(base_url="http://127.0.0.1:11434/v1", api_key="ollama")
        parsed = provider._parse_tool_response(response)
        assert parsed is not None
        assert parsed["domain"] == "social_communication"

    def test_content_fallback_rejects_unrelated_free_text(self) -> None:
        """Free text that happens to be present must never be misread as a
        tool call -- only exact-shaped JSON is accepted."""
        message = Mock()
        message.tool_calls = None
        message.content = "I cannot help with that request."
        choice = Mock()
        choice.message = message
        response = Mock()
        response.choices = [choice]

        provider = OllamaExtractionProvider(base_url="http://127.0.0.1:11434/v1", api_key="ollama")
        assert provider._parse_tool_response(response) is None


class TestPromptSelection:
    async def test_conversational_source_type(self) -> None:
        provider = _provider_with_mock(_FULL_TOOL_INPUT)
        await provider.extract(_make_request(source_type=SourceType.CONVERSATIONAL))
        call_kwargs = provider._client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        user_content = messages[-1]["content"]
        assert "contributor observation" in user_content.lower()

    async def test_chat_segment_source_type(self) -> None:
        provider = _provider_with_mock(_FULL_TOOL_INPUT)
        request = _make_request(
            source_type=SourceType.CHAT_SEGMENT,
            text="*CHI:\txxx .\n%spa:\t$NIA:RP:VNR\n*INV:\tyou want the toy ?",
        )
        await provider.extract(request)
        call_kwargs = provider._client.chat.completions.create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        user_content = messages[-1]["content"]
        assert "CHAT" in user_content

    async def test_forces_tool_choice(self) -> None:
        provider = _provider_with_mock(_FULL_TOOL_INPUT)
        await provider.extract(_make_request())
        call_kwargs = provider._client.chat.completions.create.call_args
        tool_choice = call_kwargs.kwargs.get("tool_choice") or call_kwargs[1].get("tool_choice")
        assert tool_choice == {"type": "function", "function": {"name": "record_observation"}}
