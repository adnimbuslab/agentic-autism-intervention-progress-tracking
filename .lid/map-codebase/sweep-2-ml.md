# Sweep 2: src/backend/ml/ — File-by-File Report

Scope: 13 files under `src/backend/ml/`. All 13 were read in full (one, `__init__.py`, is empty — 0 bytes).

---

```yaml
- path: src/backend/ml/__init__.py
  purpose: Package marker for src/backend/ml — no content.
  exports: none
  dependencies: none
  data_shapes: none
  side_effects: none
  role: Makes src/backend/ml a Python package. No re-exports, so all submodules must be imported by their full dotted path (confirmed elsewhere in the codebase, e.g. `from src.backend.ml.extraction import ...`).
  observations: File is completely empty (0 lines). Unlike src/backend/ml/extraction/__init__.py (which curates a public API with __all__), this top-level package has no equivalent aggregation point — no single place exports ValidationEngine, AbstentionRouter, AdequacyRouter, AnalyticsEngine, ReportingClient. Not necessarily a defect, just an inconsistency in aggregation pattern across the two __init__.py files in scope.
```

```yaml
- path: src/backend/ml/abstention_router.py
  purpose: Final routing gate that combines extraction status and deterministic validation result into one RoutingDecision, and generates focused non-leading clarification questions for contributors.
  exports:
    - class AbstentionRouter with methods route(extraction, validation) -> RoutingDecision, generate_clarification_questions(observation, validation) -> list[str], and static _has_recoverable_fields(observation, validation) -> bool
    - module constants _MAX_CLARIFICATION_QUESTIONS=3, _CRITICAL_FIELDS={"behavior","domain"}, _QUESTION_TEMPLATES (dict field->question text)
  dependencies:
    - src.backend.ml.extraction.schemas: ExtractionResult, ExtractionStatus
    - src.backend.ml.schemas: FieldValidation, RoutingDecision, ValidationResult
    - src.backend.schemas.observation_schema: StructuredObservation (outside ml/ scope)
  data_shapes: "Consumes an ExtractionResult (status + observations list) and a ValidationResult (routing + field_validations). Produces a RoutingDecision enum value, or a list[str] of clarification question strings (max 3, deduplicated, drawn from a fixed template dict keyed by field name)."
  side_effects: none — pure logic, no I/O.
  role: Sits after ValidationEngine and before persistence/notification in the observation pipeline; per CLAUDE.md this implements "Abstention is a first-class output when evidence is inadequate" and the "focused, non-leading clarification questions" requirement.
  observations:
    - "route() logic (lines 30-57): when validation.routing == CLARIFY it re-checks recoverability via _has_recoverable_fields, but when validation.routing is RETAIN_WITH_UNKNOWN or INTERVENTIONIST_REVIEW it upgrades to CLARIFY whenever extraction.status==PARTIAL and extraction.clarification_questions is non-empty — i.e., the LLM extraction provider's own suggested clarification_questions field can override/redirect the deterministic validation routing decision. This is a coupling point between the (non-deterministic) LLM extraction layer and the (deterministic) validation/routing layer worth flagging: CLAUDE.md states validation should be deterministic, but here LLM-authored `extraction.clarification_questions` presence directly changes routing outcome (line 47-55)."
    - "_QUESTION_TEMPLATES (lines 16-24) hardcodes exactly 7 field names; generate_clarification_questions() only ever produces questions for fields present in this dict — any field validated elsewhere (e.g. confidence, goal_context validity) has no corresponding question and is silently dropped from candidate list if not in the dict (see _has_recoverable_fields's intersection with set(_QUESTION_TEMPLATES) at line 109)."
    - "No logging of routing decisions — CLAUDE.md requires 'All model invocations logged with version, config hash, and timestamp' but this router (a non-model decision point) has zero logging."
```

```yaml
- path: src/backend/ml/adequacy_router.py
  purpose: Deterministic (pure Python, explicitly no-LLM per module docstring) evidence-sufficiency assessment — decides whether accumulated structured records for a child/review-period are ADEQUATE, LIMITED, or INSUFFICIENT for analytics/reporting, and which specific cross-cutting comparisons (contributor, setting) must be partially withheld.
  exports:
    - class AdequacyRouter with method assess(records, goals, review_start, review_end, expected_observation_count=None) -> AdequacyResult
    - private check methods: _check_coverage, _check_temporal_distribution, _check_contributor_representation, _check_setting_representation, _check_goal_coverage, _check_field_completeness, _compute_level
  dependencies:
    - src.backend.config.settings (adequacy_limited_observations, adequacy_min_observations, adequacy_field_completeness_threshold, adequacy_temporal_cluster_max_ratio) — outside ml/ scope
    - src.backend.ml.schemas: AdequacyCheck, AdequacyCheckResult, AdequacyLevel, AdequacyResult
    - src.backend.schemas.observation_schema.LLM_EXTRACTED_FIELDS — imported but NOT used anywhere in this file (see observations)
    - stdlib: collections.Counter, datetime.date
  data_shapes: "Input: list[dict] of structured-record-like dicts (keys accessed via .get: observation_date, contributor_role, setting, domain, behavior, outcome), list[dict] of goals (keys: domain), review_start/review_end dates. Output: AdequacyResult{level, eligible, checks: list[AdequacyCheckResult], partial_abstentions: dict[str,str], quality_flags: list[str]}."
  side_effects: none — pure computation.
  role: Implements CLAUDE.md's 'Analytics MUST be withheld when adequacy checks fail — never force a conclusion' and the Adequacy/Abstention Router box in the AI/ML layer of the architecture. Sits between the structured record store and AnalyticsEngine/ReportingClient — AnalyticsResult.compute() and EvidencePacket both take an AdequacyResult as input.
  observations:
    - "Line 18 imports LLM_EXTRACTED_FIELDS from observation_schema but it is never referenced in the file body — dead import. _check_field_completeness (lines 251-281) instead hardcodes its own critical_fields = {'behavior','domain','outcome'} literal set rather than reusing LLM_EXTRACTED_FIELDS, which is a separate constant used by validation_engine.py for a related but different completeness computation. This is a duplication/inconsistency: two different notions of 'completeness fields' exist across adequacy_router.py (3 fields) and validation_engine.py (LLM_EXTRACTED_FIELDS, presumably more fields)."
    - "AdequacyCheck enum (in schemas.py) defines TIMELINESS and CONSISTENCY members that are never checked in this file — assess() only runs 6 of the 8 enum-listed check types (COVERAGE, TEMPORAL_DISTRIBUTION, CONTRIBUTOR_REPRESENTATION, SETTING_REPRESENTATION, GOAL_COVERAGE, FIELD_COMPLETENESS). TIMELINESS and CONSISTENCY appear to be planned-but-unimplemented checks."
    - "_compute_level (lines 72-96) has somewhat intricate branching (critical-checks-failed vs failed-checks>2 vs record_count thresholds) whose precise decision table is not documented; behavior for edge cases (e.g., exactly settings.adequacy_min_observations records with exactly 2 failed non-critical checks) requires tracing all branches — flagging as a candidate for a decision-table comment/test rather than a bug."
    - "review_start/review_end parameters (lines 29-30) are accepted but only review_start/review_end are unused in the body except that _check_temporal_distribution doesn't reference them either (lines 120-161) — it only computes same-day clustering ratio among the records' own dates, never checks distribution against the review_start/review_end window itself. So the review period boundaries are currently passed in but not used to validate temporal coverage relative to the period boundaries."
```

```yaml
- path: src/backend/ml/analytics_engine.py
  purpose: Deterministic KPI computation over validated structured records — explicit module docstring states "all KPIs computed by code, never by LLM."
  exports:
    - class AnalyticsEngine with method compute(child_id, review_period_id, records, adequacy, goal_id=None) -> AnalyticsResult
    - private per-KPI methods: _observation_count, _domain_distribution, _modality_distribution, _prompt_level_distribution, _outcome_distribution, _independence_rate, _contributor_distribution, _setting_distribution, _missing_data_rate, _positive_outcome_rate, _cross_setting_comparison, _cross_contributor_comparison, _prompt_support_trend, _outcome_trend, and static _sort_by_date
  dependencies:
    - src.backend.ml.schemas: AdequacyResult, AnalyticsResult, KpiResult
    - stdlib: collections.Counter, datetime.date
  data_shapes: "Input: list[dict] of structured records (keys: domain, modality, prompt_level, outcome, contributor_role, setting, observation_date) and an AdequacyResult. Output: AnalyticsResult{child_id, review_period_id, goal_id, kpis: list[KpiResult], adequacy}. Each KpiResult carries numerator/denominator/value plus abstained/abstention_reason/prerequisites_met/display_eligible flags."
  side_effects: none — pure computation, deterministic given same inputs (matches docstring claim).
  role: Implements 'Analytics Engine' box in AI/ML layer; consumed downstream by ReportingClient (via EvidencePacket.analytics) to build report prose without the reporting LLM doing any arithmetic itself.
  observations:
    - "If adequacy.eligible is False, compute() short-circuits and returns a single synthetic KPI named 'all_analytics' with abstained=True (lines 32-49) — no other KPI methods run at all. This is a hard binary switch: there's no 'partial adequate' path where a subset of KPIs run even though CLAUDE.md/adequacy_router.py otherwise models AdequacyLevel as three-valued (ADEQUATE/LIMITED/INSUFFICIENT) with per-check partial_abstentions (cross_setting_comparison, cross_contributor_comparison) intended for finer-grained withholding. Those partial_abstentions ARE consulted later at lines 218 and 239 inside _cross_setting_comparison/_cross_contributor_comparison, but only reachable when adequacy.eligible is True in the first place — i.e. LIMITED-but-eligible periods get partial withholding of just those two KPIs, while INSUFFICIENT periods get total withholding of everything. Internally consistent, just worth noting the two different granularities of withholding used at different adequacy levels."
    - "_domain_distribution, _modality_distribution, _prompt_level_distribution, _outcome_distribution, _contributor_distribution, _setting_distribution (lines 85-165) all compute a `dist` or `counts` breakdown via Counter but only surface `len(counts)` (the count of distinct categories) as both numerator and value in the returned KpiResult — the actual per-category distribution/percentages (e.g., the `dist` dict built at line 88 in _domain_distribution) is computed then discarded and never included in the KpiResult. Only _domain_distribution computes `dist` at all (line 88); the other five distribution methods don't even build the per-category dict. This looks like an incomplete/placeholder implementation — a KpiResult schema (schemas.py) has no field to carry a per-category breakdown, so if the intent was to expose the full distribution to the reporting layer, that capability doesn't currently exist end-to-end."
    - "None of the abstention-eligible KPIs (_independence_rate line 126, _positive_outcome_rate line 191, _prompt_support_trend line 259, _outcome_trend line 287) apply any adequacy-level-based threshold beyond their own local sample-size checks (e.g. 'need >= 4 records') — abstention here is purely a function of the KPI's own denominator, independent of the overall AdequacyLevel (LIMITED vs ADEQUATE), so a 'LIMITED' but eligible period can still emit fully-confident-looking KPIs for e.g. domain_distribution with no caveats attached at this layer (caveats are added later by ReportingClient using adequacy.quality_flags, not by AnalyticsEngine itself)."
```

```yaml
- path: src/backend/ml/extraction/__init__.py
  purpose: Public API surface and factory for the pluggable extraction-provider subsystem.
  exports:
    - re-exports ExtractionProvider (base.py), FineTunedExtractionProvider (finetuned_model.py), ExtractionRequest/ExtractionResult/ExtractionStatus/ProviderInfo/SourceType (schemas.py), TemporaryLLMExtractionProvider (temporary_llm.py)
    - function get_extraction_provider(provider_type: str, **kwargs) -> ExtractionProvider — factory keyed by string "temporary_llm" or "finetuned_model"
  dependencies:
    - src.backend.ml.extraction.base.ExtractionProvider
    - src.backend.ml.extraction.finetuned_model.FineTunedExtractionProvider
    - src.backend.ml.extraction.schemas.{ExtractionRequest, ExtractionResult, ExtractionStatus, ProviderInfo, SourceType}
    - src.backend.ml.extraction.temporary_llm.TemporaryLLMExtractionProvider
  data_shapes: n/a (pure re-export + factory dispatch)
  side_effects: "Instantiates TemporaryLLMExtractionProvider(**kwargs) — this constructor (see temporary_llm.py) creates an AsyncAnthropic client, i.e. calling get_extraction_provider('temporary_llm', api_key=...) has the side effect of constructing a network-capable HTTP client object (no network call yet, but client setup happens here)."
  role: This is the seam CLAUDE.md refers to as 'ExtractionProvider' pluggability — confirmed by code: src/backend/services/observation_service.py and src/backend/services/observation_workflow.py both call get_extraction_provider(...) rather than importing a concrete provider directly, matching the 'Backend business logic MUST NOT call a specific LLM vendor directly' safety rule.
  observations:
    - "Factory raises ValueError for unknown provider_type (line 35) — no validation elsewhere in this file of what kwargs are actually valid per provider_type; get_extraction_provider('finetuned_model', api_key='...') would silently ignore api_key since FineTunedExtractionProvider() takes no constructor args, whereas get_extraction_provider('temporary_llm') without api_key would raise inside TemporaryLLMExtractionProvider.__init__ (which requires api_key positionally) — no arg-shape guardrails at the factory boundary."
    - "The `# type: ignore[arg-type]` comment on line 32 signals the author is aware **kwargs isn't statically typed against TemporaryLLMExtractionProvider's actual __init__ signature (api_key: str, model: str = ...) — a minor type-safety gap, not a runtime bug currently."
```

```yaml
- path: src/backend/ml/extraction/base.py
  purpose: Defines the ExtractionProvider Protocol — the pluggable interface contract that both current and future extraction providers must satisfy.
  exports:
    - "@runtime_checkable Protocol class ExtractionProvider with async def extract(request: ExtractionRequest) -> ExtractionResult and def get_info() -> ProviderInfo"
  dependencies:
    - typing.Protocol, typing.runtime_checkable (stdlib)
    - src.backend.ml.extraction.schemas: ExtractionRequest, ExtractionResult, ProviderInfo
  data_shapes: "Protocol only — no concrete data, just method signatures over ExtractionRequest -> ExtractionResult and () -> ProviderInfo."
  side_effects: none
  role: "This is the literal embodiment of CLAUDE.md's 'ExtractionProvider' pluggable interface described in the Architecture section (AI/ML layer) and the 'Current extraction architecture' diagram in the project overview. Both TemporaryLLMExtractionProvider and FineTunedExtractionProvider structurally satisfy this Protocol (verified: both classes define async extract(request) and get_info() with matching signatures) even though neither explicitly subclasses ExtractionProvider — this is intentional given Python's structural Protocol typing."
  observations:
    - "Docstring on extract() (lines 23-29) states 'App-known metadata fields ... must be preserved in the resulting StructuredObservation — they must not be generated by the LLM,' which is a hard contract requirement documented only as a comment, not enforced by any code in this file. Enforcement is actually done concretely in temporary_llm.py's _build_observation (lines 132-137, which explicitly copies child_id/session_id/contributor_role/observation_date/setting from the request rather than the tool_input) — but nothing here in base.py would catch a future provider implementation that violated this by, e.g., letting the LLM set child_id. No runtime validation of Protocol conformance to this specific sub-rule exists in scope."
    - "No abstract/base exception types, no shared helper logic — this is a pure interface file with zero implementation, consistent with 'Protocol' pattern."
```

```yaml
- path: src/backend/ml/extraction/finetuned_model.py
  purpose: Placeholder/stub for the future fine-tuned foundation-model extraction provider referenced throughout CLAUDE.md as "[FUTURE]".
  exports:
    - class FineTunedExtractionProvider with async extract(request) -> ExtractionResult (raises NotImplementedError) and get_info() -> ProviderInfo (returns is_available=False)
  dependencies:
    - src.backend.ml.extraction.schemas: ExtractionRequest, ExtractionResult, ProviderInfo
  data_shapes: "get_info() returns a fixed ProviderInfo(name='finetuned_extraction', provider_type='finetuned_model', model_id='not_available', version='0.0.0', is_available=False). extract() never returns — always raises."
  side_effects: none (raises an exception, no I/O)
  role: "Confirms the CLAUDE.md claim precisely: this is explicitly a stub, not a working provider. The class docstring itself says 'Placeholder for the future fine-tuned extraction provider' (line 13) and extract()'s docstring says 'Not yet implemented -- awaiting fine-tuned model training' (line 16). This matches CLAUDE.md's instruction 'Do NOT train or fine-tune the final foundation model during this phase' and the 'FineTunedExtractionProvider [FUTURE]' architecture note — the code and docs are consistent here, no drift."
  observations:
    - "Module docstring (line 1) itself says 'stub' — this is the one file in scope that is self-describing as incomplete by design rather than by omission; no TODO markers needed since the intent is stated directly."
    - "Because get_extraction_provider('finetuned_model') (extraction/__init__.py line 34) will happily construct this class with zero validation, any caller that selects this provider_type in the current phase will get a provider whose extract() always raises NotImplementedError at call time rather than being rejected earlier (e.g., at provider-selection/config time) — worth noting as a place where a caller could reach a stub in production if a config flag were flipped prematurely. No caller in the current codebase does this (grep confirms only 'temporary_llm' is used at call sites in src/backend/services/)."
```

```yaml
- path: src/backend/ml/extraction/prompts.py
  purpose: Prompt templates and the Claude tool_use JSON schema used by the temporary LLM extraction provider to constrain and structure its output.
  exports:
    - PROMPT_VERSION = "1.0.0" (module constant)
    - EXTRACTION_TOOL_SCHEMA: dict — Claude tool_use schema definition for a "record_observation" tool
    - build_system_prompt() -> str
    - build_user_prompt_conversational(text, clarification_history=None) -> str
    - build_user_prompt_chat_segment(text, clarification_history=None) -> str
  dependencies:
    - src.backend.schemas.observation_schema: Domain, Modality, Outcome, PromptLevel (enums, outside ml/ scope) — used to populate the tool schema's enum lists and the system prompt's "VALID ENUM VALUES" text
  data_shapes: "EXTRACTION_TOOL_SCHEMA is an Anthropic tool-use JSON schema (type object) with properties: domain, goal_context, behavior, modality, prompt_context, prompt_level, outcome, duration_seconds, confidence, abstention_reason — 'required' list is [domain, behavior, modality, prompt_level, outcome, confidence] (line 68) even though every one of those fields' type includes 'null' (nullable-but-required, i.e. the tool call must always populate the key, value may be None)."
  side_effects: none — pure string/dict construction.
  role: Directly implements the CLAUDE.md safety rule 'The extraction provider MUST NOT generate field values not supported by the source text' via explicit prompt instructions (build_system_prompt, lines 84-97: 'NEVER fabricate or infer beyond what the text explicitly states', 'Set abstention_reason when evidence is insufficient'). Also implements the CHAT-segment-vs-conversational duality described in CLAUDE.md (two distinct source types get two distinct user-prompt builders, both sharing the same system prompt and tool schema).
  observations:
    - "goal_ids field on ExtractionRequest (schemas.py) is never referenced anywhere in this file — build_user_prompt_conversational/build_user_prompt_chat_segment take clarification_history but not goal_ids/goal context, so 'Goal context for extraction guidance' (schemas.py comment, line 43-44) is not actually threaded into the prompt text here. The LLM is asked to extract goal_context per-observation (a free-text field in the tool schema, lines 25-28) but is never told what the child's actual active goal IDs/titles are, despite ExtractionRequest.goal_ids existing specifically for that purpose. This looks like an incomplete wiring between ExtractionRequest.goal_ids and the prompt builders."
    - "PROMPT_VERSION is a single global constant (1.0.0) shared by both conversational and CHAT-segment prompt paths — there's no separate versioning if one prompt template changes but not the other, so provenance/audit trails (ExtractionResult.prompt_version, used for 'All model invocations logged with version...') can't distinguish which of the two prompt templates was actually used, only that 'some version of the prompts module' was in effect."
    - "CHAT-format guide (lines 134-140) hardcodes speaker codes (CHI/INV/MOT/FAT) and format conventions with no reference to whatever canonical CHAT-parsing logic exists in the data-pipeline scope (outside this sweep) — potential duplication/drift risk if the actual CHAT parser's format assumptions diverge from what's documented here for the LLM's benefit; not verifiable without reading the data pipeline code, flagged as a cross-scope question."
```

```yaml
- path: src/backend/ml/extraction/schemas.py
  purpose: Pydantic input/output contracts for the extraction-provider interface (the "same ExtractionResult contract" CLAUDE.md requires both providers to share).
  exports:
    - "enum SourceType(str, Enum): CONVERSATIONAL, CHAT_SEGMENT"
    - "class ExtractionRequest(BaseModel): source_type, text, child_id, session_id, contributor_role, observation_date, setting, metadata, goal_ids, clarification_history"
    - "enum ExtractionStatus(str, Enum): SUCCESS, PARTIAL, ABSTAINED, FAILED"
    - "class ExtractionResult(BaseModel): status, observations, provider, model, prompt_version, schema_version='1.0', generated_at, clarification_questions, raw_llm_response, extraction_duration_ms, token_usage"
    - "class ProviderInfo(BaseModel): name, provider_type: Literal['temporary_llm','finetuned_model'], model_id, version, is_available=True"
  dependencies:
    - pydantic: BaseModel, Field
    - src.backend.schemas.observation_schema: ContributorRole, Setting, StructuredObservation (outside ml/ scope)
    - stdlib: enum, datetime (UTC, date, datetime), typing (Literal, Optional)
  data_shapes: "ExtractionRequest carries raw text + app-known metadata (child_id, session_id, contributor_role, observation_date, setting) that per base.py's contract must be echoed back unmodified into StructuredObservation. ExtractionResult wraps a list[StructuredObservation] plus provider/model/prompt_version provenance and optional raw_llm_response/token_usage for audit."
  side_effects: none — pure schema definitions.
  role: "This is the literal 'ExtractionResult contract' CLAUDE.md mandates both providers share — confirmed both temporary_llm.py and finetuned_model.py's type signatures use exactly ExtractionRequest -> ExtractionResult from this file, so the shared-contract claim in CLAUDE.md is accurate as implemented."
  observations:
    - "ProviderInfo.provider_type is a Literal['temporary_llm','finetuned_model'] (line 89) — this hardcodes exactly the two known provider type strings, matching the factory's provider_type dispatch strings in extraction/__init__.py (lines 31-34) exactly. Good consistency; if a third provider type were ever added, both this Literal and the factory would need synchronized updates (no dynamic registry)."
    - "ExtractionResult.raw_llm_response and token_usage are Optional[str]/Optional[dict] with no size/redaction guardrails — raw_llm_response is documented as 'Raw provenance for audit' (line 77) but nothing in this file constrains what ends up there (could include full model chain-of-thought or arbitrarily large payloads); left to callers to manage, not visible whether this is bounded elsewhere."
    - "metadata: dict[str, object] (line 41, 'Source-specific context') is untyped/opaque — no schema for what keys it may contain; only usage clue is that it's declared but not referenced by prompts.py or temporary_llm.py's _build_user_prompt, meaning it may currently be unused/unwired (see also the goal_ids observation in prompts.py)."
```

```yaml
- path: src/backend/ml/extraction/temporary_llm.py
  purpose: The CURRENT working ExtractionProvider implementation — calls the Anthropic Claude API (tool_use / forced tool_choice) to extract a StructuredObservation from either a conversational contributor observation or a CHAT transcript segment.
  exports:
    - class TemporaryLLMExtractionProvider(api_key: str, model: str = "claude-sonnet-4-20250514") with async extract(request) -> ExtractionResult and get_info() -> ProviderInfo
    - module constants _NULL_THRESHOLD=5, _ABSTENTION_CONFIDENCE=0.3
    - module function _now_ms() -> int
  dependencies:
    - anthropic: APIError, AsyncAnthropic (external SDK, network-capable)
    - src.backend.ml.extraction.prompts: EXTRACTION_TOOL_SCHEMA, PROMPT_VERSION, build_system_prompt, build_user_prompt_chat_segment, build_user_prompt_conversational
    - src.backend.ml.extraction.schemas: ExtractionRequest, ExtractionResult, ExtractionStatus, ProviderInfo, SourceType
    - src.backend.schemas.observation_schema: Domain, Modality, Outcome, PromptLevel, StructuredObservation (outside ml/ scope)
    - stdlib: json (imported but see observations — unused), time, datetime (UTC, datetime), typing.Any
  data_shapes: "Takes ExtractionRequest, sends a single Claude messages.create() call with tool_choice forced to 'record_observation', parses the tool_use block's `input` dict into a StructuredObservation (preserving app-known fields from the request verbatim — child_id, session_id, contributor_role, observation_date, setting — and mapping domain/modality/prompt_level/outcome strings to their enum types), and returns an ExtractionResult with status derived from confidence + null-field count heuristics."
  side_effects: "Live network call to the Anthropic API on every extract() invocation (self._client.messages.create(...), line 50-57) — this is the one file in the ml/ scope that performs real external-service I/O. No logging (no `logging` import) — extract()'s failure paths (APIError, generic Exception, lines 89-98) are silently swallowed into a FAILED ExtractionResult rather than logged anywhere, unlike reporting_client.py which does `logger.exception(...)` on its LLM-call failure path."
  role: "This is literally the '[CURRENT]' TemporaryLLMExtractionProvider that CLAUDE.md's architecture diagram names — confirmed as a real, working implementation (not a stub), directly calling `claude-sonnet-4-20250514` by default. It is the only concrete, functioning ExtractionProvider in the codebase today."
  observations:
    - "`import json` (line 5) is never used anywhere in the file body — dead import."
    - "Status-determination heuristics (_determine_status, lines 150-173) are hardcoded magic numbers: _NULL_THRESHOLD=5 nullable fields out of 8 checked triggers ABSTAINED (line 165), confidence < 0.3 triggers ABSTAINED (line 156), and SUCCESS requires only behavior+domain both non-null (lines 168-171) — otherwise PARTIAL. These thresholds are local to this provider and not shared/reused by validation_engine.py's separate confidence thresholds (_CONFIDENCE_THRESHOLD=0.7, _LOW_CONFIDENCE_THRESHOLD=0.4) — i.e. there are two independent, differently-calibrated confidence-threshold schemes (0.3 here vs 0.4/0.7 in validation_engine.py) that a reader must track separately; not necessarily a bug (different layers, different purposes: extraction self-assessment vs. deterministic validation) but a notable overlap/possible-confusion point."
    - "No retry/backoff logic around the Anthropic API call — a single APIError immediately produces a FAILED ExtractionResult (lines 89-93) with no distinction between transient (e.g. rate limit, timeout) vs. permanent errors."
    - "No timeout configured explicitly on AsyncAnthropic(api_key=api_key) (line 42) — relies on SDK defaults."
    - "get_info() (lines 100-107) hardcodes provider name 'temporary_llm_extraction' and version=PROMPT_VERSION (i.e. the prompt version, not a provider/model version) — conflates 'prompt version' with 'provider version' semantically; ProviderInfo.version's intended meaning is ambiguous from the schema alone (schemas.py doesn't clarify), and this is the only concrete implementation to observe, so cannot cross check against finetuned_model.py's convention (which uses version='0.0.0', a literal semver-looking value, not a prompt version) — inconsistent interpretation of the `version` field across the two providers."
    - "This class does not implement/subclass ExtractionProvider (base.py) nominally — it satisfies the Protocol structurally only. No `class TemporaryLLMExtractionProvider(ExtractionProvider):` declaration anywhere, consistent with typing.Protocol usage but means a typo in a method signature wouldn't be caught by inheritance-based type checking, only by whatever static analysis (mypy?) checks Protocol conformance, which isn't verifiable from reading source alone."
```

```yaml
- path: src/backend/ml/reporting_client.py
  purpose: The "Grounded Reporting LLM" — turns a deterministic EvidencePacket into professional progress-report prose sections, with an LLM call plus a fully deterministic non-LLM fallback path, plus post-generation regex-based safety validation against prohibited clinical/diagnostic language.
  exports:
    - REPORTING_SYSTEM_PROMPT: str (module constant, the system prompt used for report generation)
    - PROHIBITED_PATTERNS: list[str] (regex patterns for diagnosis/treatment/causal/prognosis/normalizing/goal-modification language)
    - function validate_report(sections: list[ReportSection], evidence_packet: EvidencePacket) -> list[str] (returns list of validation error strings, empty if clean)
    - class ReportingClient(api_key=None, model=None) with async generate_report(evidence_packet) -> GeneratedReportData
  dependencies:
    - src.backend.config.settings (anthropic_api_key, reporting_model, reporting_prompt_version) — outside ml/ scope
    - src.backend.ml.schemas: EvidencePacket, GeneratedReportData, ReportSection (also implicitly KpiResult, referenced only as a forward-reference type-hint string "KpiResult" at line 232 — see observations)
    - anthropic (imported lazily inside _call_llm, not at module top) — AsyncAnthropic
    - stdlib: json, logging, re, datetime (UTC, datetime)
  data_shapes: "Input: EvidencePacket (child_id, review_period dates, goals, structured_records, analytics: AnalyticsResult, adequacy: AdequacyResult, quality_flags, contributor/setting summaries, counts). Output: GeneratedReportData{child_id, review_period_id, sections: list[ReportSection]{heading, body, evidence_refs, abstention_note}, provider, model, prompt_version, validation_passed, validation_errors}. LLM call expects the model to return a raw JSON array of section dicts (heading/body/evidence_refs/abstention_note) — parsed via json.loads with a regex-array-extraction fallback (lines 180-186) if the model wraps JSON in prose."
  side_effects: "Live network call to Anthropic API in _call_llm() (line 172) when the primary path is used. On ANY exception (not just APIError — a bare `except Exception` at line 139) falls back to a fully deterministic, template-based report (`_build_fallback_sections`), logged via `logger.exception(...)` (line 140). This is the only file in scope with an explicit logging call."
  role: "Implements the 'Reporting LLM' box in CLAUDE.md's AI/ML layer and directly enforces the safety rule 'The reporting LLM MUST NOT produce diagnostic statements, treatment recommendations, or causal claims' via two independent layers: (1) prompt-level instruction (REPORTING_SYSTEM_PROMPT PROHIBITED list, lines 37-46) and (2) a post-hoc regex safety net (validate_report + PROHIBITED_PATTERNS, lines 76-117) that runs on the LLM's actual output regardless of which path (LLM or fallback) produced it. Also directly implements 'Every report statement traces back to source observation' via evidence_refs on each ReportSection, though nothing enforces that evidence_refs are populated/correct beyond what the LLM or fallback code chooses to include."
  observations:
    - "validate_report() only ever collects errors into a list and returns it — GeneratedReportData.validation_passed is set based on `len(validation_errors)==0` (line 164) but NOTHING in generate_report() acts on a failed validation: there is no retry, no rejection, no re-prompt, no abstention when validation fails. A report that trips PROHIBITED_PATTERNS (e.g. contains the word 'delayed' incidentally, which is one of the ALWAYS-matched words at line 81 regardless of context) is still returned to the caller with validation_passed=False and validation_errors populated, but the actual `sections` (potentially containing prohibited language) are returned unmodified. Downstream consumers (outside this scope) must apparently check validation_passed themselves and decide what to do — worth flagging since CLAUDE.md's 'MUST NOT produce diagnostic statements...' safety rule reads as a hard constraint, but this file only detects violations after the fact rather than preventing their delivery to the caller."
    - "PROHIBITED_PATTERNS regexes are blunt substring/word matches (e.g. line 81 `\\b(normal|abnormal|delayed|deficit)\\b` matches ANY occurrence of 'delayed' anywhere in report body text, even in an unobjectionable context like 'the observation was delayed by scheduling' — a false-positive risk, though erring toward over-flagging is arguably the safer failure mode for this domain)."
    - "`_kpi_lookup` static method type-hints its return as `dict[str, \"KpiResult\"]` (line 232) as a forward-reference string, but KpiResult is never actually imported anywhere in this file (only EvidencePacket, GeneratedReportData, ReportSection are imported from ml.schemas at line 16) — this is a broken/unresolvable forward reference; at runtime Python doesn't evaluate string annotations unless something calls `get_type_hints()`, so it won't crash, but static type checkers would flag `KpiResult` as undefined in this module's namespace."
    - "`_call_llm` imports `anthropic` locally inside the method (line 169) rather than at module top, unlike temporary_llm.py which imports AsyncAnthropic/APIError at module level — inconsistent import style between the two files that both call the Anthropic SDK within ml/."
    - "No forced tool_choice/tool_use schema for the reporting call (unlike temporary_llm.py's forced tool_choice) — relies entirely on prompt instruction ('OUTPUT FORMAT: Return a JSON array...', lines 56-72) plus post-hoc json.loads/regex-extraction (lines 180-186) to get structured output, which is a materially weaker structural guarantee than temporary_llm.py's tool_use approach, and is presumably why the fallback path (_build_fallback_sections) exists as a robustness measure — but the fallback is triggered only on exceptions from _call_llm (JSONDecodeError included, since it's raised inside _call_llm at line 185), not on e.g. successfully-parsed-but-schema-invalid section dicts (e.g. `_parse_sections` at lines 188-199 uses `.get()` with defaults for every field, so a malformed section dict degrades silently to empty-string body rather than triggering the fallback)."
    - "Anthropic model call in `_call_llm` has no `tool_choice`/temperature/max_tokens tuning beyond max_tokens=4096 (line 174) — no explicit temperature setting, so this depends on the SDK/model default, which could affect determinism of report wording (though CLAUDE.md doesn't require the *wording* to be deterministic, only that facts/numbers must be reproduced exactly — validate_report doesn't actually check number-for-number fidelity against evidence_packet KPI values, it only checks for prohibited language and abstention acknowledgment; there's no verification that reproduced numbers match the source exactly, despite rule 2 in REPORTING_SYSTEM_PROMPT saying 'Reproduce all pre-computed numbers EXACTLY as provided')."
```

```yaml
- path: src/backend/ml/schemas.py
  purpose: Shared Pydantic data contracts for the ML pipeline's validation, adequacy, analytics, and reporting stages (distinct from src/backend/ml/extraction/schemas.py, which covers only the extraction-provider boundary).
  exports:
    - "enum ValidationSeverity(str,Enum): ERROR, WARNING, INFO"
    - "class FieldValidation(BaseModel): field_name, is_valid, severity, message"
    - "enum RoutingDecision(str,Enum): ACCEPT, CLARIFY, RETAIN_WITH_UNKNOWN, INTERVENTIONIST_REVIEW, REJECT"
    - "class ValidationResult(BaseModel): is_valid, routing, field_validations, clarification_questions, messages"
    - "enum AdequacyLevel(str,Enum): ADEQUATE, LIMITED, INSUFFICIENT"
    - "enum AdequacyCheck(str,Enum): COVERAGE, TIMELINESS, SETTING_REPRESENTATION, CONTRIBUTOR_REPRESENTATION, FIELD_COMPLETENESS, CONSISTENCY, GOAL_COVERAGE, TEMPORAL_DISTRIBUTION"
    - "class AdequacyCheckResult(BaseModel): check, passed, detail, value, threshold"
    - "class AdequacyResult(BaseModel): level, eligible, checks, partial_abstentions, quality_flags"
    - "class KpiResult(BaseModel): name, numerator, denominator, value, prerequisites_met, display_eligible, abstained, abstention_reason"
    - "class AnalyticsResult(BaseModel): child_id, review_period_id, goal_id, kpis, adequacy, computed_at"
    - "class EvidencePacket(BaseModel): child_id, review_period_id, review_period_start, review_period_end, goals, structured_records, record_ids, record_versions, analytics, adequacy, quality_flags, contributor_summary, setting_summary, observation_count, abstained_count, review_count"
    - "class ReportSection(BaseModel): heading, body, evidence_refs, abstention_note"
    - "class GeneratedReportData(BaseModel): child_id, review_period_id, sections, generated_at, provider, model, prompt_version, validation_passed, validation_errors"
  dependencies:
    - pydantic: BaseModel, Field
    - stdlib: enum, datetime (UTC, datetime), typing.Optional
  data_shapes: "This IS the shared data-shape definition file for validation_engine.py, abstention_router.py, adequacy_router.py, analytics_engine.py, and reporting_client.py — all five other non-extraction ml/ files import from here."
  side_effects: none — pure schema definitions.
  role: "Central shared-contract module for the deterministic pipeline stages (validation -> abstention routing -> adequacy -> analytics -> reporting), analogous to how extraction/schemas.py is the shared contract for the extraction-provider boundary. Notably this file is named identically in purpose-pattern to extraction/schemas.py but lives one directory up — two separate 'schemas.py' files in scope with non-overlapping content (confirmed: no symbol name collisions between them)."
  observations:
    - "AdequacyCheck enum declares TIMELINESS and CONSISTENCY (lines 55, 59) that — per the adequacy_router.py review above — are never actually produced by AdequacyRouter.assess(); these two enum members are currently dead/aspirational relative to the one concrete consumer of this enum in scope."
    - "EvidencePacket.structured_records: list[dict[str,object]] (line 112) and record_versions: dict[str,int] (line 114) — the 'versioned Structured Record Store' concept from CLAUDE.md's Data layer is represented here only as an opaque dict[str,int] (record_id -> version number), with no richer version-history type; consistent with CLAUDE.md's principle 'Corrections create new record versions — never overwrite originals' but the actual versioning mechanics (how old versions are retained/looked up) live outside this ml/ scope entirely (likely in a data/model layer not covered by this sweep)."
    - "No `model_config` / `ConfigDict` customization anywhere in this file (e.g. no frozen=True, no extra='forbid') — all these Pydantic models accept arbitrary extra behavior per Pydantic v2 defaults; not necessarily a problem, just notable that none of these contracts are hardened against typo'd/extra fields at construction time."
```

```yaml
- path: src/backend/ml/validation_engine.py
  purpose: "Deterministic validation engine for StructuredObservation records — explicit module docstring: 'no LLM involvement.' Checks enum validity, critical-field presence, cross-field consistency, goal-context plausibility, confidence range, and overall completeness, then derives a RoutingDecision."
  exports:
    - class ValidationEngine with method validate(observation, goal_ids=None) -> ValidationResult
    - private static methods: _validate_enums, _validate_critical_fields, _validate_cross_field, _validate_goal_context, _validate_confidence, _validate_completeness, _determine_routing
    - module constants: _CONFIDENCE_THRESHOLD=0.7, _LOW_CONFIDENCE_THRESHOLD=0.4, _CRITICAL_FIELDS={"behavior","domain"}, _IMPORTANT_FIELDS={"modality","prompt_level","outcome"}, _VERBAL_KEYWORDS (frozenset of ~15 words)
  dependencies:
    - src.backend.ml.schemas: FieldValidation, RoutingDecision, ValidationResult, ValidationSeverity
    - src.backend.schemas.observation_schema: LLM_EXTRACTED_FIELDS, Domain, Modality, Outcome, PromptLevel, StructuredObservation (outside ml/ scope)
  data_shapes: "Input: StructuredObservation (pydantic model with domain/modality/prompt_level/outcome enums, behavior/prompt_context/goal_context strings, confidence float, etc.) plus optional goal_ids: list[str]. Output: ValidationResult{is_valid, routing: RoutingDecision, field_validations: list[FieldValidation], messages: list[str]}."
  side_effects: none — pure computation, matches docstring's 'no LLM involvement' claim.
  role: "Implements the 'Deterministic Validation Engine' box in CLAUDE.md's AI/ML layer and the safety rule 'LLM outputs pass through deterministic validation before persistence.' Sits directly downstream of TemporaryLLMExtractionProvider.extract() and upstream of AbstentionRouter.route() — the ValidationResult produced here is one of the two inputs AbstentionRouter.route() consumes (the other being the raw ExtractionResult)."
  observations:
    - "_CRITICAL_FIELDS ({'behavior','domain'}) and the question-template fields in abstention_router.py's _CRITICAL_FIELDS are literally duplicated as separate frozenset literals in two different files (validation_engine.py line 22 and abstention_router.py line 14) with identical values — same conceptual constant defined twice rather than shared from one location (e.g. ml/schemas.py). If one were updated without the other, the two files would silently diverge on what counts as 'critical.'"
    - "_determine_routing (lines 179-222) is a layered decision function: REJECT if both critical fields missing (line 198) > INTERVENTIONIST_REVIEW if any ERROR-severity validation failed OR confidence < 0.4 (lines 201-205) > CLARIFY if any critical field missing OR more than 1 WARNING (line 207) > RETAIN_WITH_UNKNOWN if any important field missing OR confidence < 0.7 (lines 210-220) > else ACCEPT. This is a nontrivial, undocumented-outside-code decision table; worth flagging as a candidate for an explicit spec/comment given how much downstream behavior (abstention routing, review queues) depends on getting this exactly right."
    - "_validate_cross_field's verbal-modality check (lines 103-114) is a WARNING-severity heuristic keyword match against _VERBAL_KEYWORDS — a fairly blunt lexical check (e.g. behavior text containing 'wordless' would false-positive-match 'word' as a substring keyword — actually `in` check here is on whole-word split? No: `any(kw in behavior_lower for kw in _VERBAL_KEYWORDS)` at line 108 is a plain substring `in` check on the full lowercased string, not tokenized — so 'wordless' contains 'word' and would be treated as a verbal-keyword match even though it may describe the opposite; a minor false-negative-avoidance risk in the validator, i.e. it would fail to flag some genuinely non-verbal-but-'word'-containing text as inconsistent)."
    - "_validate_goal_context (lines 136-149) only checks `observation.goal_context not in goal_ids` as a plain containment test in a caller-supplied list[str] — no fuzzy matching or ID-normalization; if goal_ids passed in have different casing/whitespace than the LLM-extracted goal_context free-text field (which per prompts.py is an LLM-generated free-text description, not a structured ID — see EXTRACTION_TOOL_SCHEMA's goal_context description 'Goal or objective the observation relates to, if identifiable', prompts.py line 27), this check would almost always fail/mismatch since goal_context is natural-language text while goal_ids are presumably actual goal IDs — this looks like a real semantic mismatch: the validator compares a free-text LLM description against a list of goal ID strings, which would essentially never match unless the LLM happens to emit an exact goal ID. Flagging as a likely functional gap rather than a mere style note, though full confirmation would require seeing how goal_ids is populated by call sites outside this scope."
```
