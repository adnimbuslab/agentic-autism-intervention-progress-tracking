"""Extraction prompt templates and tool schema for Claude API tool_use."""

from __future__ import annotations

from src.backend.schemas.observation_schema import (
    Domain,
    Modality,
    Outcome,
    PromptLevel,
)

PROMPT_VERSION = "1.0.0"

# @spec EXTRACT-019
EXTRACTION_TOOL_SCHEMA: dict = {
    "name": "record_observation",
    "description": "Record a structured behavioral observation extracted from the source text.",
    "input_schema": {
        "type": "object",
        "properties": {
            "domain": {
                "type": ["string", "null"],
                "enum": [None] + [e.value for e in Domain],
                "description": "Developmental domain observed.",
            },
            "goal_context": {
                "type": ["string", "null"],
                "description": "Goal or objective the observation relates to, if identifiable.",
            },
            "behavior": {
                "type": ["string", "null"],
                "description": "Observable behavior the child exhibited, described factually.",
            },
            "modality": {
                "type": ["string", "null"],
                "enum": [None] + [e.value for e in Modality],
                "description": "Communication modality used by the child.",
            },
            "prompt_context": {
                "type": ["string", "null"],
                "description": "Description of the prompt or support provided, if any.",
            },
            "prompt_level": {
                "type": ["string", "null"],
                "enum": [None] + [e.value for e in PromptLevel],
                "description": "Level of prompting provided.",
            },
            "outcome": {
                "type": ["string", "null"],
                "enum": [None] + [e.value for e in Outcome],
                "description": "Result of the child's behavioral attempt.",
            },
            "duration_seconds": {
                "type": ["integer", "null"],
                "minimum": 0,
                "description": "Duration of the observed behavior in seconds, if stated.",
            },
            "confidence": {
                "type": "number",
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Your confidence in the accuracy of this extraction (0.0-1.0).",
            },
            "abstention_reason": {
                "type": ["string", "null"],
                "description": "Reason for low confidence or inability to extract, if applicable.",
            },
        },
        "required": ["domain", "behavior", "modality", "prompt_level", "outcome", "confidence"],
    },
}


# OpenAI-compatible (function-calling) tool schema, derived from
# EXTRACTION_TOOL_SCHEMA above. The Anthropic and OpenAI tool-call shapes
# differ at the envelope level ("input_schema" vs. "function.parameters")
# but both use standard JSON Schema for the body, so the field list is
# reused rather than duplicated -- keeps the two vendor schemas from
# drifting out of sync with each other.
EXTRACTION_TOOL_SCHEMA_OPENAI: dict = {
    "type": "function",
    "function": {
        "name": EXTRACTION_TOOL_SCHEMA["name"],
        "description": EXTRACTION_TOOL_SCHEMA["description"],
        "parameters": EXTRACTION_TOOL_SCHEMA["input_schema"],
    },
}


def build_system_prompt() -> str:
    """System prompt shared by both source types."""
    domain_values = ", ".join(e.value for e in Domain)
    modality_values = ", ".join(e.value for e in Modality)
    prompt_level_values = ", ".join(e.value for e in PromptLevel)
    outcome_values = ", ".join(e.value for e in Outcome)

    return (
        "You are a structured data extraction system for autism intervention behavioral observations. "
        "Your task is to extract structured fields from naturalistic observation text.\n\n"
        "RULES:\n"
        "- Extract ONLY these fields: domain, goal_context, behavior, modality, prompt_context, "
        "prompt_level, outcome, duration_seconds, confidence, abstention_reason\n"
        "- Use null for any field not clearly supported by the source text\n"
        "- NEVER fabricate or infer beyond what the text explicitly states\n"
        "- NEVER provide diagnosis, treatment recommendations, or causal claims\n"
        "- Set confidence (0.0-1.0) reflecting your certainty in the extraction overall\n"
        "- Set abstention_reason when evidence is insufficient for any required field\n\n"
        "VALID ENUM VALUES:\n"
        f"- domain: {domain_values}\n"
        f"- modality: {modality_values}\n"
        f"- prompt_level: {prompt_level_values}\n"
        f"- outcome: {outcome_values}\n\n"
        "If the text is ambiguous, vague, or lacks enough detail for a field, use null rather than guessing. "
        "A low-confidence extraction with abstention_reason is always preferable to a fabricated high-confidence one."
    )


def build_user_prompt_conversational(
    text: str,
    clarification_history: list[dict[str, str]] | None = None,
) -> str:
    """User prompt for conversational observations."""
    parts = [
        "Extract a structured behavioral observation from the following contributor observation.\n\n"
        f"OBSERVATION TEXT:\n{text}"
    ]

    if clarification_history:
        parts.append("\nCLARIFICATION HISTORY:")
        for exchange in clarification_history:
            if "question" in exchange:
                parts.append(f"Q: {exchange['question']}")
            if "answer" in exchange:
                parts.append(f"A: {exchange['answer']}")

    parts.append(
        "\nUse the record_observation tool to record the extracted observation. "
        "Set any field to null if the text does not provide sufficient evidence."
    )

    return "\n".join(parts)


def build_user_prompt_chat_segment(
    text: str,
    clarification_history: list[dict[str, str]] | None = None,
) -> str:
    """User prompt for CHAT transcript segments."""
    parts = [
        "Extract a structured behavioral observation from the following CHAT transcript segment.\n\n"
        "CHAT FORMAT GUIDE:\n"
        "- Speaker codes: CHI (child), INV (investigator), MOT (mother/parent), FAT (father)\n"
        "- Main tier lines start with *SPK:\\t (speaker code followed by tab)\n"
        "- Dependent tiers start with %code:\\t — e.g., %spa (speech act), %act (action), %gpx (gesture)\n"
        "- 'xxx' marks unintelligible speech\n"
        "- '0' on a main tier indicates no verbal production (action-only turn)\n"
        "- '[+ trn]' marks a turn-taking event\n"
        "- Utterances end with a terminator: . (period), ? (question), ! (exclamation)\n\n"
        f"CHAT SEGMENT:\n{text}"
    ]

    if clarification_history:
        parts.append("\nCLARIFICATION HISTORY:")
        for exchange in clarification_history:
            if "question" in exchange:
                parts.append(f"Q: {exchange['question']}")
            if "answer" in exchange:
                parts.append(f"A: {exchange['answer']}")

    parts.append(
        "\nUse the record_observation tool to record the extracted observation. "
        "Set any field to null if the transcript does not provide sufficient evidence."
    )

    return "\n".join(parts)
