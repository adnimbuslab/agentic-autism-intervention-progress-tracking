"""Tests for the codebook-driven re-issue round.

Three risks are under test. The re-issue must select on the codebook's stated
boundaries and nothing else, or the second round buys a kappa improvement the
protocol did not earn. The round-2 sheet must carry no trace of round 1 --
neither annotator's values, nor which field was disputed -- or the "independent
re-annotation" is an anchored one. And the merge must leave untouched every
segment that was never re-issued, since a round-2 sheet holds only a subset.
"""

from __future__ import annotations

import csv
import json

from tests.eval.extraction.export_gold_sheet import COLUMNS
from tests.eval.extraction.import_gold_sheet import merge, read_sheet
from tests.eval.extraction.reissue_gold_sheet import (
    CODEBOOK_BOUNDARIES,
    RULES,
    conflicts_for,
    freeze_round1,
    rows_for,
    select,
)


def _annotation(segment_id: str, **fields) -> dict:
    values = {
        "domain": "language",
        "behavior": "said something",
        "modality": "verbal",
        "prompt_level": "independent",
        "outcome": "correct",
    }
    values.update(fields)
    return {
        "segment_id": segment_id,
        "child_id": "carl",
        "field_values": values,
        "notes": "",
        "annotator": "annotator_a",
        "source": "spreadsheet",
    }


def _batch(*segment_ids: str) -> dict:
    return {
        "models": ["m1"],
        "candidates": [
            {
                "segment_id": segment_id,
                "child_id": "carl",
                "corpus": "rollins",
                "session_id": "sess",
                "chat_text": "*CHI:\tjuice please",
                "candidates": {
                    "m1": {"extracted_fields": {"domain": "play"}, "status": "success"}
                },
            }
            for segment_id in segment_ids
        ],
    }


class TestRuleTable:
    def test_every_pair_cites_a_rule_that_exists(self) -> None:
        for field, pairs in CODEBOOK_BOUNDARIES.items():
            for pair, rule in pairs.items():
                assert rule in RULES, f"{field} {set(pair)} cites unknown rule {rule}"

    def test_every_pair_is_two_distinct_values(self) -> None:
        for field, pairs in CODEBOOK_BOUNDARIES.items():
            for pair in pairs:
                assert len(pair) == 2, f"{field}: {set(pair)} is not a value pair"

    def test_domain_is_not_a_codebook_boundary(self) -> None:
        # Domain conflicts are category judgements no codebook rule touches.
        # Re-issuing them would inflate the post-codebook kappa for free.
        assert "domain" not in CODEBOOK_BOUNDARIES


class TestSelection:
    def test_a_boundary_conflict_is_selected(self) -> None:
        first = {"s1": _annotation("s1", modality="none")}
        second = {"s1": _annotation("s1", modality="gestural")}
        report = select(first, second)
        assert "s1" in report["selected"]
        assert report["selected"]["s1"][0]["rule"] == "modality_gestural"

    def test_agreement_is_not_selected(self) -> None:
        first = {"s1": _annotation("s1")}
        second = {"s1": _annotation("s1")}
        assert select(first, second)["selected"] == {}

    def test_a_domain_conflict_alone_is_not_selected(self) -> None:
        first = {"s1": _annotation("s1", domain="cognitive")}
        second = {"s1": _annotation("s1", domain="language")}
        report = select(first, second)
        assert report["selected"] == {}
        assert len(report["off_boundary"]) == 1

    def test_a_silent_outcome_pair_is_not_selected(self) -> None:
        # correct-vs-partial is a degree-of-completion call, not a definition.
        first = {"s1": _annotation("s1", outcome="correct")}
        second = {"s1": _annotation("s1", outcome="partial")}
        assert select(first, second)["selected"] == {}

    def test_a_silent_conflict_rides_along_when_the_segment_is_selected(self) -> None:
        first = {"s1": _annotation("s1", domain="cognitive", modality="none")}
        second = {"s1": _annotation("s1", domain="language", modality="gestural")}
        report = select(first, second)
        assert "s1" in report["selected"]
        # Selection is per segment, but the accounting still reports the domain
        # conflict as one the codebook does not resolve.
        assert [c["field"] for c in report["off_boundary"]] == ["domain"]

    def test_free_text_behavior_never_triggers_a_re_issue(self) -> None:
        first = {"s1": _annotation("s1", behavior="asked for juice")}
        second = {"s1": _annotation("s1", behavior="requested a drink")}
        assert select(first, second)["selected"] == {}

    def test_a_null_reads_as_none_not_as_a_missing_value(self) -> None:
        first = {"s1": _annotation("s1", modality=None)}
        second = {"s1": _annotation("s1", modality="gestural")}
        conflicts = conflicts_for("s1", first["s1"], second["s1"])
        modality = next(c for c in conflicts if c["field"] == "modality")
        assert modality["values"] == "none / gestural"
        assert modality["rule"] == "modality_gestural"


class TestRoundTwoBlindness:
    def test_value_columns_go_out_empty(self, tmp_path) -> None:
        rows = rows_for(_batch("s1", "s2"), {"s1", "s2"}, "annotator_a", 1)
        for row in rows:
            for field in ("domain", "behavior", "modality", "prompt_level", "outcome"):
                assert row[field] == ""

    def test_no_round_one_value_reaches_the_sheet(self, tmp_path) -> None:
        from tests.eval.extraction.export_gold_sheet import write_sheet

        rows = rows_for(_batch("s1"), {"s1"}, "annotator_a", 1)
        path = tmp_path / "round2.csv"
        write_sheet(rows, path)
        text = path.read_text(encoding="utf-8-sig")
        # The round-1 values for s1 were modality=verbal, outcome=correct.
        assert "verbal" not in text
        assert "correct" not in text

    def test_the_sheet_does_not_say_which_field_was_disputed(self) -> None:
        rows = rows_for(_batch("s1"), {"s1"}, "annotator_a", 1)
        assert set(rows[0]) == set(COLUMNS)

    def test_only_the_selected_segments_go_out(self) -> None:
        rows = rows_for(_batch("s1", "s2", "s3"), {"s1", "s3"}, "annotator_a", 1)
        assert {r["segment_id"] for r in rows} == {"s1", "s3"}

    def test_each_annotator_gets_a_different_order(self) -> None:
        batch = _batch(*[f"s{i}" for i in range(30)])
        ids = {f"s{i}" for i in range(30)}
        a = [r["segment_id"] for r in rows_for(batch, ids, "annotator_a", 1)]
        b = [r["segment_id"] for r in rows_for(batch, ids, "annotator_b", 1)]
        assert a != b

    def test_the_round_two_order_differs_from_round_one(self) -> None:
        from tests.eval.extraction.export_gold_sheet import (
            DEFAULT_SEED,
            rows_for as round1_rows_for,
        )
        from tests.eval.extraction.reissue_gold_sheet import ROUND2_SEED

        batch = _batch(*[f"s{i}" for i in range(30)])
        ids = {f"s{i}" for i in range(30)}
        one = [r["segment_id"] for r in round1_rows_for(batch, "annotator_a", DEFAULT_SEED)]
        two = [r["segment_id"] for r in rows_for(batch, ids, "annotator_a", ROUND2_SEED)]
        assert one != two

    def test_re_exporting_gives_the_same_order(self) -> None:
        batch = _batch(*[f"s{i}" for i in range(30)])
        ids = {f"s{i}" for i in range(30)}
        first = [r["segment_id"] for r in rows_for(batch, ids, "annotator_a", 1)]
        second = [r["segment_id"] for r in rows_for(batch, ids, "annotator_a", 1)]
        assert first == second


class TestFreeze:
    def test_the_snapshot_is_written_once_and_never_overwritten(
        self, tmp_path, monkeypatch
    ) -> None:
        import tests.eval.extraction.reissue_gold_sheet as module

        live = tmp_path / "gold_annotator_a.json"
        live.write_text(json.dumps({"s1": _annotation("s1")}))
        monkeypatch.setattr(module, "annotations_path", lambda a: live)
        monkeypatch.setattr(module, "round1_path", lambda a: tmp_path / f"gold_{a}_round1.json")

        path, fresh = module.freeze_round1("annotator_a")
        assert fresh and json.loads(path.read_text())["s1"]["field_values"]["modality"] == "verbal"

        # Round 2 lands on the live file; the snapshot must not follow it.
        live.write_text(json.dumps({"s1": _annotation("s1", modality="gestural")}))
        path, fresh = module.freeze_round1("annotator_a")
        assert not fresh
        assert json.loads(path.read_text())["s1"]["field_values"]["modality"] == "verbal"


class TestMerge:
    def test_a_segment_not_re_annotated_survives(self) -> None:
        existing = {"s1": _annotation("s1"), "s2": _annotation("s2")}
        merged = merge(existing, {"s1": _annotation("s1", modality="gestural")})
        assert set(merged) == {"s1", "s2"}
        assert merged["s2"] == existing["s2"]

    def test_a_re_annotated_segment_takes_the_new_value(self) -> None:
        existing = {"s1": _annotation("s1", modality="verbal")}
        merged = merge(existing, {"s1": _annotation("s1", modality="none")})
        assert merged["s1"]["field_values"]["modality"] == "none"

    def test_merging_does_not_mutate_the_existing_annotations(self) -> None:
        existing = {"s1": _annotation("s1", modality="verbal")}
        merge(existing, {"s1": _annotation("s1", modality="none")})
        assert existing["s1"]["field_values"]["modality"] == "verbal"


class TestRoundIsRecorded:
    def test_the_import_stamps_the_round_it_came_from(self, tmp_path) -> None:
        from tests.eval.extraction.export_gold_sheet import write_sheet

        row = {c: "" for c in COLUMNS}
        row.update(
            segment_id="s1", child_id="carl", corpus="rollins", session_id="sess",
            transcript="*CHI:\tjuice", domain="language", behavior="asked",
            modality="verbal", prompt_level="independent", outcome="correct",
        )
        path = tmp_path / "sheet.csv"
        write_sheet([row], path)

        report = read_sheet(path, "annotator_a", {"s1"}, round_number=2)
        assert report["annotations"]["s1"]["round"] == 2

    def test_the_round_defaults_to_one(self, tmp_path) -> None:
        from tests.eval.extraction.export_gold_sheet import write_sheet

        row = {c: "" for c in COLUMNS}
        row.update(
            segment_id="s1", child_id="carl", corpus="rollins", session_id="sess",
            transcript="*CHI:\tjuice", domain="language", behavior="asked",
            modality="verbal", prompt_level="independent", outcome="correct",
        )
        path = tmp_path / "sheet.csv"
        write_sheet([row], path)

        report = read_sheet(path, "annotator_a", {"s1"})
        assert report["annotations"]["s1"]["round"] == 1
