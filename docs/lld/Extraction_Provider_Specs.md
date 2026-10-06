# Extraction Provider — EARS Specs

Owning design: [Extraction_Provider.md](./Extraction_Provider.md). Prefix: `EXTRACT`.

Test citations below reflect an actual `@spec`-annotation pass (each spec ID appears as a comment above the test that verifies it). `[x]` = annotated test exists and passes; `[ ]` = no test currently cites this spec, though the underlying code already implements it — an active gap in test coverage, not in behavior; `[D]` = correct intent, not achievable/needed yet.

## Contract Invariants

- [x] **EXTRACT-001**: The system shall preserve app-known metadata fields (`child_id`, `session_id`, `contributor_role`, `observation_date`, `setting`) from the `ExtractionRequest` into the `ExtractionResult` unchanged; no extraction provider shall generate or modify these fields. — `tests/eval/extraction/test_schema_conformance.py::TestSchemaConformance::test_app_known_fields_preserved`
- [D] **EXTRACT-002**: Both `TemporaryLLMExtractionProvider` and `FineTunedExtractionProvider` shall return the same `ExtractionResult` contract shape from `extract()`. — not achievable today: `FineTunedExtractionProvider.extract()` only raises `NotImplementedError` (EXTRACT-030), so no shared-shape test can exist until a real implementation lands; see [Foundation_Model_Fine_Tuning.md](./Foundation_Model_Fine_Tuning.md).
- [x] **EXTRACT-003**: Where `ExtractionResult.observations` contains more than one element, the system shall validate and route only the first element (`observations[0]`) in the current phase; remaining elements shall not be processed by the Deterministic Validation Engine or the Abstention Router. The multi-observation list shape is retained for forward compatibility (see [Extraction_Provider.md](./Extraction_Provider.md) Open Questions); only single-observation consumption is in scope today. — `tests/phase3/test_observation_workflow.py::TestValidateNode::test_multi_observation_only_first_is_validated`

## Result Envelope

These specs evolve the shared `ExtractionResult` contract additively so that a composing provider (MARS) reports what deterministic validation needs without a provider-specific side channel. The shape stays identical across providers; optional fields differ in *applicability*, not in presence, which is what EXTRACT-002 requires.

- [x] **EXTRACT-020**: `ExtractionResult` shall carry `control_confidence` — the single confidence quantity deterministic validation gates on, regardless of which provider produced the result. Consumers shall gate on `control_confidence` rather than on a provider's internal confidence, so that the meaning of a validation threshold does not vary by provider. — `tests/phase4/test_result_envelope.py::TestControlConfidence`

- [x] **EXTRACT-021**: `ExtractionResult` shall carry an optional provenance envelope describing how the result was obtained — provider type, generator identities, judge identities, rankings, and the underlying confidence quantities — and an optional `reason_code`. Provenance shall not be written onto `StructuredObservation`, which describes the observation itself rather than its derivation. A single-model provider populates it with empty judge identities and an empty ranking; that is an accurate statement that judging did not occur, not filler. — `tests/phase4/test_result_envelope.py::TestProvenanceEnvelope`

- [x] **EXTRACT-022**: Where a provider generates an extraction directly rather than selecting among candidates, that provider shall set `control_confidence` equal to the confidence of the observation it produced. Composing providers set it per their own rules (see [Mars_Reranking_Specs.md](./Mars_Reranking_Specs.md) MARS-032). — `tests/phase4/test_result_envelope.py::TestGeneratingProviderControlConfidence`

## TemporaryLLMExtractionProvider

- [ ] **EXTRACT-010**: When calling the Claude API for extraction, the system shall force `tool_choice` to the `record_observation` tool so the model cannot respond in free text. — no test inspects the Anthropic call kwargs to assert `tool_choice` is forced; behavior is implemented, coverage gap only.
- [x] **EXTRACT-011**: Where `ExtractionRequest.source_type` is `chat_segment`, the system shall build the prompt using the CHAT-format primer (speaker codes, `%code:` tiers, `xxx`, `0`, `[+ trn]`, terminators); where `source_type` is `conversational`, the system shall build the prompt without the CHAT-format primer. — `test_schema_conformance.py::test_conversational_source_type`, `::test_chat_segment_source_type`
- [x] **EXTRACT-012**: When `clarification_history` is present on the `ExtractionRequest`, the system shall append it to the prompt regardless of `source_type`. — `tests/eval/extraction/test_clarification.py::test_clarification_history_in_conversational_prompt`, `::test_clarification_history_in_chat_prompt`
- [x] **EXTRACT-013**: If a *generating* provider's extraction `confidence` is less than 0.3, then that provider shall set `ExtractionResult.status` to `ABSTAINED`. This rule scopes to providers that produce an extraction from source text; it is not applied by a composing provider to a candidate it selected (see [Mars_Reranking_Specs.md](./Mars_Reranking_Specs.md) MARS-024). — `tests/eval/extraction/test_abstention.py::test_low_confidence_triggers_abstention_status`
- [x] **EXTRACT-014**: If 5 or more of the 8 extracted fields (`domain`, `goal_context`, `behavior`, `modality`, `prompt_context`, `prompt_level`, `outcome`, `duration_seconds`) are null, then a *generating* provider shall set `ExtractionResult.status` to `ABSTAINED`. Scoped as in EXTRACT-013. — `tests/eval/extraction/test_unsupported_fields.py::test_status_abstained_many_nulls`
- [x] **EXTRACT-015**: When neither the confidence-abstention (EXTRACT-013) nor the null-field-abstention (EXTRACT-014) condition applies, and both `behavior` and `domain` are present, a *generating* provider shall set `ExtractionResult.status` to `SUCCESS`. Scoped as in EXTRACT-013. — `test_unsupported_fields.py::test_status_success_when_complete`
- [x] **EXTRACT-016**: When neither the confidence-abstention (EXTRACT-013) nor the null-field-abstention (EXTRACT-014) condition applies, and `behavior` or `domain` (but not both) is missing, a *generating* provider shall set `ExtractionResult.status` to `PARTIAL`. Scoped as in EXTRACT-013. — `test_unsupported_fields.py::test_status_partial_when_critical_missing`
- [x] **EXTRACT-017**: If the Claude API call raises `anthropic.APIError` or any other exception during extraction, then the system shall return a failed `ExtractionResult` with `status=FAILED`, empty `observations`, and the raw response preserved when available. — `test_abstention.py::test_api_error_returns_failed`
- [x] **EXTRACT-018**: If the LLM response contains no `tool_use` block matching `record_observation`, then the system shall return a failed `ExtractionResult` with message "No valid tool_use block in LLM response". — `test_abstention.py::test_no_tool_use_block_returns_failed`
- [ ] **EXTRACT-019**: The tool schema shall require `domain`, `behavior`, `modality`, `prompt_level`, `outcome`, and `confidence` as present keys, with all but `confidence` nullable, so the model must explicitly assert `null` rather than omit an unsupported field. — no test inspects `EXTRACTION_TOOL_SCHEMA`'s required/nullable shape directly; behavior is implemented, coverage gap only.

## FineTunedExtractionProvider (stub, current phase)

- [x] **EXTRACT-030**: Where no fine-tuned model is available (current phase), `FineTunedExtractionProvider.extract()` shall raise `NotImplementedError`. — `tests/eval/extraction/test_extraction.py::TestFineTunedStub::test_finetuned_extract_raises`
- [x] **EXTRACT-031**: Where no fine-tuned model is available (current phase), `FineTunedExtractionProvider.get_info()` shall report `is_available=false`, `model_id="not_available"`, `version="0.0.0"`. — `test_extraction.py::TestFineTunedStub::test_finetuned_unavailable`

## References

- [Extraction_Provider.md](./Extraction_Provider.md) — full design and decisions.
- [Foundation_Model_Fine_Tuning.md](./Foundation_Model_Fine_Tuning.md) — the deferred design that will eventually replace EXTRACT-030/031 with real behavior; new specs will be added here, not to that design doc, once that work begins.
