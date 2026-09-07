"""Temporary general-purpose LLM extraction provider using Claude API."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

from anthropic import APIError, AsyncAnthropic

from src.backend.ml.extraction.prompts import (
    EXTRACTION_TOOL_SCHEMA,
    PROMPT_VERSION,
    build_system_prompt,
    build_user_prompt_chat_segment,
    build_user_prompt_conversational,
)
from src.backend.ml.extraction.schemas import (
    ControlConfidenceState,
    ExtractionProvenance,
    ExtractionRequest,
    ExtractionResult,
    ExtractionStatus,
    ProviderInfo,
    SourceType,
)
from src.backend.schemas.observation_schema import (
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    StructuredObservation,
)

_NULL_THRESHOLD = 5
_ABSTENTION_CONFIDENCE = 0.3


class TemporaryLLMExtractionProvider:
    """Extraction provider backed by a general-purpose Claude model."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514") -> None:
        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model

    # @spec EXTRACT-001, EXTRACT-010, EXTRACT-017, EXTRACT-018
    # @spec EXTRACT-020, EXTRACT-021, EXTRACT-022
    async def extract(self, request: ExtractionRequest) -> ExtractionResult:
        """Extract structured observation from source text via Claude tool_use."""
        start_ms = _now_ms()
        try:
            user_prompt = self._build_user_prompt(request)
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=build_system_prompt(),
                messages=[{"role": "user", "content": user_prompt}],
                tools=[EXTRACTION_TOOL_SCHEMA],
                tool_choice={"type": "tool", "name": "record_observation"},
            )

            tool_input = self._parse_tool_response(response)
            if tool_input is None:
                return self._failed_result(
                    "No valid tool_use block in LLM response",
                    raw=self._serialize_response(response),
                    duration_ms=_now_ms() - start_ms,
                )

            observation = self._build_observation(request, tool_input)
            status = self._determine_status(tool_input, observation)

            token_usage = None
            if response.usage:
                token_usage = {
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                }

            # EXTRACT-022: this provider generates directly, so the quantity
            # deterministic validation gates on is the observation's own
            # confidence. Composing providers combine several (MARS-032).
            return ExtractionResult(
                status=status,
                observations=[observation],
                provider=self.get_info().name,
                model=self._model,
                prompt_version=PROMPT_VERSION,
                generated_at=datetime.now(UTC),
                raw_llm_response=self._serialize_response(response),
                extraction_duration_ms=_now_ms() - start_ms,
                token_usage=token_usage,
                control_confidence=observation.confidence,
                control_confidence_state=(
                    ControlConfidenceState.AVAILABLE
                    if observation.confidence is not None
                    else None
                ),
                provenance=ExtractionProvenance(
                    provider_type=self.get_info().name,
                    generator_ids=[self._model],
                    generator_confidence=observation.confidence,
                ),
            )

        except APIError as exc:
            return self._failed_result(
                f"Anthropic API error: {exc.message}",
                duration_ms=_now_ms() - start_ms,
            )
        except Exception as exc:
            return self._failed_result(
                f"Unexpected error: {exc!s}",
                duration_ms=_now_ms() - start_ms,
            )

    def get_info(self) -> ProviderInfo:
        """Return metadata about this provider."""
        return ProviderInfo(
            name="temporary_llm_extraction",
            provider_type="temporary_llm",
            model_id=self._model,
            version=PROMPT_VERSION,
        )

    # @spec EXTRACT-011, EXTRACT-012
    def _build_user_prompt(self, request: ExtractionRequest) -> str:
        history = request.clarification_history or None
        if request.source_type == SourceType.CHAT_SEGMENT:
            return build_user_prompt_chat_segment(request.text, history)
        return build_user_prompt_conversational(request.text, history)

    @staticmethod
    def _parse_tool_response(response: Any) -> dict[str, Any] | None:
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_observation":
                return block.input
        return None

    @staticmethod
    def _build_observation(
        request: ExtractionRequest,
        tool_input: dict[str, Any],
    ) -> StructuredObservation:
        domain_raw = tool_input.get("domain")
        modality_raw = tool_input.get("modality")
        prompt_level_raw = tool_input.get("prompt_level")
        outcome_raw = tool_input.get("outcome")

        return StructuredObservation(
            child_id=request.child_id,
            session_id=request.session_id,
            contributor_role=request.contributor_role,
            observation_date=request.observation_date,
            setting=request.setting,
            domain=Domain(domain_raw) if domain_raw else None,
            goal_context=tool_input.get("goal_context"),
            behavior=tool_input.get("behavior"),
            modality=Modality(modality_raw) if modality_raw else None,
            prompt_context=tool_input.get("prompt_context"),
            prompt_level=PromptLevel(prompt_level_raw) if prompt_level_raw else None,
            outcome=Outcome(outcome_raw) if outcome_raw else None,
            duration_seconds=tool_input.get("duration_seconds"),
            confidence=tool_input.get("confidence"),
            abstention_reason=tool_input.get("abstention_reason"),
        )

    # @spec EXTRACT-013, EXTRACT-014, EXTRACT-015, EXTRACT-016
    @staticmethod
    def _determine_status(
        tool_input: dict[str, Any],
        observation: StructuredObservation,
    ) -> ExtractionStatus:
        confidence = tool_input.get("confidence")
        if confidence is not None and confidence < _ABSTENTION_CONFIDENCE:
            return ExtractionStatus.ABSTAINED

        null_count = sum(
            1
            for field in ("domain", "goal_context", "behavior", "modality",
                          "prompt_context", "prompt_level", "outcome", "duration_seconds")
            if tool_input.get(field) is None
        )
        if null_count >= _NULL_THRESHOLD:
            return ExtractionStatus.ABSTAINED

        has_behavior = observation.behavior is not None
        has_domain = observation.domain is not None
        if has_behavior and has_domain:
            return ExtractionStatus.SUCCESS

        return ExtractionStatus.PARTIAL

    def _failed_result(
        self,
        message: str,
        raw: str | None = None,
        duration_ms: int | None = None,
    ) -> ExtractionResult:
        return ExtractionResult(
            status=ExtractionStatus.FAILED,
            observations=[],
            provider=self.get_info().name,
            model=self._model,
            prompt_version=PROMPT_VERSION,
            generated_at=datetime.now(UTC),
            raw_llm_response=raw,
            extraction_duration_ms=duration_ms,
            clarification_questions=[],
        )

    @staticmethod
    def _serialize_response(response: Any) -> str:
        try:
            return response.model_dump_json()
        except Exception:
            return str(response)


def _now_ms() -> int:
    return int(time.monotonic() * 1000)
