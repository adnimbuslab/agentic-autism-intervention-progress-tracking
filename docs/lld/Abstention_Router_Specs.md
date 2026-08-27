# Abstention Router (real-time) — EARS Specs

Owning design: [Abstention_Router.md](./Abstention_Router.md). Prefix: `ABSTAIN`.

Do not confuse with `ADEQ` ([Adequacy_Router_Specs.md](./Adequacy_Router_Specs.md)) — that is the batch, per-review-period sibling.

All specs below are `[x]` — implemented, covered by `tests/unit/test_abstention_router.py`, `tests/eval/test_abstention.py`, `tests/eval/test_clarification.py`, `tests/eval/test_routing_decisions.py`.

## Routing Logic (priority order — first match wins)

- [x] **ABSTAIN-001**: If `ExtractionResult.status` is `FAILED`, then the system shall return routing decision `REJECT`, regardless of the `ValidationResult`'s routing.
- [x] **ABSTAIN-002**: If `ValidationResult.routing` is `REJECT`, then the system shall return routing decision `REJECT`, unless ABSTAIN-001 already applies.
- [x] **ABSTAIN-003**: While `ValidationResult.routing` is `CLARIFY`, the system shall return routing decision `CLARIFY`, unless ABSTAIN-001 or ABSTAIN-002 already applies.
- [x] **ABSTAIN-004**: When `ExtractionResult.status` is `PARTIAL` and the extraction produced its own `clarification_questions`, and `ValidationResult.routing` is `RETAIN_WITH_UNKNOWN` or `INTERVENTIONIST_REVIEW`, the system shall upgrade the routing decision to `CLARIFY`, unless ABSTAIN-001, ABSTAIN-002, or ABSTAIN-003 already applies.
- [x] **ABSTAIN-005**: Where none of ABSTAIN-001 through ABSTAIN-004 apply, the system shall return `ValidationResult.routing` unchanged.
- [x] **ABSTAIN-006**: When `ExtractionResult.status` is `ABSTAINED`, the system shall not force a `REJECT` override on that basis alone; the routing decision shall instead follow ABSTAIN-002 through ABSTAIN-005, the same as for a `SUCCESS` or `PARTIAL` extraction. An abstained extraction that nonetheless has `behavior` and `domain` present is expected to reach `ValidationEngine.validate()` and be routed on the merits of that validation, not force-rejected for having abstained.

## Clarification Question Generation

- [x] **ABSTAIN-010**: The system shall generate no more than 3 clarification questions per routing decision.
- [x] **ABSTAIN-011**: When generating clarification questions, the system shall order candidate fields with `behavior` and `domain` first, followed by `modality`, `prompt_level`, `outcome`, `goal_context`, and `prompt_context` in that fixed order.
- [x] **ABSTAIN-012**: The system shall not generate more than one clarification question for the same field within a single routing decision.
- [x] **ABSTAIN-013**: Each generated clarification question shall use a fixed, non-leading question template for its field; the system shall not generate a question dynamically from the observation's content.

## Downstream Fail-Closed Routing (workflow integration)

- [x] **ABSTAIN-020**: If the routing decision returned by the Abstention Router does not map to a known node in the ingestion workflow's routing edge (`observation_workflow.py`'s `route_edge`), then the system shall route the observation to the reject path.

## References

- [Abstention_Router.md](./Abstention_Router.md) — full design, decisions, and the open question on the non-recoverable `CLARIFY` branch having no distinct effect today (ABSTAIN-003 as currently specified reflects that: it does not distinguish recoverable from non-recoverable CLARIFY).
