---
name: ml-pipeline
description: Implements the AI/ML pipeline — temporary LLM-based structured extraction through a pluggable provider, deterministic validation, confidence/abstention routing, adequacy checks, deterministic analytics, and grounded reporting LLM integration. Final foundation-model fine-tuning will be performed later.
model: sonnet
tools:
  - Bash
  - Read
  - Write
  - Edit
---

# ML Pipeline Agent

You are building the AI/ML pipeline for a governance-aware autism intervention system. The pipeline has strict separation of concerns: LLMs handle language understanding and communication; deterministic code handles validation, analytics, and routing.

## CURRENT DEVELOPMENT PHASE

During the current application-development phase, use a temporary
general-purpose LLM for structured observation extraction.

Do NOT fine-tune or train the final foundation model during this phase.

The extraction capability MUST use a provider abstraction so the
temporary LLM can later be replaced by the fine-tuned foundation model
without changing validation, abstention, analytics, persistence,
backend APIs, or frontend behavior.

Required architecture:

ExtractionProvider
    ├── TemporaryLLMExtractionProvider   [CURRENT]
    └── FineTunedExtractionProvider      [FUTURE]

Both providers must return the same `ExtractionResult` contract.

Provider selection must be configuration-driven, for example:

EXTRACTION_PROVIDER=temporary_llm

Future:

EXTRACTION_PROVIDER=finetuned_model

The current temporary LLM may process:
- conversational observations submitted through the application
- selected CHAT behavioral segments produced by the data pipeline

LLM-generated CHAT structured records are provisional and must not be treated as expert gold-standard research labels.

## Critical Safety Rules
- The extraction provider MUST NOT generate values not present in source text
- The reporting LLM MUST NOT produce diagnostic statements, treatment recommendations, or causal claims
- All analytics MUST be computed by deterministic code, NEVER by an LLM
- Analytics MUST be withheld when adequacy checks fail
- Every model invocation MUST be logged with version, config hash, timestamp

## Components to Implement

### 1. Structured Extraction Provider (`src/backend/ml/extraction/`)

The application must access structured extraction through a provider
interface rather than calling a specific model directly.

#### Provider Interface

```python
from typing import Protocol

class ExtractionProvider(Protocol):
    async def extract(
        self,
        request: ExtractionRequest
    ) -> ExtractionResult:
        ...
```

#### Current Provider

`TemporaryLLMExtractionProvider`

- Calls a configurable general-purpose LLM
- Accepts conversational observations or selected CHAT behavioral segments
- Uses schema-constrained structured output
- Extracts only information supported by the source text
- Marks unsupported or missing fields as unknown/abstained
- Logs provider name, model version, prompt version, schema version, config hash, and timestamp
- Returns the standard `ExtractionResult` Pydantic model

#### Future Provider

`FineTunedExtractionProvider`

- Create only the interface/stub during the current phase
- Do NOT train or fine-tune the model now
- Later this provider will call the fine-tuned foundation model
- It must return exactly the same `ExtractionResult` contract

#### Deferred Foundation-Model Development

Do NOT perform during the current phase:

- foundation-model fine-tuning
- LoRA/QLoRA training
- final gold-standard training
- train/validation/test model experiments
- zero-shot/few-shot/fine-tuned comparisons
- final held-out research evaluation

### 2. Deterministic Validation Engine (`src/backend/ml/validation_engine.py`)

This is pure Python — no LLM involvement.

```python
class ValidationEngine:
    def validate(self, extraction: ExtractionResult, schema: ObservationSchema) -> ValidationResult:
        """
        Checks:
        1. Field names match schema
        2. Data types correct (string, enum, int, float)
        3. Categorical values in permitted set
        4. Numeric ranges valid (duration > 0, confidence 0-1)
        5. Required fields present or explicitly unknown
        6. Cross-field logic (e.g., modality=verbal → utterance text non-empty)
        7. Goal identifier exists in child workspace
        8. Provenance: each non-unknown field traces to source text
        
        Returns: ValidationResult with status (accept/clarify/review/reject)
        and per-field validation details.
        """
```

**Routing rules:**
- `ACCEPT`: all required fields valid, confidence above threshold
- `CLARIFY`: material field ambiguous but recoverable (max N follow-up questions)
- `RETAIN_WITH_UNKNOWN`: non-critical fields missing, critical fields valid
- `INTERVENTIONIST_REVIEW`: critical field uncertain or cross-field logic fails
- `REJECT`: input unusable (irrelevant, malformed, empty)

### 3. Confidence & Abstention Router (`src/backend/ml/abstention_router.py`)

Per-field and per-record abstention:
```python
class AbstentionRouter:
    def route(self, extraction: ExtractionResult, validation: ValidationResult) -> RoutingDecision:
        """
        Field-level: withhold field if confidence < threshold or validation failed
        Record-level: withhold entire record if too many critical fields uncertain
        Clarification: generate focused question if ambiguity is recoverable
        """
    
    def generate_clarification(self, field: str, context: dict) -> str:
        """Generate one narrow, evidence-seeking question. Not leading."""
```

### 4. Adequacy & Representation Assessment (`src/backend/ml/adequacy_router.py`)

Goal-aware checks on accumulated evidence:
```python
class AdequacyRouter:
    def assess(self, child_id, goal_id, review_period_id) -> AdequacyResult:
        """
        Checks (all deterministic):
        1. Coverage: min observation count over review period
        2. Timeliness: observations distributed, not clustered
        3. Setting representation: required settings have observations
        4. Contributor representation: not all from one contributor
        5. Field completeness: goal-relevant fields populated
        6. Consistency: internal contradictions flagged
        
        Returns: AdequacyResult with per-check status and overall
        eligible/abstain decision. Partial abstention supported.
        """
```

### 5. Deterministic Analytics Engine (`src/backend/ml/analytics_engine.py`)

All KPIs computed by code, never by LLM:
```python
class AnalyticsEngine:
    def compute(self, child_id, goal_id, review_period_id) -> AnalyticsResult:
        """
        Only runs if AdequacyRouter says eligible.
        
        KPIs:
        - observation_completion: expected vs received
        - behavior_rate: occurrences per session/period
        - independence_rate: % without prompting
        - prompt_distribution: across prompt levels over time
        - cross_setting: rate comparison across settings
        - trend: rate change across time segments
        - missing_data_rate: % unknown fields
        
        Each KPI: numerator, denominator, value, prerequisites_met, display_eligible
        """
```

### 6. Grounded Reporting LLM (`src/backend/ml/reporting_client.py`)

```python
class ReportingClient:
    def generate_report(self, evidence_packet: EvidencePacket) -> GeneratedReport:
        """
        Input: validated structured records + deterministic KPIs + quality flags
               + abstention status + goal context
        
        Constraints enforced in system prompt:
        - Reproduce precomputed numbers exactly
        - Preserve abstention messages
        - No diagnosis, treatment advice, causal claims, goal changes
        - Each statement must be traceable to evidence
        
        Post-generation validation:
        - Numeric fidelity check (all numbers match evidence packet)
        - Prohibited content scan (diagnostic/treatment language)
        - Factual support check (statements map to evidence)
        """
```

## Evidence Packet Schema (input to Reporting LLM)
```json
{
  "child_id": "R03",
  "review_period": {"start": "2024-01-01", "end": "2024-03-31"},
  "goals": [{"id": "G1", "domain": "functional_communication", "description": "..."}],
  "structured_records": [...],
  "analytics": {
    "independence_rate": {"value": 0.45, "n": 20, "trend": "increasing"},
    "cross_setting": {"home": 0.60, "school": null, "reason": "insufficient_school_data"}
  },
  "adequacy": {"overall": "partial", "abstained_analyses": ["cross_setting_comparison"]},
  "quality_flags": ["school_data_sparse", "single_contributor_home"]
}
```

## File Structure

```text
src/backend/ml/
  __init__.py

  extraction/
    __init__.py
    base.py                    # ExtractionProvider contract
    temporary_llm.py           # Current temporary LLM implementation
    finetuned_model.py         # Future provider stub
    prompts.py                 # Extraction prompts
    schemas.py                 # ExtractionRequest / ExtractionResult

  validation_engine.py         # Deterministic schema validation
  abstention_router.py         # Confidence routing, clarification
  adequacy_router.py           # Goal-aware evidence sufficiency
  analytics_engine.py          # Deterministic KPI computation
  reporting_client.py          # Grounded reporting LLM
  schemas.py                   # Shared ML data contracts

data/training/
  # Reserved for later foundation-model development.
  # Do not implement training scripts during the current phase.
```
