"""Judge-response validation and deterministic rank fusion.

Judges return an ordering over the aliases they were shown, and nothing else.
Everything downstream of that is arithmetic performed here in code: no model
aggregates the rankings, selects a winner, or adjudicates a tie.

This module produces a *provisional* winner. Whether that winner may actually
be returned is decided by the agreement gate and the integrity check, which
live elsewhere -- fusion deliberately has no authority to return anything.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.backend.ml.extraction.mars.blinding import JudgePresentation
from src.backend.ml.extraction.mars.candidates import MarsCandidate
from src.backend.ml.extraction.mars.safety import MarsAbstentionReason

# Conventional RRF constant. Damps the influence of top ranks so a candidate
# ranked consistently well outweighs one ranked first by a single judge.
RRF_K = 60

RejectionReason = str


class JudgeResponse(BaseModel):
    """One judge's parsed answer.

    Carries only an ordering of internal candidate ids. There is deliberately
    no field on this model that could hold an extracted value: a judge that
    emits a value is an extractor, and MARS has no code path that reads one
    from a judge response.
    """

    judge_id: str
    internal_ids: list[str] = Field(default_factory=list)
    rejection: RejectionReason | None = None

    @property
    def is_valid(self) -> bool:
        return self.rejection is None


# @spec MARS-009, MARS-010
def parse_judge_response(
    raw: object,
    presentation: JudgePresentation,
    *,
    judge_id: str,
) -> JudgeResponse:
    """Validate a judge's raw answer and resolve aliases to internal ids.

    Accepts a sequence of alias strings and nothing else. A mapping, a prose
    string, or a payload that also carries field values is rejected outright
    rather than mined for whichever part looks like a ranking -- reading a
    ranking out of a malformed response would be the first step toward reading
    other things out of it too.
    """
    def rejected(reason: RejectionReason) -> JudgeResponse:
        return JudgeResponse(judge_id=judge_id, rejection=reason)

    if not isinstance(raw, list) or not raw:
        return rejected("unparseable")
    if not all(isinstance(item, str) for item in raw):
        return rejected("unparseable")

    aliases: list[str] = list(raw)
    if len(set(aliases)) != len(aliases):
        return rejected("duplicate_alias")
    if any(alias not in presentation.aliases for alias in aliases):
        return rejected("unknown_alias")
    if len(aliases) != len(presentation.aliases):
        return rejected("incomplete_ordering")

    resolved = [presentation.resolve(alias) for alias in aliases]
    if any(internal_id is None for internal_id in resolved):
        return rejected("unknown_alias")

    return JudgeResponse(judge_id=judge_id, internal_ids=[i for i in resolved if i])


# @spec MARS-011
def validate_response_count(
    responses: list[JudgeResponse],
    *,
    min_valid_judge_responses: int,
) -> MarsAbstentionReason | None:
    """Abstention reason when too few judges returned a usable ranking.

    Distinct from the roster shortfall of MARS-028: that one is a
    configuration problem detected before any judge is called, this one is a
    model-execution problem detected after.
    """
    if sum(1 for response in responses if response.is_valid) < min_valid_judge_responses:
        return MarsAbstentionReason.INSUFFICIENT_VALID_JUDGE_RESPONSES
    return None


# @spec MARS-012, MARS-021
def fuse_rankings(
    responses: list[JudgeResponse],
    candidates: list[MarsCandidate],
) -> dict[str, float]:
    """Reciprocal Rank Fusion over the valid rankings.

        score(c) = sum over judges of  1 / (RRF_K + rank_j(c))

    Chosen over averaging judge scores because judges produce orderings rather
    than calibrated numbers, and over a first-place vote because it uses the
    whole ranking instead of only its head.

    Candidate multiplicity contributes nothing here (MARS-021). Several models
    agreeing measures shared training distribution, not correctness, so
    weighting by it would systematically favor whichever model family is
    over-represented in the ensemble.
    """
    scores = {candidate.internal_id: 0.0 for candidate in candidates}
    for response in responses:
        if not response.is_valid:
            continue
        for position, internal_id in enumerate(response.internal_ids, start=1):
            if internal_id in scores:
                scores[internal_id] += 1.0 / (RRF_K + position)
    return scores


# @spec MARS-013, MARS-014, MARS-021
def select_provisional_winner(
    scores: dict[str, float],
    candidates: list[MarsCandidate],
) -> str | None:
    """Highest fused score, ties resolved deterministically.

    Multiplicity enters only here, and only after the fused scores are exactly
    equal -- it separates otherwise indistinguishable candidates rather than
    adding weight to the ranking.

    The final tie-break is the stable internal id, never a judge-visible alias:
    aliases are per-judge and carry no global ordering, so a tie broken on one
    would not reproduce.
    """
    if not scores:
        return None

    multiplicity = {c.internal_id: c.multiplicity for c in candidates}
    return min(
        scores,
        key=lambda internal_id: (
            -scores[internal_id],
            -multiplicity.get(internal_id, 0),
            internal_id,
        ),
    )
