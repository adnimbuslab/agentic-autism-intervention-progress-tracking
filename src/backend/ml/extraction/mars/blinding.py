"""Derived seeds and per-judge blinding.

What MARS guarantees here is **deterministic orchestration replay**: the same
source, candidate set, configuration, MARS version and run seed reproduce the
same aliases, the same presentation order, and the same seeds. It is not a
claim that a judge returns the same ranking twice -- that depends on whether
the inference backend is itself deterministic, which MARS does not control.

Seeds are *derived* rather than drawn. Recording a randomly drawn seed only
reproduces a run if the record survives; deriving it makes identical inputs
reproduce identical presentations by construction.
"""

from __future__ import annotations

import hashlib
from typing import Any

from pydantic import BaseModel, Field

from src.backend.ml.extraction.mars.candidates import (
    FINGERPRINT_FIELDS,
    MarsCandidate,
    normalize_value,
)

_ALIAS_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no look-alike 0/O, 1/I
_ALIAS_LENGTH = 4


def _digest(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def canonical_judge_identity(judge_id: str) -> str:
    """Fold textual variants of one judge identity together.

    Case and surrounding whitespace only. Vendor-prefix folding (treating
    ``ollama/llama3.2`` as ``llama3.2``) is deliberately *not* done here: it is
    a semantic claim about which strings name the same model, and getting it
    wrong in either direction is a safety problem -- over-folding would merge
    two genuinely different models, under-folding would let one model judge its
    own output past MARS-027. It stays an explicit roster decision.
    """
    return " ".join(judge_id.split()).casefold()


# @spec MARS-008
def candidate_set_fingerprint(candidates: list[MarsCandidate]) -> str:
    """Identify the set of alternatives being judged, independent of ordering.

    Built from sorted internal ids, so provider responses arriving in a
    different order -- which is normal for concurrent calls -- cannot change
    the presentation. Because internal ids are content-derived, the fingerprint
    is also independent of generator identity and generator confidence: it
    describes *what* is being judged, not who produced it. Provenance already
    affects judge eligibility (MARS-027) separately, and letting it also move
    the seed would reshuffle a presentation for a candidate set that never
    changed.
    """
    return _digest(*sorted(candidate.internal_id for candidate in candidates))


# @spec MARS-008
def derive_request_seed(
    *,
    source_id: str,
    mars_version: str,
    candidates: list[MarsCandidate],
    run_seed: str,
) -> str:
    """Seed for one MARS request.

    ``run_seed`` varies deliberately across experimental arms and stays fixed
    in production.
    """
    return _digest(
        "mars.request",
        source_id,
        mars_version,
        candidate_set_fingerprint(candidates),
        run_seed,
    )


# @spec MARS-008
def derive_judge_seed(request_seed: str, judge_id: str) -> str:
    """Seed for one judge's presentation within a request."""
    return _digest("mars.judge", request_seed, canonical_judge_identity(judge_id))


def _alias_from(material: str, length: int) -> str:
    value = int(material, 16)
    out: list[str] = []
    for _ in range(length):
        value, index = divmod(value, len(_ALIAS_ALPHABET))
        out.append(_ALIAS_ALPHABET[index])
    return "".join(out)


class JudgePresentation(BaseModel):
    """What one judge sees, and how to read its answer back.

    ``aliases`` maps the judge-visible alias to the internal candidate id.
    ``order`` is the sequence the candidates are presented in. The two derive
    from separate hash material, so an alias carries no information about the
    position its candidate occupies.
    """

    judge_id: str
    judge_seed: str
    aliases: dict[str, str] = Field(default_factory=dict)
    order: list[str] = Field(default_factory=list)
    # Normalized extracted content per alias -- exactly what the judge sees, so
    # holding it on the model leaks nothing that judge_payload() would not.
    presented_fields: dict[str, dict[str, Any]] = Field(default_factory=dict)

    def resolve(self, alias: str) -> str | None:
        """Map a judge-supplied alias back to an internal candidate id."""
        return self.aliases.get(alias)

    def judge_payload(self) -> list[dict[str, Any]]:
        """Exactly what may be sent to the judge.

        Aliases and normalized extracted content, nothing else. Internal ids,
        generator identity, generator confidence, control confidence and
        multiplicity are all withheld -- each would let a judge prefer a
        candidate for a reason other than the evidence.
        """
        return [
            {"alias": alias, "fields": self.presented_fields.get(alias, {})}
            for alias in self.order
        ]


# @spec MARS-007, MARS-008, MARS-033
def build_judge_presentation(
    *,
    judge_id: str,
    candidates: list[MarsCandidate],
    request_seed: str,
) -> JudgePresentation:
    """Assign this judge its own aliases and presentation order.

    Alias and order derive from separate material under the same judge seed, so
    presentation order is independent of alias assignment. Ordering by a hash
    rather than by input position is what turns each judge's position bias into
    noise that fusion averages out; a fixed order shared by all judges would
    let their biases align and be amplified instead.
    """
    judge_seed = derive_judge_seed(request_seed, judge_id)

    entries: list[tuple[str, str, str]] = []
    for candidate in candidates:
        order_material = _digest(judge_seed, candidate.internal_id, "order")
        alias_material = _digest(judge_seed, candidate.internal_id, "alias")
        entries.append((order_material, alias_material, candidate.internal_id))
    entries.sort()

    aliases: dict[str, str] = {}
    order: list[str] = []
    fields: dict[str, dict[str, Any]] = {}
    by_internal_id = {candidate.internal_id: candidate for candidate in candidates}

    for _, alias_material, internal_id in entries:
        # Lengthen on collision rather than perturbing the material, so the
        # assignment stays a pure function of the seed and the candidate.
        length = _ALIAS_LENGTH
        alias = _alias_from(alias_material, length)
        while alias in aliases:
            length += 1
            alias = _alias_from(alias_material, length)

        aliases[alias] = internal_id
        order.append(alias)
        observation = by_internal_id[internal_id].observation
        fields[alias] = {
            name: normalize_value(getattr(observation, name, None))
            for name in FINGERPRINT_FIELDS
        }

    return JudgePresentation(
        judge_id=canonical_judge_identity(judge_id),
        judge_seed=judge_seed,
        aliases=aliases,
        order=order,
        presented_fields=fields,
    )
