"""Tests for source-level gold annotation.

Blindness is the property under test. If model output can reach the annotator,
gold stops being model-independent and every generator's accuracy becomes
partly a measure of how persuasive its output looked.
"""

from __future__ import annotations

import inspect

from src.backend.schemas.observation_schema import Domain, Modality, Outcome, PromptLevel
from tests.eval.extraction import annotate_gold
from tests.eval.extraction.annotate_gold import (
    CATEGORICAL_VALUES,
    FIELDS,
    FREE_TEXT_FIELDS,
    segments_for_annotation,
)


def _batch(*segment_ids: str) -> dict:
    return {
        "models": ["m1", "m2"],
        "candidates": [
            {
                "segment_id": segment_id,
                "child_id": "c1",
                "corpus": "rollins",
                "session_id": "s",
                "chat_text": "CHI: juice please",
                "candidates": {
                    "m1": {"extracted_fields": {"domain": "language"}, "status": "success"},
                    "m2": {"extracted_fields": {"domain": "play"}, "status": "success"},
                },
            }
            for segment_id in segment_ids
        ],
    }


class TestBlindness:
    def test_model_candidates_are_stripped_from_what_the_annotator_sees(self) -> None:
        segments = segments_for_annotation(_batch("s1"))

        assert "candidates" not in segments[0]
        assert segments[0]["chat_text"] == "CHI: juice please"

    def test_no_model_output_survives_anywhere_in_the_segment(self) -> None:
        rendered = repr(segments_for_annotation(_batch("s1")))

        for leak in ("m1", "m2", "language", "play", "success", "extracted_fields"):
            assert leak not in rendered

    def test_the_module_never_reads_the_candidates_key(self) -> None:
        """Structural, not a matter of annotator discipline."""
        source = inspect.getsource(annotate_gold)
        body = source.split('"""', 2)[-1]  # skip the module docstring

        assert 'entry["candidates"]' not in body
        assert "['candidates']" not in body


class TestAssignment:
    def test_every_annotator_sees_every_segment(self) -> None:
        """Gold is a property of the source, so there is no per-annotator split."""
        segments = segments_for_annotation(_batch("s1", "s2", "s3"))

        assert [s["segment_id"] for s in segments] == ["s1", "s2", "s3"]

    def test_the_whole_batch_is_the_overlap(self) -> None:
        batch = _batch("s1", "s2")

        assert len(segments_for_annotation(batch)) == len(batch["candidates"])


class TestVocabulary:
    def test_categorical_fields_offer_the_schema_values(self) -> None:
        assert CATEGORICAL_VALUES["domain"] == [d.value for d in Domain]
        assert CATEGORICAL_VALUES["modality"] == [m.value for m in Modality]
        assert CATEGORICAL_VALUES["prompt_level"] == [p.value for p in PromptLevel]
        assert CATEGORICAL_VALUES["outcome"] == [o.value for o in Outcome]

    def test_every_field_is_either_categorical_or_free_text(self) -> None:
        assert set(FIELDS) == set(CATEGORICAL_VALUES) | FREE_TEXT_FIELDS

    def test_behavior_is_the_only_free_text_field(self) -> None:
        assert set(FREE_TEXT_FIELDS) == {"behavior"}
