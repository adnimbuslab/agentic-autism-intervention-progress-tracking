"""Tests for the adjudication round trip.

Three risks. The sheet must carry exactly the conflicted fields -- a row for a
field the annotators agreed on invites the adjudicator to overrule a consensus
nobody disputed. `a` and `b` must resolve to the values printed in the row, or
a decision stops meaning what the adjudicator saw when they made it. And a
partially decided segment must stay out of the gold standard rather than be
half-recorded.
"""

from __future__ import annotations

import csv

import pytest

from tests.eval.extraction.export_adjudication_sheet import (
    COLUMNS,
    conflict_rows,
    rule_for,
    write_sheet,
)
from tests.eval.extraction.import_adjudication_sheet import (
    DecisionError,
    parse_decision,
    read_sheet,
)

FIELDS = ["domain", "behavior", "modality", "prompt_level", "outcome"]


def _annotation(segment_id: str, **values) -> dict:
    base = {
        "domain": "language",
        "behavior": "said something",
        "modality": "verbal",
        "prompt_level": "independent",
        "outcome": "correct",
    }
    base.update(values)
    return {
        "segment_id": segment_id,
        "child_id": "carl",
        "field_values": base,
        "notes": "",
        "annotator": "x",
        "source": "spreadsheet",
    }


class TestExport:
    def test_only_conflicted_fields_get_a_row(self) -> None:
        first = {"s1": _annotation("s1", modality="none")}
        second = {"s1": _annotation("s1", modality="gestural")}
        rows = conflict_rows(first, second, ["s1"], {"s1": "*CHI:\tjuice"})
        assert [r["field"] for r in rows] == ["modality"]

    def test_a_fully_agreed_segment_produces_no_rows(self) -> None:
        gold = {"s1": _annotation("s1")}
        assert conflict_rows(gold, gold, ["s1"], {}) == []

    def test_both_annotators_values_are_carried(self) -> None:
        first = {"s1": _annotation("s1", outcome="none")}
        second = {"s1": _annotation("s1", outcome="correct")}
        row = conflict_rows(first, second, ["s1"], {})[0]
        assert row["annotator_a"] == "none"
        assert row["annotator_b"] == "correct"

    def test_a_null_is_shown_as_the_word_none_not_as_blank(self) -> None:
        first = {"s1": _annotation("s1", modality=None)}
        second = {"s1": _annotation("s1", modality="gestural")}
        row = conflict_rows(first, second, ["s1"], {})[0]
        assert row["annotator_a"] == "none"

    def test_the_transcript_is_on_every_row(self) -> None:
        first = {"s1": _annotation("s1", modality="none", outcome="none")}
        second = {"s1": _annotation("s1", modality="gestural", outcome="correct")}
        rows = conflict_rows(first, second, ["s1"], {"s1": "*CHI:\tjuice"})
        assert all(r["transcript"] == "*CHI:\tjuice" for r in rows)

    def test_rows_are_grouped_by_segment(self) -> None:
        first = {s: _annotation(s, modality="none") for s in ("s1", "s2")}
        second = {s: _annotation(s, modality="gestural", outcome="partial")
                  for s in ("s1", "s2")}
        rows = conflict_rows(first, second, ["s1", "s2"], {})
        assert [r["segment_id"] for r in rows] == ["s1", "s1", "s2", "s2"]

    def test_free_text_comes_last_within_a_segment(self) -> None:
        first = {"s1": _annotation("s1", behavior="pointed", outcome="none")}
        second = {"s1": _annotation("s1", behavior="gestured", outcome="correct")}
        rows = conflict_rows(first, second, ["s1"], {})
        assert [r["field"] for r in rows] == ["outcome", "behavior"]

    def test_a_codebook_pair_carries_its_rule(self) -> None:
        assert rule_for("modality", "none", "gestural") != ""
        assert "gestural is a communicative gesture" in rule_for(
            "modality", "none", "gestural"
        )

    def test_a_pair_the_codebook_is_silent_on_carries_no_rule(self) -> None:
        assert rule_for("domain", "cognitive", "language") == ""
        assert rule_for("outcome", "correct", "partial") == ""

    def test_the_sheet_round_trips_through_csv(self, tmp_path) -> None:
        first = {"s1": _annotation("s1", modality="none")}
        second = {"s1": _annotation("s1", modality="gestural")}
        rows = conflict_rows(first, second, ["s1"], {"s1": "*MOT:\thi\n*CHI:\tbye"})
        path = tmp_path / "adj.csv"
        write_sheet(rows, path)
        back = list(csv.DictReader(path.open(newline="", encoding="utf-8-sig")))
        assert list(back[0]) == COLUMNS
        assert back[0]["transcript"] == "*MOT:\thi\n*CHI:\tbye"


class TestParseDecision:
    def test_a_adopts_the_left_value_as_printed(self) -> None:
        assert parse_decision("modality", "a", "none", "gestural") == ("decided", None)
        assert parse_decision("modality", "a", "verbal", "gestural") == (
            "decided", "verbal"
        )

    def test_b_adopts_the_right_value_as_printed(self) -> None:
        assert parse_decision("modality", "b", "none", "gestural") == (
            "decided", "gestural"
        )

    def test_a_third_value_is_accepted(self) -> None:
        assert parse_decision("modality", "multimodal", "none", "gestural") == (
            "decided", "multimodal"
        )

    def test_the_null_word_is_a_decision(self) -> None:
        assert parse_decision("outcome", "none", "correct", "partial") == (
            "decided", None
        )

    def test_an_empty_cell_is_not_a_decision(self) -> None:
        assert parse_decision("outcome", "", "correct", "partial") == ("blank", None)

    def test_free_text_is_taken_as_written(self) -> None:
        state, value = parse_decision("behavior", "reached for the cup", "x", "y")
        assert (state, value) == ("decided", "reached for the cup")

    def test_capitalisation_and_spacing_are_forgiven(self) -> None:
        assert parse_decision("prompt_level", " Partial Physical ", "a", "b") == (
            "decided", "partial_physical"
        )

    def test_an_unlisted_value_raises_rather_than_being_guessed(self) -> None:
        with pytest.raises(DecisionError, match="not 'a', 'b'"):
            parse_decision("modality", "pointing", "none", "gestural")


def _sheet(tmp_path, *rows) -> "object":
    path = tmp_path / "adj.csv"
    filled = []
    for segment_id, field, left, right, decision in rows:
        row = {c: "" for c in COLUMNS}
        row.update(
            segment_id=segment_id, child_id="carl", field=field,
            transcript="*CHI:\tjuice", annotator_a=left, annotator_b=right,
            decision=decision,
        )
        filled.append(row)
    write_sheet(filled, path)
    return path


class TestImport:
    def test_a_decided_row_becomes_a_decision(self, tmp_path) -> None:
        path = _sheet(tmp_path, ("s1", "modality", "none", "gestural", "a"))
        report = read_sheet(path)
        assert report["decisions"] == {"s1": {"modality": None}}
        assert report["n_decided"] == 1

    def test_an_undecided_row_is_reported_not_guessed(self, tmp_path) -> None:
        path = _sheet(tmp_path, ("s1", "modality", "none", "gestural", ""))
        report = read_sheet(path)
        assert report["decisions"] == {}
        assert len(report["blank"]) == 1

    def test_a_segment_with_any_undecided_field_is_flagged_incomplete(
        self, tmp_path
    ) -> None:
        path = _sheet(
            tmp_path,
            ("s1", "modality", "none", "gestural", "a"),
            ("s1", "outcome", "correct", "partial", ""),
        )
        report = read_sheet(path)
        assert report["incomplete_segments"] == ["s1"]

    def test_a_fully_decided_segment_is_not_flagged(self, tmp_path) -> None:
        path = _sheet(
            tmp_path,
            ("s1", "modality", "none", "gestural", "a"),
            ("s1", "outcome", "correct", "partial", "b"),
        )
        report = read_sheet(path)
        assert report["incomplete_segments"] == []
        assert report["decisions"]["s1"] == {"modality": None, "outcome": "partial"}

    def test_a_bad_cell_is_reported_with_its_row(self, tmp_path) -> None:
        path = _sheet(tmp_path, ("s1", "modality", "none", "gestural", "wiggling"))
        report = read_sheet(path)
        assert len(report["errors"]) == 1
        assert report["errors"][0]["segment_id"] == "s1"

    def test_a_duplicated_row_keeps_the_first_and_reports_it(self, tmp_path) -> None:
        path = _sheet(
            tmp_path,
            ("s1", "modality", "none", "gestural", "a"),
            ("s1", "modality", "none", "gestural", "b"),
        )
        report = read_sheet(path)
        assert report["decisions"]["s1"]["modality"] is None
        assert report["duplicates"] == ["s1/modality"]

    def test_notes_are_kept_against_the_field(self, tmp_path) -> None:
        path = tmp_path / "adj.csv"
        row = {c: "" for c in COLUMNS}
        row.update(segment_id="s1", field="outcome", annotator_a="correct",
                   annotator_b="partial", decision="a", notes="the adult confirms it")
        write_sheet([row], path)
        assert read_sheet(path)["notes"]["s1"]["outcome"] == "the adult confirms it"


class TestGoldAssembly:
    def test_only_fully_resolved_segments_reach_gold(self) -> None:
        from tests.eval.extraction.adjudicate import build_gold, split_by_consensus

        first = {
            "s1": _annotation("s1", modality="none"),
            "s2": _annotation("s2", modality="none", outcome="none"),
        }
        second = {
            "s1": _annotation("s1", modality="gestural"),
            "s2": _annotation("s2", modality="gestural", outcome="correct"),
        }
        agreed, conflicts = split_by_consensus(first, second, ["s1", "s2"])
        # s1 fully decided; s2 decided on modality only.
        adjudicated = {
            "s1": {"modality": "gestural"},
            "s2": {"modality": "gestural"},
        }
        gold, counts = build_gold(agreed, adjudicated, first)
        assert set(gold) == {"s1"}
        assert counts["unresolved"] == 1

    def test_an_adjudicated_segment_is_marked_as_such(self) -> None:
        from tests.eval.extraction.adjudicate import build_gold, split_by_consensus

        first = {"s1": _annotation("s1", modality="none")}
        second = {"s1": _annotation("s1", modality="gestural")}
        agreed, _ = split_by_consensus(first, second, ["s1"])
        gold, _ = build_gold(agreed, {"s1": {"modality": "gestural"}}, first)
        assert gold["s1"]["source"] == "adjudicated"
        assert gold["s1"]["field_values"]["modality"] == "gestural"
