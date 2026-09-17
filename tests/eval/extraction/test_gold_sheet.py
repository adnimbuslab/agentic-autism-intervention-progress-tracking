"""Tests for the spreadsheet annotation round-trip.

Two risks are under test. The sheet must not carry model output out of the
repository, or blindness is lost the moment the file is emailed. And the
importer must never guess: a value it cannot read is an error the annotator
resolves, not a nearest-match substitution that enters the gold standard as
though they had chosen it.
"""

from __future__ import annotations

import csv

import pytest

from tests.eval.extraction.export_gold_sheet import (
    COLUMNS,
    NULL_WORD,
    rows_for,
    write_reference,
    write_sheet,
)
from tests.eval.extraction.import_gold_sheet import CellError, parse_cell, read_sheet


def _batch(*segment_ids: str) -> dict:
    return {
        "models": ["m1", "m2"],
        "candidates": [
            {
                "segment_id": segment_id,
                "child_id": "carl",
                "corpus": "rollins",
                "session_id": "sess",
                "chat_text": "*CHI:\tjuice please",
                "candidates": {
                    "m1": {"extracted_fields": {"domain": "language"}, "status": "success"},
                    "m2": {"extracted_fields": {"domain": "play"}, "status": "abstained"},
                },
            }
            for segment_id in segment_ids
        ],
    }


def _write(tmp_path, rows, name="sheet.csv"):
    path = tmp_path / name
    write_sheet(rows, path)
    return path


def _filled(**overrides) -> dict:
    row = {c: "" for c in COLUMNS}
    row.update(
        segment_id="s1", child_id="carl", corpus="rollins", session_id="sess",
        transcript="*CHI:\tjuice please", domain="language",
        behavior="asks for juice", modality="verbal",
        prompt_level="independent", outcome="correct",
    )
    row.update(overrides)
    return row


class TestExportBlindness:
    def test_no_model_output_reaches_the_sheet(self, tmp_path) -> None:
        rows = rows_for(_batch("s1"), "annotator_a", seed=42)
        text = _write(tmp_path, rows).read_text(encoding="utf-8-sig")

        for leak in ("m1", "m2", "abstained", "success", "extracted_fields"):
            assert leak not in text

    def test_value_columns_are_left_blank(self, tmp_path) -> None:
        rows = rows_for(_batch("s1"), "annotator_a", seed=42)

        assert rows[0]["domain"] == ""
        assert rows[0]["outcome"] == ""

    def test_the_transcript_survives_its_newlines(self, tmp_path) -> None:
        path = _write(tmp_path, rows_for(_batch("s1"), "annotator_a", seed=42))
        parsed = list(csv.DictReader(path.open(newline="", encoding="utf-8-sig")))

        assert parsed[0]["transcript"] == "*CHI:\tjuice please"

    def test_each_annotator_gets_a_different_order(self) -> None:
        """Shared order would correlate the two annotators' fatigue."""
        batch = _batch(*[f"s{i}" for i in range(40)])
        a = [r["segment_id"] for r in rows_for(batch, "annotator_a", seed=42)]
        b = [r["segment_id"] for r in rows_for(batch, "annotator_b", seed=42)]

        assert a != b
        assert sorted(a) == sorted(b)

    def test_re_exporting_gives_the_same_order(self) -> None:
        """An annotator re-downloading must not get a reshuffled sheet."""
        batch = _batch(*[f"s{i}" for i in range(40)])
        first = [r["segment_id"] for r in rows_for(batch, "annotator_a", seed=42)]
        again = [r["segment_id"] for r in rows_for(batch, "annotator_a", seed=42)]

        assert first == again

    def test_the_reference_sheet_lists_the_null_convention(self, tmp_path) -> None:
        path = tmp_path / "ref.csv"
        write_reference(path)
        text = path.read_text(encoding="utf-8-sig")

        assert NULL_WORD in text
        assert "social_communication" in text


class TestCellParsing:
    def test_a_listed_value_is_accepted(self) -> None:
        assert parse_cell("domain", "language") == ("value", "language")

    def test_capitalisation_and_spacing_are_forgiven(self) -> None:
        assert parse_cell("domain", "  Language ") == ("value", "language")

    def test_a_space_or_hyphen_is_read_as_the_underscore_form(self) -> None:
        assert parse_cell("domain", "social communication")[1] == "social_communication"
        assert parse_cell("prompt_level", "Partial-Physical")[1] == "partial_physical"

    @pytest.mark.parametrize("word", ["none", "None", "n/a", "NA", "null", "-", "--"])
    def test_the_null_finding_is_recognised_however_it_is_written(self, word) -> None:
        assert parse_cell("modality", word) == ("null", None)

    def test_an_empty_cell_is_not_a_null(self) -> None:
        """The distinction the whole design rests on."""
        assert parse_cell("modality", "")[0] == "empty"
        assert parse_cell("modality", "   ")[0] == "empty"
        assert parse_cell("modality", "none")[0] == "null"

    def test_free_text_is_taken_as_written(self) -> None:
        assert parse_cell("behavior", "Asks For Juice") == ("value", "Asks For Juice")

    def test_an_unlisted_value_raises_rather_than_being_guessed(self) -> None:
        with pytest.raises(CellError) as excinfo:
            parse_cell("domain", "langauge")

        assert "not an allowed value" in str(excinfo.value)
        assert "language" in str(excinfo.value)


class TestImport:
    def test_a_complete_row_becomes_a_gold_annotation(self, tmp_path) -> None:
        path = _write(tmp_path, [_filled()])
        report = read_sheet(path, "annotator_a", {"s1"})

        assert report["n_complete"] == 1
        record = report["annotations"]["s1"]
        assert record["field_values"]["domain"] == "language"
        assert record["annotator"] == "annotator_a"

    def test_a_null_is_recorded_as_none_not_omitted(self, tmp_path) -> None:
        path = _write(tmp_path, [_filled(prompt_level="none")])
        report = read_sheet(path, "annotator_a", {"s1"})

        values = report["annotations"]["s1"]["field_values"]
        assert "prompt_level" in values
        assert values["prompt_level"] is None

    def test_an_incomplete_row_is_excluded_and_reported(self, tmp_path) -> None:
        path = _write(tmp_path, [_filled(outcome="")])
        report = read_sheet(path, "annotator_a", {"s1"})

        assert report["annotations"] == {}
        assert report["incomplete"][0]["blank"] == ["outcome"]

    def test_a_bad_cell_is_reported_with_its_row(self, tmp_path) -> None:
        path = _write(tmp_path, [_filled(domain="langauge")])
        report = read_sheet(path, "annotator_a", {"s1"})

        assert report["annotations"] == {}
        assert report["errors"][0]["segment_id"] == "s1"
        assert "not an allowed value" in report["errors"][0]["problem"]

    def test_an_unknown_segment_id_is_reported_not_imported(self, tmp_path) -> None:
        path = _write(tmp_path, [_filled(segment_id="not_a_segment")])
        report = read_sheet(path, "annotator_a", {"s1"})

        assert report["annotations"] == {}
        assert report["unknown_segments"] == ["not_a_segment"]

    def test_a_duplicated_segment_keeps_the_first_and_reports_it(self, tmp_path) -> None:
        path = _write(tmp_path, [_filled(), _filled(domain="play")])
        report = read_sheet(path, "annotator_a", {"s1"})

        assert report["annotations"]["s1"]["field_values"]["domain"] == "language"
        assert report["duplicates"] == ["s1"]

    def test_segments_absent_from_the_sheet_are_reported(self, tmp_path) -> None:
        path = _write(tmp_path, [_filled()])
        report = read_sheet(path, "annotator_a", {"s1", "s2"})

        assert report["missing_segments"] == ["s2"]

    def test_the_imported_shape_matches_what_the_chain_consumes(self, tmp_path) -> None:
        """Import must be indistinguishable from the interactive tool's output."""
        from tests.eval.extraction.agreement_report import build_report

        path = _write(tmp_path, [_filled()])
        annotations = read_sheet(path, "annotator_a", {"s1"})["annotations"]

        report = build_report(annotations, annotations)
        assert report["n_overlap_segments"] == 1
        assert report["per_field"]["domain"]["n"] == 1


class TestSegmentSetSource:
    """The importer must accept both artefact shapes that define a segment set.

    The annotation batch keys segments under 'candidates'; the held-out set
    uses 'segments' and its ids are deliberately absent from the batch. An
    importer that only knew the batch shape would reject every row of a
    held-out round as an unknown segment, silently producing an empty import.
    """

    def test_batch_shaped_and_holdout_shaped_files_both_define_ids(self) -> None:
        batch = {"candidates": [{"segment_id": "s1"}, {"segment_id": "s2"}]}
        holdout = {"segments": [{"segment_id": "h1"}, {"segment_id": "h2"}]}
        for payload, expected in ((batch, {"s1", "s2"}), (holdout, {"h1", "h2"})):
            entries = payload.get("candidates") or payload.get("segments") or []
            assert {e["segment_id"] for e in entries} == expected

    def test_a_holdout_row_imports_against_the_holdout_ids(self, tmp_path) -> None:
        row = _filled(segment_id="h1")
        path = _write(tmp_path, [row])
        report = read_sheet(path, "annotator_a", {"h1"})
        assert report["n_complete"] == 1
        assert not report["unknown_segments"]

    def test_the_same_row_is_rejected_against_the_batch_ids(self, tmp_path) -> None:
        # Held-out ids are absent from the batch by construction, so importing
        # a held-out sheet against the batch must reject rather than accept.
        row = _filled(segment_id="h1")
        path = _write(tmp_path, [row])
        report = read_sheet(path, "annotator_a", {"s1", "s2"})
        assert report["n_complete"] == 0
        assert report["unknown_segments"] == ["h1"]
