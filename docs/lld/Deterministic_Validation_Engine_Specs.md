# Deterministic Validation Engine — EARS Specs

Owning design: [Deterministic_Validation_Engine.md](./Deterministic_Validation_Engine.md). Prefix: `VALID`.

Scope note: these specs describe `ValidationEngine.validate()` itself. The zero-observations short-circuit performed by `observation_workflow.py`'s `validate_node` *before* calling this engine belongs to the (not yet documented) Observation Orchestrator component, not here.

All specs below are `[x]` — implemented, covered by `tests/unit/test_validation_engine.py`, `tests/eval/test_cross_field_logic.py`, `tests/eval/test_routing_decisions.py`, `tests/eval/test_unsupported_fields.py`.

## Invariant

- [x] **VALID-001**: The system shall determine `ValidationResult` using deterministic rule evaluation only, without invoking any LLM.

## Routing Decision (priority order — first match wins)

- [x] **VALID-010**: If both `behavior` and `domain` are missing from the observation, then the system shall set the routing decision to `REJECT`.
- [x] **VALID-011**: If any field validation carries `ERROR` severity, or `confidence` is less than 0.4, then the system shall set the routing decision to `INTERVENTIONIST_REVIEW`, unless VALID-010 already applies.
- [x] **VALID-012**: If exactly one of `behavior`/`domain` is missing, or more than one field validation carries `WARNING` severity, then the system shall set the routing decision to `CLARIFY`, unless VALID-010 or VALID-011 already applies.
- [x] **VALID-013**: If an important field (`modality`, `prompt_level`, or `outcome`) is missing, or `confidence` is less than 0.7, then the system shall set the routing decision to `RETAIN_WITH_UNKNOWN`, unless VALID-010, VALID-011, or VALID-012 already applies.
- [x] **VALID-014**: Where none of VALID-010 through VALID-013 apply, the system shall set the routing decision to `ACCEPT`.

## Cross-Field Consistency Checks

- [x] **VALID-020**: When `modality` is `VERBAL` and `behavior` is present but contains none of the approved verbal keywords (`said`, `say`, `spoke`, `told`, `word`, `utterance`, `verbal`, `vocali…`, etc.), the system shall record a `WARNING`-severity field validation.
- [x] **VALID-021**: When `prompt_level` is `INDEPENDENT` and `prompt_context` is not null, the system shall record a `WARNING`-severity field validation.
- [x] **VALID-022**: If `outcome` is present but `behavior` is null, then the system shall record an `ERROR`-severity field validation.
- [x] **VALID-023**: When the observation's `goal_context` does not match any goal ID in the supplied `goal_ids`, the system shall record a `WARNING`-severity (not `ERROR`) field validation.
- [x] **VALID-024**: If `confidence` falls outside the range `[0, 1]`, then the system shall record a field validation failure for `confidence`.

## References

- [Deterministic_Validation_Engine.md](./Deterministic_Validation_Engine.md) — full design, decisions, and the `ValidationSeverity.INFO` open question (defined but never produced — no spec covers it, by design, until it is).
