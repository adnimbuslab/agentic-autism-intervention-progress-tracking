"""MARS candidate formation: admission, first-observation-only, deduplication.

Covers MARS-003, MARS-029, MARS-004 and the 0/1/many branch classification.
Judging, fusion and agreement are deliberately out of scope here — this module
stops at the point where reranking would begin.
"""

from __future__ import annotations

import json
from datetime import date

import pytest

from src.backend.ml.extraction.mars.candidates import (
    CandidateBranch,
    MarsCandidate,
    build_candidates,
    classify_branch,
    fingerprint_observation,
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


def _obs(behavior: str = "Child pointed", confidence: float | None = 0.8, **kw: object):
    payload: dict[str, object] = {
        "child_id": "child_1",
        "session_id": "session_1",
        "contributor_role": ContributorRole.INTERVENTIONIST,
        "observation_date": date(2026, 9, 7),
        "setting": Setting.CLINIC,
        "domain": Domain.SOCIAL_COMMUNICATION,
        "behavior": behavior,
        "modality": Modality.GESTURAL,
        "prompt_level": PromptLevel.INDEPENDENT,
        "outcome": Outcome.CORRECT,
        "confidence": confidence,
    }
    payload.update(kw)
    return StructuredObservation(**payload)  # type: ignore[arg-type]


def _result(
    model: str,
    observations: list[StructuredObservation],
    status: ExtractionStatus = ExtractionStatus.SUCCESS,
) -> ExtractionResult:
    return ExtractionResult(
        status=status,
        observations=observations,
        provider="test_provider",
        model=model,
        prompt_version="1.0",
    )


class TestAdmission:
    """MARS-029: malformed provider semantics must not leak candidates merely
    because the payload happens to contain data."""

    # @spec MARS-029
    def test_failed_result_is_rejected_even_carrying_an_observation(self) -> None:
        results = [_result("model_a", [_obs()], status=ExtractionStatus.FAILED)]

        assert build_candidates(results) == []

    # @spec MARS-029
    def test_abstained_result_is_rejected_even_carrying_an_observation(self) -> None:
        results = [_result("model_a", [_obs()], status=ExtractionStatus.ABSTAINED)]

        assert build_candidates(results) == []

    # @spec MARS-029
    def test_success_with_no_observations_is_rejected(self) -> None:
        assert build_candidates([_result("model_a", [])]) == []

    # @spec MARS-029
    @pytest.mark.parametrize("status", [ExtractionStatus.SUCCESS, ExtractionStatus.PARTIAL])
    def test_reviewable_status_with_a_valid_observation_is_admitted(
        self, status: ExtractionStatus
    ) -> None:
        candidates = build_candidates([_result("model_a", [_obs()], status=status)])

        assert len(candidates) == 1

    # @spec MARS-029
    def test_structurally_inadmissible_observation_is_rejected(self) -> None:
        """An observation with neither behavior nor domain carries nothing to rank."""
        results = [_result("model_a", [_obs(behavior=None, domain=None)])]

        assert build_candidates(results) == []

    # @spec MARS-029
    def test_rejections_are_reported_for_provenance(self) -> None:
        results = [
            _result("model_a", [_obs()], status=ExtractionStatus.FAILED),
            _result("model_b", [_obs()]),
        ]

        candidates, rejected = build_candidates(results, with_rejections=True)

        assert [c.generator_ids for c in candidates] == [["model_b"]]
        assert rejected == [("model_a", "status_not_reviewable")]


class TestFirstObservationOnly:
    """MARS-003: one provider response contributes at most one candidate."""

    # @spec MARS-003
    def test_only_the_first_observation_becomes_a_candidate(self) -> None:
        first, second, third = _obs("A"), _obs("B"), _obs("C")

        candidates = build_candidates([_result("model_a", [first, second, third])])

        assert len(candidates) == 1
        assert candidates[0].observation.behavior == "A"
        behaviors = {c.observation.behavior for c in candidates}
        assert "B" not in behaviors
        assert "C" not in behaviors

    # @spec MARS-003
    def test_generating_provider_remains_identifiable(self) -> None:
        candidates = build_candidates([_result("model_a", [_obs("A"), _obs("B")])])

        assert candidates[0].generator_ids == ["model_a"]


class TestDeduplication:
    """MARS-004: identical field values collapse, generator provenance does not."""

    # @spec MARS-004
    def test_identical_observations_collapse_to_one_candidate(self) -> None:
        candidates = build_candidates(
            [_result("model_a", [_obs("X")]), _result("model_b", [_obs("X")])]
        )

        assert len(candidates) == 1
        assert candidates[0].generator_ids == ["model_a", "model_b"]
        assert candidates[0].multiplicity == 2

    # @spec MARS-004
    def test_differing_observations_stay_separate(self) -> None:
        candidates = build_candidates(
            [_result("model_a", [_obs("X")]), _result("model_b", [_obs("Y")])]
        )

        assert len(candidates) == 2
        assert [c.generator_ids for c in candidates] == [["model_a"], ["model_b"]]

    # @spec MARS-004
    def test_normalization_collapses_case_and_surrounding_whitespace(self) -> None:
        """The defined normalization is textual only."""
        candidates = build_candidates(
            [
                _result("model_a", [_obs("  Child Pointed  ")]),
                _result("model_b", [_obs("child pointed")]),
            ]
        )

        assert len(candidates) == 1
        assert candidates[0].generator_ids == ["model_a", "model_b"]

    # @spec MARS-004
    def test_normalization_does_not_interpret_meaning(self) -> None:
        """Deterministic dedup must not acquire an NLP interpretation step:
        semantically similar wording is a different candidate."""
        candidates = build_candidates(
            [_result("model_a", [_obs("improved")]), _result("model_b", [_obs("improving")])]
        )

        assert len(candidates) == 2

    # @spec MARS-004
    def test_partial_and_success_of_the_same_fields_still_collapse(self) -> None:
        candidates = build_candidates(
            [
                _result("model_a", [_obs("X")]),
                _result("model_b", [_obs("X")], status=ExtractionStatus.PARTIAL),
            ]
        )

        assert len(candidates) == 1
        assert candidates[0].multiplicity == 2


class TestFingerprint:
    """The fingerprint is a function of normalized observation fields only."""

    # @spec MARS-004
    def test_confidence_does_not_affect_the_fingerprint(self) -> None:
        """Otherwise two providers agreeing on the observation but differing on
        confidence would never deduplicate, and the complete-generator-set rule
        that judge independence depends on would be ineffective."""
        assert fingerprint_observation(_obs("X", confidence=0.10)) == fingerprint_observation(
            _obs("X", confidence=0.99)
        )

    # @spec MARS-004
    def test_differing_extracted_fields_change_the_fingerprint(self) -> None:
        assert fingerprint_observation(_obs("X")) != fingerprint_observation(_obs("Y"))

    # @spec MARS-004
    def test_fingerprint_is_stable_across_calls(self) -> None:
        assert fingerprint_observation(_obs("X")) == fingerprint_observation(_obs("X"))

    # @spec MARS-004
    def test_candidates_agreeing_only_on_confidence_still_collapse(self) -> None:
        candidates = build_candidates(
            [
                _result("model_a", [_obs("X", confidence=0.10)]),
                _result("model_b", [_obs("X", confidence=0.99)]),
            ]
        )

        assert len(candidates) == 1
        assert candidates[0].multiplicity == 2


class TestGeneratorProvenance:
    """Per-generator confidence survives dedup without being aggregated.

    Aggregating it would be a confidence-policy decision, and that rule is not
    yet defined (MARS-032 consumes it later). Preserving every contribution now
    keeps the decision explicit rather than implicit in this implementation.
    """

    # @spec MARS-004
    def test_each_generator_contribution_is_preserved(self) -> None:
        candidates = build_candidates(
            [
                _result("model_a", [_obs("X", confidence=0.82)]),
                _result("model_b", [_obs("X", confidence=0.91)]),
            ]
        )

        assert candidates[0].generator_confidences == {"model_a": 0.82, "model_b": 0.91}

    # @spec MARS-004
    def test_no_single_generator_confidence_is_derived(self) -> None:
        """Step 3 must not silently pick a rule (min/max/mean) for merged candidates."""
        assert not hasattr(MarsCandidate, "generator_confidence")

    # @spec MARS-004, MARS-027
    def test_generator_sets_survive_serialization(self) -> None:
        """Judge independence is evaluated against these sets, including on a
        replay path, so they must round-trip intact."""
        candidates = build_candidates(
            [
                _result("model_a", [_obs("X")]),
                _result("model_b", [_obs("X")]),
                _result("model_c", [_obs("Y")]),
            ]
        )

        restored = [
            MarsCandidate.model_validate(json.loads(c.model_dump_json())) for c in candidates
        ]

        by_behavior = {c.observation.behavior: c for c in restored}
        assert by_behavior["X"].generator_ids == ["model_a", "model_b"]
        assert by_behavior["Y"].generator_ids == ["model_c"]
        assert by_behavior["X"].internal_id == candidates[0].internal_id

    # @spec MARS-004
    def test_internal_id_is_stable_and_distinct_per_candidate(self) -> None:
        candidates = build_candidates(
            [_result("model_a", [_obs("X")]), _result("model_b", [_obs("Y")])]
        )
        again = build_candidates(
            [_result("model_a", [_obs("X")]), _result("model_b", [_obs("Y")])]
        )

        assert [c.internal_id for c in candidates] == [c.internal_id for c in again]
        assert len({c.internal_id for c in candidates}) == 2


class TestBranchClassification:
    """0 / 1 / many — the boundary Step 3 stops at."""

    # @spec MARS-005
    def test_zero_candidates_is_the_abstain_branch(self) -> None:
        assert classify_branch([]) is CandidateBranch.NO_REVIEWABLE_CANDIDATE

    # @spec MARS-006
    def test_one_candidate_is_the_short_circuit_branch(self) -> None:
        candidates = build_candidates([_result("model_a", [_obs("X")])])

        assert classify_branch(candidates) is CandidateBranch.SINGLE_CANDIDATE

    # @spec MARS-006
    def test_agreeing_providers_reach_the_short_circuit_branch(self) -> None:
        """Three providers, one distinct candidate — no ranking question exists."""
        candidates = build_candidates(
            [_result(m, [_obs("X")]) for m in ("model_a", "model_b", "model_c")]
        )

        assert classify_branch(candidates) is CandidateBranch.SINGLE_CANDIDATE

    # @spec MARS-028
    @pytest.mark.parametrize("n", [2, 3, 5])
    def test_multiple_candidates_require_reranking(self, n: int) -> None:
        candidates = build_candidates(
            [_result(f"model_{i}", [_obs(f"behavior {i}")]) for i in range(n)]
        )

        assert len(candidates) == n
        assert classify_branch(candidates) is CandidateBranch.RERANK_REQUIRED

    # @spec MARS-028
    def test_many_branch_does_not_select_a_candidate(self) -> None:
        """Classification reports that reranking is required; it must not quietly
        pick a winner, which would bypass every downstream safety gate."""
        candidates = build_candidates(
            [_result("model_a", [_obs("X")]), _result("model_b", [_obs("Y")])]
        )
        branch = classify_branch(candidates)

        assert branch is CandidateBranch.RERANK_REQUIRED
        assert not hasattr(branch, "selected")
