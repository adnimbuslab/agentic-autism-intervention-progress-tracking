"""Helper for driving TemporaryLLMExtractionProvider with a mocked API call."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, Mock

from src.backend.ml.extraction.schemas import ExtractionRequest, ExtractionResult, SourceType
from src.backend.ml.extraction.temporary_llm import TemporaryLLMExtractionProvider
from src.backend.schemas.observation_schema import ContributorRole, Setting


def _mock_response(tool_input: dict) -> Mock:
    block = Mock()
    block.type = "tool_use"
    block.name = "record_observation"
    block.input = tool_input
    response = Mock()
    response.content = [block]
    response.usage = Mock(input_tokens=100, output_tokens=50)
    response.model_dump_json = Mock(return_value="{}")
    return response


async def extract_with_confidence(confidence: float | None) -> ExtractionResult:
    provider = TemporaryLLMExtractionProvider(api_key="test")
    provider._client = Mock()
    provider._client.messages = Mock()
    provider._client.messages.create = AsyncMock(
        return_value=_mock_response({
            "domain": "social_communication",
            "behavior": "Child pointed to the requested item",
            "modality": "gestural",
            "prompt_level": "independent",
            "outcome": "correct",
            "confidence": confidence,
        })
    )
    return await provider.extract(
        ExtractionRequest(
            source_type=SourceType.CONVERSATIONAL,
            text="Child pointed to the item independently.",
            child_id="child_1",
            session_id="session_1",
            contributor_role=ContributorRole.INTERVENTIONIST,
            observation_date=date(2026, 9, 7),
            setting=Setting.CLINIC,
        )
    )
