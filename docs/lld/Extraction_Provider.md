---
parent: high-level-design
prefix: EXTRACT
---

# Extraction Provider

*Brownfield LLD — reverse-engineered from `src/backend/ml/extraction/`. Decisions marked `[inferred]` were observed in code, not confirmed by the author; confirm or refute them as this doc is revisited.*

## Context and Design Philosophy

The extraction provider is the single seam through which any LLM (temporary or, later, fine-tuned) turns an observation's free text into a `StructuredObservation`. Per CLAUDE.md, no other layer may call a vendor LLM directly — everything downstream (validation, abstention, analytics, reporting) is written against `ExtractionResult`, never against a specific vendor's response shape. This LLD is entirely about the two implementations behind that seam and the safety invariants baked into the current (temporary-LLM) one.

This component sits at the front of the **real-time ingestion pipeline**: `extract_node → validate_node → route_node` inside `observation_workflow.py`'s LangGraph. It is a distinct arrow segment from the **batch analytics/reporting pipeline** (Adequacy Router → Analytics Engine → Reporting LLM), which operates on many already-persisted records per review period rather than one observation at a time — see [Adequacy_Router.md](./Adequacy_Router.md) and [Analytics_Engine.md](./Analytics_Engine.md).

## Interface Contract

```text
ExtractionProvider(Protocol):
  async extract(request: ExtractionRequest) -> ExtractionResult
  get_info() -> ProviderInfo
```

`ExtractionRequest`: `source_type` (`conversational` | `chat_segment`), `text` (non-empty), app-known passthrough fields (`child_id`, `session_id`, `contributor_role`, `observation_date`, `setting`), `metadata`, `goal_ids`, `clarification_history`.

`ExtractionResult`: `status` (`success` | `partial` | `abstained` | `failed`), `observations: list[StructuredObservation]`, `provider`, `model`, `prompt_version`, `schema_version` ("1.0"), `generated_at`, `clarification_questions`, `raw_llm_response` (kept for audit provenance), `extraction_duration_ms`, `token_usage`.

`ProviderInfo`: `name`, `provider_type` (`temporary_llm` | `finetuned_model`), `model_id`, `version`, `is_available`.

**Invariant, stated in both the protocol docstring and the schema docstring:** app-known metadata fields must be preserved from the request into the result unchanged — the LLM never generates `child_id`, `session_id`, or similar fields. This is a safety invariant, not a convenience.

## Implementations

### TemporaryLLMExtractionProvider (current)

Wraps the Claude API with **forced tool use** (`tool_choice={"type": "tool", "name": "record_observation"}`) so the model can only respond through `EXTRACTION_TOOL_SCHEMA` — it cannot fall back to free text. The schema's `required` array lists `domain, behavior, modality, prompt_level, outcome, confidence`; all but `confidence` are nullable, so the model must explicitly assert `null` rather than omit a field it can't support.

Two prompt builders select on `source_type`:
- `build_user_prompt_conversational` — for contributor chat observations.
- `build_user_prompt_chat_segment` — adds a CHAT-format primer (speaker codes `CHI`/`INV`/`MOT`/`FAT`, `%code:` dependent tiers, `xxx` = unintelligible, `0` = no verbal production, `[+ trn]`, terminators) for segments drawn from Rollins/Flusberg transcripts.

Both append `clarification_history` when present. `PROMPT_VERSION = "1.0.0"`, tracked separately from `ExtractionResult.schema_version`.

The system prompt states explicit safety rules: never fabricate or infer beyond what the text states; never diagnose, recommend treatment, or make causal claims; prefer null + `abstention_reason` over a guess.

**Result-status rules (exact):**

| Condition | Status |
|---|---|
| `confidence < 0.3` (`_ABSTENTION_CONFIDENCE`) | `ABSTAINED` |
| ≥5 of 8 extracted fields null (`_NULL_THRESHOLD`) — fields: `domain, goal_context, behavior, modality, prompt_context, prompt_level, outcome, duration_seconds` | `ABSTAINED` |
| Both `behavior` and `domain` present | `SUCCESS` |
| Otherwise | `PARTIAL` |

**Error handling:** `anthropic.APIError` and any other exception around the full `extract()` body route to `_failed_result()` — `status=FAILED`, empty observations, raw response preserved when available. A response with no matching `tool_use` block also routes to `_failed_result()` with message `"No valid tool_use block in LLM response"`.

### FineTunedExtractionProvider (future — stub)

`extract()` raises `NotImplementedError("Fine-tuned model not yet available")`. `get_info()` returns `is_available=False`, `model_id="not_available"`, `version="0.0.0"`. No model loading or config plumbing exists yet — this confirms CLAUDE.md's phase boundary: the fine-tuned provider is a contract placeholder, not a partial implementation.

## Decisions & Alternatives

| Decision | Chosen | Alternatives Considered | Rationale |
|---|---|---|---|
| Structured-output enforcement | Forced tool-use (`tool_choice` pinned to `record_observation`) | Free-text response parsed by regex/JSON-mode; unconstrained function calling | `[inferred]` Forced tool use removes an entire failure mode (model answering in prose instead of the schema) at the API level rather than via post-hoc parsing |
| Abstention thresholds | Fixed constants (`confidence < 0.3`, `≥5/8` null fields) in code, not configurable per request | Per-goal or per-domain configurable thresholds | `[inferred]` Simplicity for the current phase; revisit if different domains need different abstention sensitivity |
| Null must be explicit, not omitted | Tool schema requires all extractable keys present (nullable), forcing an explicit `null` | Allow the model to omit fields it can't support | `[inferred]` An omitted field is ambiguous (forgot vs. not supported); a forced explicit `null` is unambiguous and auditable |
| Multi-observation contract, single-observation consumption | `ExtractionResult.observations` is a list, but every downstream consumer (`validate_node`, `route_node`) only reads `observations[0]` | Single-observation return type | `[inferred]` — likely forward-looking for chat-segment extraction that could yield multiple observations per segment; currently unused. Flagged as an open question below rather than assumed intentional. |

## Open Questions & Future Decisions

### Deferred
1. `ExtractionResult.observations` is modeled as a list but only index `0` is ever consumed by `validate_node`/`route_node` in `observation_workflow.py`. Confirm whether multi-observation extraction is a near-term goal (e.g., for CHAT segments spanning multiple behavioral episodes) or whether the contract should be narrowed to a single `StructuredObservation`.
2. `FineTunedExtractionProvider`'s config surface (model path/version, loading strategy, `ProviderInfo` population) is undefined — to be specified when foundation-model fine-tuning work begins, per CLAUDE.md's phase boundary. See [Foundation_Model_Fine_Tuning.md](./Foundation_Model_Fine_Tuning.md) for the deferred training/dataset/evaluation design that fills this stub in.

## References

- `src/backend/ml/extraction/base.py`, `schemas.py`, `temporary_llm.py`, `finetuned_model.py`, `prompts.py`.
- `src/backend/services/observation_workflow.py` — `extract_node`, the real-time pipeline's entry point into this component.
- `docs/High_Level_Design.md` § Key Design Decisions (pluggable extraction provider).
- Tests: `tests/phase6/integration/test_extraction_pipeline_e2e.py`, `tests/phase6/integration/test_audit_provenance_e2e.py`, `tests/eval/test_extraction_hallucination.py`, `tests/eval/test_prompt_injection.py`, `tests/eval/test_schema_conformance.py` / `test_schema_validation.py`.
