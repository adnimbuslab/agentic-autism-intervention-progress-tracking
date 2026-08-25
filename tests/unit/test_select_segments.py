"""Tests for the behavioral segment selection pipeline (Step 5)."""

from __future__ import annotations

from data.pipeline.models import (
    Episode,
    EpisodeType,
    Utterance,
)
from data.pipeline.select_segments import select_segments


def _make_episode(
    child_id: str,
    episode_type: EpisodeType = EpisodeType.REQUEST,
    seq: int = 1,
    corpus: str = "rollins",
) -> Episode:
    session_id = f"{corpus}_{child_id}_test.cha"
    return Episode(
        episode_id=f"{child_id}_{session_id}_ep_{seq:03d}",
        corpus=corpus,
        child_id=child_id,
        session_id=session_id,
        source_file="test.cha",
        episode_type=episode_type,
        utterances=[
            Utterance(speaker="INV", text="what do you want?", line_number=1),
            Utterance(speaker="CHI", text="cookie please .", line_number=2),
        ],
        start_line=1,
        end_line=2,
    )


def _make_episodes_for_children(
    child_ids: list[str],
    episodes_per_child: int = 5,
) -> list[Episode]:
    episodes: list[Episode] = []
    types = list(EpisodeType)
    for child_id in child_ids:
        corpus = "rollins" if child_id in ("carl", "sid", "josh") else "flusberg"
        for i in range(episodes_per_child):
            ep = _make_episode(
                child_id=child_id,
                episode_type=types[i % len(types)],
                seq=i + 1,
                corpus=corpus,
            )
            episodes.append(ep)
    return episodes


class TestSelectSegments:
    def test_all_children_represented(self) -> None:
        child_ids = ["carl", "sid", "jack", "rick", "mark"]
        episodes = _make_episodes_for_children(child_ids, episodes_per_child=10)
        segments = select_segments(episodes, max_segments=100)
        represented = {seg.source.child_id for seg in segments}
        assert represented == set(child_ids)

    def test_segment_format(self) -> None:
        episodes = _make_episodes_for_children(["carl", "sid"], episodes_per_child=5)
        segments = select_segments(episodes, max_segments=50)
        for seg in segments:
            assert seg.segment_id
            assert "_seg_" in seg.segment_id
            assert seg.source.corpus in ("rollins", "flusberg")
            assert seg.source.child_id
            assert seg.source.session_id
            assert seg.source.source_file
            assert len(seg.source.turns) > 0

    def test_provisional_extraction_null(self) -> None:
        episodes = _make_episodes_for_children(["carl"], episodes_per_child=3)
        segments = select_segments(episodes)
        for seg in segments:
            assert seg.provisional_extraction.status == "provisional_llm"
            assert seg.provisional_extraction.structured_record is None
            assert seg.provisional_extraction.provider is None
            assert seg.provisional_extraction.model is None
            assert seg.provisional_extraction.prompt_version is None
            assert seg.provisional_extraction.schema_version is None
            assert seg.provisional_extraction.generated_at is None

    def test_source_provenance(self) -> None:
        episodes = _make_episodes_for_children(["carl"], episodes_per_child=3)
        segments = select_segments(episodes)
        for seg, ep in zip(segments, episodes):
            assert seg.source.corpus == ep.corpus
            assert seg.source.child_id == ep.child_id
            assert seg.source.session_id == ep.session_id
            assert len(seg.source.turns) == len(ep.utterances)
            for turn, utt in zip(seg.source.turns, ep.utterances):
                assert turn.speaker == utt.speaker
                assert turn.text == utt.text

    def test_balanced_selection(self) -> None:
        child_ids = ["carl", "sid", "josh", "jack", "rick"]
        episodes = _make_episodes_for_children(child_ids, episodes_per_child=20)
        segments = select_segments(episodes, max_segments=100)

        counts: dict[str, int] = {}
        for seg in segments:
            counts[seg.source.child_id] = counts.get(seg.source.child_id, 0) + 1

        if len(counts) > 1:
            max_count = max(counts.values())
            min_count = min(counts.values())
            assert max_count <= 2 * min_count + 1
