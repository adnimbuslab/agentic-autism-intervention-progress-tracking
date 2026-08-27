---
parent: high-level-design
---

# Abstention Router (real-time)

*Brownfield LLD — reverse-engineered from `src/backend/ml/abstention_router.py`. Decisions marked `[inferred]` were observed in code, not confirmed by the author.*

## Context and Design Philosophy

**Naming note:** the HLD's System Design lists a single "Adequacy/Abstention Router" box in the AI/ML layer. The implementation is actually **two distinct components** operating at two different granularities: this `AbstentionRouter` (per-observation, real-time, inside the ingestion LangGraph) and the batch [Adequacy Router](./Adequacy_Router.md) (per-review-period, operating over many already-persisted records for analytics eligibility). They share a family resemblance — both can produce an abstention outcome — but they answer different questions ("is *this* observation usable?" vs. "is *this period's evidence base* sufficient for analytics?") and have no code-level dependency in one direction (only `AnalyticsEngine` reads `AdequacyResult`; nothing reads `AbstentionRouter`'s output except the ingestion graph). Treating them as one box in the HLD diagram undersells that split — see `docs/High_Level_Design.md` for the corrected diagram.

This component is the final routing gate of the real-time ingestion pipeline: `extract_node → validate_node → route_node`, combining the extraction provider's own status with the Deterministic Validation Engine's routing decision, and generating the focused clarification questions CLAUDE.md calls for ("non-leading clarification questions").

## Interface Contract

```text
AbstentionRouter.route(extraction: ExtractionResult, validation: ValidationResult) -> RoutingDecision
AbstentionRouter.generate_clarification_questions(observation, validation) -> list[str]
```

## Routing Logic (exact order — first match wins)

1. `extraction.status == FAILED` → **REJECT** (overrides everything else).
2. `validation.routing == REJECT` → **REJECT**.
3. `validation.routing == CLARIFY` → stays `CLARIFY` if `_has_recoverable_fields()` finds a failed/null field with a question template; if not recoverable, the code falls through to `return validation.routing`, which is still `CLARIFY` — see Open Questions, this branch has no distinct effect today.
4. `extraction.status == PARTIAL` and the extraction itself produced `clarification_questions`, and `validation.routing` is `RETAIN_WITH_UNKNOWN` or `INTERVENTIONIST_REVIEW` → upgraded to **CLARIFY**.
5. Otherwise → passthrough `validation.routing` unchanged.

`route_edge` (in `observation_workflow.py`) maps the resulting `RoutingDecision` to a graph node name (`accept` / `clarify` / `retain` / `review` / `reject`); an unmapped or unrecognized decision value defaults to `"reject"` — the graph is fail-closed by construction.

## Clarification Question Generation

- `_MAX_CLARIFICATION_QUESTIONS = 3`.
- `_QUESTION_TEMPLATES` covers 7 fields: `behavior, domain, modality, prompt_level, outcome, goal_context, prompt_context` — each with fixed, non-leading question text.
- Candidate order: critical fields first (`behavior`, `domain`), then the remaining 5 in a fixed order.
- Deduplicated via a `seen` set; generation stops once 3 questions are collected.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Extraction failure overrides validation entirely | `extraction.status == FAILED` short-circuits to REJECT before validation's routing is even consulted | Let validation's routing stand even on a failed extraction | `[inferred]` A failed extraction has no trustworthy structured content to validate against — validation's routing would be evaluating garbage |
| Fixed question bank vs. generated questions | Static `_QUESTION_TEMPLATES` per field, capped at 3 | LLM-generated follow-up questions tailored to the specific observation | `[inferred]` Matches CLAUDE.md's "non-leading clarification questions" principle directly — a fixed, reviewed template bank cannot leak leading or suggestive phrasing the way a generated question could |
| Cap of 3 questions | Hard-coded `_MAX_CLARIFICATION_QUESTIONS = 3` | Uncapped, or a cap proportional to number of missing fields | `[inferred]` Bounds contributor burden per turn; a bank of 7 possible templates could otherwise ask a long chain of questions in one exchange |

## Open Questions & Future Decisions

### Deferred
1. **Non-recoverable CLARIFY branch has no distinct effect.** When `validation.routing == CLARIFY` and `_has_recoverable_fields()` returns false, the code still returns `CLARIFY` — the same as the recoverable case. Confirm whether a non-recoverable `CLARIFY` should downgrade to `INTERVENTIONIST_REVIEW` (nothing left to usefully ask the contributor) or whether always asking is intended even when no template matches.
2. Rename this component (in the HLD diagram and any future code comments) to disambiguate from the batch Adequacy Router, since both currently read as "the abstention/adequacy thing" from the box label alone.

## References

- `src/backend/ml/abstention_router.py`.
- `src/backend/services/observation_workflow.py` — `route_node`, `route_edge`.
- [Adequacy_Router.md](./Adequacy_Router.md) — the batch-level sibling this component is often conflated with.
- `docs/High_Level_Design.md` § Key Design Principles ("non-leading clarification questions").
- Tests: `tests/unit/test_abstention_router.py`, `tests/eval/test_abstention.py`, `tests/eval/test_clarification.py`, `tests/eval/test_routing_decisions.py`.
