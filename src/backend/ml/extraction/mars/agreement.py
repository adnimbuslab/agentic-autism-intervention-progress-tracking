"""The agreement gate: may the provisional RRF winner proceed?

Fusion decides *which* candidate; this decides *whether there is enough judge
support to return it*. The two are separate on purpose. RRF uses whole rankings,
so it can favour a candidate ranked consistently well over one with the most
first-place votes -- a mathematically correct winner that judges never actually
chose. This gate is what stops such a candidate from being returned on fused
score alone.

The gate never selects. It is handed the winner fusion already produced and
answers one question about that candidate. It does not rerun fusion, substitute
the candidate judges preferred, or resolve a tie in anyone's favour. Where the
answer is no, a later step owns turning that into an abstained result.
"""

from __future__ import annotations

import enum
from collections import Counter

from pydantic import BaseModel, Field

from src.backend.ml.extraction.mars.fusion import JudgeResponse
from src.backend.ml.extraction.mars.safety import MarsAbstentionReason


class AgreementFailure(enum.StrEnum):
    """Why the provisional winner may not proceed.

    Finer-grained than the abstention reason code so provenance can say which
    condition fired; all of them that MARS attributes to disagreement map onto
    the single `judge_disagreement` code.
    """

    NO_VALID_RANKINGS = "no_valid_rankings"
    NOT_MODAL_FIRST_CHOICE = "not_modal_first_choice"
    MODAL_TIE = "modal_tie"
    BELOW_THRESHOLD = "below_threshold"


# Failures MARS attributes to judge disagreement. NO_VALID_RANKINGS is
# deliberately excluded: MARS-011 owns that condition upstream and emits
# `insufficient_valid_judge_responses`. Reaching it here means the pipeline
# skipped that check, so the gate refuses without relabelling it as
# disagreement -- an empty judge panel is not a panel that disagreed.
_DISAGREEMENT_FAILURES = frozenset({
    AgreementFailure.NOT_MODAL_FIRST_CHOICE,
    AgreementFailure.MODAL_TIE,
    AgreementFailure.BELOW_THRESHOLD,
})


class AgreementDecision(BaseModel):
    """Agreement metadata only -- no candidate, no observation, no confidence.

    Confidence composition (MARS-032) consumes `first_choice_support` later;
    deriving anything confidence-shaped here would settle that decision early.
    """

    passed: bool
    provisional_internal_id: str
    valid_judge_count: int
    first_choice_support: float | None = None
    is_modal_first_choice: bool = False
    modal_internal_ids: list[str] = Field(default_factory=list)
    threshold: float
    failure: AgreementFailure | None = None
    reason_code: MarsAbstentionReason | None = None


# @spec MARS-015, MARS-016, MARS-030, MARS-031
def evaluate_agreement(
    *,
    provisional_internal_id: str,
    responses: list[JudgeResponse],
    threshold: float,
) -> AgreementDecision:
    """Decide whether ``provisional_internal_id`` has enough judge support.

    ``threshold`` is required and has no default: its value is an open
    calibration question (informed by human disagreement observed on the
    annotated batch, validated against the accuracy/abstention trade-off), and
    a default here would settle it by accident.

    Order follows MARS-031 -- the modal check precedes the threshold check, so
    a winner judges never ranked first is rejected regardless of how the
    threshold is set.
    """
    valid = [response for response in responses if response.is_valid]

    def decision(
        failure: AgreementFailure | None,
        *,
        support: float | None,
        modal: list[str],
    ) -> AgreementDecision:
        return AgreementDecision(
            passed=failure is None,
            provisional_internal_id=provisional_internal_id,
            valid_judge_count=len(valid),
            first_choice_support=support,
            is_modal_first_choice=provisional_internal_id in modal,
            modal_internal_ids=modal,
            threshold=threshold,
            failure=failure,
            reason_code=(
                MarsAbstentionReason.JUDGE_DISAGREEMENT
                if failure in _DISAGREEMENT_FAILURES
                else None
            ),
        )

    if not valid:
        return decision(AgreementFailure.NO_VALID_RANKINGS, support=None, modal=[])

    first_choices = Counter(response.internal_ids[0] for response in valid)
    top_count = max(first_choices.values())
    modal = sorted(
        internal_id for internal_id, count in first_choices.items() if count == top_count
    )

    # MARS-015: share of valid judges ranking *this* candidate first.
    support = first_choices.get(provisional_internal_id, 0) / len(valid)

    # MARS-030, checked before the threshold: fusion and judge first-choice
    # consensus must identify the same candidate.
    if provisional_internal_id not in modal:
        return decision(
            AgreementFailure.NOT_MODAL_FIRST_CHOICE, support=support, modal=modal
        )

    # A tie for the mode is not a consensus. Breaking it here -- by id,
    # multiplicity, or fused score -- would manufacture agreement that the
    # judges did not express, which is what the abstain-over-assert tenet
    # exists to prevent.
    if len(modal) > 1:
        return decision(AgreementFailure.MODAL_TIE, support=support, modal=modal)

    # MARS-016: strictly below the threshold abstains, so equality proceeds.
    if support < threshold:
        return decision(AgreementFailure.BELOW_THRESHOLD, support=support, modal=modal)

    return decision(None, support=support, modal=modal)
