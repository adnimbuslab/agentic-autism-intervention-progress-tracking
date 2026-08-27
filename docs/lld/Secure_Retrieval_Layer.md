---
parent: high-level-design
---

# Secure Retrieval Layer (Planned)

**Status: not yet implemented.** This is a forward design for the role/child/goal-scoped retrieval layer specified in `CLAUDE_PROJECT_HANDOFF.md` §8. It is written now, ahead of code, because the current-phase decision (handoff §24) is to finalize schema and ground-truth methodology first; when that work lands, this LLD is the design this layer implements against — it should not need to be rediscovered.

## Context and Design Philosophy

The current system already scopes access at the authorization layer: `authorize_child_access` and `get_authorized_children` (`src/backend/api/deps.py`) resolve, per request, which children a user may act on via `ActorAssignment` rows and `Role`. That check happens once, per API call, against relational data — it has no retrieval or ranking component because there is nothing to rank yet.

The Secure Retrieval Layer extends this same authorization primitive to a new situation: supplying an LLM (the observation-guidance conversation, or a future extraction/reporting step) with *relevant permitted context* rather than the full permitted record set. The design philosophy carries over unchanged from the rest of the system — **the LLM never decides what it is allowed to see; authorization is resolved in code before anything reaches a prompt.** This LLD's only new concern is: given an already-authorized (org, user, role, child, goal) tuple, what is the least amount of relevant content to retrieve, and how is it kept from leaking un-permitted material through the retrieval index itself.

## Scope: Three Retrieval Use Cases

Per handoff §8, this layer serves three distinct callers, each with its own query shape and consumer:

| Use case | Queried by | Retrieves | Feeds |
|---|---|---|---|
| Observation Guidance RAG | Contributor conversation turn | Active goal definition, interventionist guidance, permitted recent observations for that child+goal | The clarification-question generator in the observation orchestrator |
| Extraction RAG | `ExtractionProvider.extract()` call | Schema/field definitions, approved prompt-type taxonomy, curated few-shot examples, active goal context | The extraction provider's prompt construction (both `TemporaryLLMExtractionProvider` and, later, `FineTunedExtractionProvider`) |
| Explanation RAG | Reporting LLM | The specific source observations underlying a given analytics/trajectory figure | The grounded-explanation prompt, so every claim cites real evidence |

These share one authorization-and-index mechanism but are separate query paths — a guidance query must never leak into an extraction query's context and vice versa, since each has a different permitted-document-type scope (see below).

## Authorization-Before-Retrieval Contract

Every retrieval call takes an already-resolved authorization tuple, not raw user input:

```text
RetrievalRequest:
  organization_id: UUID
  user_id: UUID
  role: Role
  authorized_child_ids: set[UUID]   # from get_authorized_children(), not re-derived here
  goal_id: UUID | None              # None only for use cases with no active goal yet
  permitted_document_types: set[DocumentType]
  use_case: Literal["guidance", "extraction", "explanation"]
```

The retrieval layer's own query is then a straightforward filter, never a policy decision:

```text
WHERE organization_id = request.organization_id
  AND child_id IN request.authorized_child_ids
  AND (goal_id = request.goal_id OR request.goal_id IS NULL)
  AND document_type IN request.permitted_document_types
```

**The retrieval layer must reject a request that does not carry a pre-resolved `authorized_child_ids`/`role` tuple.** It has no path to compute authorization itself — that would duplicate (and risk diverging from) `authorize_child_access`/`get_authorized_children`, which remain the single source of truth for who may see what.

## Storage Separation

Two stores, matching handoff §8's recommended separation:

- **Authoritative Data Store** — the existing Observation Store and Structured Record Store (encrypted, direct identifiers present, already implemented). Retrieval never reads from here directly; it reads only from the index below and, on a cache miss, re-fetches the specific authoritative record by ID through the normal authorized data-access path.
- **Retrieval Index** — a new pseudonymized, minimized index built for vector search:

```text
RetrievalIndexRecord:
  pseudonymous_child_id: str   # not the raw child_id
  goal_id: UUID
  observation_id: UUID         # pointer back to the authoritative store, not the content itself
  document_type: DocumentType
  embedding: vector
  permitted_role_metadata: set[Role]
```

Direct identifiers (child name, contributor name, free-text PII beyond what's needed to embed the clinical content) are not embedded. The index is a pointer-plus-embedding structure; the authoritative content it points to is fetched through existing authorized read paths, not duplicated into the vector store.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Where authorization is resolved | Retrieval layer accepts a pre-resolved tuple from the existing `deps.py` authorization functions; it does not re-implement role/child checks | Have the retrieval layer independently query `ActorAssignment`/`Role` | Two independent implementations of "who can see this child's data" will drift; the existing authorization code is already tested and is the system's single source of truth |
| Index content | Pseudonymized pointer + embedding, content fetched from the authoritative store on demand | Embed and store full observation text directly in the vector index for lower query latency | Handoff §8 explicitly recommends minimizing what's in the retrieval index; a pointer-based index means a compromised vector store leaks far less |
| Query path separation | Three distinct query paths (guidance/extraction/explanation) sharing one authorization+index mechanism, not one general-purpose retrieval endpoint | Single generic `/retrieve` call parameterized by use case | Each use case has a different permitted-document-type scope and a different consumer; collapsing them into one endpoint risks a guidance query accidentally picking up extraction-only content (e.g. curated examples that shouldn't appear in a parent-facing question) |
| Sequencing relative to the rest of the system | Deferred until schema, annotation protocol, and ground truth are finalized (handoff §24) | Build retrieval now, alongside the temporary-LLM pipeline, and adjust later | Retrieval content (schema definitions, taxonomy, examples) would need to be re-indexed once the target schema stabilizes; building it before that churns work |

## Open Questions & Future Decisions

### Deferred
1. Embedding model choice — deferred until the extraction target schema (handoff §11) is finalized, since example curation depends on the final field set.
2. Whether `permitted_role_metadata` needs per-record granularity or can be derived entirely from `document_type` + existing role policy at query time.
3. Cache/refresh strategy for the pointer-based index when an authoritative record is corrected (a new structured-record version is created — see `docs/High_Level_Design.md` § Key Design Decisions). The index likely needs a re-embed-on-correction hook once this layer exists.
4. Whether Explanation RAG needs its own narrower index or can reuse the Extraction RAG index filtered to `document_type = observation`.

## References

- `CLAUDE_PROJECT_HANDOFF.md` §8 (Module C — Secure RAG), §24 (sequencing decision).
- `docs/High_Level_Design.md` § Secure Retrieval Layer (planned) — parent architecture context.
- `src/backend/api/deps.py` — `get_authorized_children`, `authorize_child_access`, `require_role` (existing authorization primitives this layer must reuse, not duplicate).
