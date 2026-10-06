"""MARS safety invariants that hold before any ranking occurs.

Covers MARS-017/018 (output integrity — MARS selects, it never synthesizes) and
MARS-027/028 (judge-generator independence and roster sufficiency).

Both are checkable without judging, and both must hold on the single-candidate
short-circuit as well as the reranked path.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.backend.ml.extraction.mars.candidates import build_candidates
from src.backend.ml.extraction.mars.safety import (
    MARS_INTEGRITY_FIELDS,
    MarsAbstentionReason,
    eligible_judges,
    find_matching_candidate,
    roster_shortfall,
)
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


def _obs(**kw: object) -> StructuredObservation:
    payload: dict[str, object] = {
        "child_id": "child_1",
        "session_id": "session_1",
        "contributor_role": ContributorRole.INTERVENTIONIST,
        "observation_date": date(2026, 9, 7),
        "setting": Setting.CLINIC,
        "domain": Domain.SOCIAL_COMMUNICATION,
        "behavior": "Child pointed",
        "modality": Modality.GESTURAL,
        "prompt_level": PromptLevel.INDEPENDENT,
        "outcome": Outcome.CORRECT,
        "confidence": 0.8,
    }
    payload.update(kw)
    return StructuredObservation(**payload)  # type: ignore[arg-type]


def _result(model: str, observation: StructuredObservation) -> ExtractionResult:
    return ExtractionResult(
        status=ExtractionStatus.SUCCESS,
        observations=[observation],
        provider="test_provider",
        model=model,
        prompt_version="1.0",
    )


class TestOutputIntegrity:
    """MARS-017: the returned observation equals one and the same candidate."""

    # @spec MARS-017
    def test_an_unmodified_candidate_matches(self) -> None:
        candidates = build_candidates([_result("model_a", _obs())])

        assert find_matching_candidate(candidates[0].observation, candidates) is not None

    # @spec MARS-017, MARS-018
    def test_fields_combined_from_two_candidates_do_not_match(self) -> None:
        """The defect this invariant exists to prevent.

        Every individual value below exists in some candidate, yet the assembled
        observation was never produced by any of them.
        """
        c1 = _obs(domain=Domain.SOCIAL_COMMUNICATION, outcome=Outcome.CORRECT)
        c2 = _obs(domain=Domain.LANGUAGE, outcome=Outcome.INCORRECT)
        candidates = build_candidates([_result("model_a", c1), _result("model_b", c2)])

        frankenstein = _obs(
            domain=Domain.SOCIAL_COMMUNICATION,  # from C1
            outcome=Outcome.INCORRECT,  # from C2
        )

        assert find_matching_candidate(frankenstein, candidates) is None

    # @spec MARS-017, MARS-018
    def test_a_value_present_in_no_candidate_does_not_match(self) -> None:
        candidates = build_candidates([_result("model_a", _obs())])
        fabricated = _obs(behavior="Child spoke a full sentence")

        assert find_matching_candidate(fabricated, candidates) is None

    # @spec MARS-017
    def test_matching_uses_the_same_normalization_as_deduplication(self) -> None:
        """Case and surrounding whitespace do not break identity."""
        candidates = build_candidates([_result("model_a", _obs(behavior="Child Pointed"))])

        assert find_matching_candidate(_obs(behavior="  child pointed "), candidates) is not None

    # @spec MARS-017
    def test_semantically_similar_wording_does_not_match(self) -> None:
        """Integrity is identity, not interpretation."""
        candidates = build_candidates([_result("model_a", _obs(behavior="improved"))])

        assert find_matching_candidate(_obs(behavior="improving"), candidates) is None

    # @spec MARS-017
    def test_returns_the_specific_candidate_that_matched(self) -> None:
        c1, c2 = _obs(behavior="X"), _obs(behavior="Y")
        candidates = build_candidates([_result("model_a", c1), _result("model_b", c2)])

        matched = find_matching_candidate(_obs(behavior="Y"), candidates)

        assert matched is not None
        assert matched.generator_ids == ["model_b"]

    # @spec MARS-017
    def test_no_candidates_never_matches(self) -> None:
        assert find_matching_candidate(_obs(), []) is None

    # @spec MARS-017, MARS-018
    def test_integrity_applies_on_the_single_candidate_path(self) -> None:
        """MARS-006 skips reranking, never integrity. A sole candidate is the
        case with the least corroboration, not the most."""
        candidates = build_candidates([_result("model_a", _obs(behavior="X"))])

        assert find_matching_candidate(_obs(behavior="X"), candidates) is not None
        assert find_matching_candidate(_obs(behavior="tampered"), candidates) is None

    # @spec MARS-018
    def test_integrity_failure_has_its_own_reason_code(self) -> None:
        assert MarsAbstentionReason.INTEGRITY_FAILURE == "integrity_failure"


class TestJudgeIndependence:
    """MARS-027: a model never judges a set containing its own generation."""

    # @spec MARS-027
    def test_a_generator_is_ineligible_to_judge(self) -> None:
        candidates = build_candidates([_result("model_a", _obs(behavior="X"))])

        assert eligible_judges(["model_a", "model_d"], candidates) == ["model_d"]

    # @spec MARS-027
    def test_eligibility_spans_every_candidate_not_just_one(self) -> None:
        candidates = build_candidates(
            [_result("model_a", _obs(behavior="X")), _result("model_b", _obs(behavior="Y"))]
        )

        assert eligible_judges(["model_a", "model_b", "model_d"], candidates) == ["model_d"]

    # @spec MARS-004, MARS-027
    def test_a_merged_generator_remains_ineligible(self) -> None:
        """The dedup loophole. Both models produced the same fields, so the
        duplicate collapsed — neither becomes independent as a result, and
        identical output is likeliest between similar models, which is exactly
        where self-preference is most probable."""
        candidates = build_candidates(
            [_result("model_a", _obs(behavior="X")), _result("model_b", _obs(behavior="X"))]
        )

        assert len(candidates) == 1
        assert candidates[0].generator_ids == ["model_a", "model_b"]
        assert eligible_judges(["model_a", "model_b", "model_d"], candidates) == ["model_d"]

    # @spec MARS-027
    def test_an_unrelated_model_is_eligible(self) -> None:
        candidates = build_candidates([_result("model_a", _obs())])

        assert eligible_judges(["model_d", "model_e"], candidates) == ["model_d", "model_e"]

    # @spec MARS-027
    def test_same_family_but_different_model_is_eligible(self) -> None:
        """Exact overlap is prohibited; same-family overlap is recorded, not
        forbidden — prohibiting it would make the roster infeasible to satisfy
        from locally available models."""
        candidates = build_candidates([_result("llama3.2:1b", _obs())])

        assert eligible_judges(["llama3.2:3b"], candidates) == ["llama3.2:3b"]

    # @spec MARS-027
    def test_eligibility_preserves_roster_order(self) -> None:
        candidates = build_candidates([_result("model_b", _obs())])

        assert eligible_judges(["model_d", "model_b", "model_c"], candidates) == [
            "model_d",
            "model_c",
        ]

    # @spec MARS-027
    def test_every_judge_may_be_excluded(self) -> None:
        candidates = build_candidates(
            [_result("model_a", _obs(behavior="X")), _result("model_b", _obs(behavior="Y"))]
        )

        assert eligible_judges(["model_a", "model_b"], candidates) == []


class TestRosterSufficiency:
    """MARS-028: too few eligible judges abstains rather than relaxing MARS-027."""

    # @spec MARS-028
    def test_shortfall_when_roster_cannot_supply_the_minimum(self) -> None:
        candidates = build_candidates(
            [_result("model_a", _obs(behavior="X")), _result("model_b", _obs(behavior="Y"))]
        )

        shortfall = roster_shortfall(
            ["model_a", "model_b", "model_d"], candidates, min_eligible_judges=3
        )

        assert shortfall is MarsAbstentionReason.INSUFFICIENT_ELIGIBLE_JUDGES

    # @spec MARS-028
    def test_no_shortfall_when_exactly_the_minimum_is_eligible(self) -> None:
        candidates = build_candidates([_result("model_a", _obs())])

        assert (
            roster_shortfall(
                ["model_a", "model_d", "model_e"], candidates, min_eligible_judges=2
            )
            is None
        )

    # @spec MARS-027, MARS-028
    def test_generators_and_judges_from_one_roster_leave_nobody_eligible(self) -> None:
        """The feasibility edge: three generators judged by the same three models."""
        candidates = build_candidates(
            [_result(m, _obs(behavior=m)) for m in ("model_a", "model_b", "model_c")]
        )

        assert eligible_judges(["model_a", "model_b", "model_c"], candidates) == []
        assert (
            roster_shortfall(
                ["model_a", "model_b", "model_c"], candidates, min_eligible_judges=1
            )
            is MarsAbstentionReason.INSUFFICIENT_ELIGIBLE_JUDGES
        )

    # @spec MARS-006, MARS-028
    @pytest.mark.parametrize("min_eligible", [1, 3, 10])
    def test_single_candidate_path_needs_no_judges_at_all(self, min_eligible: int) -> None:
        """MARS-028 is scoped to the reranking path. A sole candidate returns
        without a roster, however large the configured minimum."""
        candidates = build_candidates([_result("model_a", _obs())])

        assert roster_shortfall([], candidates, min_eligible_judges=min_eligible) is None

    # @spec MARS-028
    def test_empty_roster_with_multiple_candidates_is_a_shortfall(self) -> None:
        candidates = build_candidates(
            [_result("model_a", _obs(behavior="X")), _result("model_b", _obs(behavior="Y"))]
        )

        assert (
            roster_shortfall([], candidates, min_eligible_judges=1)
            is MarsAbstentionReason.INSUFFICIENT_ELIGIBLE_JUDGES
        )

    # @spec MARS-026, MARS-028
    def test_shortfall_reason_is_distinct_from_the_response_failure(self) -> None:
        """Roster insufficiency and invalid judge responses have different
        remedies — configuration versus model execution — so they never share
        a reason code."""
        assert (
            MarsAbstentionReason.INSUFFICIENT_ELIGIBLE_JUDGES
            != MarsAbstentionReason.INSUFFICIENT_VALID_JUDGE_RESPONSES
        )


class TestIntegrityFieldSet:
    """MARS-017's field set is designated, not inherited from the schema.

    Deriving it from `StructuredObservation.model_fields` would let a future
    operational field — a validation timestamp, a UI flag, a source version —
    silently change integrity policy the moment someone adds it.
    """

    # @spec MARS-017
    def test_covers_every_extracted_field(self) -> None:
        from src.backend.schemas.observation_schema import LLM_EXTRACTED_FIELDS

        assert set(MARS_INTEGRITY_FIELDS) >= LLM_EXTRACTED_FIELDS

    # @spec MARS-017
    def test_covers_application_known_attribution(self) -> None:
        assert {"child_id", "session_id", "setting"} <= set(MARS_INTEGRITY_FIELDS)

    # @spec MARS-017
    def test_excludes_generator_self_assessment(self) -> None:
        """`confidence` and `abstention_reason` describe the generator, not the
        observation, and including them would collide with MARS-032."""
        assert "confidence" not in MARS_INTEGRITY_FIELDS
        assert "abstention_reason" not in MARS_INTEGRITY_FIELDS

    # @spec MARS-017
    def test_a_tampered_child_id_fails_integrity(self) -> None:
        candidates = build_candidates([_result("model_a", _obs())])

        assert find_matching_candidate(_obs(child_id="child_2"), candidates) is None

    # @spec MARS-017
    def test_confidence_alone_does_not_break_a_match(self) -> None:
        """A merged candidate carries one contributor's confidence; returning it
        must not fail integrity on that basis."""
        candidates = build_candidates([_result("model_a", _obs(confidence=0.82))])

        assert find_matching_candidate(_obs(confidence=0.91), candidates) is not None

    # @spec MARS-017
    def test_set_is_explicit_not_derived_from_the_schema(self) -> None:
        """A new schema field must not join the integrity set by default."""
        from src.backend.schemas.observation_schema import StructuredObservation

        assert set(MARS_INTEGRITY_FIELDS) != set(StructuredObservation.model_fields)
