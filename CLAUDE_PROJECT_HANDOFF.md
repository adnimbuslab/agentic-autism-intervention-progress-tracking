# Claude Handoff --- Secure RAG Longitudinal Autism Intervention Support Project

## 1. Purpose of This File

This document is a technical/research handoff for continuing development
of a proposed **interventionist-led, governance-aware AI system for
longitudinal autism intervention support**.

The project is **not intended to diagnose autism, prescribe treatment,
or autonomously change intervention goals**. The interventionist remains
the decision-maker. AI is used to improve observation collection,
structure longitudinal evidence, support analytics, and explain progress
trajectories.

## 2. Core Research Problem

Parents, teachers, and intervention staff generate useful
natural-language observations about a child's progress, but those
observations are often heterogeneous and unstructured. This makes
longitudinal review against interventionist-defined goals difficult.

The proposed system creates a closed loop:

**Interventionist-defined goal → goal-aware observation collection → raw
observation preservation → secure RAG-assisted structured extraction →
deterministic validation → longitudinal analytics → goal-attainment
trajectory → evidence-grounded explanation → interventionist review.**

## 3. Actors

-   **Interventionist:** creates and manages long-term and short-term
    goals; defines attainment criteria; reviews AI outputs; makes final
    decisions.
-   **Parent/Caregiver:** contributes observations from home/community
    settings.
-   **Teacher:** contributes observations from educational settings.
-   **System/AI:** asks goal-relevant follow-up questions, structures
    observations, calculates analytics, and presents evidence-linked
    projections.

## 4. End-to-End Architecture

``` text
                    INTERVENTIONIST
                           |
             Defines Long/Short-Term Goal
             + measurable attainment criteria
                           |
                           v
                 Goal / Knowledge Store
              - active goal definition
              - success criteria
              - prompt taxonomy
              - approved terminology
              - interventionist guidance
                           |
                           v
Parent / Teacher ---> Observation Screen
                           |
                           v
               Authentication + Authorization
              - organization/tenant scope
              - user role
              - authorized child
              - active goal
                           |
                           v
                     SECURE RAG
              - active goal context
              - approved guidelines
              - permitted relevant history
              - schema/definitions
              - curated examples
                           |
                           v
                   Goal-Aware LLM Chat
              asks relevant follow-up questions
                           |
                           v
                    RAW DATA STORE
              original observation preserved
                           |
                           v
              STRUCTURED EXTRACTION PIPELINE
                  Secure RAG context
                         +
                extraction model / LLM
                         +
               deterministic validation
                           |
                           v
                 Structured Observation
                           |
                           v
               Longitudinal Feature Engine
              - independence rate
              - prompting dependency
              - observation frequency
              - setting consistency
              - temporal trend
              - rolling performance
                           |
                           v
                Goal Trajectory Analytics
                           |
                           v
              Probable Goal-Attainment Window
                           |
                           v
                Secure Evidence Retrieval
                           |
                           v
                 RAG-Based Explanation
                           |
                           v
                    INTERVENTIONIST
             Accept / reject / modify / review
```

## 5. Module A --- Goal Definition

The interventionist should define each short-term goal before
observation collection.

Suggested goal fields:

``` json
{
  "goal_id": "G123",
  "child_id": "PSEUDONYMIZED_ID",
  "domain": "functional_communication",
  "target_skill": "requesting",
  "goal_description": "Independently request a preferred item",
  "target_threshold": 0.80,
  "required_settings": 2,
  "required_consecutive_periods": 3,
  "allowed_prompt_types": ["verbal", "gestural", "physical"],
  "status": "active"
}
```

The interventionist, not the LLM, owns the goal and attainment
definition.

## 6. Module B --- Goal-Aware Observation Collection

When a parent or teacher opens the observation screen, the system
retrieves only authorized context for the selected child and active
goal.

Example goal:

> Child will independently request a preferred item in 4 of 5
> opportunities across two settings.

The LLM can ask targeted questions such as:

-   Did the child have an opportunity to request something today?
-   Did the child request independently?
-   Was a prompt required?
-   If prompted, what type of prompt was used?
-   How many opportunities did you observe?
-   What was the setting?

### Important constraint

The LLM must **not invent an observation or convert an unanswered
question into evidence**. The contributor's original natural-language
response must be preserved unchanged.

## 7. Raw Observation Data Model

Minimum proposed record:

``` json
{
  "observation_id": "OBS001",
  "child_id": "PSEUDONYMIZED_ID",
  "goal_id": "G123",
  "observer_role": "parent",
  "setting": "home",
  "observation_timestamp": "...",
  "raw_text": "During dinner he asked for juice twice without help...",
  "source": "guided_observation_chat"
}
```

Raw evidence should remain available even after structured extraction so
every AI-derived field can be traced back to source evidence.

## 8. Module C --- Secure RAG

RAG should not function as unrestricted search over all children or all
records.

Use **role-aware, child-scoped, goal-scoped retrieval**.

Before vector retrieval, the backend authorization layer determines:

``` text
organization_id
user_id
role
permitted_child_id(s)
goal_id
permitted_document/data types
```

Retrieval must apply these constraints before results are passed to the
LLM.

Conceptually:

``` text
WHERE organization_id = authorized_org
  AND child_id = authorized_child
  AND goal_id = active_goal
  AND access_policy_allows(user_role, resource) = TRUE
```

The LLM must never be responsible for deciding authorization.

### Recommended storage separation

**Authoritative Data Store**

Contains encrypted raw and structured observations and other
authoritative records.

**Retrieval Index / Vector Store**

Prefer pseudonymized/minimized content and metadata such as:

``` text
pseudonymous_child_id
goal_id
observation_id
document_type
embedding
permitted_role metadata
```

Avoid putting unnecessary direct identifiers into embeddings/vector
records.

### Secure RAG use cases

1.  **Observation Guidance RAG** --- retrieves active goal,
    interventionist guidance, definitions, and permitted recent context
    to generate better follow-up questions.
2.  **Extraction RAG** --- retrieves schema definitions, prompt
    taxonomy, approved examples, and goal context to support consistent
    extraction.
3.  **Explanation RAG** --- retrieves source observations underlying
    analytics/forecasting so interventionists can see why a trajectory
    was produced.

## 9. Module D --- Observation-to-Structure Extraction

Example raw text:

> During dinner he asked for juice by himself twice. Later I reminded
> him to ask for crackers.

Possible target representation:

``` json
{
  "goal_domain": "functional_communication",
  "target_skill": "requesting",
  "setting": "home",
  "opportunities": 3,
  "independent_count": 2,
  "prompted_count": 1,
  "prompt_type": "verbal",
  "evidence_spans": [
    "asked for juice by himself twice",
    "I reminded him to ask for crackers"
  ],
  "extraction_confidence": 0.0
}
```

Do not force fields when evidence is absent. Use explicit `unknown`,
`null`, or review-required states where appropriate.

## 10. Why Train a Model?

Training is **not required simply because the system contains AI**.

A foundation LLM + secure RAG can initially perform guided questioning
and baseline extraction. Training is useful when the research task
requires repeatable domain-specific mapping from heterogeneous
observation language into an exact interventionist-approved schema.

In simple terms:

-   **RAG tells the model what relevant information/context to look
    at.**
-   **Training teaches the model how observations should be mapped into
    the project's schema.**
-   **Deterministic validation checks whether the extracted
    representation obeys explicit rules and remains supported by
    evidence.**

The primary model-development contribution should therefore be the
**observation-to-structure extraction task**, rather than attempting to
train a large general-purpose clinical LLM.

## 11. Proposed Extraction Training Dataset

Training unit:

``` text
Input  = natural-language observation + permitted goal context
Target = expert/interventionist-approved structured annotation
```

Suggested columns:

``` text
Observation_ID
Child_ID
Goal_ID
Observer_Role
Setting
Observation_Text

--- expert labels ---

Domain
Target_Skill
Opportunity_Count
Independent_Count
Prompted_Count
Prompt_Type
Behavior/Outcome
Context
Evidence_Span(s)
Annotation_Confidence
```

### Ground truth

Whenever possible, structured ground truth should come from trained
domain annotators/interventionists using a documented annotation
protocol.

Do not automatically treat an LLM-generated structure as ground truth.

## 12. Rollins / Flusberg Data

Existing Rollins/Flusberg resources may be useful for
communication/language patterns, vocabulary, task/schema development, or
development of examples **depending on the exact variables and
licensing/consent conditions in those datasets**.

Do not claim that these datasets directly train a longitudinal
intervention-goal predictor unless their data and labels actually
support that task.

Preferred conceptual use:

``` text
Existing ASD/language resources
          |
          v
Domain vocabulary / pattern analysis
          |
          v
Target schema + annotation guideline development
          |
          v
Real observation text
          |
          v
Expert annotation
          |
          v
Extraction training/evaluation dataset
```

## 13. Extraction Experiments

Recommended comparison:

``` text
Baseline A: deterministic/rule-based extraction
Baseline B: foundation LLM zero-shot
Baseline C: foundation LLM + secure RAG
Model D: fine-tuned extraction model
Model E: fine-tuned model + secure RAG + deterministic validation
```

Potential evaluation metrics:

-   field-level precision
-   field-level recall
-   field-level F1
-   exact structured-record match
-   evidence-span accuracy
-   unsupported extraction rate
-   missing-information handling
-   inter-annotator agreement for human ground truth

### Unsupported Extraction Rate

This is particularly important for safety.

If the observation never states that a physical prompt occurred but the
system outputs `prompt_type = physical`, that is an unsupported
extraction and should be measured explicitly.

## 14. Data Splitting

**Do not randomly split individual observations if observations from the
same child can enter multiple partitions.**

Use child-level separation, for example:

``` text
70% children -> training
15% children -> validation
15% children -> held-out testing
```

No child in the held-out test set should appear in training.

If temporal forecasting is evaluated, also design the split to prevent
future information from leaking into past prediction points.

## 15. Deterministic Validation Layer

The extraction model should not be the final authority.

Example checks:

``` text
independent_count >= 0
prompted_count >= 0
independent_count + prompted_count <= known opportunities
prompt_type must be from approved taxonomy
required evidence span must exist in raw observation
child_id and goal_id cannot be changed by model output
unknown information cannot be fabricated
```

Conflicting, unsupported, or low-confidence records should be routed to
human review.

## 16. Longitudinal Feature Layer

Once observations are structured, aggregate them by:

``` text
Child -> Goal -> Review Period -> Setting
```

Potential features:

-   independent performance rate
-   prompted performance rate
-   prompt dependency
-   observation count
-   rolling mean
-   temporal slope/change
-   home performance
-   school performance
-   intervention-session performance
-   cross-setting consistency
-   days since goal start
-   number of consecutive periods satisfying criterion

## 17. Goal-Attainment Forecasting

Do **not** initially oversell this as a clinical prediction model if
sufficient longitudinal labeled data do not exist.

### Phase 1 --- Transparent deterministic trajectory

Example:

``` text
Goal threshold = 80%
Current rolling performance = 62%
Recent slope = +4.5 percentage points/week

Simple projected crossing time:
(80 - 62) / 4.5 ~= 4 weeks
```

Present this as a trajectory estimate conditional on the recent trend,
with uncertainty and limitations.

The graph should distinguish:

-   observed values
-   interventionist-defined threshold
-   fitted trend
-   projected trajectory
-   estimated attainment window

### Phase 2 --- ML forecasting, only with adequate data

Possible comparison:

``` text
Deterministic trend baseline
vs
Linear / logistic models
vs
Random Forest
vs
XGBoost
vs
Temporal model (only if justified by dataset size)
```

Possible outcomes:

``` text
Probability of goal attainment within N weeks
or
Estimated time-to-goal / attainment interval
```

A simpler interpretable model should be preferred if performance is
comparable to a complex model.

## 18. Evidence-Grounded Explanation

When an interventionist asks why the system estimates a particular
trajectory, Secure RAG should retrieve the authorized observations
underlying the calculation.

Example explanation style:

> The projected trajectory is associated with increasing independent
> requesting across recent review periods and reduced verbal prompting.
> Performance in the school setting remains below the
> interventionist-defined threshold, so the goal is not yet considered
> attained.

Every important claim should be traceable to underlying
observations/analytics rather than generated from model memory.

## 19. Governance / Safety Requirements

Core controls:

1.  Authentication and backend authorization before retrieval.
2.  Organization/tenant isolation.
3.  Role-aware access.
4.  Child-scoped retrieval.
5.  Goal-scoped retrieval where applicable.
6.  Data minimization/pseudonymization in retrieval indexes.
7.  Encryption in transit and at rest.
8.  Raw observation preservation.
9.  Evidence-linked structured extraction.
10. Deterministic validation.
11. Retrieval and generation audit logging.
12. Prompt-injection-aware design: retrieved/user text must not override
    authorization policy.
13. Human review for uncertain/unsupported output.
14. Interventionist retains authority over goals and decisions.
15. No autonomous diagnosis, treatment prescription, or goal
    modification.

Any production/clinical deployment would additionally require
appropriate privacy, security, consent, institutional, and regulatory
review; do not infer compliance merely from the architecture.

## 20. Research Positioning

The project should not be described simply as an "autism chatbot" or
"RAG application."

The research concept is approximately:

> **An interventionist-led, secure, evidence-grounded AI framework for
> guided acquisition, structured extraction, and longitudinal analysis
> of multi-observer autism intervention observations.**

The strongest contribution hierarchy currently is:

### Primary contribution

Secure RAG-assisted and interventionist-aligned transformation of
heterogeneous observation text into structured longitudinal evidence.

### Secondary contribution

Goal-aware LLM dialogue that guides parents/teachers toward more
complete observations without inventing evidence.

### Exploratory contribution

Transparent goal-attainment trajectory estimation/forecasting.

### Governance contribution

Role/child/goal-scoped retrieval, data minimization, deterministic
validation, evidence traceability, auditability, and mandatory
interventionist oversight.

## 21. Proposed Research Questions

Possible RQs to refine:

**RQ1:** How accurately can AI models transform heterogeneous
caregiver/teacher observation text into an interventionist-defined
structured schema?

**RQ2:** Does retrieval of goal-specific definitions and approved
examples improve extraction accuracy and reduce unsupported extraction
compared with zero-shot LLM extraction?

**RQ3:** Does deterministic post-validation further reduce unsupported
or internally inconsistent structured outputs?

**RQ4:** Can goal-aware conversational guidance improve completeness of
observation records without increasing unsupported information?

**RQ5 (exploratory):** How well do transparent longitudinal trajectory
methods estimate interventionist-defined goal attainment compared with
simple ML baselines when sufficient longitudinal data are available?

## 22. Immediate Next Steps for Claude

Do **not** redesign the architecture from scratch before resolving the
data methodology.

Priority work:

1.  Inspect the available Rollins and Flusberg datasets and document
    exactly what fields, longitudinal structure, observation text,
    labels, participant structure, and licensing constraints exist.
2.  Determine precisely what portions can support this project and what
    cannot.
3.  Finalize the target structured observation schema.
4.  Draft a formal annotation guideline with definitions for
    independence, prompted response, prompt type, opportunity, setting,
    target behavior/skill, missing data, ambiguity, and evidence spans.
5.  Define the ground-truth annotation process and inter-annotator
    agreement procedure.
6.  Define training/validation/test construction with strict child-level
    separation.
7.  Specify the Secure RAG metadata/filtering architecture.
8.  Specify baseline extraction experiments and evaluation metrics.
9.  Keep forecasting deterministic/exploratory until the available
    longitudinal data justify model training.
10. Only after the above, finalize implementation architecture and
    manuscript Methods sections.

## 23. Critical Principles Claude Should Preserve

-   Never conflate **RAG** with **model training**.
-   Never use synthetic/LLM-generated labels as unquestioned ground
    truth.
-   Never allow the LLM to enforce its own access control.
-   Never expose one child's records through another child's retrieval
    context.
-   Never discard the original observation after extraction.
-   Never claim a field that is not supported by source evidence.
-   Never mix observations from the same child across train and test
    partitions.
-   Never call a trend projection a validated clinical prediction unless
    validation supports that claim.
-   Never allow the model to autonomously modify interventionist-defined
    goals.
-   Keep the interventionist as the final human authority.

## 24. Current Project Decision

The architecture is sufficiently defined for now. **The next bottleneck
is data and ground-truth design, not adding more AI components.**

Focus first on:

**available data -\> exact schema -\> annotation protocol -\> ground
truth -\> leakage-safe dataset -\> extraction experiments -\> secure RAG
evaluation -\> longitudinal analytics.**
