# Extraction Provider — EARS Specs

Owning design: [Extraction_Provider.md](./Extraction_Provider.md). Prefix: `EXTRACT`.

All specs below are `[x]` — implemented and covered by `tests/phase6/integration/test_extraction_pipeline_e2e.py`, `tests/phase6/integration/test_audit_provenance_e2e.py`, `tests/eval/test_extraction_hallucination.py`, `tests/eval/test_schema_conformance.py` / `test_schema_validation.py`, `tests/eval/test_prompt_injection.py`, unless noted otherwise.

## Contract Invariants

- [x] **EXTRACT-001**: The system shall preserve app-known metadata fields (`child_id`, `session_id`, `contributor_role`, `observation_date`, `setting`) from the `ExtractionRequest` into the `ExtractionResult` unchanged; no extraction provider shall generate or modify these fields.
- [x] **EXTRACT-002**: Both `TemporaryLLMExtractionProvider` and `FineTunedExtractionProvider` shall return the same `ExtractionResult` contract shape from `extract()`.
- [x] **EXTRACT-003**: Where `ExtractionResult.observations` contains more than one element, the system shall validate and route only the first element (`observations[0]`) in the current phase; remaining elements shall not be processed by the Deterministic Validation Engine or the Abstention Router. The multi-observation list shape is retained for forward compatibility (see [Extraction_Provider.md](./Extraction_Provider.md) Open Questions); only single-observation consumption is in scope today.

## TemporaryLLMExtractionProvider

- [x] **EXTRACT-010**: When calling the Claude API for extraction, the system shall force `tool_choice` to the `record_observation` tool so the model cannot respond in free text.
- [x] **EXTRACT-011**: Where `ExtractionRequest.source_type` is `chat_segment`, the system shall build the prompt using the CHAT-format primer (speaker codes, `%code:` tiers, `xxx`, `0`, `[+ trn]`, terminators); where `source_type` is `conversational`, the system shall build the prompt without the CHAT-format primer.
- [x] **EXTRACT-012**: When `clarification_history` is present on the `ExtractionRequest`, the system shall append it to the prompt regardless of `source_type`.
- [x] **EXTRACT-013**: If the extraction's `confidence` is less than 0.3, then the system shall set `ExtractionResult.status` to `ABSTAINED`.
- [x] **EXTRACT-014**: If 5 or more of the 8 extracted fields (`domain`, `goal_context`, `behavior`, `modality`, `prompt_context`, `prompt_level`, `outcome`, `duration_seconds`) are null, then the system shall set `ExtractionResult.status` to `ABSTAINED`.
- [x] **EXTRACT-015**: When neither the confidence-abstention (EXTRACT-013) nor the null-field-abstention (EXTRACT-014) condition applies, and both `behavior` and `domain` are present, the system shall set `ExtractionResult.status` to `SUCCESS`.
- [x] **EXTRACT-016**: When neither the confidence-abstention (EXTRACT-013) nor the null-field-abstention (EXTRACT-014) condition applies, and `behavior` or `domain` (but not both) is missing, the system shall set `ExtractionResult.status` to `PARTIAL`.
- [x] **EXTRACT-017**: If the Claude API call raises `anthropic.APIError` or any other exception during extraction, then the system shall return a failed `ExtractionResult` with `status=FAILED`, empty `observations`, and the raw response preserved when available.
- [x] **EXTRACT-018**: If the LLM response contains no `tool_use` block matching `record_observation`, then the system shall return a failed `ExtractionResult` with message "No valid tool_use block in LLM response".
- [x] **EXTRACT-019**: The tool schema shall require `domain`, `behavior`, `modality`, `prompt_level`, `outcome`, and `confidence` as present keys, with all but `confidence` nullable, so the model must explicitly assert `null` rather than omit an unsupported field.

## FineTunedExtractionProvider (stub, current phase)

- [x] **EXTRACT-030**: Where no fine-tuned model is available (current phase), `FineTunedExtractionProvider.extract()` shall raise `NotImplementedError`.
- [x] **EXTRACT-031**: Where no fine-tuned model is available (current phase), `FineTunedExtractionProvider.get_info()` shall report `is_available=false`, `model_id="not_available"`, `version="0.0.0"`.

## References

- [Extraction_Provider.md](./Extraction_Provider.md) — full design and decisions.
- [Foundation_Model_Fine_Tuning.md](./Foundation_Model_Fine_Tuning.md) — the deferred design that will eventually replace EXTRACT-030/031 with real behavior; new specs will be added here, not to that design doc, once that work begins.
