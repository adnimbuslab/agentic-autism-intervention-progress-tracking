"""Tests for the CHAT transcript parser."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from data.pipeline.chat_parser import parse_chat_file, parse_corpus_directory


class TestChatParserHeaders:
    def test_parses_participants(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        assert "CHI" in session.header.participants
        assert "INV" in session.header.participants
        assert session.header.participants["CHI"] == "Target_Child"
        assert session.header.participants["INV"] == "Investigator"

    def test_parses_date_ddmmmyyyy(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        assert session.header.date == date(2000, 1, 15)

    def test_parses_date_iso_format(self, multiline_chat_file: Path) -> None:
        session = parse_chat_file(multiline_chat_file, corpus="flusberg", child_id="test")
        assert session.header.date == date(2001, 3, 15)

    def test_parses_id_lines(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        assert "CHI" in session.header.participant_ids
        chi_info = session.header.participant_ids["CHI"]
        assert chi_info["age"] == "3;6.15"
        assert chi_info["sex"] == "male"

    def test_parses_language(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        assert "eng" in session.header.languages

    def test_parses_location(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        assert session.header.location == "Lab"

    def test_preserves_corpus_and_child_id(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="carl")
        assert session.corpus == "rollins"
        assert session.child_id == "carl"

    def test_preserves_source_file(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        assert session.source_file == "test_session.cha"


class TestChatParserUtterances:
    def test_parses_correct_utterance_count(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        assert session.utterance_count == 6

    def test_parses_speaker_codes(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        speakers = [u.speaker for u in session.utterances]
        assert speakers == ["INV", "CHI", "INV", "CHI", "CHI", "CHI"]

    def test_parses_utterance_text(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        assert session.utterances[0].text == "what are you doing ?"
        assert session.utterances[1].text == "I play with car ."

    def test_handles_xxx_marker(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        assert session.utterances[3].text == "xxx ."

    def test_handles_zero_utterance(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        assert session.utterances[4].text == "0 ."

    def test_handles_special_markers(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        assert "[+ trn]" in session.utterances[5].text

    def test_handles_multiline_utterances(self, multiline_chat_file: Path) -> None:
        session = parse_chat_file(multiline_chat_file, corpus="flusberg", child_id="test")
        assert "at school today ?" in session.utterances[0].text
        assert "I played on the swings ." in session.utterances[1].text

    def test_tracks_line_numbers(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        assert session.utterances[0].line_number > 0
        for i in range(1, len(session.utterances)):
            assert session.utterances[i].line_number > session.utterances[i - 1].line_number


class TestChatParserDependentTiers:
    def test_links_spa_tier_to_utterance(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        inv_utterance = session.utterances[0]
        spa_tiers = [t for t in inv_utterance.dependent_tiers if t.tier_type == "spa"]
        assert len(spa_tiers) == 1
        assert "$q:a" in spa_tiers[0].content

    def test_links_multiple_tiers_to_utterance(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        chi_utterance = session.utterances[1]
        tier_types = {t.tier_type for t in chi_utterance.dependent_tiers}
        assert tier_types == {"spa", "act", "gpx"}

    def test_act_tier_content(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        chi_utterance = session.utterances[1]
        act_tiers = [t for t in chi_utterance.dependent_tiers if t.tier_type == "act"]
        assert len(act_tiers) == 1
        assert "picks up toy car" in act_tiers[0].content

    def test_multiline_tier_content(self, multiline_chat_file: Path) -> None:
        session = parse_chat_file(multiline_chat_file, corpus="flusberg", child_id="test")
        chi_utterance = session.utterances[1]
        act_tiers = [t for t in chi_utterance.dependent_tiers if t.tier_type == "act"]
        assert len(act_tiers) == 1
        assert "gestures toward window" in act_tiers[0].content

    def test_utterance_without_tiers(self, sample_chat_file: Path) -> None:
        session = parse_chat_file(sample_chat_file, corpus="rollins", child_id="test")
        xxx_utterance = session.utterances[3]
        assert len(xxx_utterance.dependent_tiers) == 0


class TestChatParserEdgeCases:
    def test_minimal_file(self, minimal_chat_file: Path) -> None:
        session = parse_chat_file(minimal_chat_file, corpus="test", child_id="test")
        assert session.utterance_count == 1
        assert session.utterances[0].speaker == "CHI"
        assert session.utterances[0].text == "hello ."

    def test_missing_date_returns_none(self, minimal_chat_file: Path) -> None:
        session = parse_chat_file(minimal_chat_file, corpus="test", child_id="test")
        assert session.header.date is None

    def test_empty_file(self, tmp_path: Path) -> None:
        empty_file = tmp_path / "empty.cha"
        empty_file.write_text("", encoding="utf-8")
        session = parse_chat_file(empty_file, corpus="test", child_id="test")
        assert session.utterance_count == 0
        assert session.header.participants == {}

    def test_headers_only_file(self, tmp_path: Path) -> None:
        content = "@UTF8\n@Begin\n@Participants:\tCHI Target_Child\n@End\n"
        f = tmp_path / "headers_only.cha"
        f.write_text(content, encoding="utf-8")
        session = parse_chat_file(f, corpus="test", child_id="test")
        assert session.utterance_count == 0
        assert "CHI" in session.header.participants


class TestCorpusDirectoryChildAttribution:
    """Child attribution over a real corpus directory layout.

    The ASDBank corpora identify the child by *directory* (``Rollins/Carl/020800.cha``),
    not by filename -- filenames are bare session ages and repeat across children.
    Every test above supplies ``child_id`` directly to ``parse_chat_file``, so the
    attribution step itself needs its own coverage: an unattributed corpus silently
    collapses every child to ``"unknown"``, which defeats the child-level split
    that leakage-safe evaluation depends on.
    """

    def _corpus(self, tmp_path: Path, content: str) -> Path:
        corpus = tmp_path / "Rollins"
        for child, sessions in (("Carl", ["020800", "021100"]), ("Mars", ["030100"])):
            child_dir = corpus / child
            child_dir.mkdir(parents=True)
            for session in sessions:
                (child_dir / f"{session}.cha").write_text(content, encoding="utf-8")
        return corpus

    def test_attributes_child_from_directory_name(
        self, sample_chat_content: str, tmp_path: Path
    ) -> None:
        corpus = self._corpus(tmp_path, sample_chat_content)
        sessions = parse_corpus_directory(
            corpus, "rollins", {"carl": ["carl"], "mars": ["mars"]}
        )

        assert {s.child_id for s in sessions} == {"carl", "mars"}
        assert sorted(s.child_id for s in sessions) == ["carl", "carl", "mars"]

    def test_no_session_is_left_unattributed(
        self, sample_chat_content: str, tmp_path: Path
    ) -> None:
        corpus = self._corpus(tmp_path, sample_chat_content)
        sessions = parse_corpus_directory(
            corpus, "rollins", {"carl": ["carl"], "mars": ["mars"]}
        )

        assert [s for s in sessions if s.child_id == "unknown"] == []

    def test_unmatched_child_still_falls_back_to_unknown(
        self, sample_chat_content: str, tmp_path: Path
    ) -> None:
        corpus = self._corpus(tmp_path, sample_chat_content)
        sessions = parse_corpus_directory(corpus, "rollins", {"carl": ["carl"]})

        assert sorted(s.child_id for s in sessions) == ["carl", "carl", "unknown"]

    def test_filename_borne_child_id_still_matches(
        self, sample_chat_content: str, tmp_path: Path
    ) -> None:
        """Flat layouts that encode the child in the filename must keep working."""
        corpus = tmp_path / "Flat"
        corpus.mkdir()
        (corpus / "brett_070315.cha").write_text(sample_chat_content, encoding="utf-8")

        sessions = parse_corpus_directory(corpus, "flusberg", {"brett": ["brett"]})

        assert [s.child_id for s in sessions] == ["brett"]
