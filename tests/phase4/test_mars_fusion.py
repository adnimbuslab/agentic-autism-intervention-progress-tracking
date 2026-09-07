"""MARS ranking and fusion: response validation and deterministic selection.

Covers MARS-009/010 (judges supply an ordering and nothing else), MARS-011
(`min_valid_judge_responses`), MARS-012 (Reciprocal Rank Fusion in code),
MARS-013 (stable-internal-id tie-break) and MARS-021 (multiplicity carries no
numerical weight).

The agreement gate is *not* here — fusion produces a provisional winner, and
whether that winner may be returned is step 7's question.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.backend.ml.extraction.mars.blinding import (
    build_judge_presentation,
    derive_request_seed,
)
from src.backend.ml.extraction.mars.candidates import build_candidates
from src.backend.ml.extraction.mars.fusion import (
    RRF_K,
    JudgeResponse,
    fuse_rankings,
    parse_judge_response,
    select_provisional_winner,
    validate_response_count,
)
from src.backend.ml.extraction.mars.safety import MarsAbstentionReason
from src.backend.ml.extraction.schemas import ExtractionResult, ExtractionStatus
from src.backend.schemas.observation_schema import (
    ContributorRole,
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    Setting,
    StructuredObservation,
)


def _obs(behavior: str) -> StructuredObservation:
    return StructuredObservation(
        child_id="child_1",
        session_id="session_1",
        contributor_role=ContributorRole.INTERVENTIONIST,
        observation_date=date(2026, 9, 7),
        setting=Setting.CLINIC,
        domain=Domain.SOCIAL_COMMUNICATION,
        behavior=behavior,
        modality=Modality.GESTURAL,
        prompt_level=PromptLevel.INDEPENDENT,
        outcome=Outcome.CORRECT,
        confidence=0.8,
    )


def _result(model: str, behavior: str) -> ExtractionResult:
    return ExtractionResult(
        status=ExtractionStatus.SUCCESS,
        observations=[_obs(behavior)],
        provider="test_provider",
        model=model,
        prompt_version="1.0",
    )


def _candidates(*pairs: tuple[str, str]):
    return build_candidates([_result(m, b) for m, b in pairs])


ABC = (("model_a", "A"), ("model_b", "B"), ("model_c", "C"))


def _presentation(candidates, judge: str = "model_d"):
    return build_judge_presentation(
        judge_id=judge,
        candidates=candidates,
        request_seed=derive_request_seed(
            source_id="seg_1", mars_version="1.0.0", candidates=candidates, run_seed="r"
        ),
    )


def _aliases_for(presentation, behaviors: list[str], candidates) -> list[str]:
    """Judge-visible aliases naming candidates in the given behavior order."""
    by_behavior = {c.observation.behavior: c.internal_id for c in candidates}
    reverse = {internal: alias for alias, internal in presentation.aliases.items()}
    return [reverse[by_behavior[b]] for b in behaviors]


def _ranking(behaviors: list[str], candidates, judge: str = "model_d") -> JudgeResponse:
    presentation = _presentation(candidates, judge)
    return parse_judge_response(
        _aliases_for(presentation, behaviors, candidates), presentation, judge_id=judge
    )


class TestResponseValidation:
    """MARS-009/010: an ordering over presented aliases, or nothing."""

    # @spec MARS-009
    def test_a_complete_ordering_is_valid(self) -> None:
        candidates = _candidates(*ABC)
        response = _ranking(["A", "B", "C"], candidates)

        assert response.is_valid
        by_behavior = {c.observation.behavior: c.internal_id for c in candidates}
        assert response.internal_ids == [by_behavior[b] for b in ("A", "B", "C")]

    # @spec MARS-010
    def test_an_unpresented_alias_is_rejected(self) -> None:
        candidates = _candidates(*ABC)
        presentation = _presentation(candidates)
        aliases = _aliases_for(presentation, ["A", "B", "C"], candidates)

        response = parse_judge_response(
            [*aliases[:2], "ZZZZ"], presentation, judge_id="model_d"
        )

        assert not response.is_valid
        assert response.rejection == "unknown_alias"

    # @spec MARS-010
    def test_an_omitted_candidate_is_rejected(self) -> None:
        candidates = _candidates(*ABC)
        presentation = _presentation(candidates)
        aliases = _aliases_for(presentation, ["A", "B", "C"], candidates)

        response = parse_judge_response(aliases[:2], presentation, judge_id="model_d")

        assert not response.is_valid
        assert response.rejection == "incomplete_ordering"

    # @spec MARS-010
    def test_a_duplicated_alias_is_rejected(self) -> None:
        candidates = _candidates(*ABC)
        presentation = _presentation(candidates)
        aliases = _aliases_for(presentation, ["A", "B", "C"], candidates)

        response = parse_judge_response(
            [aliases[0], aliases[0], aliases[1]], presentation, judge_id="model_d"
        )

        assert not response.is_valid
        assert response.rejection == "duplicate_alias"

    # @spec MARS-010
    @pytest.mark.parametrize(
        "raw",
        [
            None,
            "",
            "K7 P4 R9",
            {"ranking": ["K7"]},
            [1, 2, 3],
            [],
        ],
    )
    def test_unparseable_responses_are_rejected(self, raw: object) -> None:
        candidates = _candidates(*ABC)
        response = parse_judge_response(raw, _presentation(candidates), judge_id="model_d")

        assert not response.is_valid
        assert response.rejection is not None

    # @spec MARS-009
    def test_a_response_carrying_field_values_is_not_read_for_them(self) -> None:
        """A judge that emits an extraction is an extractor. There is no code
        path that reads a structured field value from a judge response."""
        candidates = _candidates(*ABC)
        response = parse_judge_response(
            {"ranking": ["K7", "P4", "R9"], "outcome": "correct", "domain": "language"},
            _presentation(candidates),
            judge_id="model_d",
        )

        assert not response.is_valid
        assert not hasattr(response, "outcome")
        assert not hasattr(response, "domain")

    # @spec MARS-010
    def test_rejection_records_the_judge_for_provenance(self) -> None:
        candidates = _candidates(*ABC)
        response = parse_judge_response(None, _presentation(candidates), judge_id="model_d")

        assert response.judge_id == "model_d"
        assert not response.is_valid


class TestResponseCount:
    """MARS-011: too few valid rankings abstains rather than fusing the rest."""

    # @spec MARS-011
    def test_below_minimum_abstains(self) -> None:
        candidates = _candidates(*ABC)
        valid = [_ranking(["A", "B", "C"], candidates)]

        assert (
            validate_response_count(valid, min_valid_judge_responses=2)
            is MarsAbstentionReason.INSUFFICIENT_VALID_JUDGE_RESPONSES
        )

    # @spec MARS-011
    def test_exactly_the_minimum_proceeds(self) -> None:
        candidates = _candidates(*ABC)
        valid = [
            _ranking(["A", "B", "C"], candidates, judge="model_d"),
            _ranking(["B", "A", "C"], candidates, judge="model_e"),
        ]

        assert validate_response_count(valid, min_valid_judge_responses=2) is None

    # @spec MARS-010, MARS-011
    def test_invalid_responses_do_not_count_toward_the_minimum(self) -> None:
        candidates = _candidates(*ABC)
        presentation = _presentation(candidates)
        responses = [
            _ranking(["A", "B", "C"], candidates),
            parse_judge_response(None, presentation, judge_id="model_e"),
        ]

        assert (
            validate_response_count(responses, min_valid_judge_responses=2)
            is MarsAbstentionReason.INSUFFICIENT_VALID_JUDGE_RESPONSES
        )

    # @spec MARS-011
    def test_no_responses_at_all_abstains(self) -> None:
        assert (
            validate_response_count([], min_valid_judge_responses=1)
            is MarsAbstentionReason.INSUFFICIENT_VALID_JUDGE_RESPONSES
        )


class TestReciprocalRankFusion:
    """MARS-012: fusion is arithmetic, performed in code."""

    # @spec MARS-012
    def test_scores_match_the_rrf_formula(self) -> None:
        candidates = _candidates(*ABC)
        by_behavior = {c.observation.behavior: c.internal_id for c in candidates}
        rankings = [
            _ranking(["A", "B", "C"], candidates, judge="model_d"),
            _ranking(["A", "C", "B"], candidates, judge="model_e"),
            _ranking(["B", "A", "C"], candidates, judge="model_f"),
        ]

        scores = fuse_rankings(rankings, candidates)

        assert scores[by_behavior["A"]] == pytest.approx(
            1 / (RRF_K + 1) + 1 / (RRF_K + 1) + 1 / (RRF_K + 2)
        )
        assert scores[by_behavior["B"]] == pytest.approx(
            1 / (RRF_K + 2) + 1 / (RRF_K + 3) + 1 / (RRF_K + 1)
        )
        assert scores[by_behavior["C"]] == pytest.approx(
            1 / (RRF_K + 3) + 1 / (RRF_K + 2) + 1 / (RRF_K + 3)
        )

    # @spec MARS-012
    def test_uses_the_whole_ranking_not_just_first_place(self) -> None:
        """A candidate ranked second by everyone outscores one ranked first once
        and last otherwise — the reason RRF is preferred to a first-place vote."""
        candidates = _candidates(*ABC)
        by_behavior = {c.observation.behavior: c.internal_id for c in candidates}
        rankings = [
            _ranking(["A", "C", "B"], candidates, judge="model_d"),
            _ranking(["B", "C", "A"], candidates, judge="model_e"),
            _ranking(["B", "C", "A"], candidates, judge="model_f"),
        ]

        scores = fuse_rankings(rankings, candidates)

        assert scores[by_behavior["C"]] > scores[by_behavior["A"]]

    # @spec MARS-012
    def test_every_candidate_receives_a_score(self) -> None:
        candidates = _candidates(*ABC)
        scores = fuse_rankings([_ranking(["A", "B", "C"], candidates)], candidates)

        assert set(scores) == {c.internal_id for c in candidates}

    # @spec MARS-012
    def test_invalid_rankings_are_excluded_from_fusion(self) -> None:
        candidates = _candidates(*ABC)
        presentation = _presentation(candidates)
        valid = _ranking(["A", "B", "C"], candidates)
        invalid = parse_judge_response(None, presentation, judge_id="model_e")

        assert fuse_rankings([valid, invalid], candidates) == fuse_rankings(
            [valid], candidates
        )


class TestTieBreaking:
    """MARS-013: ties resolve by multiplicity, then stable internal id."""

    # @spec MARS-013, MARS-021
    def test_exact_tie_breaks_toward_higher_multiplicity(self) -> None:
        # A produced by two generators, B by one; judges split evenly.
        candidates = build_candidates(
            [
                _result("model_a", "A"),
                _result("model_x", "A"),
                _result("model_b", "B"),
            ]
        )
        by_behavior = {c.observation.behavior: c.internal_id for c in candidates}
        rankings = [
            _ranking(["A", "B"], candidates, judge="model_d"),
            _ranking(["B", "A"], candidates, judge="model_e"),
        ]

        scores = fuse_rankings(rankings, candidates)

        assert scores[by_behavior["A"]] == pytest.approx(scores[by_behavior["B"]])
        # Guard against this test passing for the wrong reason: the id tie-break
        # alone would pick B here, so A winning can only be multiplicity's doing.
        assert by_behavior["A"] > by_behavior["B"]
        assert select_provisional_winner(scores, candidates) == by_behavior["A"]

    # @spec MARS-013
    def test_remaining_tie_breaks_by_ascending_internal_id(self) -> None:
        candidates = _candidates(("model_a", "A"), ("model_b", "B"))
        rankings = [
            _ranking(["A", "B"], candidates, judge="model_d"),
            _ranking(["B", "A"], candidates, judge="model_e"),
        ]

        scores = fuse_rankings(rankings, candidates)
        expected = min(c.internal_id for c in candidates)

        assert select_provisional_winner(scores, candidates) == expected

    # @spec MARS-013
    def test_tie_break_never_uses_a_judge_visible_alias(self) -> None:
        """Aliases are per-judge and carry no global ordering, so a tie broken on
        one would not be reproducible across judges."""
        candidates = _candidates(("model_a", "A"), ("model_b", "B"))
        rankings = [
            _ranking(["A", "B"], candidates, judge="model_d"),
            _ranking(["B", "A"], candidates, judge="model_e"),
        ]
        scores = fuse_rankings(rankings, candidates)

        winner = select_provisional_winner(scores, candidates)

        assert winner in {c.internal_id for c in candidates}

    # @spec MARS-014
    def test_selection_is_reproducible_from_stored_rankings(self) -> None:
        candidates = _candidates(*ABC)
        rankings = [
            _ranking(["A", "B", "C"], candidates, judge="model_d"),
            _ranking(["B", "A", "C"], candidates, judge="model_e"),
        ]

        first = select_provisional_winner(fuse_rankings(rankings, candidates), candidates)
        second = select_provisional_winner(fuse_rankings(rankings, candidates), candidates)

        assert first == second


class TestMultiplicityHasNoNumericalWeight:
    """MARS-021: multiplicity is a tie-break, never a score."""

    # @spec MARS-021
    def test_scores_are_identical_regardless_of_multiplicity(self) -> None:
        """Three weak models agreeing is a measure of shared training
        distribution, not of correctness."""
        single = _candidates(("model_a", "A"), ("model_b", "B"))
        merged = build_candidates(
            [
                _result("model_a", "A"),
                _result("model_x", "A"),
                _result("model_y", "A"),
                _result("model_b", "B"),
            ]
        )

        assert merged[0].multiplicity == 3
        assert single[0].multiplicity == 1

        single_scores = fuse_rankings(
            [_ranking(["A", "B"], single, judge="model_d")], single
        )
        merged_scores = fuse_rankings(
            [_ranking(["A", "B"], merged, judge="model_d")], merged
        )

        assert sorted(single_scores.values()) == pytest.approx(
            sorted(merged_scores.values())
        )

    # @spec MARS-021
    def test_multiplicity_cannot_overturn_a_ranked_result(self) -> None:
        """A candidate with multiplicity 3 that judges rank last still loses."""
        candidates = build_candidates(
            [
                _result("model_a", "A"),
                _result("model_x", "A"),
                _result("model_y", "A"),
                _result("model_b", "B"),
            ]
        )
        by_behavior = {c.observation.behavior: c.internal_id for c in candidates}
        rankings = [
            _ranking(["B", "A"], candidates, judge="model_d"),
            _ranking(["B", "A"], candidates, judge="model_e"),
        ]

        scores = fuse_rankings(rankings, candidates)

        assert scores[by_behavior["B"]] > scores[by_behavior["A"]]
        assert select_provisional_winner(scores, candidates) == by_behavior["B"]
