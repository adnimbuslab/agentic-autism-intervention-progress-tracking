"""MARS -- multi-LLM-augmented reranking, composed behind ExtractionProvider.

See docs/lld/Mars_Reranking.md. Candidate formation, pre-ranking safety
invariants, blinding, deterministic fusion, the agreement gate, and confidence composition
the result envelope, and the provider itself are implemented.
"""

from src.backend.ml.extraction.mars.agreement import (
    AgreementDecision,
    AgreementFailure,
    evaluate_agreement,
)
from src.backend.ml.extraction.mars.blinding import (
    JudgePresentation,
    build_judge_presentation,
    candidate_set_fingerprint,
    canonical_judge_identity,
    derive_judge_seed,
    derive_request_seed,
)
from src.backend.ml.extraction.mars.candidates import (
    FINGERPRINT_FIELDS,
    CandidateBranch,
    MarsCandidate,
    build_candidates,
    classify_branch,
    fingerprint_observation,
    normalize_value,
)
from src.backend.ml.extraction.mars.confidence import (
    GeneratorConfidencePolicy,
    MarsConfidence,
    aggregate_generator_confidence,
    compose_confidence,
    derive_selection_confidence,
)
from src.backend.ml.extraction.mars.envelope import (
    ModelDescriptor,
    ModelRole,
    build_abstained_result,
    build_selected_result,
)
from src.backend.ml.extraction.mars.fusion import (
    RRF_K,
    JudgeResponse,
    fuse_rankings,
    parse_judge_response,
    select_provisional_winner,
    validate_response_count,
)
from src.backend.ml.extraction.mars.provider import (
    MarsExtractionProvider,
    MarsGenerator,
    MarsJudge,
)
from src.backend.ml.extraction.mars.safety import (
    MARS_INTEGRITY_FIELDS,
    MarsAbstentionReason,
    eligible_judges,
    find_matching_candidate,
    roster_shortfall,
)

__all__ = [
    "FINGERPRINT_FIELDS",
    "AgreementDecision",
    "AgreementFailure",
    "MARS_INTEGRITY_FIELDS",
    "RRF_K",
    "CandidateBranch",
    "GeneratorConfidencePolicy",
    "MarsConfidence",
    "MarsExtractionProvider",
    "MarsGenerator",
    "MarsJudge",
    "ModelDescriptor",
    "ModelRole",
    "JudgePresentation",
    "JudgeResponse",
    "MarsAbstentionReason",
    "MarsCandidate",
    "aggregate_generator_confidence",
    "build_abstained_result",
    "build_candidates",
    "build_judge_presentation",
    "build_selected_result",
    "candidate_set_fingerprint",
    "canonical_judge_identity",
    "classify_branch",
    "compose_confidence",
    "derive_judge_seed",
    "derive_selection_confidence",
    "derive_request_seed",
    "eligible_judges",
    "evaluate_agreement",
    "find_matching_candidate",
    "fingerprint_observation",
    "fuse_rankings",
    "normalize_value",
    "parse_judge_response",
    "roster_shortfall",
    "select_provisional_winner",
    "validate_response_count",
]
