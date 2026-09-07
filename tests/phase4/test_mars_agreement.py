"""MARS agreement gate: may the provisional RRF winner proceed?

Covers MARS-015 (top-choice support of the provisionally selected candidate),
MARS-016 (threshold gate), MARS-030 (fusion winner must also be the modal first
choice) and MARS-031 (execution order).

The gate never selects. It is handed the winner fusion already chose and answers
one question about that candidate. Abstention envelopes, confidence composition
and provider orchestration are owned by later steps.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.backend.ml.extraction.mars.agreement import (
    AgreementFailure,
    evaluate_agreement,
)
from src.backend.ml.extraction.mars.blinding import (
    build_judge_presentation,
    derive_request_seed,
)
from src.backend.ml.extraction.mars.candidates import build_candidates
from src.backend.ml.extraction.mars.fusion import (
    JudgeResponse,
    fuse_rankings,
    parse_judge_response,
    select_provisional_winner,
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

THRESHOLD = 0.6


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


def _ranking(behaviors: list[str], candidates, judge: str) -> JudgeResponse:
    presentation = build_judge_presentation(
        judge_id=judge,
        candidates=candidates,
        request_seed=derive_request_seed(
            source_id="seg_1", mars_version="1.0.0", candidates=candidates, run_seed="r"
        ),
    )
    by_behavior = {c.observation.behavior: c.internal_id for c in candidates}
    reverse = {internal: alias for alias, internal in presentation.aliases.items()}
    aliases = [reverse[by_behavior[b]] for b in behaviors]
    return parse_judge_response(aliases, presentation, judge_id=judge)


def _ids(candidates) -> dict[str, str]:
    return {c.observation.behavior: c.internal_id for c in candidates}


def _winner(rankings, candidates) -> str:
    return select_provisional_winner(fuse_rankings(rankings, candidates), candidates)


class TestGatePasses:
    """MARS-015/016: sufficient top-choice support for the returned candidate."""

    # @spec MARS-015, MARS-016
    def test_unanimous_first_choice_passes(self) -> None:
        candidates = _candidates(("model_a", "A"), ("model_b", "B"), ("model_c", "C"))
        rankings = [
            _ranking(["A", "B", "C"], candidates, "j1"),
            _ranking(["A", "C", "B"], candidates, "j2"),
            _ranking(["A", "B", "C"], candidates, "j3"),
        ]
        winner = _winner(rankings, candidates)
        assert winner == _ids(candidates)["A"]

        decision = evaluate_agreement(
            provisional_internal_id=winner, responses=rankings, threshold=THRESHOLD
        )

        assert decision.passed
        assert decision.first_choice_support == pytest.approx(1.0)
        assert decision.is_modal_first_choice
        assert decision.failure is None
        assert decision.reason_code is None

    # @spec MARS-016
    def test_support_exactly_at_the_threshold_passes(self) -> None:
        """The gate abstains *below* the threshold, so equality proceeds."""
        candidates = _candidates(("model_a", "A"), ("model_b", "B"))
        rankings = [
            _ranking(["A", "B"], candidates, "j1"),
            _ranking(["A", "B"], candidates, "j2"),
            _ranking(["A", "B"], candidates, "j3"),
            _ranking(["B", "A"], candidates, "j4"),
        ]
        winner = _winner(rankings, candidates)

        decision = evaluate_agreement(
            provisional_internal_id=winner, responses=rankings, threshold=0.75
        )

        assert decision.first_choice_support == pytest.approx(0.75)
        assert decision.passed


class TestFusionWinnerMustBeModalFirstChoice:
    """MARS-030 — the reason this gate exists separately from fusion."""

    # @spec MARS-030
    def test_rrf_winner_with_no_first_place_votes_is_rejected(self) -> None:
        """A is ranked second by every judge, so whole-ranking RRF selects it
        while three other candidates each hold a first-place vote. A mathematically
        valid RRF winner must not escape the gate on fused score alone.
        """
        candidates = _candidates(
            ("model_a", "A"), ("model_b", "B"), ("model_c", "C"), ("model_d", "D")
        )
        ids = _ids(candidates)
        rankings = [
            _ranking(["B", "A", "C", "D"], candidates, "j1"),
            _ranking(["C", "A", "D", "B"], candidates, "j2"),
            _ranking(["D", "A", "B", "C"], candidates, "j3"),
        ]

        # Independently established facts, asserted before the gate is consulted.
        winner = _winner(rankings, candidates)
        assert winner == ids["A"], "fusion must genuinely select A for this test to bind"

        first_places = [r.internal_ids[0] for r in rankings]
        assert first_places.count(ids["A"]) == 0
        assert sorted(first_places) == sorted([ids["B"], ids["C"], ids["D"]])

        decision = evaluate_agreement(
            provisional_internal_id=winner, responses=rankings, threshold=0.0
        )

        assert not decision.passed
        assert decision.failure is AgreementFailure.NOT_MODAL_FIRST_CHOICE
        assert decision.reason_code is MarsAbstentionReason.JUDGE_DISAGREEMENT
        assert decision.first_choice_support == pytest.approx(0.0)

    # @spec MARS-030
    def test_a_zero_threshold_cannot_bypass_the_modal_requirement(self) -> None:
        """MARS-030 is independent of MARS-016: no threshold value admits a
        winner that is not the modal first choice."""
        candidates = _candidates(
            ("model_a", "A"), ("model_b", "B"), ("model_c", "C"), ("model_d", "D")
        )
        rankings = [
            _ranking(["B", "A", "C", "D"], candidates, "j1"),
            _ranking(["C", "A", "D", "B"], candidates, "j2"),
            _ranking(["D", "A", "B", "C"], candidates, "j3"),
        ]

        decision = evaluate_agreement(
            provisional_internal_id=_winner(rankings, candidates),
            responses=rankings,
            threshold=0.0,
        )

        assert not decision.passed


class TestModalButBelowThreshold:
    """MARS-016 is a separate condition from MARS-030."""

    # @spec MARS-015, MARS-016
    def test_modal_winner_below_threshold_is_rejected(self) -> None:
        candidates = _candidates(("model_a", "A"), ("model_b", "B"), ("model_c", "C"))
        ids = _ids(candidates)
        rankings = [
            _ranking(["A", "B", "C"], candidates, "j1"),
            _ranking(["A", "B", "C"], candidates, "j2"),
            _ranking(["B", "A", "C"], candidates, "j3"),
        ]
        winner = _winner(rankings, candidates)
        assert winner == ids["A"]

        decision = evaluate_agreement(
            provisional_internal_id=winner, responses=rankings, threshold=0.8
        )

        assert decision.is_modal_first_choice
        assert decision.first_choice_support == pytest.approx(2 / 3)
        assert not decision.passed
        assert decision.failure is AgreementFailure.BELOW_THRESHOLD
        assert decision.reason_code is MarsAbstentionReason.JUDGE_DISAGREEMENT

    # @spec MARS-016
    def test_the_same_case_passes_under_a_lower_threshold(self) -> None:
        candidates = _candidates(("model_a", "A"), ("model_b", "B"), ("model_c", "C"))
        rankings = [
            _ranking(["A", "B", "C"], candidates, "j1"),
            _ranking(["A", "B", "C"], candidates, "j2"),
            _ranking(["B", "A", "C"], candidates, "j3"),
        ]

        decision = evaluate_agreement(
            provisional_internal_id=_winner(rankings, candidates),
            responses=rankings,
            threshold=0.6,
        )

        assert decision.passed


class TestModalTie:
    """A tie for the mode is not a consensus, and is not resolved here."""

    # @spec MARS-030
    def test_tied_first_choice_mode_is_rejected(self) -> None:
        candidates = _candidates(("model_a", "A"), ("model_b", "B"), ("model_c", "C"))
        ids = _ids(candidates)
        rankings = [
            _ranking(["A", "B", "C"], candidates, "j1"),
            _ranking(["A", "C", "B"], candidates, "j2"),
            _ranking(["B", "A", "C"], candidates, "j3"),
            _ranking(["B", "C", "A"], candidates, "j4"),
        ]

        first_places = [r.internal_ids[0] for r in rankings]
        assert first_places.count(ids["A"]) == 2
        assert first_places.count(ids["B"]) == 2

        decision = evaluate_agreement(
            provisional_internal_id=_winner(rankings, candidates),
            responses=rankings,
            threshold=0.0,
        )

        assert not decision.passed
        assert decision.failure is AgreementFailure.MODAL_TIE
        assert decision.reason_code is MarsAbstentionReason.JUDGE_DISAGREEMENT
        assert sorted(decision.modal_internal_ids) == sorted([ids["A"], ids["B"]])

    # @spec MARS-030
    def test_a_modal_tie_is_not_broken_by_id_multiplicity_or_score(self) -> None:
        """Whichever candidate fusion picked, the tie itself fails the gate."""
        candidates = _candidates(("model_a", "A"), ("model_b", "B"), ("model_c", "C"))
        ids = _ids(candidates)
        rankings = [
            _ranking(["A", "B", "C"], candidates, "j1"),
            _ranking(["A", "C", "B"], candidates, "j2"),
            _ranking(["B", "A", "C"], candidates, "j3"),
            _ranking(["B", "C", "A"], candidates, "j4"),
        ]

        for provisional in (ids["A"], ids["B"]):
            decision = evaluate_agreement(
                provisional_internal_id=provisional, responses=rankings, threshold=0.0
            )
            assert not decision.passed
            assert decision.failure is AgreementFailure.MODAL_TIE


class TestOnlyValidRankingsCount:
    """MARS-015: the agreement value derives only from valid judge rankings."""

    # @spec MARS-015
    def test_invalid_rankings_contribute_no_support(self) -> None:
        candidates = _candidates(("model_a", "A"), ("model_b", "B"), ("model_c", "C"))
        presentation = build_judge_presentation(
            judge_id="j_bad",
            candidates=candidates,
            request_seed=derive_request_seed(
                source_id="seg_1", mars_version="1.0.0", candidates=candidates, run_seed="r"
            ),
        )
        valid = [
            _ranking(["A", "B", "C"], candidates, "j1"),
            _ranking(["A", "B", "C"], candidates, "j2"),
        ]
        invalid = parse_judge_response(None, presentation, judge_id="j_bad")

        with_invalid = evaluate_agreement(
            provisional_internal_id=_winner(valid, candidates),
            responses=[*valid, invalid],
            threshold=THRESHOLD,
        )
        without = evaluate_agreement(
            provisional_internal_id=_winner(valid, candidates),
            responses=valid,
            threshold=THRESHOLD,
        )

        assert with_invalid.valid_judge_count == 2
        assert with_invalid.first_choice_support == without.first_choice_support
        assert with_invalid.first_choice_support == pytest.approx(1.0)

    # @spec MARS-015
    def test_no_valid_rankings_cannot_pass(self) -> None:
        candidates = _candidates(("model_a", "A"), ("model_b", "B"))
        presentation = build_judge_presentation(
            judge_id="j_bad",
            candidates=candidates,
            request_seed=derive_request_seed(
                source_id="seg_1", mars_version="1.0.0", candidates=candidates, run_seed="r"
            ),
        )
        invalid = [parse_judge_response(None, presentation, judge_id="j_bad")]

        decision = evaluate_agreement(
            provisional_internal_id=candidates[0].internal_id,
            responses=invalid,
            threshold=0.0,
        )

        assert not decision.passed
        assert decision.valid_judge_count == 0
        assert decision.failure is AgreementFailure.NO_VALID_RANKINGS
        assert decision.first_choice_support is None


class TestGateIndependence:
    """The gate evaluates what it is given, and nothing about candidates."""

    # @spec MARS-031
    def test_agreement_evaluates_the_supplied_winner_not_its_own_choice(self) -> None:
        """Handed a candidate fusion did not pick, the gate reports on *that*
        candidate rather than substituting the one judges preferred."""
        candidates = _candidates(("model_a", "A"), ("model_b", "B"), ("model_c", "C"))
        ids = _ids(candidates)
        rankings = [
            _ranking(["A", "B", "C"], candidates, "j1"),
            _ranking(["A", "B", "C"], candidates, "j2"),
            _ranking(["A", "B", "C"], candidates, "j3"),
        ]
        assert _winner(rankings, candidates) == ids["A"]

        decision = evaluate_agreement(
            provisional_internal_id=ids["C"], responses=rankings, threshold=0.0
        )

        assert decision.provisional_internal_id == ids["C"]
        assert decision.first_choice_support == pytest.approx(0.0)
        assert not decision.passed
        assert decision.modal_internal_ids == [ids["A"]]

    # @spec MARS-015
    def test_judge_ordering_does_not_change_the_outcome(self) -> None:
        candidates = _candidates(("model_a", "A"), ("model_b", "B"), ("model_c", "C"))
        rankings = [
            _ranking(["A", "B", "C"], candidates, "j1"),
            _ranking(["B", "A", "C"], candidates, "j2"),
            _ranking(["A", "C", "B"], candidates, "j3"),
        ]
        winner = _winner(rankings, candidates)

        forward = evaluate_agreement(
            provisional_internal_id=winner, responses=rankings, threshold=THRESHOLD
        )
        reversed_ = evaluate_agreement(
            provisional_internal_id=winner,
            responses=list(reversed(rankings)),
            threshold=THRESHOLD,
        )

        assert forward.passed == reversed_.passed
        assert forward.first_choice_support == reversed_.first_choice_support
        assert sorted(forward.modal_internal_ids) == sorted(reversed_.modal_internal_ids)

    # @spec MARS-021
    def test_multiplicity_carries_no_agreement_weight(self) -> None:
        """A candidate produced by three generators earns no extra vote."""
        merged = build_candidates(
            [
                _result("model_a", "A"),
                _result("model_x", "A"),
                _result("model_y", "A"),
                _result("model_b", "B"),
            ]
        )
        assert merged[0].multiplicity == 3
        ids = _ids(merged)
        rankings = [
            _ranking(["B", "A"], merged, "j1"),
            _ranking(["B", "A"], merged, "j2"),
            _ranking(["A", "B"], merged, "j3"),
        ]

        decision = evaluate_agreement(
            provisional_internal_id=ids["A"], responses=rankings, threshold=0.0
        )

        assert decision.first_choice_support == pytest.approx(1 / 3)
        assert decision.modal_internal_ids == [ids["B"]]
        assert not decision.passed

    # @spec MARS-015
    def test_agreement_needs_no_candidate_objects_at_all(self) -> None:
        """Internal ids cannot influence agreement, because the gate never sees
        the candidates — only the rankings and the id it was handed."""
        candidates = _candidates(("model_a", "A"), ("model_b", "B"))
        rankings = [
            _ranking(["A", "B"], candidates, "j1"),
            _ranking(["A", "B"], candidates, "j2"),
        ]

        decision = evaluate_agreement(
            provisional_internal_id=_ids(candidates)["A"],
            responses=rankings,
            threshold=0.5,
        )

        assert decision.passed


class TestThresholdIsSupplied:
    """Open Question 1 leaves the threshold value undetermined."""

    # @spec MARS-016
    def test_threshold_has_no_default(self) -> None:
        """Inventing one would settle a calibration decision by accident."""
        candidates = _candidates(("model_a", "A"), ("model_b", "B"))
        rankings = [_ranking(["A", "B"], candidates, "j1")]

        with pytest.raises(TypeError):
            evaluate_agreement(  # type: ignore[call-arg]
                provisional_internal_id=candidates[0].internal_id, responses=rankings
            )

    # @spec MARS-016
    def test_threshold_is_recorded_on_the_decision(self) -> None:
        candidates = _candidates(("model_a", "A"), ("model_b", "B"))
        rankings = [_ranking(["A", "B"], candidates, "j1")]

        decision = evaluate_agreement(
            provisional_internal_id=candidates[0].internal_id,
            responses=rankings,
            threshold=0.42,
        )

        assert decision.threshold == 0.42
