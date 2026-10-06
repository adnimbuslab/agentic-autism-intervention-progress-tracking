"""Extraction provider backed by a local model served through Ollama's
OpenAI-compatible API (or any other OpenAI-compatible endpoint), using the
``openai`` Python client instead of the ``anthropic`` client.

Sibling to TemporaryLLMExtractionProvider -- implements the same
ExtractionProvider contract (EXTRACT-002) and the same abstention/status
rules (EXTRACT-013 through EXTRACT-016), reusing the vendor-neutral prompt
builders in prompts.py. The tool-call mechanics differ (OpenAI-style forced
function-calling instead of Anthropic-style forced tool_choice), and the
response shape differs (``choices[0].message.tool_calls`` instead of a
content-block list), which is why this is a separate class rather than a
branch inside TemporaryLLMExtractionProvider.

Not all models served via Ollama reliably honor forced tool_choice --
verify the configured model actually returns a tool call rather than free
text before relying on this in production.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from typing import Any

from openai import APIError, AsyncOpenAI

from src.backend.ml.extraction.prompts import (
    EXTRACTION_TOOL_SCHEMA_OPENAI,
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
_TOOL_NAME = "record_observation"


_NUMERIC_FIELD_COERCERS: dict[str, type] = {"confidence": float, "duration_seconds": int}


def _normalize_null_strings(tool_input: dict[str, Any]) -> dict[str, Any]:
    """Correct two JSON serialization quirks observed live against
    llama3.2:latest via Ollama, despite the tool schema declaring proper
    JSON types for both:

    1. The literal string ``"null"``/``"none"`` (any case) instead of JSON
       ``null`` for absent fields. Left as-is this reaches Pydantic and
       fails validation for typed optional fields (e.g.
       ``duration_seconds: Optional[int]``) instead of being treated as
       genuinely missing.
    2. Numeric fields (``confidence``, ``duration_seconds``) emitted as
       JSON strings (e.g. ``"1"``, ``"1.0"``) instead of numbers. Left
       as-is this crashes the numeric-comparison abstention rules in
       ``_determine_status`` (``confidence < _ABSTENTION_CONFIDENCE`` raises
       ``TypeError`` comparing str to float) before StructuredObservation's
       own Pydantic coercion ever gets a chance to run.

    Neither correction invents or infers a value the model didn't already
    supply -- both reinterpret a value in a technically-wrong-but-unambiguous
    JSON shape.
    """
    normalized: dict[str, Any] = {}
    for key, value in tool_input.items():
        if isinstance(value, str) and value.strip().lower() in ("null", "none"):
            normalized[key] = None
            continue
        coercer = _NUMERIC_FIELD_COERCERS.get(key)
        if coercer is not None and isinstance(value, str):
            try:
                normalized[key] = coercer(float(value))
                continue
            except ValueError:
                pass
        normalized[key] = value
    return normalized


class OllamaExtractionProvider:
    """Extraction provider backed by a local model via an OpenAI-compatible
    endpoint (Ollama by default)."""

    def __init__(self, base_url: str, api_key: str, model: str = "llama3.2:latest") -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model

    # @spec EXTRACT-001, EXTRACT-010, EXTRACT-017, EXTRACT-018
    # @spec EXTRACT-020, EXTRACT-021, EXTRACT-022
    async def extract(self, request: ExtractionRequest) -> ExtractionResult:
        """Extract structured observation from source text via a forced
        OpenAI-style function/tool call."""
        start_ms = _now_ms()
        try:
            user_prompt = self._build_user_prompt(request)
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": build_system_prompt()},
                    {"role": "user", "content": user_prompt},
                ],
                tools=[EXTRACTION_TOOL_SCHEMA_OPENAI],
                tool_choice={"type": "function", "function": {"name": _TOOL_NAME}},
            )

            tool_input = self._parse_tool_response(response)
            if tool_input is None:
                return self._failed_result(
                    "No valid tool call in LLM response",
                    raw=self._serialize_response(response),
                    duration_ms=_now_ms() - start_ms,
                )

            observation = self._build_observation(request, tool_input)
            status = self._determine_status(tool_input, observation)

            token_usage = None
            if response.usage:
                token_usage = {
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
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
                f"OpenAI-compatible API error: {exc.message if hasattr(exc, 'message') else exc!s}",
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
            name="ollama_extraction",
            provider_type="ollama",
            model_id=self._model,
            version=PROMPT_VERSION,
        )

    def _build_user_prompt(self, request: ExtractionRequest) -> str:
        history = request.clarification_history or None
        if request.source_type == SourceType.CHAT_SEGMENT:
            return build_user_prompt_chat_segment(request.text, history)
        return build_user_prompt_conversational(request.text, history)

    @staticmethod
    def _parse_tool_response(response: Any) -> dict[str, Any] | None:
        message = response.choices[0].message

        if message.tool_calls:
            for call in message.tool_calls:
                if call.function.name == _TOOL_NAME:
                    try:
                        return _normalize_null_strings(json.loads(call.function.arguments))
                    except json.JSONDecodeError:
                        return None
            return None

        # Fallback for small local models (observed with llama3.2:latest via
        # Ollama) that do not populate the OpenAI ``tool_calls`` field even
        # under forced tool_choice, and instead write the tool-call JSON as
        # plain text into ``message.content``. Only accept content shaped
        # exactly like the expected tool call -- never fabricate fields from
        # unrelated free text, and never treat an unparsable/mismatched
        # response as anything but "no valid tool call".
        if message.content:
            try:
                parsed = json.loads(message.content)
            except json.JSONDecodeError:
                return None
            if isinstance(parsed, dict) and parsed.get("name") == _TOOL_NAME:
                params = parsed.get("parameters")
                if isinstance(params, dict):
                    return _normalize_null_strings(params)
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
