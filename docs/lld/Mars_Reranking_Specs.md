# MARS — Multi-LLM-Augmented Reranking — EARS Specs

Owning design: [Mars_Reranking.md](./Mars_Reranking.md). Prefix: `MARS`.

Scope note: these specs cover the `MarsExtractionProvider` component only — candidate
generation across wrapped providers, multi-LLM reranking, deterministic fusion, and the
abstention conditions internal to that component. They do **not** cover deterministic
validation, per-observation abstention routing, persistence, or analytics, each of which
owns its own specs and consumes MARS output exactly as it consumes any other
`ExtractionProvider` output.

Scope of the determinism guarantees: MARS provides **deterministic orchestration replay**, not deterministic
LLM inference. Re-execution reproduces the same candidate set, aliases, presentation order, seeds, judge
assignment, and fusion arithmetic (MARS-033). It does not reproduce a judge's *answer* unless the inference
backend itself guarantees that, which MARS neither controls nor claims. MARS-014 is therefore stated over
stored judge rankings rather than over re-executed judge calls.

Specs marked `[x]` are implemented and cited by a test; `[ ]` are designed but not yet built.

## Contract

- [x] **MARS-001**: The `MarsExtractionProvider` shall satisfy the `ExtractionProvider` protocol, accepting an `ExtractionRequest` and returning an `ExtractionResult`, so that consuming layers require no modification to use it in place of a single-model provider. — `tests/phase4/test_mars_provider.py::TestConfiguration`, `tests/phase4/test_mars_provider.py::TestFullPipeline`

- [x] **MARS-002**: The `MarsExtractionProvider` shall not validate, persist, or route its own output; MARS output shall pass through the Deterministic Validation Engine on the same path as any other extraction-provider output. — `tests/phase4/test_mars_provider.py::TestConfiguration::test_provider_satisfies_the_extraction_contract`

## Candidate Generation

- [x] **MARS-003**: The system shall request an extraction from every configured candidate provider for the same source text. Each admitted provider response shall contribute **at most one** candidate, taken from `observations[0]`, consistent with EXTRACT-003. MARS shall not interpret additional elements of `observations`. — `tests/phase4/test_mars_candidates.py::TestFirstObservationOnly`

- [x] **MARS-029**: The system shall admit a provider response as a candidate only where its `status` is neither `FAILED` nor `ABSTAINED`, its `observations` list is non-empty, and `observations[0]` passes the required structural checks. A response failing any of these shall be discarded and the discard recorded in provenance. "Admitted candidate" as used throughout these specs means a candidate that passed this predicate. — `tests/phase4/test_mars_candidates.py::TestAdmission`

- [x] **MARS-004**: The system shall collapse admitted candidates whose extracted field values are all equal into a single candidate that retains the **complete set** of generator identities that produced it, together with a multiplicity count equal to that set's size. A merged candidate's generator provenance shall never be reduced to a single representative generator. — `tests/phase4/test_mars_candidates.py::TestDeduplication`, `tests/phase4/test_mars_candidates.py::TestFingerprint`, `tests/phase4/test_mars_candidates.py::TestGeneratorProvenance`

- [x] **MARS-005**: If the number of admitted candidates (MARS-029) is zero, then the system shall abstain with `reason_code=no_reviewable_candidate`. — `tests/phase4/test_mars_envelope.py::TestProvenanceDescribesWhatHappened::test_abstention_before_judging_carries_empty_judge_fields`

- [x] **MARS-006**: If exactly one distinct candidate remains after deduplication, then the system shall skip reranking and select that candidate without invoking any judge and without applying the eligible-judge requirement of MARS-028. Skipping reranking shall not skip the output-integrity verification of MARS-017; a sole candidate that fails that verification shall abstain under MARS-018 rather than be returned. On this path the system shall not synthesize judge-derived selection evidence; control confidence therefore remains unavailable unless another explicitly defined and validated confidence mechanism exists, and the system shall declare that unavailability rather than omit it (VALID-015). — `tests/phase4/test_mars_provider.py::TestShortCircuit`

## Reranking

- [x] **MARS-007**: The system shall assign each candidate a stable internal identifier not visible to judges, and shall present candidates to each judge under **per-judge opaque aliases** that carry no provider attribution and no cross-judge correspondence. The system shall map aliases back to internal identifiers on receipt of each judge's response. — `tests/phase4/test_mars_blinding.py::TestJudgePresentation`, `tests/phase4/test_mars_blinding.py::TestNoInformationLeakage`

- [x] **MARS-008**: The system shall derive, rather than draw, the seeds governing per-judge alias assignment and presentation order: a request seed from the source identity, the MARS version, a fingerprint of the admitted candidate set, and a configured run seed; and a per-judge seed from the request seed and that judge's model identity. All derived seeds and the configured run seed shall be recorded in provenance. — `tests/phase4/test_mars_blinding.py::TestSeedDerivation`, `tests/phase4/test_mars_blinding.py::TestCandidateSetFingerprint`

- [x] **MARS-033**: Where the same source text, admitted candidate set, configuration, MARS version, and configured run seed are supplied, the system shall produce identical per-judge alias assignments and identical presentation orders. — `tests/phase4/test_mars_blinding.py::TestJudgePresentation::test_presentation_is_invariant_to_candidate_input_order`

- [x] **MARS-009**: The system shall accept from a judge only an ordering over the presented candidate labels, and shall have no code path that reads a structured field value from a judge response. — `tests/phase4/test_mars_fusion.py::TestResponseValidation`

- [x] **MARS-010**: If a judge response references a label that was not presented, omits a presented label, or cannot be parsed as an ordering, then the system shall discard that response as invalid and shall record the discard in the result's provenance. — `tests/phase4/test_mars_fusion.py::TestResponseValidation`

- [x] **MARS-011**: If the number of valid judge rankings is below `min_valid_judge_responses`, then the system shall abstain with `reason_code=insufficient_valid_judge_responses` rather than fusing the rankings that remain. `min_valid_judge_responses` and `min_eligible_judges` (MARS-028) are distinct configuration values governing distinct stages, and neither shall be derived from the other. — `tests/phase4/test_mars_fusion.py::TestResponseCount`

- [x] **MARS-027**: A judge shall be ineligible for a candidate set where its model identity appears in the complete generator provenance of **any** candidate in that set, including generator identities merged during deduplication under MARS-004. Candidate provenance shall not be exposed to judges during ranking. Same-family (non-identical) generator/judge overlap is permitted and shall be recorded under MARS-020 rather than prohibited. — `tests/phase4/test_mars_safety.py::TestJudgeIndependence`

- [x] **MARS-028**: Where two or more admitted candidates require reranking, if the configured roster cannot supply `min_eligible_judges` judges after applying the independence constraint of MARS-027, then the system shall abstain with `reason_code=insufficient_eligible_judges` rather than relaxing that constraint. This requirement shall not apply on the single-candidate path of MARS-006. — `tests/phase4/test_mars_safety.py::TestRosterSufficiency`

## Fusion

- [x] **MARS-012**: The system shall compute each candidate's fused score from the valid judge rankings by Reciprocal Rank Fusion, in deterministic code, with no model invoked to perform or adjudicate the aggregation. — `tests/phase4/test_mars_fusion.py::TestReciprocalRankFusion`

- [x] **MARS-013**: Where two or more candidates share the highest fused score, the system shall break the tie by descending multiplicity, and shall break a remaining tie by ascending **stable internal candidate identifier**. The judge-visible alias of MARS-007 shall never participate in tie resolution. — `tests/phase4/test_mars_fusion.py::TestTieBreaking`

- [x] **MARS-014**: Where the same source identity, admitted candidate set, configuration, MARS version, run seed, and **stored judge rankings** are supplied, orchestration and deterministic fusion shall reproduce the same result. This is a determinism claim about MARS's own steps only; it does not assert that re-executing a judge yields the same ranking, which depends on the inference backend (see the scope note above). — `tests/phase4/test_mars_provider.py::TestReplayDeterminism`

- [x] **MARS-021**: Candidate multiplicity shall not contribute numerical weight to ranking or fusion. Multiplicity may be used only as a deterministic tie-break after the primary ranking procedure produces an exact tie, as specified in MARS-013. — `tests/phase4/test_mars_fusion.py::TestMultiplicityHasNoNumericalWeight`

## Confidence Semantics

- [x] **MARS-022**: The system shall preserve two distinct confidence quantities in provenance on every non-abstained result: `generator_confidence`, supplied by the extraction provider that produced the selected candidate, and `mars_selection_confidence`, describing confidence in MARS's own selection. Neither shall be stored or reported as the other, and neither shall be written to `control_confidence` alone (MARS-032). Provenance shall not be written onto `StructuredObservation`, which describes the observation rather than how it was obtained. — `tests/phase4/test_mars_confidence.py::TestGeneratorConfidenceAggregation`

- [x] **MARS-023**: The system shall derive `mars_selection_confidence` solely from the judge rankings, their fused scores, and the inter-judge agreement statistic. `generator_confidence` shall not contribute to it, so that a candidate carrying high generator confidence about which judges strongly disagree yields low selection confidence. — `tests/phase4/test_mars_confidence.py::TestSelectionConfidence`

- [x] **MARS-024**: The system shall determine its own `ExtractionResult.status` from the MARS gates alone (MARS-005, MARS-006, MARS-011, MARS-016, MARS-018, MARS-028, MARS-030), and shall not re-apply the single-provider status rules of EXTRACT-013 and EXTRACT-014 to the selected candidate. Those rules govern each generating provider's own result, which MARS has already applied through the admission predicate of MARS-029. — `tests/phase4/test_mars_envelope.py::TestSelectedResult`

- [x] **MARS-032**: The system shall set `ExtractionResult.control_confidence` — the quantity deterministic validation gates on (EXTRACT-020) — to a conservative deterministic combination of `generator_confidence` and `mars_selection_confidence`, initially their minimum. Neither underlying quantity shall be written to `control_confidence` alone, and both shall be preserved in provenance under MARS-022. Replacing the combination function shall not change the contract. `generator_confidence` alone shall never populate `control_confidence`. Where control confidence is unavailable on a **successful** result, the system shall record why it is unavailable, and downstream routing shall treat that absence as insufficient evidence for automatic acceptance rather than as evidence of high confidence (VALID-015). — `tests/phase4/test_mars_confidence.py::TestControlConfidence`, `tests/phase4/test_mars_confidence.py::TestConfidenceIsDescriptiveOnly`

## Agreement Gate

- [x] **MARS-015**: The system shall determine per-instance judge agreement as the **top-choice support of the provisionally selected candidate** — the share of valid judges ranking that candidate first. The agreement value shall be derived only from valid judge rankings and shall be the value used by the disagreement abstention gate (MARS-016). Full-ranking agreement statistics such as Kendall's W may be computed and recorded for evaluation and diagnostics but shall not independently cause abstention. — `tests/phase4/test_mars_agreement.py::TestOnlyValidRankingsCount`, `tests/phase4/test_mars_agreement.py::TestGateIndependence`

- [x] **MARS-030**: MARS shall return a candidate only when the candidate selected by deterministic fusion is also the **unique** modal first-choice candidate among all valid judge rankings and satisfies the configured minimum top-choice-support threshold (MARS-016). If no unique modal first-choice candidate exists, including a tie for the highest number of first-choice votes, the system shall abstain with `reason_code=judge_disagreement` and shall not resolve the tie using fused score, candidate multiplicity, internal identifier, input order, or any other secondary criterion. — `tests/phase4/test_mars_agreement.py::TestFusionWinnerMustBeModalFirstChoice`, `tests/phase4/test_mars_agreement.py::TestModalTie`

- [x] **MARS-031**: The system shall execute selection in this order: compute fused scores (MARS-012), resolve ties to a provisional selected candidate (MARS-013), verify that candidate is the modal first choice (MARS-030), compute its top-choice support (MARS-015), apply the agreement gate (MARS-016), then apply output-integrity verification (MARS-017). The agreement gate shall evaluate the candidate that would be returned, not a candidate identified independently of the fusion result. — `tests/phase4/test_mars_agreement.py::TestGateIndependence::test_agreement_evaluates_the_supplied_winner_not_its_own_choice`

- [x] **MARS-016**: If the top-choice support computed under MARS-015 is below the configured threshold, then the system shall abstain with `reason_code=judge_disagreement` rather than returning the selected candidate. No other agreement statistic shall gate this decision. — `tests/phase4/test_mars_agreement.py::TestGatePasses`, `tests/phase4/test_mars_agreement.py::TestModalButBelowThreshold`, `tests/phase4/test_mars_agreement.py::TestThresholdIsSupplied`

## Output Integrity

- [x] **MARS-017**: Before returning a selected candidate, the system shall verify that the returned observation is field-for-field equal, under a defined normalization, to **one and the same** admitted candidate. The system shall not construct a returned observation by combining fields drawn from more than one candidate. This verification shall apply on every path that returns a candidate, including the single-candidate short-circuit of MARS-006. — `tests/phase4/test_mars_safety.py::TestOutputIntegrity`

- [x] **MARS-018**: If the verification in MARS-017 fails, then the system shall abstain and record an integrity failure, and shall not return the selected candidate. — `tests/phase4/test_mars_envelope.py::TestIntegrityFailureEnvelope`

## Provenance

- [x] **MARS-019**: The system shall record provenance in the shared `ExtractionResult` envelope (EXTRACT-021), not in a MARS-specific side channel, in every result including every abstained result, describing the execution that actually occurred: the identifiers of the candidate providers invoked, the identifiers of the judges invoked, each valid judge's ranking, the fused scores, the top-choice support of the selected candidate, the modal first choice, any diagnostic full-ranking agreement statistic computed, the agreement threshold applied, and the seeds used. Where a stage did not execute, its provenance fields shall be present and empty rather than absent — an abstention raised before any judge was invoked carries empty `judge_ids` and `ranking`, and this is a complete record, not a partial one. — `tests/phase4/test_mars_envelope.py::TestProvenanceDescribesWhatHappened`

- [x] **MARS-020**: The system shall record the model identifier, model family, and configuration hash of every candidate provider and every judge it invokes, so that a MARS result is attributable to a specific ensemble configuration and so that same-family generator/judge overlap is measurable after the fact. — `tests/phase4/test_mars_envelope.py::TestModelRegistry`

- [x] **MARS-025**: Every abstained result shall carry one canonical shape regardless of which gate raised it: `status=ABSTAINED`, a `reason_code`, `candidate_count`, `generator_ids`, `judge_ids`, `ranking`, `selected_candidate=null`, and `provenance`. `judge_ids` and `ranking` shall be empty lists where judging did not occur. — `tests/phase4/test_mars_envelope.py::TestCanonicalAbstentionShape`

- [x] **MARS-026**: The system shall draw `reason_code` from a closed enumeration with one member per abstention gate — `no_reviewable_candidate` (MARS-005), `insufficient_valid_judge_responses` (MARS-011), `insufficient_eligible_judges` (MARS-028), `judge_disagreement` (MARS-016, MARS-030), and `integrity_failure` (MARS-018) — so that abstention causes are machine-separable rather than distinguishable only by prose. — `tests/phase4/test_mars_envelope.py::TestCanonicalAbstentionShape::test_reason_code_enumeration_is_closed`

## Deferred (not in scope here — see owning LLD)

- The numeric threshold governing MARS-016 is undetermined. Its selection procedure is settled — informed by human disagreement observed on the annotated batch and validated against the accuracy/abstention trade-off — but the value awaits that annotation (Open Question 1). Human annotation κ and judge top-choice concordance measure different tasks and are not numerically interchangeable; see the owning LLD before setting one from the other.
- Per-field reranking is deferred in favor of whole-record selection (Open Question 2); these specs describe whole-record selection only.
- Judge count and vendor spread are undecided (Open Question 3). Judge *eligibility* is specified — MARS-027 prohibits exact generator/judge model overlap and MARS-028 abstains when the roster cannot satisfy it — but roster *size* and composition beyond that constraint are not.
- The choice of diagnostic full-ranking statistic permitted by MARS-015 (Kendall's W, mean pairwise Kendall's τ, or another) is unconstrained, since no such statistic gates any decision.

## References

- [Mars_Reranking.md](./Mars_Reranking.md) — owning design, rationale, and open questions.
- [Extraction_Provider_Specs.md](./Extraction_Provider_Specs.md) — the protocol MARS-001 binds to.
- [Deterministic_Validation_Engine_Specs.md](./Deterministic_Validation_Engine_Specs.md) — downstream validation referenced by MARS-002.
- [Abstention_Router_Specs.md](./Abstention_Router_Specs.md) — per-observation abstention, distinct from MARS's internal abstention conditions (MARS-005, MARS-011, MARS-016, MARS-018).
