"""MARS blinding and reproducibility: derived seeds and per-judge aliases.

Covers MARS-007 (per-judge opaque aliases over stable internal ids), MARS-008
(derived rather than drawn seeds) and MARS-033 (identical inputs reproduce
identical presentations).

The guarantee under test is *orchestration* replay — same candidate set, same
aliases, same order, same seeds. It is not a claim that a judge returns the
same ranking twice; that depends on the inference backend, not on MARS.
"""

from __future__ import annotations

from datetime import date

import pytest

from src.backend.ml.extraction.mars.blinding import (
    JudgePresentation,
    build_judge_presentation,
    candidate_set_fingerprint,
    canonical_judge_identity,
    derive_judge_seed,
    derive_request_seed,
)
from src.backend.ml.extraction.mars.candidates import build_candidates
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

MARS_VERSION = "1.0.0"
RUN_SEED = "run-seed-42"
SOURCE_ID = "carl_rollins_carl_020800.cha_seg_001"


def _obs(behavior: str = "Child pointed", confidence: float | None = 0.8) -> StructuredObservation:
    return StructuredObservation(
        child_id="child_1",
        session_id="session_1",
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


def _result(model: str, behavior: str, confidence: float | None = 0.8) -> ExtractionResult:
    return ExtractionResult(
        status=ExtractionStatus.SUCCESS,
        observations=[_obs(behavior, confidence)],
        provider="test_provider",
        model=model,
        prompt_version="1.0",
    )


def _candidates(*pairs: tuple[str, str]):
    return build_candidates([_result(model, behavior) for model, behavior in pairs])


ABC = (("model_a", "A"), ("model_b", "B"), ("model_c", "C"))


def _request_seed(candidates, run_seed: str = RUN_SEED) -> str:
    return derive_request_seed(
        source_id=SOURCE_ID,
        mars_version=MARS_VERSION,
        candidates=candidates,
        run_seed=run_seed,
    )


class TestCandidateSetFingerprint:
    """Order-independent, and a function of content rather than provenance."""

    # @spec MARS-008
    def test_is_invariant_to_provider_response_order(self) -> None:
        """Asynchronous providers may return in any order; the same evidence and
        configuration must not produce a different presentation because of it."""
        forward = _candidates(*ABC)
        shuffled = _candidates(ABC[2], ABC[0], ABC[1])

        assert candidate_set_fingerprint(forward) == candidate_set_fingerprint(shuffled)

    # @spec MARS-008
    def test_changes_when_the_candidate_content_changes(self) -> None:
        assert candidate_set_fingerprint(_candidates(*ABC)) != candidate_set_fingerprint(
            _candidates(("model_a", "A"), ("model_b", "B"))
        )

    # @spec MARS-008
    def test_is_independent_of_generator_provenance(self) -> None:
        """The fingerprint describes the alternatives being judged, not who
        produced them. Provenance already affects judge eligibility separately,
        and letting it also move the seed would change the presentation for a
        candidate set that did not change."""
        one_generator = _candidates(("model_a", "A"))
        two_generators = _candidates(("model_a", "A"), ("model_x", "A"))

        assert len(two_generators) == 1
        assert two_generators[0].generator_ids == ["model_a", "model_x"]
        assert candidate_set_fingerprint(one_generator) == candidate_set_fingerprint(
            two_generators
        )

    # @spec MARS-008
    def test_is_independent_of_generator_confidence(self) -> None:
        low = build_candidates([_result("model_a", "A", confidence=0.1)])
        high = build_candidates([_result("model_a", "A", confidence=0.99)])

        assert candidate_set_fingerprint(low) == candidate_set_fingerprint(high)


class TestSeedDerivation:
    """MARS-008: seeds are derived, not drawn."""

    # @spec MARS-008
    def test_request_seed_is_reproducible(self) -> None:
        assert _request_seed(_candidates(*ABC)) == _request_seed(_candidates(*ABC))

    # @spec MARS-008
    def test_request_seed_is_invariant_to_candidate_order(self) -> None:
        assert _request_seed(_candidates(*ABC)) == _request_seed(
            _candidates(ABC[2], ABC[0], ABC[1])
        )

    # @spec MARS-008
    @pytest.mark.parametrize(
        "kwargs",
        [
            {"source_id": "other_segment"},
            {"mars_version": "2.0.0"},
            {"run_seed": "different-run"},
        ],
    )
    def test_request_seed_changes_with_each_input(self, kwargs: dict) -> None:
        base = dict(
            source_id=SOURCE_ID,
            mars_version=MARS_VERSION,
            candidates=_candidates(*ABC),
            run_seed=RUN_SEED,
        )

        assert derive_request_seed(**base) != derive_request_seed(**{**base, **kwargs})

    # @spec MARS-008
    def test_judge_seed_derives_from_request_seed_and_identity(self) -> None:
        request_seed = _request_seed(_candidates(*ABC))

        assert derive_judge_seed(request_seed, "model_d") == derive_judge_seed(
            request_seed, "model_d"
        )
        assert derive_judge_seed(request_seed, "model_d") != derive_judge_seed(
            request_seed, "model_e"
        )

    # @spec MARS-008
    @pytest.mark.parametrize("variant", ["model_d", "MODEL_D", "  Model_D  "])
    def test_judge_identity_is_canonicalized(self, variant: str) -> None:
        """Case and surrounding whitespace must not fork one judge into several."""
        assert canonical_judge_identity(variant) == "model_d"

    # @spec MARS-008
    def test_canonicalized_identities_share_a_judge_seed(self) -> None:
        request_seed = _request_seed(_candidates(*ABC))

        assert derive_judge_seed(request_seed, "MODEL_D") == derive_judge_seed(
            request_seed, "model_d"
        )


class TestJudgePresentation:
    """MARS-007: per-judge aliases, per-judge order, no cross-judge correspondence."""

    def _present(self, judge: str, candidates=None) -> JudgePresentation:
        candidates = _candidates(*ABC) if candidates is None else candidates
        return build_judge_presentation(
            judge_id=judge, candidates=candidates, request_seed=_request_seed(candidates)
        )

    # @spec MARS-007, MARS-033
    def test_presentation_is_reproducible(self) -> None:
        first, second = self._present("model_d"), self._present("model_d")

        assert first.aliases == second.aliases
        assert first.order == second.order

    # @spec MARS-033
    def test_presentation_is_invariant_to_candidate_input_order(self) -> None:
        forward = self._present("model_d", _candidates(*ABC))
        shuffled = self._present("model_d", _candidates(ABC[2], ABC[0], ABC[1]))

        assert forward.aliases == shuffled.aliases
        assert forward.order == shuffled.order

    # @spec MARS-007
    def test_different_judges_get_independent_alias_maps(self) -> None:
        d, e = self._present("model_d"), self._present("model_e")

        assert d.aliases != e.aliases

    # @spec MARS-007
    def test_aliases_are_unique_within_one_presentation(self) -> None:
        presentation = self._present("model_d")

        assert len(set(presentation.aliases)) == len(presentation.aliases)

    # @spec MARS-007
    def test_every_candidate_is_presented_exactly_once(self) -> None:
        candidates = _candidates(*ABC)
        presentation = self._present("model_d", candidates)

        assert sorted(presentation.aliases.values()) == sorted(
            c.internal_id for c in candidates
        )

    # @spec MARS-007
    def test_aliases_resolve_back_to_internal_ids(self) -> None:
        candidates = _candidates(*ABC)
        presentation = self._present("model_d", candidates)

        for alias in presentation.order:
            assert presentation.resolve(alias) in {c.internal_id for c in candidates}

    # @spec MARS-007
    def test_unknown_alias_does_not_resolve(self) -> None:
        assert self._present("model_d").resolve("ZZZZ") is None

    # @spec MARS-007
    def test_alias_is_never_the_internal_id(self) -> None:
        candidates = _candidates(*ABC)
        presentation = self._present("model_d", candidates)
        internal_ids = {c.internal_id for c in candidates}

        assert internal_ids.isdisjoint(set(presentation.aliases))

    # @spec MARS-007
    def test_alias_does_not_encode_presentation_position(self) -> None:
        """Order and alias derive from separate hash material.

        If aliases were handed out in presentation order from a fixed sequence
        (C1, C2, C3...), sorting them would reproduce the order exactly. Six
        candidates make an accidental match a 1-in-720 coincidence rather than
        a plausible pass.
        """
        candidates = _candidates(*[(f"model_{i}", f"behavior {i}") for i in range(6)])
        presentation = self._present("model_d", candidates)

        assert len(presentation.order) == 6
        assert list(presentation.order) != sorted(presentation.aliases)


class TestNoInformationLeakage:
    """Nothing identifying a candidate's origin may reach a judge."""

    def _payload_text(self) -> str:
        candidates = _candidates(*ABC)
        presentation = build_judge_presentation(
            judge_id="model_d",
            candidates=candidates,
            request_seed=_request_seed(candidates),
        )
        return str(presentation.judge_payload())

    # @spec MARS-007, MARS-009
    def test_internal_candidate_id_never_reaches_the_judge(self) -> None:
        candidates = _candidates(*ABC)
        payload = self._payload_text()

        for candidate in candidates:
            assert candidate.internal_id not in payload

    # @spec MARS-007
    def test_generator_identity_never_reaches_the_judge(self) -> None:
        payload = self._payload_text()

        for model in ("model_a", "model_b", "model_c"):
            assert model not in payload

    # @spec MARS-007
    def test_generator_confidence_never_reaches_the_judge(self) -> None:
        candidates = build_candidates(
            [
                _result("model_a", "A", confidence=0.11),
                _result("model_b", "B", confidence=0.99),
            ]
        )
        presentation = build_judge_presentation(
            judge_id="model_d",
            candidates=candidates,
            request_seed=_request_seed(candidates),
        )
        payload = str(presentation.judge_payload())

        assert "0.11" not in payload
        assert "0.99" not in payload
        assert "confidence" not in payload

    # @spec MARS-007
    def test_payload_carries_only_aliases_and_extracted_content(self) -> None:
        candidates = _candidates(*ABC)
        presentation = build_judge_presentation(
            judge_id="model_d",
            candidates=candidates,
            request_seed=_request_seed(candidates),
        )

        payload = presentation.judge_payload()

        assert [entry["alias"] for entry in payload] == list(presentation.order)
        for entry in payload:
            assert set(entry) == {"alias", "fields"}
            assert "confidence" not in entry["fields"]


class TestPresentationBoundaryInvariant:
    """What a judge sees is normalized, and anything reading it must know.

    A fake judge that assumed display values retained original casing silently
    produced empty rankings, which surfaced as `unparseable` responses rather
    than as an obvious wiring error. Pinning the invariant here means the next
    judge implementation — fake or real — fails against a named expectation
    instead of a confusing symptom.
    """

    def _presentation(self):
        candidates = _candidates(("model_a", "Child Pointed"), ("model_b", "Child SPOKE"))
        return build_judge_presentation(
            judge_id="model_d",
            candidates=candidates,
            request_seed=_request_seed(candidates),
        )

    # @spec MARS-007
    def test_presented_values_are_normalized_not_verbatim(self) -> None:
        behaviors = {
            entry["fields"]["behavior"] for entry in self._presentation().judge_payload()
        }

        assert behaviors == {"child pointed", "child spoke"}

    # @spec MARS-007
    def test_presented_fields_match_the_dedup_normalization(self) -> None:
        """One normalization, so identity means the same thing on both sides."""
        from src.backend.ml.extraction.mars.candidates import normalize_value

        for entry in self._presentation().judge_payload():
            for value in entry["fields"].values():
                assert value == normalize_value(value)

    # @spec MARS-007
    def test_presented_fields_carry_only_extracted_content(self) -> None:
        from src.backend.ml.extraction.mars.candidates import FINGERPRINT_FIELDS

        for entry in self._presentation().judge_payload():
            assert set(entry["fields"]) == set(FINGERPRINT_FIELDS)
