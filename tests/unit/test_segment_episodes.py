"""Tests for the episode segmentation pipeline (Step 4)."""

from __future__ import annotations

from data.pipeline.models import (
    DependentTier,
    EpisodeType,
    Session,
    SessionHeader,
    Utterance,
)
from data.pipeline.segment_episodes import segment_sessions


def _make_session(
    utterances: list[Utterance],
    child_id: str = "carl",
    corpus: str = "rollins",
    source_file: str = "test.cha",
) -> Session:
    return Session(
        source_file=source_file,
        corpus=corpus,
        child_id=child_id,
        header=SessionHeader(
            participants={"CHI": "Target_Child", "INV": "Investigator"},
        ),
        utterances=utterances,
    )


def _utt(speaker: str, text: str, line: int, tiers: list[DependentTier] | None = None) -> Utterance:
    return Utterance(
        speaker=speaker,
        text=text,
        line_number=line,
        dependent_tiers=tiers or [],
    )


class TestSegmentEpisodes:
    def test_episode_size_bounds(self) -> None:
        utterances = [
            _utt("INV", "what do you want?", 1, [DependentTier(tier_type="spa", content="$q:a")]),
            _utt("CHI", "I want cookie .", 2, [DependentTier(tier_type="spa", content="$r:a REQ")]),
            _utt("INV", "ok here you go .", 3, [DependentTier(tier_type="spa", content="$c:a")]),
            _utt("CHI", "thank you .", 4, [DependentTier(tier_type="spa", content="$r:a")]),
        ]
        session = _make_session(utterances)
        episodes = segment_sessions([session])
        for ep in episodes:
            assert 2 <= len(ep.utterances) <= 8

    def test_child_involvement(self) -> None:
        utterances = [
            _utt("INV", "look at this .", 1, [DependentTier(tier_type="spa", content="$c:a")]),
            _utt("CHI", "wow .", 2, [DependentTier(tier_type="spa", content="$r:a")]),
            _utt("INV", "do you like it?", 3, [DependentTier(tier_type="spa", content="$q:a")]),
            _utt("CHI", "yes .", 4, [DependentTier(tier_type="spa", content="$r:a AN")]),
        ]
        session = _make_session(utterances)
        episodes = segment_sessions([session])
        for ep in episodes:
            speakers = [u.speaker for u in ep.utterances]
            assert "CHI" in speakers

    def test_episode_type_tagging(self) -> None:
        request_utts = [
            _utt("INV", "what do you need?", 1, [DependentTier(tier_type="spa", content="$q:a QN")]),
            _utt("CHI", "I want juice .", 2, [DependentTier(tier_type="spa", content="$r:a REQ")]),
            _utt("INV", "here is juice .", 3),
        ]
        session = _make_session(request_utts)
        episodes = segment_sessions([session])
        assert len(episodes) > 0
        assert episodes[0].episode_type == EpisodeType.REQUEST

    def test_empty_session_no_episodes(self) -> None:
        session = _make_session(utterances=[])
        episodes = segment_sessions([session])
        assert episodes == []

    def test_episode_id_format(self) -> None:
        utterances = [
            _utt("INV", "hello .", 1, [DependentTier(tier_type="spa", content="$c:a")]),
            _utt("CHI", "hi .", 2, [DependentTier(tier_type="spa", content="$r:a")]),
            _utt("INV", "how are you?", 3),
            _utt("CHI", "good .", 4),
        ]
        session = _make_session(utterances, child_id="carl")
        episodes = segment_sessions([session])
        assert len(episodes) > 0
        for ep in episodes:
            assert ep.episode_id.startswith("carl_")
            assert "_ep_" in ep.episode_id
            parts = ep.episode_id.split("_ep_")
            assert len(parts[-1]) == 3
            assert parts[-1].isdigit()

    def test_behavioral_annotation_required(self) -> None:
        bare_utts = [
            _utt("INV", "hello .", 1),
            _utt("CHI", "hi .", 2),
            _utt("INV", "ok .", 3),
            _utt("CHI", "bye .", 4),
        ]
        annotated_utts = [
            _utt("INV", "what is this?", 10, [DependentTier(tier_type="spa", content="$q:a")]),
            _utt("CHI", "a ball .", 11, [DependentTier(tier_type="spa", content="$r:a AN")]),
            _utt("INV", "good .", 12, [DependentTier(tier_type="spa", content="$c:a")]),
        ]
        bare_session = _make_session(bare_utts, source_file="bare.cha")
        annotated_session = _make_session(annotated_utts, source_file="annotated.cha")

        bare_episodes = segment_sessions([bare_session])
        annotated_episodes = segment_sessions([annotated_session])

        for ep in bare_episodes:
            assert ep.episode_type == EpisodeType.OTHER

        assert len(annotated_episodes) > 0
        assert any(ep.episode_type != EpisodeType.OTHER for ep in annotated_episodes)
