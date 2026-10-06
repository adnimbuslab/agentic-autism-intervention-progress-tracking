"""MarsExtractionProvider: end-to-end orchestration.

Covers MARS-001/002 (provider contract), MARS-006 (short circuit proven by
call counting, not by a returned boolean) and MARS-014 (orchestration-level
replay determinism).

Every generator and judge here is a deterministic fake with a call counter, so
"no model was called" is demonstrated rather than asserted.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.backend.ml.extraction.base import ExtractionProvider
from src.backend.ml.extraction.mars.blinding import JudgePresentation
from src.backend.ml.extraction.mars.confidence import GeneratorConfidencePolicy
from src.backend.ml.extraction.mars.provider import (
    MarsExtractionProvider,
    MarsGenerator,
    MarsJudge,
)
from src.backend.ml.extraction.mars.safety import MarsAbstentionReason
from src.backend.ml.extraction.schemas import (
    ControlConfidenceState,
    ExtractionRequest,
    ExtractionResult,
    ExtractionStatus,
    ModelDescriptor,
    ModelRole,
    SourceType,
)
from src.backend.ml.schemas import RoutingDecision
from src.backend.ml.validation_engine import ValidationEngine
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

# Fields that legitimately vary between two identical runs.
NONDETERMINISTIC_FIELDS = {"generated_at"}


def _request() -> ExtractionRequest:
    return ExtractionRequest(
        source_type=SourceType.CHAT_SEGMENT,
        text="*CHI:\tbus .\n%act:\tpoints at the bus",
        child_id="carl",
        session_id="020800",
        contributor_role=ContributorRole.INTERVENTIONIST,
        observation_date=date(2026, 9, 7),
        setting=Setting.CLINIC,
    )


def _obs(behavior: str, confidence: float | None = 0.8, **kw) -> StructuredObservation:
    payload = dict(
        child_id="carl",
        session_id="020800",
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
    payload.update(kw)
    return StructuredObservation(**payload)  # type: ignore[arg-type]


class FakeGenerator(ExtractionProvider):
    """Deterministic generator with a call counter."""

    def __init__(
        self,
        identifier: str,
        observation: StructuredObservation | None,
        status: ExtractionStatus = ExtractionStatus.SUCCESS,
    ) -> None:
        self.identifier = identifier
        self._observation = observation
        self._status = status
        self.calls = 0

    async def extract(self, request: ExtractionRequest) -> ExtractionResult:
        self.calls += 1
        return ExtractionResult(
            status=self._status,
            observations=[self._observation] if self._observation else [],
            provider="fake",
            model=self.identifier,
            prompt_version="1.0",
        )

    def get_info(self):  # pragma: no cover - unused by MARS
        raise NotImplementedError


class FakeJudge:
    """Ranks by a fixed behavior order, with a call counter."""

    def __init__(self, identifier: str, order: list[str] | None, raw: object = None) -> None:
        self.identifier = identifier
        self._order = order
        self._raw = raw
        self.calls = 0

    async def rank(self, *, source_text: str, presentation: JudgePresentation) -> object:
        self.calls += 1
        if self._order is None:
            return self._raw
        # presented_fields carries *normalized* content, so match casefolded.
        by_behavior = {
            str(fields["behavior"]).casefold(): alias
            for alias, fields in presentation.presented_fields.items()
        }
        return [by_behavior[b.casefold()] for b in self._order if b.casefold() in by_behavior]


def _gen(identifier: str, observation, status=ExtractionStatus.SUCCESS) -> MarsGenerator:
    fake = FakeGenerator(identifier, observation, status)
    return MarsGenerator(
        fake,
        ModelDescriptor(
            identifier=identifier,
            family=identifier.split("_")[0],
            config_hash="g1",
            role=ModelRole.GENERATOR,
        ),
    )


def _judge(identifier: str, order=None, raw=None) -> MarsJudge:
    fake = FakeJudge(identifier, order, raw)
    return MarsJudge(
        fake,
        ModelDescriptor(
            identifier=identifier,
            family=identifier.split("_")[0],
            config_hash="j1",
            role=ModelRole.JUDGE,
        ),
    )


def _provider(generators, judges, *, threshold=0.5, min_eligible=1, min_valid=1):
    return MarsExtractionProvider(
        generators=generators,
        judges=judges,
        agreement_threshold=threshold,
        generator_confidence_policy=MIN,
        min_eligible_judges=min_eligible,
        min_valid_judge_responses=min_valid,
        run_seed="run-1",
    )


class TestConfiguration:
    """MARS-001/002: explicit configuration, validated early."""

    # @spec MARS-001
    @pytest.mark.parametrize(
        "missing",
        ["agreement_threshold", "generator_confidence_policy", "min_eligible_judges",
         "min_valid_judge_responses", "run_seed"],
    )
    def test_every_calibration_value_is_required(self, missing: str) -> None:
        kwargs = dict(
            generators=[_gen("model_a", _obs("A"))],
            judges=[_judge("judge_d")],
            agreement_threshold=0.5,
            generator_confidence_policy=MIN,
            min_eligible_judges=1,
            min_valid_judge_responses=1,
            run_seed="run-1",
        )
        kwargs.pop(missing)

        with pytest.raises(TypeError):
            MarsExtractionProvider(**kwargs)  # type: ignore[arg-type]

    # @spec MARS-001
    def test_at_least_one_generator_is_required(self) -> None:
        with pytest.raises(ValueError, match="at least one candidate generator"):
            _provider([], [_judge("judge_d")])

    # @spec MARS-001
    @pytest.mark.parametrize("threshold", [-0.01, 1.01])
    def test_threshold_must_be_a_probability(self, threshold: float) -> None:
        with pytest.raises(ValueError, match=r"must lie in \[0, 1\]"):
            _provider([_gen("model_a", _obs("A"))], [], threshold=threshold)

    # @spec MARS-001, MARS-027
    def test_identities_colliding_after_canonicalization_are_rejected(self) -> None:
        """Two spellings of one identity would make eligibility ambiguous — a
        model excluded under one spelling and admitted under the other."""
        with pytest.raises(ValueError, match="Duplicate judge identity"):
            _provider(
                [_gen("model_a", _obs("A"))],
                [_judge("Judge_D"), _judge("  judge_d ")],
            )

    # @spec MARS-001
    def test_roles_must_be_declared_correctly(self) -> None:
        mislabelled = MarsJudge(
            FakeJudge("judge_d", ["A"]),
            ModelDescriptor(identifier="judge_d", role=ModelRole.GENERATOR),
        )

        with pytest.raises(ValueError, match="must be declared with role judge"):
            _provider([_gen("model_a", _obs("A"))], [mislabelled])

    # @spec MARS-002
    def test_provider_satisfies_the_extraction_contract(self) -> None:
        provider = _provider([_gen("model_a", _obs("A"))], [])

        assert hasattr(provider, "extract")


class TestShortCircuit:
    """MARS-006 — proven by call counting, not by a returned flag."""

    async def _run_agreeing(self):
        gens = [_gen(f"model_{i}", _obs("A")) for i in "abc"]
        judges = [_judge("judge_d", ["A"]), _judge("judge_e", ["A"])]
        result = await _provider(gens, judges).extract(_request())
        return result, gens, judges

    # @spec MARS-006
    async def test_no_judge_is_called_when_one_candidate_survives(self) -> None:
        result, gens, judges = await self._run_agreeing()

        assert result.provenance.candidate_count == 1
        assert [j.judge.calls for j in judges] == [0, 0]

    # @spec MARS-006
    async def test_every_generator_is_still_called_exactly_once(self) -> None:
        _, gens, _ = await self._run_agreeing()

        assert [g.provider.calls for g in gens] == [1, 1, 1]

    # @spec MARS-006
    async def test_no_fusion_or_agreement_evidence_is_produced(self) -> None:
        result, _, _ = await self._run_agreeing()

        provenance = result.provenance
        assert provenance.judge_ids == []
        assert provenance.ranking == []
        assert provenance.fused_scores == {}
        assert provenance.top_choice_support is None
        assert provenance.modal_internal_ids == []
        assert provenance.seeds == {}

    # @spec MARS-006, MARS-025
    async def test_short_circuit_uses_the_canonical_envelope(self) -> None:
        result, _, _ = await self._run_agreeing()

        assert result.status is ExtractionStatus.SUCCESS
        assert result.observations[0].behavior == "A"
        assert result.provenance.generator_ids == ["model_a", "model_b", "model_c"]
        assert result.provenance.selected_internal_id is not None

    # @spec MARS-006
    async def test_the_adjacent_negative_case_runs_the_full_pipeline(self) -> None:
        """Two distinct candidates: judges are called and fusion evidence exists."""
        gens = [_gen("model_a", _obs("A")), _gen("model_b", _obs("B"))]
        judges = [_judge("judge_d", ["A", "B"]), _judge("judge_e", ["A", "B"])]

        result = await _provider(gens, judges).extract(_request())

        assert result.provenance.candidate_count == 2
        assert [j.judge.calls for j in judges] == [1, 1]
        assert result.provenance.fused_scores != {}
        assert result.provenance.top_choice_support == pytest.approx(1.0)


class TestFullPipeline:
    """Success and every abstention path, end to end."""

    # @spec MARS-001
    async def test_agreement_pass_yields_success(self) -> None:
        gens = [_gen("model_a", _obs("A")), _gen("model_b", _obs("B"))]
        judges = [_judge("judge_d", ["A", "B"]), _judge("judge_e", ["A", "B"])]

        result = await _provider(gens, judges).extract(_request())

        assert result.status is ExtractionStatus.SUCCESS
        assert result.observations[0].behavior == "A"
        assert result.control_confidence == pytest.approx(0.8)

    # @spec MARS-016
    async def test_agreement_failure_yields_canonical_abstention(self) -> None:
        gens = [_gen("model_a", _obs("A")), _gen("model_b", _obs("B"))]
        judges = [_judge("judge_d", ["A", "B"]), _judge("judge_e", ["B", "A"])]

        result = await _provider(gens, judges, threshold=0.9).extract(_request())

        assert result.status is ExtractionStatus.ABSTAINED
        assert result.reason_code == MarsAbstentionReason.JUDGE_DISAGREEMENT
        assert result.observations == []
        assert result.control_confidence is None
        assert result.provenance.fused_scores != {}

    # @spec MARS-005
    async def test_no_admissible_candidate_abstains(self) -> None:
        gens = [
            _gen("model_a", _obs("A"), status=ExtractionStatus.FAILED),
            _gen("model_b", None),
        ]

        result = await _provider(gens, [_judge("judge_d", ["A"])]).extract(_request())

        assert result.reason_code == MarsAbstentionReason.NO_REVIEWABLE_CANDIDATE
        assert result.provenance.candidate_count == 0
        assert result.provenance.discarded_generators == [
            ["model_a", "status_not_reviewable"],
            ["model_b", "no_observations"],
        ]

    # @spec MARS-011
    async def test_no_valid_ranking_abstains_on_response_count(self) -> None:
        gens = [_gen("model_a", _obs("A")), _gen("model_b", _obs("B"))]
        judges = [_judge("judge_d", None, raw="not a ranking")]

        result = await _provider(gens, judges).extract(_request())

        assert result.reason_code == (
            MarsAbstentionReason.INSUFFICIENT_VALID_JUDGE_RESPONSES
        )
        assert result.provenance.discarded_judges == [["judge_d", "unparseable"]]

    # @spec MARS-010
    async def test_a_malformed_response_is_excluded_but_others_count(self) -> None:
        gens = [_gen("model_a", _obs("A")), _gen("model_b", _obs("B"))]
        judges = [_judge("judge_d", ["A", "B"]), _judge("judge_e", None, raw=None)]

        result = await _provider(gens, judges).extract(_request())

        assert result.status is ExtractionStatus.SUCCESS
        assert result.provenance.ranking == [result.provenance.ranking[0]]
        assert result.provenance.discarded_judges == [["judge_e", "unparseable"]]

    # @spec MARS-028
    async def test_roster_without_eligible_judges_abstains(self) -> None:
        gens = [_gen("model_a", _obs("A")), _gen("model_b", _obs("B"))]
        judges = [_judge("model_a"), _judge("model_b")]

        result = await _provider(gens, judges).extract(_request())

        assert result.reason_code == MarsAbstentionReason.INSUFFICIENT_ELIGIBLE_JUDGES
        assert [j.judge.calls for j in judges] == [0, 0]

    # @spec MARS-024
    async def test_low_generator_confidence_does_not_abstain(self) -> None:
        gens = [_gen("model_a", _obs("A", 0.2)), _gen("model_b", _obs("B", 0.2))]
        judges = [_judge("judge_d", ["A", "B"]), _judge("judge_e", ["A", "B"])]

        result = await _provider(gens, judges).extract(_request())

        assert result.status is ExtractionStatus.SUCCESS
        assert result.control_confidence == pytest.approx(0.2)

    # @spec MARS-024
    async def test_sparse_observation_does_not_abstain(self) -> None:
        sparse = _obs("A", 0.8, modality=None, prompt_level=None, outcome=None)
        gens = [_gen("model_a", sparse), _gen("model_b", _obs("B"))]
        judges = [_judge("judge_d", ["A", "B"]), _judge("judge_e", ["A", "B"])]

        result = await _provider(gens, judges).extract(_request())

        assert result.status is ExtractionStatus.SUCCESS

    # @spec MARS-021, MARS-032
    async def test_minimum_policy_cannot_change_the_winner(self) -> None:
        """Aggregation is descriptive: it moves confidence, never selection."""
        gens = [
            _gen("model_a", _obs("A", 0.9)),
            _gen("model_x", _obs("A", 0.3)),
            _gen("model_b", _obs("B", 0.99)),
        ]
        judges = [_judge("judge_d", ["A", "B"]), _judge("judge_e", ["A", "B"])]

        result = await _provider(gens, judges).extract(_request())

        assert result.observations[0].behavior == "A"
        assert result.provenance.generator_confidence == pytest.approx(0.3)
        assert result.control_confidence == pytest.approx(0.3)

    # @spec MARS-001
    async def test_every_public_result_is_the_canonical_envelope(self) -> None:
        cases = [
            ([_gen("model_a", _obs("A"))], [_judge("judge_d", ["A"])]),
            (
                [_gen("model_a", _obs("A")), _gen("model_b", _obs("B"))],
                [_judge("judge_d", ["A", "B"])],
            ),
            ([_gen("model_a", None)], [_judge("judge_d", ["A"])]),
        ]

        for gens, judges in cases:
            result = await _provider(gens, judges).extract(_request())
            assert isinstance(result, ExtractionResult)
            assert result.provenance is not None


class TestReplayDeterminism:
    """MARS-014 at the level its claim actually covers."""

    def _build(self):
        gens = [
            _gen("model_a", _obs("A", 0.7)),
            _gen("model_b", _obs("B", 0.9)),
            _gen("model_c", _obs("C", 0.8)),
        ]
        judges = [
            _judge("judge_d", ["A", "B", "C"]),
            _judge("judge_e", ["A", "C", "B"]),
            _judge("judge_f", ["B", "A", "C"]),
        ]
        return _provider(gens, judges, min_valid=2)

    # @spec MARS-014
    async def test_two_identical_runs_produce_identical_envelopes(self) -> None:
        first = await self._build().extract(_request())
        second = await self._build().extract(_request())

        a = first.model_dump()
        b = second.model_dump()
        for field in NONDETERMINISTIC_FIELDS:
            a.pop(field), b.pop(field)

        assert a == b

    # @spec MARS-014
    async def test_every_semantic_provenance_field_replays(self) -> None:
        first = (await self._build().extract(_request())).provenance
        second = (await self._build().extract(_request())).provenance

        for field in (
            "candidate_count", "selected_internal_id", "fused_scores",
            "top_choice_support", "modal_internal_ids", "agreement_threshold",
            "agreement_failure", "diagnostic_statistics", "seeds",
            "discarded_generators", "discarded_judges", "generator_ids",
            "judge_ids", "ranking", "generator_confidence",
            "mars_selection_confidence",
        ):
            assert getattr(first, field) == getattr(second, field), field

        assert [m.model_dump() for m in first.models] == [
            m.model_dump() for m in second.models
        ]

    # @spec MARS-014
    async def test_only_the_timestamp_differs(self) -> None:
        """Documents the exclusion rather than assuming it."""
        first = await self._build().extract(_request())
        second = await self._build().extract(_request())

        differing = {
            k for k in first.model_dump()
            if first.model_dump()[k] != second.model_dump()[k]
        }

        assert differing <= NONDETERMINISTIC_FIELDS

    # @spec MARS-008, MARS-014
    async def test_generator_order_does_not_change_the_outcome(self) -> None:
        """The candidate-set fingerprint is order-independent, so provider
        responses arriving in a different order must not move the result."""
        def build(order):
            gens = [
                _gen(f"model_{i}", _obs(b, c))
                for i, b, c in order
            ]
            judges = [
                _judge("judge_d", ["A", "B", "C"]),
                _judge("judge_e", ["A", "C", "B"]),
            ]
            return _provider(gens, judges)

        forward = await build([("a", "A", 0.7), ("b", "B", 0.9), ("c", "C", 0.8)]).extract(
            _request()
        )
        shuffled = await build([("c", "C", 0.8), ("a", "A", 0.7), ("b", "B", 0.9)]).extract(
            _request()
        )

        assert forward.observations[0].behavior == shuffled.observations[0].behavior
        assert forward.provenance.seeds == shuffled.provenance.seeds
        assert forward.provenance.fused_scores == shuffled.provenance.fused_scores
        assert forward.control_confidence == shuffled.control_confidence


class TestShortCircuitSafetyRouting:
    """The short-circuit path must not be handled more weakly than the
    single-model provider MARS replaces.

    No judges run, so no reranking evidence exists and MARS establishes no
    control confidence. Declaring that explicitly is what makes downstream
    route it for review instead of accepting it on silence (VALID-015).
    """

    async def _short_circuit(self, confidence: float):
        gens = [_gen(f"model_{i}", _obs("A", confidence)) for i in "abc"]
        judges = [_judge("judge_d", ["A"]), _judge("judge_e", ["A"])]
        return await _provider(gens, judges).extract(_request())

    # @spec MARS-006, MARS-032
    @pytest.mark.parametrize("confidence", [0.1, 0.99])
    async def test_short_circuit_declares_confidence_unavailable(
        self, confidence: float
    ) -> None:
        result = await self._short_circuit(confidence)

        assert result.status is ExtractionStatus.SUCCESS
        assert result.control_confidence is None
        assert result.control_confidence_state is (
            ControlConfidenceState.NOT_AVAILABLE_SHORT_CIRCUIT
        )

    # @spec MARS-006, VALID-015
    @pytest.mark.parametrize("confidence", [0.1, 0.99])
    async def test_short_circuit_routes_to_interventionist_review(
        self, confidence: float
    ) -> None:
        """v1 is deliberately conservative — generator consensus, however
        confident, is not a substitute for reranking evidence."""
        result = await self._short_circuit(confidence)

        routing = ValidationEngine().validate(
            result.observations[0],
            control_confidence=result.control_confidence,
            control_confidence_state=result.control_confidence_state,
        ).routing

        assert routing is RoutingDecision.INTERVENTIONIST_REVIEW

    # @spec MARS-032
    async def test_short_circuit_never_fabricates_selection_confidence(self) -> None:
        result = await self._short_circuit(0.99)

        assert result.provenance.mars_selection_confidence is None
        assert result.provenance.top_choice_support is None

    # @spec MARS-032
    async def test_generator_confidence_is_never_copied_into_control(self) -> None:
        result = await self._short_circuit(0.99)

        assert result.provenance.generator_confidence == pytest.approx(0.99)
        assert result.control_confidence is None

    # @spec MARS-016, VALID-015
    async def test_judged_path_can_still_reach_accept(self) -> None:
        gens = [_gen("model_a", _obs("A", 0.9)), _gen("model_b", _obs("B", 0.9))]
        judges = [_judge("judge_d", ["A", "B"]), _judge("judge_e", ["A", "B"])]

        result = await _provider(gens, judges).extract(_request())
        routing = ValidationEngine().validate(
            result.observations[0],
            control_confidence=result.control_confidence,
            control_confidence_state=result.control_confidence_state,
        ).routing

        assert result.control_confidence_state is ControlConfidenceState.AVAILABLE
        assert result.control_confidence == pytest.approx(0.9)
        assert routing is RoutingDecision.ACCEPT

    # @spec MARS-025
    async def test_abstention_remains_abstention(self) -> None:
        """The routing patch changes nothing about an abstained result: it
        carries no observation to route in the first place."""
        gens = [_gen("model_a", _obs("A")), _gen("model_b", _obs("B"))]
        judges = [_judge("judge_d", ["A", "B"]), _judge("judge_e", ["B", "A"])]

        result = await _provider(gens, judges, threshold=0.9).extract(_request())

        assert result.status is ExtractionStatus.ABSTAINED
        assert result.observations == []
        assert result.control_confidence_state is (
            ControlConfidenceState.NOT_AVAILABLE_ABSTAINED
        )
