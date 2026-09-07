"""MarsExtractionProvider -- orchestration only.

Composes the tested components in the order MARS-031 prescribes. Every policy
decision lives in the component that owns it: deduplication in `candidates`,
eligibility and integrity in `safety`, validation and fusion in `fusion`, the
gate in `agreement`, composition in `confidence`, and envelope construction in
`envelope`. Nothing here re-implements any of them, and no component gains
authority by being invoked from here.

MARS occupies the `ExtractionProvider` position rather than adding a stage:
consumers see the existing contract, so validation, abstention routing,
persistence, analytics and reporting are untouched.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.backend.ml.extraction.base import ExtractionProvider
from src.backend.ml.extraction.mars.agreement import evaluate_agreement
from src.backend.ml.extraction.mars.blinding import (
    JudgePresentation,
    build_judge_presentation,
    canonical_judge_identity,
    derive_request_seed,
)
from src.backend.ml.extraction.mars.candidates import (
    CandidateBranch,
    build_candidates,
    classify_branch,
)
from src.backend.ml.extraction.mars.confidence import (
    GeneratorConfidencePolicy,
    compose_confidence,
)
from src.backend.ml.extraction.mars.envelope import (
    build_abstained_result,
    build_selected_result,
)
from src.backend.ml.extraction.mars.fusion import (
    fuse_rankings,
    parse_judge_response,
    select_provisional_winner,
    validate_response_count,
)
from src.backend.ml.extraction.mars.safety import (
    MarsAbstentionReason,
    eligible_judges,
    find_matching_candidate,
    roster_shortfall,
)
from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    ExtractionResult,
    ModelDescriptor,
    ModelRole,
)

MARS_VERSION = "1.0.0"


@runtime_checkable
class JudgeProvider(Protocol):
    """Ranks a blinded candidate set.

    Returns whatever the model produced; `parse_judge_response` decides whether
    it is usable. A judge is never asked for, and never read for, a field value.
    """

    async def rank(
        self, *, source_text: str, presentation: JudgePresentation
    ) -> object: ...


class MarsGenerator:
    """A candidate-generating provider paired with its recorded identity."""

    def __init__(self, provider: ExtractionProvider, descriptor: ModelDescriptor) -> None:
        self.provider = provider
        self.descriptor = descriptor


class MarsJudge:
    """A ranking model paired with its recorded identity."""

    def __init__(self, judge: JudgeProvider, descriptor: ModelDescriptor) -> None:
        self.judge = judge
        self.descriptor = descriptor


class MarsExtractionProvider:
    """Multi-LLM-augmented reranking behind the `ExtractionProvider` contract."""

    # @spec MARS-001, MARS-002
    def __init__(
        self,
        *,
        generators: list[MarsGenerator],
        judges: list[MarsJudge],
        agreement_threshold: float,
        generator_confidence_policy: GeneratorConfidencePolicy,
        min_eligible_judges: int,
        min_valid_judge_responses: int,
        run_seed: str,
        mars_version: str = MARS_VERSION,
    ) -> None:
        """Every calibration value is supplied; none has a default.

        The threshold in particular is an open calibration question, so a
        default here would settle it invisibly.
        """
        if not generators:
            raise ValueError("MARS requires at least one candidate generator.")
        if not 0.0 <= agreement_threshold <= 1.0:
            raise ValueError(
                f"agreement_threshold must lie in [0, 1]; got {agreement_threshold}."
            )
        if min_eligible_judges < 1:
            raise ValueError("min_eligible_judges must be at least 1.")
        if min_valid_judge_responses < 1:
            raise ValueError("min_valid_judge_responses must be at least 1.")

        self._require_unique(generators, "generator")
        self._require_unique(judges, "judge")
        self._require_role(generators, ModelRole.GENERATOR)
        self._require_role(judges, ModelRole.JUDGE)

        self._generators = generators
        self._judges = judges
        self._threshold = agreement_threshold
        self._policy = generator_confidence_policy
        self._min_eligible_judges = min_eligible_judges
        self._min_valid_judge_responses = min_valid_judge_responses
        self._run_seed = run_seed
        self._mars_version = mars_version

    @staticmethod
    def _require_unique(members: list, kind: str) -> None:
        """Canonicalized identities must not collide.

        Two roster entries that fold to one identity would make judge
        eligibility (MARS-027) ambiguous -- a model could be excluded under one
        spelling and admitted under another.
        """
        identities = [canonical_judge_identity(m.descriptor.identifier) for m in members]
        duplicates = {i for i in identities if identities.count(i) > 1}
        if duplicates:
            raise ValueError(f"Duplicate {kind} identity after canonicalization: {duplicates}")

    @staticmethod
    def _require_role(members: list, role: ModelRole) -> None:
        wrong = [m.descriptor.identifier for m in members if m.descriptor.role is not role]
        if wrong:
            raise ValueError(f"Model(s) {wrong} must be declared with role {role.value}.")

    @property
    def _generator_descriptors(self) -> list[ModelDescriptor]:
        return [g.descriptor for g in self._generators]

    # @spec MARS-001, MARS-002, MARS-006, MARS-014, MARS-031
    async def extract(self, request: ExtractionRequest) -> ExtractionResult:
        """Run the pipeline in the order MARS-031 prescribes."""
        results = []
        for generator in self._generators:
            result = await generator.provider.extract(request)
            # Identity is taken from configuration, not from what the provider
            # reports, so eligibility and provenance agree on one spelling.
            results.append(
                result.model_copy(update={"model": generator.descriptor.identifier})
            )

        candidates, discarded_generators = build_candidates(results, with_rejections=True)
        branch = classify_branch(candidates)

        def abstain(reason: MarsAbstentionReason, **kwargs) -> ExtractionResult:
            return build_abstained_result(
                reason_code=reason,
                candidate_count=len(candidates),
                generators=self._generator_descriptors,
                discarded_generators=discarded_generators,
                **kwargs,
            )

        if branch is CandidateBranch.NO_REVIEWABLE_CANDIDATE:
            return abstain(MarsAbstentionReason.NO_REVIEWABLE_CANDIDATE, judges=[])

        if branch is CandidateBranch.SINGLE_CANDIDATE:
            return self._short_circuit(candidates, discarded_generators)

        return await self._rerank(request, candidates, discarded_generators)

    # @spec MARS-006
    def _short_circuit(self, candidates, discarded_generators) -> ExtractionResult:
        """One distinct candidate: skip reranking, never integrity.

        No judge is constructed, no presentation is built, and no model is
        called -- there is no ranking question when every generator produced the
        same answer. The integrity check still runs, because a sole candidate is
        the case with the least corroboration, not the most.

        `mars_selection_confidence` is absent here, and therefore so is
        `control_confidence`: no judge evidence exists, and MARS-032 forbids
        writing generator confidence alone.
        """
        candidate = candidates[0]
        if find_matching_candidate(candidate.observation, candidates) is None:
            return build_abstained_result(
                reason_code=MarsAbstentionReason.INTEGRITY_FAILURE,
                candidate_count=len(candidates),
                generators=self._generator_descriptors,
                judges=[],
                discarded_generators=discarded_generators,
            )

        confidence = compose_confidence(
            candidate=candidate,
            agreement=_no_judging_decision(candidate.internal_id, self._threshold),
            generator_policy=self._policy,
        )
        return build_selected_result(
            candidate=candidate,
            confidence=confidence,
            candidate_count=len(candidates),
            generators=self._generator_descriptors,
            judges=[],
            discarded_generators=discarded_generators,
        )

    # @spec MARS-031
    async def _rerank(self, request, candidates, discarded_generators) -> ExtractionResult:
        eligible = eligible_judges(
            [j.descriptor.identifier for j in self._judges], candidates
        )
        shortfall = roster_shortfall(
            [j.descriptor.identifier for j in self._judges],
            candidates,
            min_eligible_judges=self._min_eligible_judges,
        )
        panel = [j for j in self._judges if j.descriptor.identifier in eligible]
        panel_descriptors = [j.descriptor for j in panel]

        if shortfall is not None:
            return build_abstained_result(
                reason_code=shortfall,
                candidate_count=len(candidates),
                generators=self._generator_descriptors,
                judges=panel_descriptors,
                discarded_generators=discarded_generators,
            )

        request_seed = derive_request_seed(
            source_id=f"{request.child_id}:{request.session_id}",
            mars_version=self._mars_version,
            candidates=candidates,
            run_seed=self._run_seed,
        )
        seeds = {"request": request_seed}

        responses = []
        for judge in panel:
            presentation = build_judge_presentation(
                judge_id=judge.descriptor.identifier,
                candidates=candidates,
                request_seed=request_seed,
            )
            seeds[presentation.judge_id] = presentation.judge_seed
            raw = await judge.judge.rank(
                source_text=request.text, presentation=presentation
            )
            responses.append(
                parse_judge_response(
                    raw, presentation, judge_id=judge.descriptor.identifier
                )
            )

        valid = [r for r in responses if r.is_valid]
        rankings = [r.internal_ids for r in valid]
        discarded_judges = [
            (r.judge_id, r.rejection or "invalid") for r in responses if not r.is_valid
        ]
        common = dict(
            candidate_count=len(candidates),
            generators=self._generator_descriptors,
            judges=panel_descriptors,
            rankings=rankings,
            seeds=seeds,
            discarded_generators=discarded_generators,
            discarded_judges=discarded_judges,
        )

        count_failure = validate_response_count(
            responses, min_valid_judge_responses=self._min_valid_judge_responses
        )
        if count_failure is not None:
            return build_abstained_result(reason_code=count_failure, **common)

        scores = fuse_rankings(responses, candidates)
        provisional = select_provisional_winner(scores, candidates)
        agreement = evaluate_agreement(
            provisional_internal_id=provisional,
            responses=responses,
            threshold=self._threshold,
        )
        common |= dict(fused_scores=scores, agreement=agreement)

        if not agreement.passed:
            return build_abstained_result(
                reason_code=agreement.reason_code
                or MarsAbstentionReason.JUDGE_DISAGREEMENT,
                **common,
            )

        selected = next(c for c in candidates if c.internal_id == provisional)
        if find_matching_candidate(selected.observation, candidates) is None:
            return build_abstained_result(
                reason_code=MarsAbstentionReason.INTEGRITY_FAILURE, **common
            )

        confidence = compose_confidence(
            candidate=selected, agreement=agreement, generator_policy=self._policy
        )
        return build_selected_result(candidate=selected, confidence=confidence, **common)


def _no_judging_decision(internal_id: str, threshold: float):
    """An agreement record for a run in which judging did not occur.

    Not a passing verdict manufactured for the short-circuit: support is
    ``None`` because no judge evidence exists, which is what keeps
    `mars_selection_confidence` -- and therefore `control_confidence` -- absent
    rather than invented.
    """
    from src.backend.ml.extraction.mars.agreement import AgreementDecision

    return AgreementDecision(
        passed=True,
        provisional_internal_id=internal_id,
        valid_judge_count=0,
        first_choice_support=None,
        is_modal_first_choice=False,
        modal_internal_ids=[],
        threshold=threshold,
    )
