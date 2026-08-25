"""Tests for the deidentification pipeline (Step 3)."""

from __future__ import annotations

from data.pipeline.deidentify import deidentify_sessions
from data.pipeline.models import (
    DependentTier,
    Session,
    SessionHeader,
    Utterance,
)


def _make_session(
    utterances: list[Utterance] | None = None,
    participants: dict[str, str] | None = None,
    source_file: str = "test.cha",
    child_id: str = "carl",
    corpus: str = "rollins",
) -> Session:
    return Session(
        source_file=source_file,
        corpus=corpus,
        child_id=child_id,
        header=SessionHeader(
            participants=participants or {"CHI": "Target_Child", "INV": "Investigator"},
        ),
        utterances=utterances or [],
    )


class TestDeidentify:
    def test_known_names_replaced(self) -> None:
        session = _make_session(
            utterances=[
                Utterance(speaker="INV", text="hello Carl how are you?", line_number=1),
                Utterance(speaker="CHI", text="I am Carl .", line_number=2),
            ],
        )
        result = deidentify_sessions([session])
        for utt in result.sessions[0].utterances:
            assert "Carl" not in utt.text
            assert "[NAME]" in utt.text

    def test_tier_content_deidentified(self) -> None:
        session = _make_session(
            utterances=[
                Utterance(
                    speaker="CHI",
                    text="hi .",
                    line_number=1,
                    dependent_tiers=[
                        DependentTier(tier_type="act", content="Carl reaches for toy"),
                    ],
                ),
            ],
        )
        result = deidentify_sessions([session])
        tier = result.sessions[0].utterances[0].dependent_tiers[0]
        assert "Carl" not in tier.content
        assert "[NAME]" in tier.content

    def test_original_not_mutated(self) -> None:
        session = _make_session(
            utterances=[
                Utterance(speaker="INV", text="hello Carl .", line_number=1),
            ],
        )
        original_text = session.utterances[0].text
        deidentify_sessions([session])
        assert session.utterances[0].text == original_text

    def test_report_counts(self) -> None:
        session = _make_session(
            utterances=[
                Utterance(speaker="INV", text="Carl and Jack play .", line_number=1),
                Utterance(speaker="CHI", text="Carl happy .", line_number=2),
            ],
        )
        result = deidentify_sessions([session])
        assert result.report.replacement_count >= 3

    def test_ambiguous_flagged(self) -> None:
        session = _make_session(
            utterances=[
                Utterance(speaker="INV", text="mark the paper .", line_number=1),
            ],
        )
        result = deidentify_sessions([session])
        assert len(result.report.flagged_items) > 0
        assert any("mark" in flag.lower() for flag in result.report.flagged_items)

    def test_case_insensitive(self) -> None:
        session = _make_session(
            utterances=[
                Utterance(speaker="INV", text="carl CARL Carl .", line_number=1),
            ],
        )
        result = deidentify_sessions([session])
        text = result.sessions[0].utterances[0].text
        assert "carl" not in text.lower()
        assert text.count("[NAME]") == 3

    def test_empty_session(self) -> None:
        session = _make_session(utterances=[])
        result = deidentify_sessions([session])
        assert len(result.sessions) == 1
        assert result.sessions[0].utterances == []
        assert result.report.replacement_count == 0
