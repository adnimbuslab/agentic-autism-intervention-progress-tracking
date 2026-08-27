from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, Mock

import pytest

from src.backend.ml.extraction.prompts import (
    build_user_prompt_chat_segment,
    build_user_prompt_conversational,
)
from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    ExtractionStatus,
    SourceType,
)
from src.backend.ml.extraction.temporary_llm import TemporaryLLMExtractionProvider
from src.backend.schemas.observation_schema import ContributorRole, Setting


def _make_request(**overrides: object) -> ExtractionRequest:
    defaults: dict[str, object] = dict(
        source_type=SourceType.CONVERSATIONAL,
        text="Child did something during play.",
        child_id="child_1",
        session_id="session_1",
        contributor_role=ContributorRole.PARENT,
        observation_date=date(2024, 2, 20),
        setting=Setting.HOME,
    )
    defaults.update(overrides)
    return ExtractionRequest(**defaults)


def _mock_tool_response(tool_input: dict) -> Mock:
    tool_block = Mock()
    tool_block.type = "tool_use"
    tool_block.name = "record_observation"
    tool_block.input = tool_input

    response = Mock()
    response.content = [tool_block]
    response.usage = Mock(input_tokens=200, output_tokens=80)
    response.model_dump_json = Mock(return_value='{}')
    return response


@pytest.mark.eval
class TestClarificationPrompts:
    # @spec EXTRACT-012
    def test_clarification_history_in_conversational_prompt(self) -> None:
        history = [
            {"question": "What did the child do?", "answer": "She pointed at the cookie"},
            {"question": "Was any prompting provided?", "answer": "No, it was independent"},
        ]
        prompt = build_user_prompt_conversational("Child did something", history)
        assert "CLARIFICATION HISTORY" in prompt
        assert "Q: What did the child do?" in prompt
        assert "A: She pointed at the cookie" in prompt
        assert "Q: Was any prompting provided?" in prompt
        assert "A: No, it was independent" in prompt

    # @spec EXTRACT-012
    def test_clarification_history_in_chat_prompt(self) -> None:
        history = [{"question": "What domain?", "answer": "Communication"}]
        prompt = build_user_prompt_chat_segment("*CHI:\txxx .", history)
        assert "CLARIFICATION HISTORY" in prompt
        assert "Q: What domain?" in prompt
        assert "A: Communication" in prompt

    def test_no_history_no_section(self) -> None:
        prompt = build_user_prompt_conversational("Child waved.", None)
        assert "CLARIFICATION HISTORY" not in prompt

    def test_empty_history_no_section(self) -> None:
        prompt = build_user_prompt_conversational("Child waved.", [])
        assert "CLARIFICATION HISTORY" not in prompt


@pytest.mark.eval
class TestClarificationReExtraction:
    async def test_re_extraction_with_clarification_succeeds(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        provider._client.messages.create = AsyncMock(return_value=_mock_tool_response({
            "domain": "social_communication",
            "behavior": "Child pointed at cookie",
            "modality": "gestural",
            "prompt_level": "independent",
            "outcome": "correct",
            "confidence": 0.9,
            "goal_context": None,
            "prompt_context": None,
            "duration_seconds": None,
            "abstention_reason": None,
        }))

        request = _make_request(
            clarification_history=[
                {"question": "What did the child do?", "answer": "She pointed at the cookie"},
            ],
        )
        result = await provider.extract(request)
        assert result.status == ExtractionStatus.SUCCESS
        assert result.observations[0].behavior is not None

    async def test_clarification_history_passed_to_api(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test")
        provider._client = Mock()
        provider._client.messages = Mock()
        mock_create = AsyncMock(return_value=_mock_tool_response({
            "domain": "play",
            "behavior": "stacked blocks",
            "modality": "gestural",
            "prompt_level": "verbal",
            "outcome": "correct",
            "confidence": 0.8,
        }))
        provider._client.messages.create = mock_create

        request = _make_request(
            clarification_history=[
                {"question": "What skill area?", "answer": "Play skills"},
            ],
        )
        await provider.extract(request)

        call_kwargs = mock_create.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs[1].get("messages")
        user_content = messages[0]["content"]
        assert "What skill area?" in user_content
        assert "Play skills" in user_content
