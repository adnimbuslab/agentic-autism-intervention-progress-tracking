# Abstention Router (real-time) — EARS Specs

Owning design: [Abstention_Router.md](./Abstention_Router.md). Prefix: `ABSTAIN`.

Do not confuse with `ADEQ` ([Adequacy_Router_Specs.md](./Adequacy_Router_Specs.md)) — that is the batch, per-review-period sibling.

Test citations below reflect an actual `@spec`-annotation pass. `[x]` = annotated test exists and passes; `[ ]` = no test currently cites this spec, though the underlying code already implements it.

## Routing Logic (priority order — first match wins)

- [x] **ABSTAIN-001**: If `ExtractionResult.status` is `FAILED`, then the system shall return routing decision `REJECT`, regardless of the `ValidationResult`'s routing. — `tests/unit/test_abstention_router.py::test_failed_extraction_rejects`
- [x] **ABSTAIN-002**: If `ValidationResult.routing` is `REJECT`, then the system shall return routing decision `REJECT`, unless ABSTAIN-001 already applies. — `test_validation_reject_preserved`
- [x] **ABSTAIN-003**: While `ValidationResult.routing` is `CLARIFY`, the system shall return routing decision `CLARIFY`, unless ABSTAIN-001 or ABSTAIN-002 already applies. — `test_clarify_with_recoverable_fields`, `test_clarify_without_observations_falls_back`
- [x] **ABSTAIN-004**: When `ExtractionResult.status` is `PARTIAL` and the extraction produced its own `clarification_questions`, and `ValidationResult.routing` is `RETAIN_WITH_UNKNOWN` or `INTERVENTIONIST_REVIEW`, the system shall upgrade the routing decision to `CLARIFY`, unless ABSTAIN-001, ABSTAIN-002, or ABSTAIN-003 already applies. — `tests/phase6/integration/test_extraction_pipeline_e2e.py::test_partial_routes_clarify`
- [x] **ABSTAIN-005**: Where none of ABSTAIN-001 through ABSTAIN-004 apply, the system shall return `ValidationResult.routing` unchanged. — `test_accept_passes_through`, `test_retain_passes_through`, `test_interventionist_review_passes_through`
- [x] **ABSTAIN-006**: When `ExtractionResult.status` is `ABSTAINED`, the system shall not force a `REJECT` override on that basis alone; the routing decision shall instead follow ABSTAIN-002 through ABSTAIN-005, the same as for a `SUCCESS` or `PARTIAL` extraction. An abstained extraction that nonetheless has `behavior` and `domain` present is expected to reach `ValidationEngine.validate()` and be routed on the merits of that validation, not force-rejected for having abstained. — `test_abstention_router.py::TestRouting::test_abstained_status_does_not_force_reject`

## Clarification Question Generation

- [x] **ABSTAIN-010**: The system shall generate no more than 3 clarification questions per routing decision. — `test_max_three_questions`
- [x] **ABSTAIN-011**: When generating clarification questions, the system shall order candidate fields with `behavior` and `domain` first, followed by `modality`, `prompt_level`, `outcome`, `goal_context`, and `prompt_context` in that fixed order. — `test_critical_fields_first`
- [ ] **ABSTAIN-012**: The system shall not generate more than one clarification question for the same field within a single routing decision. — the `seen`-set dedup path is structurally unreachable with current test fixtures: no test supplies duplicate `FieldValidation` entries for the same field name to force the branch; behavior is implemented, coverage gap only.
- [x] **ABSTAIN-013**: Each generated clarification question shall use a fixed, non-leading question template for its field; the system shall not generate a question dynamically from the observation's content. — `test_questions_not_leading`

## Downstream Fail-Closed Routing (workflow integration)

- [x] **ABSTAIN-020**: If the routing decision returned by the Abstention Router does not map to a known node in the ingestion workflow's routing edge (`observation_workflow.py`'s `route_edge`), then the system shall route the observation to the reject path. — `tests/phase3/test_observation_workflow.py::TestRouteEdge::test_unknown_defaults_to_reject`

## References

- [Abstention_Router.md](./Abstention_Router.md) — full design, decisions, and the open question on the non-recoverable `CLARIFY` branch having no distinct effect today (ABSTAIN-003 as currently specified reflects that: it does not distinguish recoverable from non-recoverable CLARIFY).
