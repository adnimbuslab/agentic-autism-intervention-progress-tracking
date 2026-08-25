"""CHAT transcript (.cha) file parser.

Parses CHAT-formatted files into structured Session objects with headers,
utterances, and dependent tiers linked to parent utterances.

Reference: CHAT Transcription Format (MacWhinney, 2000)
- Headers: lines starting with @
- Utterances: lines starting with * (e.g., *CHI:, *INV:, *MOT:)
- Dependent tiers: lines starting with % (e.g., %spa:, %act:, %gpx:)
- Continuation lines: start with a tab character
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Optional

from data.pipeline.models import DependentTier, Session, SessionHeader, Utterance


def parse_chat_file(file_path: Path, corpus: str, child_id: str) -> Session:
    """Parse a single .cha file into a Session object."""
    text = file_path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    header = _parse_headers(lines)
    utterances = _parse_utterances(lines)

    return Session(
        source_file=file_path.name,
        corpus=corpus,
        child_id=child_id,
        header=header,
        utterances=utterances,
    )


def _parse_headers(lines: list[str]) -> SessionHeader:
    """Extract header metadata from @ lines."""
    header = SessionHeader()

    for line in lines:
        line = line.strip()
        if not line.startswith("@"):
            continue

        if line.startswith("@Begin") or line.startswith("@End") or line.startswith("@UTF8"):
            continue

        match = re.match(r"@(\w+):\s*(.*)", line)
        if not match:
            continue

        key, value = match.group(1), match.group(2).strip()
        header.raw_headers[key] = value

        if key == "Participants":
            header.participants = _parse_participants(value)
        elif key == "ID":
            _parse_id_line(value, header)
        elif key == "Date":
            header.date = _parse_date(value)
        elif key == "Languages":
            header.languages = [lang.strip() for lang in value.split(",")]
        elif key == "Location":
            header.location = value
        elif key == "Situation":
            header.situation = value

    return header


def _parse_participants(value: str) -> dict[str, str]:
    """Parse @Participants line into {code: role} dict."""
    participants: dict[str, str] = {}
    for entry in value.split(","):
        entry = entry.strip()
        parts = entry.split()
        if len(parts) >= 2:
            code = parts[0]
            role = parts[-1]
            participants[code] = role
        elif parts:
            participants[parts[0]] = "Unknown"
    return participants


def _parse_id_line(value: str, header: SessionHeader) -> None:
    """Parse @ID line: lang|corpus|code|age|sex|..."""
    parts = value.split("|")
    if len(parts) >= 3:
        code = parts[2].strip()
        info: dict[str, str] = {}
        if len(parts) > 0 and parts[0].strip():
            info["language"] = parts[0].strip()
        if len(parts) > 1 and parts[1].strip():
            info["corpus"] = parts[1].strip()
        if len(parts) > 3 and parts[3].strip():
            info["age"] = parts[3].strip()
        if len(parts) > 4 and parts[4].strip():
            info["sex"] = parts[4].strip()
        if code:
            header.participant_ids[code] = info


def _parse_date(value: str) -> Optional[date]:
    """Parse CHAT date formats: DD-MMM-YYYY or other variants."""
    months = {
        "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
    }

    match = re.match(r"(\d{1,2})-([A-Z]{3})-(\d{4})", value)
    if match:
        day, month_str, year = match.groups()
        month = months.get(month_str.upper())
        if month:
            try:
                return date(int(year), month, int(day))
            except ValueError:
                return None

    match = re.match(r"(\d{4})-(\d{2})-(\d{2})", value)
    if match:
        try:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        except ValueError:
            return None

    return None


def _parse_utterances(lines: list[str]) -> list[Utterance]:
    """Parse utterance lines (*SPK:) and dependent tiers (%tier:)."""
    utterances: list[Utterance] = []
    current_utterance: Optional[Utterance] = None
    current_tier_type: Optional[str] = None
    current_tier_content: list[str] = []

    for line_number, line in enumerate(lines, start=1):
        if line.startswith("@"):
            continue

        if line.startswith("*"):
            _flush_tier(current_utterance, current_tier_type, current_tier_content)
            current_tier_type = None
            current_tier_content = []

            match = re.match(r"\*(\w+):\s*(.*)", line)
            if match:
                speaker = match.group(1)
                text = match.group(2).strip()
                current_utterance = Utterance(
                    speaker=speaker,
                    text=text,
                    line_number=line_number,
                )
                utterances.append(current_utterance)

        elif line.startswith("%"):
            _flush_tier(current_utterance, current_tier_type, current_tier_content)

            match = re.match(r"%(\w+):\s*(.*)", line)
            if match:
                current_tier_type = match.group(1)
                current_tier_content = [match.group(2).strip()]
            else:
                current_tier_type = None
                current_tier_content = []

        elif line.startswith("\t") and current_utterance is not None:
            continuation = line.strip()
            if current_tier_type is not None:
                current_tier_content.append(continuation)
            else:
                current_utterance.text += " " + continuation

    _flush_tier(current_utterance, current_tier_type, current_tier_content)

    return utterances


def _flush_tier(
    utterance: Optional[Utterance],
    tier_type: Optional[str],
    tier_content: list[str],
) -> None:
    """Attach accumulated tier content to the parent utterance."""
    if utterance is not None and tier_type is not None and tier_content:
        utterance.dependent_tiers.append(
            DependentTier(
                tier_type=tier_type,
                content=" ".join(tier_content),
            )
        )


def parse_corpus_directory(
    corpus_dir: Path,
    corpus_name: str,
    child_map: dict[str, list[str]],
) -> list[Session]:
    """Parse all .cha files in a corpus directory.

    Args:
        corpus_dir: Path to the corpus directory containing .cha files.
        corpus_name: Name of the corpus (e.g., "rollins", "flusberg").
        child_map: Mapping of child_id to list of filename patterns that
                   belong to that child.

    Returns:
        List of parsed Session objects.
    """
    sessions: list[Session] = []
    cha_files = sorted(corpus_dir.glob("**/*.cha"))

    for cha_file in cha_files:
        child_id = _match_child(cha_file.name, child_map)
        if child_id is None:
            child_id = "unknown"

        session = parse_chat_file(cha_file, corpus_name, child_id)
        sessions.append(session)

    return sessions


def _match_child(filename: str, child_map: dict[str, list[str]]) -> Optional[str]:
    """Match a filename to a child_id using the child_map patterns."""
    filename_lower = filename.lower()
    for child_id, patterns in child_map.items():
        for pattern in patterns:
            if pattern.lower() in filename_lower:
                return child_id
    return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m data.pipeline.chat_parser <path-to-cha-file>")
        sys.exit(1)

    path = Path(sys.argv[1])
    if path.is_file():
        session = parse_chat_file(path, corpus="test", child_id="test")
        print(f"Parsed: {session.source_file}")
        print(f"  Participants: {session.header.participants}")
        print(f"  Date: {session.header.date}")
        print(f"  Utterances: {session.utterance_count}")
        for utt in session.utterances[:5]:
            print(f"    *{utt.speaker}: {utt.text[:80]}")
            for tier in utt.dependent_tiers:
                print(f"      %{tier.tier_type}: {tier.content[:60]}")
    elif path.is_dir():
        cha_files = list(path.glob("**/*.cha"))
        print(f"Found {len(cha_files)} .cha files in {path}")
        for f in cha_files[:5]:
            session = parse_chat_file(f, corpus="test", child_id="test")
            print(f"  {f.name}: {session.utterance_count} utterances")
