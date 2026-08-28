"""Sample real, deidentified behavioral segments from the Rollins + Flusberg
CHAT corpora for use as a test set in provider comparison, instead of
hand-written sentences.

Not a pytest test -- a data-preparation utility for compare_providers_v2.py.
"""

from __future__ import annotations

import random
from pathlib import Path

from data.pipeline.build_dataset import FLUSBERG_CHILDREN, ROLLINS_CHILDREN
from data.pipeline.chat_parser import parse_corpus_directory
from data.pipeline.deidentify import deidentify_sessions
from data.pipeline.models import BehavioralSegment
from data.pipeline.segment_episodes import segment_sessions
from data.pipeline.select_segments import select_segments

ROLLINS_DIR = Path("extracted_data/data/Rollins")
FLUSBERG_DIR = Path("/tmp/flusberg_extracted")  # unzipped Flusberg.zip


def render_segment_to_chat_text(segment: BehavioralSegment) -> str:
    """Render a BehavioralSegment's turns back into CHAT-format text, the
    same shape TemporaryLLMExtractionProvider/OllamaExtractionProvider
    expect for source_type=chat_segment."""
    lines: list[str] = []
    for turn in segment.source.turns:
        lines.append(f"*{turn.speaker}:\t{turn.text}")
        if turn.spa:
            lines.append(f"%spa:\t{turn.spa}")
        if turn.act:
            lines.append(f"%act:\t{turn.act}")
        if turn.gpx:
            lines.append(f"%gpx:\t{turn.gpx}")
    return "\n".join(lines)


def load_real_segments(max_segments: int = 200) -> list[BehavioralSegment]:
    rollins_sessions = parse_corpus_directory(ROLLINS_DIR, "rollins", ROLLINS_CHILDREN)
    flusberg_sessions = parse_corpus_directory(FLUSBERG_DIR, "flusberg", FLUSBERG_CHILDREN)
    all_sessions = rollins_sessions + flusberg_sessions

    deidentified = deidentify_sessions(all_sessions)
    episodes = segment_sessions(deidentified.sessions)
    segments = select_segments(episodes, max_segments=max_segments)
    return segments


def sample_segments(
    segments: list[BehavioralSegment], n: int, seed: int = 42,
) -> list[BehavioralSegment]:
    """Deterministic sample for reproducibility across runs."""
    rng = random.Random(seed)
    # Filter out segments with no turns or trivially short text (uninformative
    # for extraction comparison either way).
    usable = [
        s for s in segments
        if s.source.turns and len(render_segment_to_chat_text(s)) > 20
    ]
    rng.shuffle(usable)
    return usable[:n]


if __name__ == "__main__":
    segs = load_real_segments()
    print(f"Loaded {len(segs)} real behavioral segments (Rollins + Flusberg, deidentified)")
    sample = sample_segments(segs, n=5)
    for s in sample:
        print("---")
        print(f"segment_id={s.segment_id} corpus={s.source.corpus} child={s.source.child_id}")
        print(render_segment_to_chat_text(s))
