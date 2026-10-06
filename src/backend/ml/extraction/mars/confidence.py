"""Confidence composition.

Three quantities, deliberately not interchangeable:

  ``generator_confidence``       the selected candidate's own generators
  ``mars_selection_confidence``  confidence in MARS's *selection*
  ``control_confidence``         what deterministic validation gates on

This module is descriptive. It composes numbers; it does not select a
candidate, override the agreement gate, or decide whether a result may be
returned. A perfect generator confidence cannot rescue a candidate the judges
rejected -- composition records that state, it does not change it.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel

from src.backend.ml.extraction.mars.agreement import AgreementDecision
from src.backend.ml.extraction.mars.candidates import MarsCandidate


class GeneratorConfidencePolicy(enum.StrEnum):
    """How to reduce a merged candidate's several generator confidences to one.

    No MARS requirement fixes this rule -- deduplication preserves every
    contributing generator's confidence precisely so the choice stays explicit
    (MARS-004). The policy is therefore a required argument rather than a
    default: silently picking one here would settle an open decision by
    accident, in the layer least visible to whoever should be making it.
    """

    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    MEAN = "mean"


class MarsConfidence(BaseModel):
    """The three quantities, kept separate.

    Carries no candidate, no observation, and no pass/fail of its own.
    ``agreement_passed`` is copied through for provenance only -- it is the
    agreement gate's verdict, restated here, never recomputed.
    """

    generator_confidence: float | None = None
    mars_selection_confidence: float | None = None
    control_confidence: float | None = None
    agreement_passed: bool


# @spec MARS-022
def aggregate_generator_confidence(
    candidate: MarsCandidate,
    *,
    policy: GeneratorConfidencePolicy,
) -> float | None:
    """Reduce the candidate's per-generator confidences under ``policy``.

    Generators that reported no confidence contribute nothing rather than
    counting as zero. Where none reported one, the result is ``None``:
    "unknown" and "measured as zero" are different claims, and only the
    second would be a statement about the extraction.

    Multiplicity never inflates the result -- three generators agreeing at
    0.8 yield 0.8 under every policy, because agreement among models is not
    itself evidence of correctness (MARS-021).
    """
    values = sorted(v for v in candidate.generator_confidences.values() if v is not None)
    if not values:
        return None
    if policy is GeneratorConfidencePolicy.MINIMUM:
        return values[0]
    if policy is GeneratorConfidencePolicy.MAXIMUM:
        return values[-1]
    return sum(values) / len(values)


# @spec MARS-023
def derive_selection_confidence(agreement: AgreementDecision) -> float | None:
    """Confidence in MARS's selection, from judge evidence alone.

    This is the top-choice support of the selected candidate -- the inter-judge
    agreement statistic MARS-015 already defines. MARS-023 permits deriving it
    from the rankings, the fused scores, and the agreement statistic; using the
    agreement statistic by itself introduces no weighting and therefore no free
    parameter. Any formula blending fused scores in would need weights, and
    those are an unresolved calibration question, not an implementation detail.

    Taking no generator input at all is what makes MARS-023's independence
    structural rather than a promise: a candidate with high generator
    confidence that judges disagree about yields low selection confidence
    because generator confidence is not reachable from here.

    ``None`` where no valid judge ranking exists -- absent evidence, not zero
    confidence.
    """
    return agreement.first_choice_support


# @spec MARS-032
def compose_confidence(
    *,
    candidate: MarsCandidate,
    agreement: AgreementDecision,
    generator_policy: GeneratorConfidencePolicy,
) -> MarsConfidence:
    """Compose the three quantities.

        control_confidence = min(generator_confidence, mars_selection_confidence)

    The conservative reading: a returned observation is only as trustworthy as
    its weakest relevant confidence dimension. Either failure mode -- a
    confidently-extracted poor candidate, or a weakly-distinguished pair of
    strong ones -- drags the control quantity down, and neither can hide behind
    the other.

    Where either input is absent, ``control_confidence`` is ``None``. MARS-032
    forbids writing either quantity alone, so the available one cannot stand in;
    and defaulting to zero would assert a measurement that was never made.

    Replacing the combination function changes no contract: consumers depend on
    ``control_confidence``, never on how it was derived.
    """
    generator_confidence = aggregate_generator_confidence(
        candidate, policy=generator_policy
    )
    mars_selection_confidence = derive_selection_confidence(agreement)

    control_confidence = (
        min(generator_confidence, mars_selection_confidence)
        if generator_confidence is not None and mars_selection_confidence is not None
        else None
    )

    return MarsConfidence(
        generator_confidence=generator_confidence,
        mars_selection_confidence=mars_selection_confidence,
        control_confidence=control_confidence,
        agreement_passed=agreement.passed,
    )
