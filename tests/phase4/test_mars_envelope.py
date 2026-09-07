"""MARS result envelope: one canonical shape for every outcome.

Covers MARS-005 (no reviewable candidate), MARS-018 (integrity failure),
MARS-019/020 (provenance describing the execution that occurred), MARS-024
(status from MARS gates alone), MARS-025 (canonical abstention shape) and
MARS-026 (closed reason-code enumeration).

Provider orchestration is still out of scope — these builders are handed the
outcome of a run and shape it, they do not perform one.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.backend.ml.extraction.mars.agreement import AgreementDecision, AgreementFailure
from src.backend.ml.extraction.mars.candidates import build_candidates
from src.backend.ml.extraction.mars.confidence import (
    GeneratorConfidencePolicy,
    compose_confidence,
)
from src.backend.ml.extraction.mars.envelope import (
    ModelRole,
    build_abstained_result,
    build_selected_result,
)
from src.backend.ml.extraction.mars.safety import MarsAbstentionReason
from src.backend.ml.extraction.schemas import (
    ExtractionResult,
    ExtractionStatus,
    ModelDescriptor,
)
from src.backend.schemas.observation_schema import (
    ContributorRole,
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    Setting,
    StructuredObservation,
)

MIN = GeneratorConfidencePolicy.MINIMUM


def _obs(behavior: str, confidence: float | None = 0.8) -> StructuredObservation:
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
        confidence=confidence,
    )


def _result(model: str, behavior: str, confidence: float | None = 0.8) -> ExtractionResult:
    return ExtractionResult(
        status=ExtractionStatus.SUCCESS,
        observations=[_obs(behavior, confidence)],
        provider="test_provider",
        model=model,
        prompt_version="1.0",
    )


def _generators(*ids: str) -> list[ModelDescriptor]:
    return [
        ModelDescriptor(
            identifier=i, family=i.split("_")[0], config_hash="cfg1", role=ModelRole.GENERATOR
        )
        for i in ids
    ]


def _judges(*ids: str) -> list[ModelDescriptor]:
    return [
        ModelDescriptor(
            identifier=i, family=i.split("_")[0], config_hash="cfg2", role=ModelRole.JUDGE
        )
        for i in ids
    ]


def _decision(support: float | None, *, passed: bool, failure=None) -> AgreementDecision:
    return AgreementDecision(
        passed=passed,
        provisional_internal_id="cand_1",
        valid_judge_count=2,
        first_choice_support=support,
        is_modal_first_choice=passed,
        modal_internal_ids=["cand_1"] if passed else [],
        threshold=0.6,
        failure=failure,
        reason_code=MarsAbstentionReason.JUDGE_DISAGREEMENT if failure else None,
    )


ALL_REASONS = list(MarsAbstentionReason)


class TestCanonicalAbstentionShape:
    """MARS-025: one shape regardless of which gate raised it."""

    # @spec MARS-025, MARS-026
    @pytest.mark.parametrize("reason", ALL_REASONS)
    def test_every_reason_produces_the_same_envelope_shape(
        self, reason: MarsAbstentionReason
    ) -> None:
        result = build_abstained_result(
            reason_code=reason,
            candidate_count=0,
            generators=_generators("model_a"),
            judges=[],
        )

        assert result.status is ExtractionStatus.ABSTAINED
        assert result.observations == []
        assert result.reason_code == reason
        assert result.control_confidence is None
        assert result.provenance is not None
        assert result.provenance.selected_internal_id is None

    # @spec MARS-025
    def test_every_reason_yields_an_identical_field_set(self) -> None:
        dumps = [
            build_abstained_result(
                reason_code=reason,
                candidate_count=0,
                generators=_generators("model_a"),
                judges=[],
            ).model_dump()
            for reason in ALL_REASONS
        ]

        assert all(set(d) == set(dumps[0]) for d in dumps)
        assert all(
            set(d["provenance"]) == set(dumps[0]["provenance"]) for d in dumps
        )

    # @spec MARS-026
    def test_reason_code_enumeration_is_closed(self) -> None:
        assert {r.value for r in MarsAbstentionReason} == {
            "no_reviewable_candidate",
            "insufficient_eligible_judges",
            "insufficient_valid_judge_responses",
            "judge_disagreement",
            "integrity_failure",
        }


class TestProvenanceDescribesWhatHappened:
    """MARS-019: fields present and empty, never absent."""

    # @spec MARS-005, MARS-019
    def test_abstention_before_judging_carries_empty_judge_fields(self) -> None:
        """An abstention raised before any judge was invoked is a complete
        record, not a partial one."""
        result = build_abstained_result(
            reason_code=MarsAbstentionReason.NO_REVIEWABLE_CANDIDATE,
            candidate_count=0,
            generators=_generators("model_a", "model_b"),
            judges=[],
        )

        provenance = result.provenance
        assert provenance is not None
        assert provenance.generator_ids == ["model_a", "model_b"]
        assert provenance.judge_ids == []
        assert provenance.ranking == []
        assert provenance.fused_scores == {}
        assert provenance.top_choice_support is None
        assert provenance.modal_internal_ids == []
        assert provenance.agreement_threshold is None

    # @spec MARS-019
    def test_abstention_after_judging_carries_the_judge_evidence(self) -> None:
        result = build_abstained_result(
            reason_code=MarsAbstentionReason.JUDGE_DISAGREEMENT,
            candidate_count=2,
            generators=_generators("model_a", "model_b"),
            judges=_judges("judge_d", "judge_e"),
            rankings=[["cand_1", "cand_2"], ["cand_2", "cand_1"]],
            fused_scores={"cand_1": 0.032, "cand_2": 0.032},
            agreement=_decision(0.5, passed=False, failure=AgreementFailure.MODAL_TIE),
            seeds={"request": "abc", "judge_d": "def"},
        )

        provenance = result.provenance
        assert provenance is not None
        assert provenance.judge_ids == ["judge_d", "judge_e"]
        assert provenance.ranking == [["cand_1", "cand_2"], ["cand_2", "cand_1"]]
        assert provenance.fused_scores == {"cand_1": 0.032, "cand_2": 0.032}
        assert provenance.top_choice_support == pytest.approx(0.5)
        assert provenance.agreement_threshold == pytest.approx(0.6)
        assert provenance.agreement_failure == AgreementFailure.MODAL_TIE
        assert provenance.seeds == {"request": "abc", "judge_d": "def"}

    # @spec MARS-019
    def test_candidate_count_is_recorded_on_every_outcome(self) -> None:
        result = build_abstained_result(
            reason_code=MarsAbstentionReason.INSUFFICIENT_ELIGIBLE_JUDGES,
            candidate_count=3,
            generators=_generators("model_a"),
            judges=[],
        )

        assert result.provenance is not None
        assert result.provenance.candidate_count == 3

    # @spec MARS-019
    def test_discards_are_recorded(self) -> None:
        result = build_abstained_result(
            reason_code=MarsAbstentionReason.NO_REVIEWABLE_CANDIDATE,
            candidate_count=0,
            generators=_generators("model_a", "model_b"),
            judges=[],
            discarded_generators=[("model_a", "status_not_reviewable")],
            discarded_judges=[("judge_d", "unparseable")],
        )

        assert result.provenance is not None
        assert result.provenance.discarded_generators == [
            ["model_a", "status_not_reviewable"]
        ]
        assert result.provenance.discarded_judges == [["judge_d", "unparseable"]]


class TestModelRegistry:
    """MARS-020: identifier, family and config hash for every model invoked."""

    # @spec MARS-020
    def test_every_model_is_attributable(self) -> None:
        result = build_abstained_result(
            reason_code=MarsAbstentionReason.JUDGE_DISAGREEMENT,
            candidate_count=2,
            generators=_generators("llama_a", "qwen_b"),
            judges=_judges("mistral_d"),
        )

        registry = result.provenance.models
        assert {m.identifier for m in registry} == {"llama_a", "qwen_b", "mistral_d"}
        assert {m.family for m in registry} == {"llama", "qwen", "mistral"}
        assert all(m.config_hash for m in registry)

    # @spec MARS-020, MARS-027
    def test_same_family_overlap_is_visible_after_the_fact(self) -> None:
        """Same-family generator/judge overlap is permitted but must be
        measurable, which is why family is recorded rather than only identity."""
        result = build_abstained_result(
            reason_code=MarsAbstentionReason.JUDGE_DISAGREEMENT,
            candidate_count=2,
            generators=_generators("llama_1b"),
            judges=_judges("llama_3b"),
        )

        registry = result.provenance.models
        generator_families = {m.family for m in registry if m.role is ModelRole.GENERATOR}
        judge_families = {m.family for m in registry if m.role is ModelRole.JUDGE}

        assert generator_families & judge_families == {"llama"}


class TestSelectedResult:
    """A returned candidate carries the same envelope, populated."""

    def _selected(self, generator_confidence: float, support: float):
        candidate = build_candidates([_result("model_a", "A", generator_confidence)])[0]
        agreement = _decision(support, passed=True)
        confidence = compose_confidence(
            candidate=candidate, agreement=agreement, generator_policy=MIN
        )
        return candidate, agreement, confidence

    # @spec MARS-024
    def test_status_is_success_and_carries_the_observation(self) -> None:
        candidate, agreement, confidence = self._selected(0.9, 0.9)

        result = build_selected_result(
            candidate=candidate,
            confidence=confidence,
            candidate_count=2,
            generators=_generators("model_a"),
            judges=_judges("judge_d"),
            agreement=agreement,
        )

        assert result.status is ExtractionStatus.SUCCESS
        assert result.observations == [candidate.observation]
        assert result.reason_code is None
        assert result.provenance.selected_internal_id == candidate.internal_id

    # @spec MARS-032
    def test_control_confidence_reaches_the_envelope(self) -> None:
        candidate, agreement, confidence = self._selected(0.95, 0.35)

        result = build_selected_result(
            candidate=candidate,
            confidence=confidence,
            candidate_count=2,
            generators=_generators("model_a"),
            judges=_judges("judge_d"),
            agreement=agreement,
        )

        assert result.control_confidence == pytest.approx(0.35)
        assert result.provenance.generator_confidence == pytest.approx(0.95)
        assert result.provenance.mars_selection_confidence == pytest.approx(0.35)

    # @spec MARS-024
    def test_low_generator_confidence_does_not_abstain_the_mars_result(self) -> None:
        """EXTRACT-013 (confidence < 0.3 abstains) scopes to a *generating*
        provider. MARS gates alone determine MARS's status, and the admission
        predicate already applied that rule to each generator's own result."""
        candidate, agreement, confidence = self._selected(0.2, 0.9)

        result = build_selected_result(
            candidate=candidate,
            confidence=confidence,
            candidate_count=2,
            generators=_generators("model_a"),
            judges=_judges("judge_d"),
            agreement=agreement,
        )

        assert result.provenance.generator_confidence == pytest.approx(0.2)
        assert result.status is ExtractionStatus.SUCCESS

    # @spec MARS-024
    def test_many_null_fields_do_not_abstain_the_mars_result(self) -> None:
        """Likewise EXTRACT-014: MARS does not re-apply it to the selection."""
        sparse = ExtractionResult(
            status=ExtractionStatus.PARTIAL,
            observations=[
                StructuredObservation(
                    child_id="child_1",
                    session_id="session_1",
                    contributor_role=ContributorRole.INTERVENTIONIST,
                    observation_date=date(2026, 9, 7),
                    setting=Setting.CLINIC,
                    domain=Domain.SOCIAL_COMMUNICATION,
                    behavior="Child pointed",
                    confidence=0.8,
                )
            ],
            provider="test_provider",
            model="model_a",
            prompt_version="1.0",
        )
        candidate = build_candidates([sparse])[0]
        agreement = _decision(0.9, passed=True)
        confidence = compose_confidence(
            candidate=candidate, agreement=agreement, generator_policy=MIN
        )

        result = build_selected_result(
            candidate=candidate,
            confidence=confidence,
            candidate_count=2,
            generators=_generators("model_a"),
            judges=_judges("judge_d"),
            agreement=agreement,
        )

        assert result.status is ExtractionStatus.SUCCESS

    # @spec MARS-025
    def test_selected_and_abstained_share_one_field_set(self) -> None:
        candidate, agreement, confidence = self._selected(0.9, 0.9)
        selected = build_selected_result(
            candidate=candidate,
            confidence=confidence,
            candidate_count=2,
            generators=_generators("model_a"),
            judges=_judges("judge_d"),
            agreement=agreement,
        )
        abstained = build_abstained_result(
            reason_code=MarsAbstentionReason.JUDGE_DISAGREEMENT,
            candidate_count=2,
            generators=_generators("model_a"),
            judges=_judges("judge_d"),
        )

        assert set(selected.model_dump()) == set(abstained.model_dump())
        assert set(selected.model_dump()["provenance"]) == set(
            abstained.model_dump()["provenance"]
        )


class TestIntegrityFailureEnvelope:
    """MARS-018: an integrity failure abstains and returns no candidate."""

    # @spec MARS-018
    def test_integrity_failure_returns_no_observation(self) -> None:
        result = build_abstained_result(
            reason_code=MarsAbstentionReason.INTEGRITY_FAILURE,
            candidate_count=1,
            generators=_generators("model_a"),
            judges=[],
        )

        assert result.status is ExtractionStatus.ABSTAINED
        assert result.observations == []
        assert result.provenance.selected_internal_id is None
        assert result.reason_code == MarsAbstentionReason.INTEGRITY_FAILURE


class TestProvenanceIsNotOnTheObservation:
    """MARS-022: derivation metadata stays off the clinical record."""

    # @spec MARS-022
    def test_selected_observation_is_unmodified(self) -> None:
        candidate = build_candidates([_result("model_a", "A", 0.9)])[0]
        agreement = _decision(0.9, passed=True)
        confidence = compose_confidence(
            candidate=candidate, agreement=agreement, generator_policy=MIN
        )
        before = candidate.observation.model_dump()

        result = build_selected_result(
            candidate=candidate,
            confidence=confidence,
            candidate_count=2,
            generators=_generators("model_a"),
            judges=_judges("judge_d"),
            agreement=agreement,
        )

        assert result.observations[0].model_dump() == before
