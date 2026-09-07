"""Candidate formation: admission, deduplication, and branch classification.

The first stage of MARS, and deliberately the whole of it for now:

    provider responses
          -> admission predicate            (MARS-029)
          -> observations[0] only           (MARS-003)
          -> normalize + fingerprint
          -> deduplicate, merging generator provenance   (MARS-004)
          -> 0 / 1 / many branch

Reranking begins after this module and is not implemented here. Classification
reports that reranking is *required*; it never selects a candidate, because a
selection made here would bypass every downstream safety gate.
"""

from __future__ import annotations

import enum
import hashlib
import json

from pydantic import BaseModel, Field

from src.backend.ml.extraction.schemas import ExtractionResult, ExtractionStatus
from src.backend.schemas.observation_schema import (
    LLM_EXTRACTED_FIELDS,
    StructuredObservation,
)

_REVIEWABLE_STATUSES = frozenset({ExtractionStatus.SUCCESS, ExtractionStatus.PARTIAL})

# Ordered so the fingerprint payload is canonical regardless of field iteration.
FINGERPRINT_FIELDS: tuple[str, ...] = tuple(sorted(LLM_EXTRACTED_FIELDS))

RejectionReason = str


class CandidateBranch(enum.StrEnum):
    """Which path the admitted candidate set takes. Carries no selection."""

    NO_REVIEWABLE_CANDIDATE = "no_reviewable_candidate"
    SINGLE_CANDIDATE = "single_candidate"
    RERANK_REQUIRED = "rerank_required"


class MarsCandidate(BaseModel):
    """One distinct extraction, with every generator that produced it.

    ``generator_confidences`` keeps each contributing generator's own
    confidence rather than reducing them to one number. Deriving a single
    confidence for a merged candidate is a policy decision (which MARS-032
    later consumes) and is deliberately not made here -- an implicit choice of
    min/max/mean at this layer would settle it by accident.
    """

    internal_id: str
    observation: StructuredObservation
    generator_ids: list[str] = Field(default_factory=list)
    generator_confidences: dict[str, float | None] = Field(default_factory=dict)

    @property
    def multiplicity(self) -> int:
        return len(self.generator_ids)


def normalize_value(value: object) -> object:
    """Textual normalization only.

    Case and surrounding whitespace are noise in how models render the same
    answer. Anything beyond that would be an interpretation step, and dedup
    must stay deterministic -- "improved" and "improving" are different
    candidates, not the same one written differently.
    """
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    return value


def fingerprint_observation(observation: StructuredObservation) -> str:
    """Stable hash over normalized extracted fields only.

    Confidence, generator identity, judge data, and ordering are excluded by
    construction: including confidence would stop two providers that agree on
    the observation from deduplicating, which would in turn hollow out the
    complete-generator-set rule that judge independence (MARS-027) depends on.
    """
    payload = {
        field: normalize_value(getattr(observation, field, None))
        for field in FINGERPRINT_FIELDS
    }
    encoded = json.dumps(payload, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


def _admission_rejection(result: ExtractionResult) -> RejectionReason | None:
    """Return why a response is inadmissible, or None if it is admissible."""
    if result.status not in _REVIEWABLE_STATUSES:
        return "status_not_reviewable"
    if not result.observations:
        return "no_observations"
    observation = result.observations[0]
    if observation.behavior is None and observation.domain is None:
        return "structurally_inadmissible"
    return None


# @spec MARS-003, MARS-004, MARS-029
def build_candidates(
    results: list[ExtractionResult],
    with_rejections: bool = False,
) -> list[MarsCandidate] | tuple[list[MarsCandidate], list[tuple[str, RejectionReason]]]:
    """Admit, deduplicate, and merge generator provenance.

    Candidate order follows first appearance among ``results``, so the output
    is a deterministic function of the input ordering.
    """
    candidates: list[MarsCandidate] = []
    by_fingerprint: dict[str, MarsCandidate] = {}
    rejections: list[tuple[str, RejectionReason]] = []

    for result in results:
        rejection = _admission_rejection(result)
        if rejection is not None:
            rejections.append((result.model, rejection))
            continue

        # MARS-003: at most one candidate per response, from observations[0].
        observation = result.observations[0]
        fingerprint = fingerprint_observation(observation)

        existing = by_fingerprint.get(fingerprint)
        if existing is None:
            candidate = MarsCandidate(
                internal_id=fingerprint,
                observation=observation,
                generator_ids=[result.model],
                generator_confidences={result.model: observation.confidence},
            )
            by_fingerprint[fingerprint] = candidate
            candidates.append(candidate)
        elif result.model not in existing.generator_ids:
            # MARS-004: provenance accumulates; it is never reduced to a
            # single representative generator.
            existing.generator_ids.append(result.model)
            existing.generator_confidences[result.model] = observation.confidence

    if with_rejections:
        return candidates, rejections
    return candidates


# @spec MARS-005, MARS-006, MARS-028
def classify_branch(candidates: list[MarsCandidate]) -> CandidateBranch:
    """Report which path the candidate set takes, without taking it.

    Returns a branch only -- no candidate is selected here. Selecting one at
    classification time would skip the integrity check and, for the many-case,
    the entire judging and agreement pipeline.
    """
    if not candidates:
        return CandidateBranch.NO_REVIEWABLE_CANDIDATE
    if len(candidates) == 1:
        return CandidateBranch.SINGLE_CANDIDATE
    return CandidateBranch.RERANK_REQUIRED
