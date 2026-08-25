"""Deidentification of CHAT session data (Step 3).

Scans utterance text and dependent tier content for residual names and PII,
replacing them with bracketed placeholders. Operates on deep copies so
original Session objects are never mutated.
"""

from __future__ import annotations

import re
from copy import deepcopy

from data.pipeline.models import (
    DeidentificationReport,
    DeidentifiedResult,
    Session,
)

KNOWN_CHILD_NAMES: set[str] = {
    "carl", "roger", "sid", "mars", "josh",
    "jack", "rick", "mark", "brett", "stuart",
}

_LOCATION_PATTERN = re.compile(
    r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Boulevard|Blvd|Lane|Ln|Way|Court|Ct)\b",
    re.IGNORECASE,
)

_DOB_PATTERN = re.compile(
    r"\b(?:\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2})\b"
)

_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")

_PHONE_PATTERN = re.compile(
    r"\b(?:\(\d{3}\)\s*|\d{3}[-.])\d{3}[-.]?\d{4}\b"
)

_AMBIGUOUS_WORDS: set[str] = {"mark", "josh", "jack", "roger", "mars", "rick", "brett", "sid", "carl", "stuart"}

_SAFE_COMMON_WORDS: set[str] = set()


def deidentify_sessions(sessions: list[Session]) -> DeidentifiedResult:
    """Deidentify a list of sessions, returning deep copies with PII replaced."""
    report = DeidentificationReport(total_sessions=len(sessions))
    deidentified: list[Session] = []

    for session in sessions:
        session_copy = deepcopy(session)
        participant_names = _extract_participant_names(session_copy)
        all_names = participant_names | KNOWN_CHILD_NAMES

        name_pattern = _build_name_pattern(all_names)

        for utterance in session_copy.utterances:
            utterance.text, count, flags = _replace_pii(
                utterance.text, name_pattern, session_copy.source_file,
            )
            report.replacement_count += count
            report.flagged_items.extend(flags)

            for tier in utterance.dependent_tiers:
                tier.content, count, flags = _replace_pii(
                    tier.content, name_pattern, session_copy.source_file,
                )
                report.replacement_count += count
                report.flagged_items.extend(flags)

        deidentified.append(session_copy)

    return DeidentifiedResult(sessions=deidentified, report=report)


def _extract_participant_names(session: Session) -> set[str]:
    """Extract participant real names from @Participants and @ID headers."""
    names: set[str] = set()
    for code, role in session.header.participants.items():
        if role not in ("Target_Child", "Investigator", "Mother", "Father", "Unknown"):
            names.add(role.lower())
        for part in role.split("_"):
            if len(part) > 2 and part.lower() not in ("the", "child", "target", "unknown"):
                names.add(part.lower())

    for code, info in session.header.participant_ids.items():
        for key, value in info.items():
            if key == "corpus":
                continue
            for token in value.split():
                if len(token) > 2 and token.isalpha():
                    names.add(token.lower())

    return names


def _build_name_pattern(names: set[str]) -> re.Pattern[str] | None:
    """Build a compiled regex matching any of the given names as whole words."""
    if not names:
        return None
    escaped = [re.escape(name) for name in sorted(names, key=len, reverse=True)]
    return re.compile(r"\b(" + "|".join(escaped) + r")\b", re.IGNORECASE)


def _replace_pii(
    text: str,
    name_pattern: re.Pattern[str] | None,
    source_file: str,
) -> tuple[str, int, list[str]]:
    """Replace PII in text, returning (cleaned_text, replacement_count, flagged_items)."""
    count = 0
    flags: list[str] = []

    if name_pattern:
        matches = list(name_pattern.finditer(text))
        for match in matches:
            matched_word = match.group(0)
            if matched_word.lower() in _AMBIGUOUS_WORDS:
                flags.append(
                    f"Ambiguous name '{matched_word}' in {source_file}: "
                    f"...{text[max(0, match.start()-10):match.end()+10]}..."
                )
        replaced, n = name_pattern.subn("[NAME]", text)
        if n > 0:
            text = replaced
            count += n

    replaced, n = _LOCATION_PATTERN.subn("[LOCATION]", text)
    if n > 0:
        text = replaced
        count += n

    replaced, n = _DOB_PATTERN.subn("[DATE]", text)
    if n > 0:
        text = replaced
        count += n

    replaced, n = _SSN_PATTERN.subn("[SSN]", text)
    if n > 0:
        text = replaced
        count += n

    replaced, n = _PHONE_PATTERN.subn("[PHONE]", text)
    if n > 0:
        text = replaced
        count += n

    return text, count, flags


if __name__ == "__main__":
    print("Deidentification pipeline (Step 3)")
    print("=" * 40)
    print()
    print("Usage:")
    print("  from data.pipeline.chat_parser import parse_chat_file")
    print("  from data.pipeline.deidentify import deidentify_sessions")
    print()
    print("  sessions = [parse_chat_file(path, corpus, child_id)]")
    print("  result = deidentify_sessions(sessions)")
    print("  print(result.report.replacement_count)")
    print("  print(result.report.flagged_items)")
    print("  deidentified_sessions = result.sessions")
    print()
    print("API:")
    print("  deidentify_sessions(sessions: list[Session]) -> DeidentifiedResult")
    print("    - Deep-copies all sessions (originals never mutated)")
    print("    - Replaces known child names with [NAME]")
    print("    - Replaces locations with [LOCATION], dates with [DATE]")
    print("    - Flags ambiguous matches for manual review")
    print("    - Returns DeidentifiedResult with .sessions and .report")
