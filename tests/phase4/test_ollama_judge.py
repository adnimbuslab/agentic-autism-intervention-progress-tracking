"""Tests for the MARS ranking judge.

The judge is the one place where a model's output could contaminate field
values rather than just their order, so the leak tests matter as much as the
parsing ones.
"""

from __future__ import annotations

import json

import pytest

from src.backend.ml.extraction.mars.blinding import build_judge_presentation
from src.backend.ml.extraction.mars.candidates import build_candidates
from src.backend.ml.extraction.mars.fusion import parse_judge_response
from src.backend.ml.extraction.mars.ollama_judge import (
    build_judge_user_prompt,
    parse_alias_array,
)
from src.backend.ml.extraction.schemas import ExtractionResult, ExtractionStatus
from src.backend.schemas.observation_schema import (
    ContributorRole,
    Domain,
    Setting,
    StructuredObservation,
)


def _result(model: str, domain: Domain, behavior: str) -> ExtractionResult:
    from datetime import date

    return ExtractionResult(
        status=ExtractionStatus.SUCCESS,
        observations=[
            StructuredObservation(
                child_id="c1",
                session_id="s1",
                contributor_role=ContributorRole.INTERVENTIONIST,
                observation_date=date(2026, 1, 1),
                setting=Setting.CLINIC,
                domain=domain,
                behavior=behavior,
                confidence=0.9,
            )
        ],
        provider="test",
        model=model,
        prompt_version="v1",
    )


@pytest.fixture
def presentation():
    candidates = build_candidates(
        [
            _result("model_a", Domain.LANGUAGE, "asks for juice"),
            _result("model_b", Domain.SOCIAL_COMMUNICATION, "looks at parent"),
        ]
    )
    return build_judge_presentation(
        judge_id="judge_1", candidates=candidates, request_seed="seed"
    )


class TestAliasParsing:
    def test_a_bare_json_array_is_read(self) -> None:
        assert parse_alias_array('["a1", "b2"]') == ["a1", "b2"]

    def test_a_fenced_array_is_read(self) -> None:
        assert parse_alias_array('```json\n["a1", "b2"]\n```') == ["a1", "b2"]

    def test_an_array_after_prose_is_read(self) -> None:
        assert parse_alias_array('Here is my ranking: ["a1", "b2"]') == ["a1", "b2"]

    def test_prose_with_no_array_is_none(self) -> None:
        assert parse_alias_array("I think the first one is better.") is None

    def test_empty_and_none_are_none(self) -> None:
        assert parse_alias_array("") is None
        assert parse_alias_array(None) is None

    def test_malformed_json_is_none_not_an_exception(self) -> None:
        assert parse_alias_array('["a1", "b2"') is None

    def test_an_array_wrapped_in_an_object_is_still_read(self) -> None:
        """Layout is undone here; whether the content is a valid ranking is not.

        A model that wraps its answer in an object has still answered. If the
        extracted array is not a complete permutation of the aliases,
        parse_judge_response rejects it -- which is the check that should
        decide, not the bracket search.
        """
        assert parse_alias_array('{"ranking": ["a1"]}') == ["a1"]


class TestPromptLeakage:
    def test_the_prompt_carries_no_generator_identity(self, presentation) -> None:
        prompt = build_judge_user_prompt("CHI: juice please", presentation)

        assert "model_a" not in prompt
        assert "model_b" not in prompt

    def test_the_prompt_carries_no_confidence(self, presentation) -> None:
        prompt = build_judge_user_prompt("CHI: juice please", presentation)

        assert "0.9" not in prompt
        assert "confidence" not in prompt.lower()

    def test_the_prompt_carries_no_internal_ids(self, presentation) -> None:
        prompt = build_judge_user_prompt("CHI: juice please", presentation)
        internal_ids = set(presentation.aliases.values())

        assert not any(internal_id in prompt for internal_id in internal_ids)

    def test_the_prompt_shows_every_alias(self, presentation) -> None:
        prompt = build_judge_user_prompt("CHI: juice please", presentation)

        for alias in presentation.aliases:
            assert alias in prompt

    def test_the_prompt_content_is_exactly_the_judge_payload(self, presentation) -> None:
        prompt = build_judge_user_prompt("CHI: juice please", presentation)

        assert json.dumps(presentation.judge_payload(), indent=2, sort_keys=True) in prompt


class TestEndToEndWithValidation:
    def test_a_well_formed_ranking_resolves_to_internal_ids(self, presentation) -> None:
        aliases = list(presentation.order)
        raw = parse_alias_array(json.dumps(aliases))

        response = parse_judge_response(raw, presentation, judge_id="judge_1")

        assert response.rejection is None
        assert response.internal_ids == [presentation.resolve(a) for a in aliases]

    def test_a_refusal_becomes_a_rejection_not_a_crash(self, presentation) -> None:
        raw = parse_alias_array("I cannot rank these.")

        response = parse_judge_response(raw, presentation, judge_id="judge_1")

        assert response.rejection == "unparseable"

    def test_a_partial_ranking_is_rejected(self, presentation) -> None:
        raw = parse_alias_array(json.dumps(presentation.order[:1]))

        response = parse_judge_response(raw, presentation, judge_id="judge_1")

        assert response.rejection == "incomplete_ordering"

    def test_an_invented_alias_is_rejected(self, presentation) -> None:
        raw = parse_alias_array(json.dumps([*presentation.order[:-1], "not_an_alias"]))

        response = parse_judge_response(raw, presentation, judge_id="judge_1")

        assert response.rejection == "unknown_alias"
