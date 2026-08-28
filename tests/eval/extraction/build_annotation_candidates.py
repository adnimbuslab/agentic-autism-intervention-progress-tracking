"""Generate annotation candidates: real extraction outputs from a real
provider on real CHAT segments, packaged for human review.

This script does NOT produce ground truth -- it only runs the extraction
provider and records its output next to the source text so a human
annotator can judge each field. See annotate.py for the labeling step and
score_annotations.py for computing metrics from completed labels.

Not a pytest test -- makes real network calls, run directly:
    uv run python -m tests.eval.extraction.build_annotation_candidates
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

from src.backend.ml.extraction.ollama_llm import OllamaExtractionProvider
from src.backend.ml.extraction.schemas import ExtractionRequest, ExtractionStatus, SourceType
from src.backend.schemas.observation_schema import ContributorRole, Setting
from tests.eval.extraction.sample_real_segments import (
    load_real_segments,
    render_segment_to_chat_text,
    sample_segments,
)

OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
OLLAMA_API_KEY = "ollama"
MODEL = "llama3.2:latest"  # the only model that produced non-trivial output in prior comparisons
SEED = 42
N_SEGMENTS = 100  # candidate pool; not every one will reach SUCCESS/PARTIAL (~24% observed yield)

CANDIDATES_PATH = Path(__file__).parent / "results" / "annotation_candidates.json"

FIELDS = ["domain", "behavior", "modality", "prompt_level", "outcome"]


async def build() -> None:
    provider = OllamaExtractionProvider(base_url=OLLAMA_BASE_URL, api_key=OLLAMA_API_KEY, model=MODEL)

    all_segments = load_real_segments()
    sample = sample_segments(all_segments, n=N_SEGMENTS, seed=SEED)
    print(f"Running {len(sample)} real segments through {MODEL} to build annotation candidates...")

    candidates = []
    for seg in sample:
        chat_text = render_segment_to_chat_text(seg)
        request = ExtractionRequest(
            source_type=SourceType.CHAT_SEGMENT,
            text=chat_text,
            child_id="annotation_child",
            session_id="annotation_session",
            contributor_role=ContributorRole.INTERVENTIONIST,
            observation_date=date(2026, 8, 28),
            setting=Setting.CLINIC,
        )
        result = await provider.extract(request)
        if result.status not in (ExtractionStatus.SUCCESS, ExtractionStatus.PARTIAL):
            print(f"  {seg.segment_id}: {result.status.value} (skipped -- nothing to review)")
            continue

        obs = result.observations[0]
        candidate = {
            "segment_id": seg.segment_id,
            "corpus": seg.source.corpus,
            "chat_text": chat_text,
            "status": result.status.value,
            "confidence": obs.confidence,
            "extracted_fields": {
                field: (getattr(obs, field).value if hasattr(getattr(obs, field), "value") else getattr(obs, field))
                for field in FIELDS
            },
        }
        candidates.append(candidate)
        print(f"  {seg.segment_id}: {result.status.value} -- added for review")

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "model": MODEL,
        "n_reviewed_by_model": len(sample),
        "n_candidates": len(candidates),
        "note": (
            "These are MODEL OUTPUTS, not ground truth. Run annotate.py to have a "
            "human judge each field before computing any accuracy metric."
        ),
        "candidates": candidates,
    }
    CANDIDATES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CANDIDATES_PATH.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {len(candidates)} candidates to {CANDIDATES_PATH}")
    print("Next: uv run python -m tests.eval.extraction.annotate")


if __name__ == "__main__":
    import asyncio

    asyncio.run(build())
