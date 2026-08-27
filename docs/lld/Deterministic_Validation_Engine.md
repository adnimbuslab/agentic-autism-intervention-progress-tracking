---
parent: high-level-design
prefix: VALID
---

# Deterministic Validation Engine

*Brownfield LLD — reverse-engineered from `src/backend/ml/validation_engine.py`. Decisions marked `[inferred]` were observed in code, not confirmed by the author.*

## Context and Design Philosophy

The module docstring states its own invariant plainly: **no LLM involvement.** This is the component that gives the extraction provider's output deterministic, reproducible authority-checking before anything can be accepted, retained, or persisted. It sits immediately after the extraction provider in the real-time ingestion pipeline (`extract_node → validate_node → route_node` in `observation_workflow.py`) and is the concrete implementation of CLAUDE.md's "LLM outputs pass through deterministic validation before persistence."

Validation operates on **one `StructuredObservation` at a time** — it has no knowledge of the child's history or other observations. Longitudinal sufficiency is a separate concern owned by the [Adequacy Router](./Adequacy_Router.md).

## Interface Contract

```text
ValidationEngine.validate(
    observation: StructuredObservation,
    goal_ids: list[str] | None = None,
) -> ValidationResult
```

`ValidationResult`: `is_valid`, `routing: RoutingDecision`, `field_validations: list[FieldValidation]`, `clarification_questions`, `messages`.

`FieldValidation`: `field_name`, `is_valid`, `severity` (`ERROR` | `WARNING` | `INFO`), `message`.

## Checks (run in order)

1. **Enum membership** — extracted categorical fields must be members of their approved taxonomy.
2. **Critical-field presence** — `behavior` and `domain` (`_CRITICAL_FIELDS`).
3. **Cross-field consistency** (exact rules):
   - `modality == VERBAL` and `behavior` set, but none of ~15 `_VERBAL_KEYWORDS` (`said`, `say`, `spoke`, `told`, `word`, `utterance`, `verbal`, `vocali…`, etc.) appears in `behavior.lower()` → `WARNING`.
   - `prompt_level == INDEPENDENT` and `prompt_context` is not `None` → `WARNING` ("prompt context present but level is independent").
   - `outcome` set but `behavior` is `None` → `ERROR`.
4. **Goal-context membership** — `goal_context` should be among the supplied `goal_ids`; a mismatch is a `WARNING`, not an `ERROR` (see Decisions).
5. **Confidence range** — must fall in `[0, 1]`.
6. **Completeness count** — over `LLM_EXTRACTED_FIELDS`, feeding the routing decision below.

`_CRITICAL_FIELDS = {behavior, domain}`; `_IMPORTANT_FIELDS = {modality, prompt_level, outcome}`; `_CONFIDENCE_THRESHOLD = 0.7`; `_LOW_CONFIDENCE_THRESHOLD = 0.4`.

## Routing Decision Tree (`_determine_routing`, exact order — first match wins)

1. Both critical fields (`behavior` and `domain`) missing → **REJECT**.
2. Any `ERROR`-severity failure, OR `confidence < 0.4` → **INTERVENTIONIST_REVIEW**.
3. Exactly one critical field missing, OR more than one `WARNING` → **CLARIFY**.
4. Any important field (`modality` / `prompt_level` / `outcome`) missing → **RETAIN_WITH_UNKNOWN**.
5. `confidence < 0.7` → **RETAIN_WITH_UNKNOWN**.
6. Otherwise → **ACCEPT**.

`route_node` in `observation_workflow.py` treats an extraction that produced zero observations as a special case *before* this engine runs at all: it synthesizes `ValidationResult(is_valid=False, routing=REJECT, messages=["No observations extracted"])` directly, so `ValidationEngine.validate()` never receives an empty observation.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| LLM involvement in validation | None — pure Python rule evaluation | An LLM-based "self-check" pass over its own extraction | `[inferred]` A rule engine's output is reproducible and auditable in a way a second LLM call cannot guarantee; matches the HLD tenet that deterministic code is the final authority over model output |
| Goal-context mismatch severity | `WARNING`, not `ERROR` | Treat any goal mismatch as a hard error requiring review | `[inferred]` Deliberately permissive — goal linkage may not always be extractable with certainty from free text, so an ERROR here would over-trigger review for a genuinely ambiguous (not wrong) case |
| Routing is a strict priority ladder rather than a scored/weighted combination | First-match-wins ordered checks | Weighted scoring across all checks combined into one confidence-like number | `[inferred]` A priority ladder makes the "why did this route to X" question answerable by reading one ordered list, rather than reverse-engineering a weighted formula |

## Open Questions & Future Decisions

### Deferred
1. `ValidationSeverity.INFO` is defined in `schemas.py` but never produced anywhere in this engine — confirm whether it's reserved for a future check or should be removed.

## References

- `src/backend/ml/validation_engine.py`, `src/backend/ml/schemas.py`.
- `src/backend/services/observation_workflow.py` — `validate_node`.
- `docs/High_Level_Design.md` § Tenets ("Deterministic code is the final authority over model output, always").
- Tests: `tests/unit/test_validation_engine.py`, `tests/phase3/test_observation_workflow.py`, `tests/eval/test_cross_field_logic.py`, `tests/eval/test_routing_decisions.py`, `tests/eval/test_unsupported_fields.py`.
