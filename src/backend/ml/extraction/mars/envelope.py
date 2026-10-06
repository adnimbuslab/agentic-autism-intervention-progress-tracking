"""Building the MARS result envelope.

Every outcome -- selected or abstained, and whichever gate raised the
abstention -- leaves through here in one canonical shape. Callers downstream
distinguish causes by comparing ``reason_code``, never by parsing prose.

Provenance describes *the execution that actually occurred*. A stage that did
not run leaves its fields present and empty rather than absent: an abstention
raised before any judge was invoked is a complete record of a run in which
judging did not happen, not a truncated record of one where it did.

These builders shape an outcome. They do not produce one -- no candidate is
selected, no gate is evaluated, and no decision is revisited here.
"""

from __future__ import annotations

from datetime import UTC, datetime

from src.backend.ml.extraction.mars.agreement import AgreementDecision
from src.backend.ml.extraction.mars.candidates import MarsCandidate
from src.backend.ml.extraction.mars.confidence import MarsConfidence
from src.backend.ml.extraction.mars.safety import MarsAbstentionReason
from src.backend.ml.extraction.schemas import (
    ControlConfidenceState,
    ExtractionProvenance,
    ExtractionResult,
    ExtractionStatus,
    ModelDescriptor,
    ModelRole,
)

PROVIDER_TYPE = "mars"
PROMPT_VERSION = "1.0"


__all__ = [
    "PROVIDER_TYPE",
    "ModelDescriptor",
    "ModelRole",
    "build_abstained_result",
    "build_selected_result",
]


def _provenance(
    *,
    candidate_count: int,
    generators: list[ModelDescriptor],
    judges: list[ModelDescriptor],
    rankings: list[list[str]] | None,
    fused_scores: dict[str, float] | None,
    agreement: AgreementDecision | None,
    confidence: MarsConfidence | None,
    selected_internal_id: str | None,
    seeds: dict[str, str] | None,
    diagnostic_statistics: dict[str, float] | None,
    discarded_generators: list[tuple[str, str]] | None,
    discarded_judges: list[tuple[str, str]] | None,
) -> ExtractionProvenance:
    return ExtractionProvenance(
        provider_type=PROVIDER_TYPE,
        generator_ids=[m.identifier for m in generators],
        judge_ids=[m.identifier for m in judges],
        ranking=list(rankings or []),
        generator_confidence=confidence.generator_confidence if confidence else None,
        mars_selection_confidence=(
            confidence.mars_selection_confidence if confidence else None
        ),
        candidate_count=candidate_count,
        selected_internal_id=selected_internal_id,
        fused_scores=dict(fused_scores or {}),
        top_choice_support=agreement.first_choice_support if agreement else None,
        modal_internal_ids=list(agreement.modal_internal_ids) if agreement else [],
        agreement_threshold=agreement.threshold if agreement else None,
        agreement_failure=(
            agreement.failure.value if agreement and agreement.failure else None
        ),
        diagnostic_statistics=dict(diagnostic_statistics or {}),
        seeds=dict(seeds or {}),
        discarded_generators=[list(entry) for entry in (discarded_generators or [])],
        discarded_judges=[list(entry) for entry in (discarded_judges or [])],
        models=[*generators, *judges],
    )


# @spec MARS-005, MARS-018, MARS-019, MARS-020, MARS-025, MARS-026
def build_abstained_result(
    *,
    reason_code: MarsAbstentionReason,
    candidate_count: int,
    generators: list[ModelDescriptor],
    judges: list[ModelDescriptor],
    rankings: list[list[str]] | None = None,
    fused_scores: dict[str, float] | None = None,
    agreement: AgreementDecision | None = None,
    seeds: dict[str, str] | None = None,
    diagnostic_statistics: dict[str, float] | None = None,
    discarded_generators: list[tuple[str, str]] | None = None,
    discarded_judges: list[tuple[str, str]] | None = None,
    model: str = PROVIDER_TYPE,
) -> ExtractionResult:
    """One canonical abstained envelope, whichever gate raised it.

    No observation is returned and no control confidence is asserted: MARS
    withheld a conclusion, and reporting a confidence for a result that does
    not exist would invite a caller to treat the abstention as a weak answer
    rather than as no answer.
    """
    return ExtractionResult(
        status=ExtractionStatus.ABSTAINED,
        observations=[],
        provider=PROVIDER_TYPE,
        model=model,
        prompt_version=PROMPT_VERSION,
        generated_at=datetime.now(UTC),
        control_confidence=None,
        control_confidence_state=ControlConfidenceState.NOT_AVAILABLE_ABSTAINED,
        reason_code=reason_code.value,
        provenance=_provenance(
            candidate_count=candidate_count,
            generators=generators,
            judges=judges,
            rankings=rankings,
            fused_scores=fused_scores,
            agreement=agreement,
            confidence=None,
            selected_internal_id=None,
            seeds=seeds,
            diagnostic_statistics=diagnostic_statistics,
            discarded_generators=discarded_generators,
            discarded_judges=discarded_judges,
        ),
    )


# @spec MARS-019, MARS-020, MARS-024, MARS-025
def build_selected_result(
    *,
    candidate: MarsCandidate,
    confidence: MarsConfidence,
    candidate_count: int,
    generators: list[ModelDescriptor],
    judges: list[ModelDescriptor],
    agreement: AgreementDecision | None = None,
    rankings: list[list[str]] | None = None,
    fused_scores: dict[str, float] | None = None,
    seeds: dict[str, str] | None = None,
    diagnostic_statistics: dict[str, float] | None = None,
    discarded_generators: list[tuple[str, str]] | None = None,
    discarded_judges: list[tuple[str, str]] | None = None,
    model: str = PROVIDER_TYPE,
) -> ExtractionResult:
    """The envelope for a candidate that cleared every gate.

    Status comes from the MARS gates alone (MARS-024). The single-provider
    rules EXTRACT-013 and EXTRACT-014 are not re-applied to the selection:
    they govern a generating provider's own result and were already applied by
    the admission predicate, so a candidate whose generator reported low
    confidence -- or left many fields null -- still yields SUCCESS when MARS's
    own gates passed. That is deliberate: those thresholds describe one
    generator, not the ensemble.

    The observation is passed through untouched. Derivation metadata belongs
    to provenance, never to the clinical record.
    """
    return ExtractionResult(
        status=ExtractionStatus.SUCCESS,
        observations=[candidate.observation],
        provider=PROVIDER_TYPE,
        model=model,
        prompt_version=PROMPT_VERSION,
        generated_at=datetime.now(UTC),
        control_confidence=confidence.control_confidence,
        # An absent control confidence on a *successful* result means no
        # reranking evidence existed (the short circuit). Declaring that
        # explicitly is what makes downstream route it for review rather than
        # accept it (VALID-015).
        control_confidence_state=(
            ControlConfidenceState.AVAILABLE
            if confidence.control_confidence is not None
            else ControlConfidenceState.NOT_AVAILABLE_SHORT_CIRCUIT
        ),
        reason_code=None,
        provenance=_provenance(
            candidate_count=candidate_count,
            generators=generators,
            judges=judges,
            rankings=rankings,
            fused_scores=fused_scores,
            agreement=agreement,
            confidence=confidence,
            selected_internal_id=candidate.internal_id,
            seeds=seeds,
            diagnostic_statistics=diagnostic_statistics,
            discarded_generators=discarded_generators,
            discarded_judges=discarded_judges,
        ),
    )
