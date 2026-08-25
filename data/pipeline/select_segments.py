"""Behavioral segment selection (Step 5).

Selects a diverse, balanced subset of episodes and converts them into
BehavioralSegment objects ready for downstream extraction. Ensures
representation across children, episode types, and corpora.
"""

from __future__ import annotations

import math
from collections import defaultdict

from data.pipeline.models import (
    BehavioralSegment,
    Episode,
    EpisodeType,
    ProvisionalExtraction,
    SegmentSource,
    SegmentTurn,
    Utterance,
)

DEFAULT_MAX_SEGMENTS = 3000


def select_segments(
    episodes: list[Episode],
    max_segments: int = DEFAULT_MAX_SEGMENTS,
) -> list[BehavioralSegment]:
    """Select a balanced subset of episodes and convert to BehavioralSegments."""
    if not episodes:
        return []

    by_child: dict[str, list[Episode]] = defaultdict(list)
    for ep in episodes:
        by_child[ep.child_id].append(ep)

    num_children = len(by_child)
    per_child_cap = math.ceil(max_segments / num_children) if num_children > 0 else max_segments

    selected: list[Episode] = []
    for child_id, child_episodes in by_child.items():
        child_selected = _select_for_child(child_episodes, per_child_cap)
        selected.extend(child_selected)

    if len(selected) > max_segments:
        selected = selected[:max_segments]

    return _convert_to_segments(selected)


def _select_for_child(episodes: list[Episode], cap: int) -> list[Episode]:
    """Select episodes for one child, balanced across episode types."""
    by_type: dict[EpisodeType, list[Episode]] = defaultdict(list)
    for ep in episodes:
        by_type[ep.episode_type].append(ep)

    num_types = len(by_type)
    if num_types == 0:
        return []

    per_type = math.ceil(cap / num_types)

    selected: list[Episode] = []
    for ep_type, type_episodes in by_type.items():
        take = min(per_type, len(type_episodes))
        selected.extend(type_episodes[:take])

    if len(selected) > cap:
        selected = selected[:cap]

    return selected


def _convert_to_segments(episodes: list[Episode]) -> list[BehavioralSegment]:
    """Convert selected episodes into BehavioralSegment objects."""
    segments: list[BehavioralSegment] = []
    child_seq: dict[str, int] = defaultdict(int)

    for ep in episodes:
        key = f"{ep.child_id}_{ep.session_id}"
        child_seq[key] += 1
        seq = child_seq[key]

        turns = [
            _utterance_to_turn(utt) for utt in ep.utterances
        ]

        source = SegmentSource(
            corpus=ep.corpus,
            child_id=ep.child_id,
            session_id=ep.session_id,
            source_file=ep.source_file,
            turns=turns,
        )

        segment = BehavioralSegment(
            segment_id=f"{ep.child_id}_{ep.session_id}_seg_{seq:03d}",
            source=source,
            provisional_extraction=ProvisionalExtraction(),
        )
        segments.append(segment)

    return segments


def _utterance_to_turn(utt: Utterance) -> SegmentTurn:
    """Convert an Utterance into a SegmentTurn with tier annotations."""
    spa = None
    act = None
    gpx = None
    for tier in utt.dependent_tiers:
        if tier.tier_type == "spa":
            spa = tier.content
        elif tier.tier_type == "act":
            act = tier.content
        elif tier.tier_type == "gpx":
            gpx = tier.content

    return SegmentTurn(
        speaker=utt.speaker,
        text=utt.text,
        spa=spa,
        act=act,
        gpx=gpx,
    )


if __name__ == "__main__":
    print("Behavioral segment selection (Step 5)")
    print("=" * 40)
    print()
    print("Usage:")
    print("  from data.pipeline.segment_episodes import segment_sessions")
    print("  from data.pipeline.select_segments import select_segments")
    print()
    print("  episodes = segment_sessions(deidentified_sessions)")
    print("  segments = select_segments(episodes, max_segments=3000)")
    print("  for seg in segments:")
    print("      print(seg.segment_id, len(seg.source.turns))")
    print()
    print("API:")
    print("  select_segments(episodes, max_segments=3000) -> list[BehavioralSegment]")
    print("    - Selects up to max_segments episodes, balanced across children")
    print("    - Each child sampled proportionally across episode types")
    print("    - Converts to BehavioralSegment with SegmentSource and turns")
    print("    - ProvisionalExtraction fields left as null placeholders")
    print("    - Segment IDs: {child_id}_{session_id}_seg_{seq:03d}")
