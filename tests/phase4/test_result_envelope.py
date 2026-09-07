"""Shared `ExtractionResult` envelope: control confidence and provenance.

Covers EXTRACT-020/021/022 — the additive contract evolution that lets a
composing provider (MARS) report what deterministic validation needs without a
provider-specific side channel.

The point of `control_confidence` is that a validation threshold means the same
thing regardless of which provider produced the result. For a provider that
generates directly, it equals the observation's own confidence; for one that
selects among candidates, it combines generator and selection confidence
(MARS-032). Consumers gate on `control_confidence` and never on how it was derived.
"""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from src.backend.ml.extraction.schemas import (
    ExtractionProvenance,
    ExtractionResult,
    ExtractionStatus,
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


def _observation(confidence: float | None = 0.8) -> StructuredObservation:
    return StructuredObservation(
        child_id="child_1",
        session_id="session_1",
        contributor_role=ContributorRole.INTERVENTIONIST,
        observation_date=date(2026, 9, 7),
        setting=Setting.CLINIC,
        domain=Domain.SOCIAL_COMMUNICATION,
        behavior="Child pointed to the requested item",
        modality=Modality.GESTURAL,
        prompt_level=PromptLevel.INDEPENDENT,
        outcome=Outcome.CORRECT,
        confidence=confidence,
    )


def _result(**overrides: object) -> ExtractionResult:
    payload: dict[str, object] = {
        "status": ExtractionStatus.SUCCESS,
        "observations": [_observation()],
        "provider": "temporary_llm",
        "model": "test-model",
        "prompt_version": "1.0",
    }
    payload.update(overrides)
    return ExtractionResult(**payload)  # type: ignore[arg-type]


class TestControlConfidence:
    """EXTRACT-020: one confidence quantity that deterministic validation gates on."""

    # @spec EXTRACT-020
    def test_result_carries_control_confidence(self) -> None:
        result = _result(control_confidence=0.42)

        assert result.control_confidence == 0.42

    # @spec EXTRACT-020
    def test_control_confidence_defaults_to_none_when_unset(self) -> None:
        """Absent is distinguishable from zero — a provider that reports no
        confidence must not be read as reporting no confidence *in* the result."""
        assert _result().control_confidence is None

    # @spec EXTRACT-020
    @pytest.mark.parametrize("value", [-0.01, 1.01])
    def test_control_confidence_outside_unit_interval_is_rejected(self, value: float) -> None:
        with pytest.raises(ValidationError):
            _result(control_confidence=value)

    # @spec EXTRACT-020
    @pytest.mark.parametrize("value", [0.0, 0.4, 0.7, 1.0])
    def test_control_confidence_accepts_unit_interval_bounds(self, value: float) -> None:
        assert _result(control_confidence=value).control_confidence == value


class TestProvenanceEnvelope:
    """EXTRACT-021: provenance travels in the shared envelope, not a side channel."""

    # @spec EXTRACT-021
    def test_result_carries_optional_provenance_and_reason_code(self) -> None:
        result = _result(
            provenance=ExtractionProvenance(
                provider_type="mars",
                generator_ids=["model_a", "model_b"],
                judge_ids=["model_d"],
                ranking=[["cand_1", "cand_2"]],
                generator_confidence=0.9,
                mars_selection_confidence=0.5,
            ),
            reason_code=None,
        )

        assert result.provenance is not None
        assert result.provenance.generator_ids == ["model_a", "model_b"]
        assert result.provenance.mars_selection_confidence == 0.5

    # @spec EXTRACT-021
    def test_provenance_is_optional(self) -> None:
        """A provider that records nothing still returns the same shape."""
        result = _result()

        assert result.provenance is None
        assert result.reason_code is None

    # @spec EXTRACT-021
    def test_single_model_provenance_has_empty_judge_fields(self) -> None:
        """Empty judge identities are an accurate statement that judging did not
        occur, not filler — so they default to empty rather than None."""
        provenance = ExtractionProvenance(provider_type="temporary_llm", generator_ids=["m"])

        assert provenance.judge_ids == []
        assert provenance.ranking == []
        assert provenance.mars_selection_confidence is None

    # @spec EXTRACT-021
    def test_provenance_is_not_on_the_structured_observation(self) -> None:
        """`StructuredObservation` describes the observation, not its derivation.
        Ensemble bookkeeping must not leak into the clinical record."""
        observation_fields = set(StructuredObservation.model_fields)

        assert observation_fields.isdisjoint(
            {"provenance", "generator_ids", "judge_ids", "ranking", "reason_code"}
        )

    # @spec EXTRACT-021
    def test_envelope_shape_is_identical_across_providers(self) -> None:
        """EXTRACT-002 requires one contract shape. Optional fields differ in
        applicability, never in presence."""
        single = _result(provenance=ExtractionProvenance(provider_type="temporary_llm"))
        composing = _result(
            provider="mars",
            provenance=ExtractionProvenance(provider_type="mars", judge_ids=["d", "e"]),
        )

        assert set(single.model_dump()) == set(composing.model_dump())


class TestBackwardCompatibility:
    """Existing providers must remain behaviorally unchanged by the evolution."""

    # @spec EXTRACT-020, EXTRACT-021
    def test_result_constructs_without_any_new_field(self) -> None:
        """Every call site predating this change keeps working untouched."""
        result = _result()

        assert result.status is ExtractionStatus.SUCCESS
        assert result.observations[0].confidence == 0.8

    # @spec EXTRACT-020, EXTRACT-021
    def test_round_trips_through_serialization(self) -> None:
        result = _result(
            control_confidence=0.35,
            provenance=ExtractionProvenance(provider_type="mars", generator_ids=["a"]),
            reason_code="judge_disagreement",
        )

        restored = ExtractionResult.model_validate(result.model_dump(mode="json"))

        assert restored.control_confidence == 0.35
        assert restored.reason_code == "judge_disagreement"
        assert restored.provenance is not None
        assert restored.provenance.generator_ids == ["a"]

    # @spec EXTRACT-020, EXTRACT-021
    def test_legacy_payload_without_new_fields_still_validates(self) -> None:
        """A serialized result written before this change must still load."""
        legacy = {
            "status": "success",
            "observations": [],
            "provider": "temporary_llm",
            "model": "test-model",
            "prompt_version": "1.0",
        }

        restored = ExtractionResult.model_validate(legacy)

        assert restored.control_confidence is None
        assert restored.provenance is None


class TestGeneratingProviderControlConfidence:
    """EXTRACT-022: a provider that generates directly maps its observation's
    own confidence onto `control_confidence`.

    This is what makes the two quantities equal for single-model providers,
    and therefore what lets the validation gates migrate to `control_confidence`
    without changing existing behavior.
    """

    # @spec EXTRACT-022
    @pytest.mark.parametrize("confidence", [0.0, 0.29, 0.4, 0.7, 0.95, 1.0])
    async def test_temporary_llm_sets_control_confidence_from_observation(
        self, confidence: float
    ) -> None:
        from tests.phase4.conftest_envelope import extract_with_confidence

        result = await extract_with_confidence(confidence)

        assert result.observations[0].confidence == confidence
        assert result.control_confidence == confidence

    # @spec EXTRACT-022
    async def test_control_confidence_is_none_when_observation_has_none(self) -> None:
        from tests.phase4.conftest_envelope import extract_with_confidence

        result = await extract_with_confidence(None)

        assert result.control_confidence is None

    # @spec EXTRACT-021, EXTRACT-022
    async def test_generating_provider_records_empty_judge_provenance(self) -> None:
        """Judging did not occur, and the envelope says so explicitly."""
        from tests.phase4.conftest_envelope import extract_with_confidence

        result = await extract_with_confidence(0.8)

        assert result.provenance is not None
        assert result.provenance.judge_ids == []
        assert result.provenance.ranking == []
        assert result.provenance.generator_confidence == 0.8
        assert result.provenance.mars_selection_confidence is None
