"""Safety invariants checkable before any ranking happens.

Two independent guarantees:

  * **Output integrity** (MARS-017/018) -- what MARS returns is one admitted
    candidate, entire. MARS is a selector, never a synthesizer.
  * **Judge independence** (MARS-027/028) -- no model judges a candidate set
    containing its own generation, and a roster that cannot satisfy that
    constraint abstains rather than relaxing it.

Both hold on the single-candidate short-circuit as well as the reranked path,
which is the point: the sole-candidate case has the *least* corroboration.
"""

from __future__ import annotations

import enum

from src.backend.ml.extraction.mars.candidates import MarsCandidate, normalize_value
from src.backend.schemas.observation_schema import (
    LLM_EXTRACTED_FIELDS,
    StructuredObservation,
)

# Application-known attribution and context. A returned observation attached to
# the wrong child or session is an integrity failure as serious as a tampered
# outcome -- arguably worse, since it misfiles the record entirely.
_IDENTITY_FIELDS: frozenset[str] = frozenset({
    "child_id",
    "session_id",
    "contributor_role",
    "observation_date",
    "setting",
})

# Enumerated deliberately rather than derived from the model's field list.
# "Every field on StructuredObservation" would let schema evolution silently
# change integrity policy: adding an operational field later (a validation
# timestamp, a UI flag, a source version) would start failing MARS-017 without
# anyone deciding it should.
#
# Excluded on purpose: `confidence` and `abstention_reason` describe the
# generator's self-assessment rather than the observation's identity or
# content, they are already excluded from the deduplication fingerprint, and
# including them would collide with MARS-032, which derives the result-level
# control confidence separately.
MARS_INTEGRITY_FIELDS: tuple[str, ...] = tuple(sorted(_IDENTITY_FIELDS | LLM_EXTRACTED_FIELDS))


class MarsAbstentionReason(enum.StrEnum):
    """Closed enumeration, one member per abstention gate (MARS-026).

    Separate codes because the causes have different remedies: a roster
    shortfall is a configuration problem fixed before the run, while invalid
    judge responses are a model-execution problem during it.
    """

    NO_REVIEWABLE_CANDIDATE = "no_reviewable_candidate"
    INSUFFICIENT_ELIGIBLE_JUDGES = "insufficient_eligible_judges"
    INSUFFICIENT_VALID_JUDGE_RESPONSES = "insufficient_valid_judge_responses"
    JUDGE_DISAGREEMENT = "judge_disagreement"
    INTEGRITY_FAILURE = "integrity_failure"


def _comparable(observation: StructuredObservation) -> tuple[tuple[str, object], ...]:
    """The designated integrity fields, normalized, in canonical order.

    Broader than the deduplication fingerprint, which covers only the extracted
    fields, because the two answer different questions: dedup asks "did two
    generators produce the same extracted content?", integrity asks "is this
    exactly an observation MARS was authorized to return?"
    """
    return tuple(
        (name, normalize_value(getattr(observation, name, None)))
        for name in MARS_INTEGRITY_FIELDS
    )


# @spec MARS-017, MARS-018
def find_matching_candidate(
    observation: StructuredObservation,
    candidates: list[MarsCandidate],
) -> MarsCandidate | None:
    """Return the single admitted candidate this observation *is*, or None.

    Matching is whole-observation, never field-by-field across candidates.
    A per-field match would admit an observation assembled from several
    candidates -- every value traceable to some candidate, the combination
    produced by none of them -- which is the failure this check exists for.
    """
    target = _comparable(observation)
    for candidate in candidates:
        if _comparable(candidate.observation) == target:
            return candidate
    return None


# @spec MARS-027
def eligible_judges(
    judge_ids: list[str],
    candidates: list[MarsCandidate],
) -> list[str]:
    """Judges whose model identity generated none of these candidates.

    Eligibility is evaluated against the union of generator identities across
    *every* candidate, including identities merged during deduplication. A
    model does not become independent of a candidate because another model
    produced the same fields and the duplicate collapsed.

    Only exact model identity disqualifies. Same-family overlap is permitted
    and recorded (MARS-020) rather than prohibited -- family-level bias is less
    established than exact self-preference, and prohibiting it would make the
    roster infeasible to satisfy from locally available models.

    Roster order is preserved so downstream seeding stays reproducible.
    """
    generators = {model for candidate in candidates for model in candidate.generator_ids}
    return [judge for judge in judge_ids if judge not in generators]


# @spec MARS-028
def roster_shortfall(
    judge_ids: list[str],
    candidates: list[MarsCandidate],
    *,
    min_eligible_judges: int,
) -> MarsAbstentionReason | None:
    """Abstention reason when the roster cannot supply enough eligible judges.

    Scoped to the reranking path. Fewer than two candidates means no ranking
    question exists (MARS-006), so no roster is required however large the
    configured minimum -- returning None there is what keeps MARS-028 from
    colliding with the short-circuit.
    """
    if len(candidates) < 2:
        return None
    if len(eligible_judges(judge_ids, candidates)) < min_eligible_judges:
        return MarsAbstentionReason.INSUFFICIENT_ELIGIBLE_JUDGES
    return None
