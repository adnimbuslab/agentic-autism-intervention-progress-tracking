# Deterministic Validation Engine — EARS Specs

Owning design: [Deterministic_Validation_Engine.md](./Deterministic_Validation_Engine.md). Prefix: `VALID`.

Scope note: these specs describe `ValidationEngine.validate()` itself. The zero-observations short-circuit performed by `observation_workflow.py`'s `validate_node` *before* calling this engine belongs to the (not yet documented) Observation Orchestrator component, not here.

Test citations below reflect an actual `@spec`-annotation pass. `[x]` = annotated test exists and passes; `[D]` = correct intent, not achievable/needed given an upstream guarantee.

## Invariant

- [x] **VALID-001**: The system shall determine `ValidationResult` using deterministic rule evaluation only, without invoking any LLM. — `tests/unit/test_validation_engine.py::TestDeterminism::test_same_input_same_output`

## Routing Decision (priority order — first match wins)

- [x] **VALID-010**: If both `behavior` and `domain` are missing from the observation, then the system shall set the routing decision to `REJECT`. — `test_validation_engine.py::TestValidationRouting::test_all_critical_missing_rejects`
- [x] **VALID-011**: If any field validation carries `ERROR` severity, or `confidence` is less than 0.4, then the system shall set the routing decision to `INTERVENTIONIST_REVIEW`, unless VALID-010 already applies. — `test_one_critical_missing_routes_to_review`, `test_domain_missing_routes_to_review`, `test_low_confidence_routes_to_review`
- [x] **VALID-012**: If exactly one of `behavior`/`domain` is missing, or more than one field validation carries `WARNING` severity, then the system shall set the routing decision to `CLARIFY`, unless VALID-010 or VALID-011 already applies. — `tests/eval/validation/test_routing_decisions.py::TestRoutingDecisions::test_two_warnings_trigger_clarify`
- [x] **VALID-013**: If an important field (`modality`, `prompt_level`, or `outcome`) is missing, or `confidence` is less than 0.7, then the system shall set the routing decision to `RETAIN_WITH_UNKNOWN`, unless VALID-010, VALID-011, or VALID-012 already applies. — `test_medium_confidence_retains`, `test_important_fields_missing_retains`
- [x] **VALID-014**: Where none of VALID-010 through VALID-013 apply, the system shall set the routing decision to `ACCEPT`. — `test_valid_observation_accepts`

## Cross-Field Consistency Checks

- [x] **VALID-020**: When `modality` is `VERBAL` and `behavior` is present but contains none of the approved verbal keywords (`said`, `say`, `spoke`, `told`, `word`, `utterance`, `verbal`, `vocali…`, etc.), the system shall record a `WARNING`-severity field validation. — `tests/eval/validation/test_cross_field_logic.py::test_verbal_modality_without_speech_words_warns`
- [x] **VALID-021**: When `prompt_level` is `INDEPENDENT` and `prompt_context` is not null, the system shall record a `WARNING`-severity field validation. — `test_independent_prompt_with_context_warns`
- [x] **VALID-022**: If `outcome` is present but `behavior` is null, then the system shall record an `ERROR`-severity field validation. — `test_outcome_present_behavior_missing_errors`
- [x] **VALID-023**: When the observation's `goal_context` does not match any goal ID in the supplied `goal_ids`, the system shall record a `WARNING`-severity (not `ERROR`) field validation. — `test_validation_engine.py::TestGoalValidation::test_invalid_goal_context_warning`
- [D] **VALID-024**: If `confidence` falls outside the range `[0, 1]`, then the system shall record a field validation failure for `confidence`. — `StructuredObservation.confidence` already enforces `ge=0.0, le=1.0` via Pydantic at construction, so this branch is unreachable through any normal path; no test bypasses Pydantic (e.g. `model_construct`) to reach it, and none should be written solely to exercise a defensive branch Pydantic already forecloses.

## References

- [Deterministic_Validation_Engine.md](./Deterministic_Validation_Engine.md) — full design, decisions, and the `ValidationSeverity.INFO` open question (defined but never produced — no spec covers it, by design, until it is).
