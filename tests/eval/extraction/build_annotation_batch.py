"""Build a child-stratified, double-annotation-ready batch of extraction candidates.

Supersedes build_annotation_candidates.py, which drew a flat random sample and
discarded the real child. Three properties this batch has that the pilot did not:

  1. **Child stratification.** Equal candidates per child across all 11 children.
     The pilot's sample was drawn while every segment's ``child_id`` was
     ``"unknown"`` (a defect in ``chat_parser._match_child``, since fixed), so
     its 31 annotations landed 28/2/1 across three Rollins children and none at
     all on Flusberg -- an accuracy figure computed from it describes one child.

  2. **Real child_id preserved** on every candidate, so a leakage-safe
     child-level split can be constructed downstream. The pilot hardcoded
     ``child_id="annotation_child"`` into the extraction request.

  3. **Explicit annotator assignment with a double-annotated overlap**, so
     inter-rater reliability is computable. Single-annotator ground truth
     carries no reliability estimate and cannot support a κ.

Stage 1 (stratified pool selection) and stage 3 (annotator assignment) are
deterministic and need no model. Stage 2 (extraction) makes real model calls.

Multiple models may be named in ``--models``: each contributes its own candidate
extraction per segment, which is the input a reranker consumes. With one model
the batch is a plain single-model annotation set.

Run directly:
    uv run python -m tests.eval.extraction.build_annotation_batch --help
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from src.backend.ml.extraction.ollama_llm import OllamaExtractionProvider
from src.backend.ml.extraction.schemas import ExtractionRequest, ExtractionStatus, SourceType
from src.backend.schemas.observation_schema import ContributorRole, Setting
from tests.eval.extraction.sample_real_segments import (
    load_real_segments,
    render_segment_to_chat_text,
)

RESULTS_DIR = Path(__file__).parent / "results"
POOL_PATH = RESULTS_DIR / "annotation_pool.json"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"

OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
OLLAMA_API_KEY = "ollama"

FIELDS = ["domain", "behavior", "modality", "prompt_level", "outcome"]

# Not every segment yields a reviewable extraction -- the pilot observed roughly
# a 24% SUCCESS/PARTIAL yield. The pool is oversampled by this factor so the
# post-extraction batch still reaches the per-child target.
YIELD_HEADROOM = 4

DEFAULT_PER_CHILD = 30
DEFAULT_SEED = 42
DEFAULT_MIN_CHARS = 20


# --------------------------------------------------------------------------
# Stage 1 -- child-stratified pool selection (deterministic, no model calls)
# --------------------------------------------------------------------------

def build_pool(
    per_child: int = DEFAULT_PER_CHILD,
    seed: int = DEFAULT_SEED,
    min_chars: int = DEFAULT_MIN_CHARS,
) -> dict[str, Any]:
    """Select an equal-sized, deterministically shuffled pool per child."""
    segments = load_real_segments(max_segments=3000)

    by_child: dict[str, list] = defaultdict(list)
    for seg in segments:
        text = render_segment_to_chat_text(seg)
        if seg.source.turns and len(text) > min_chars:
            by_child[seg.source.child_id].append((seg, text))

    target = per_child * YIELD_HEADROOM
    pool: list[dict[str, Any]] = []
    shortfalls: dict[str, int] = {}

    for child_id in sorted(by_child):
        entries = by_child[child_id]
        # Seed per child so adding a child does not reshuffle the others.
        random.Random(f"{seed}:{child_id}").shuffle(entries)
        if len(entries) < target:
            shortfalls[child_id] = len(entries)
        for seg, text in entries[:target]:
            pool.append(
                {
                    "segment_id": seg.segment_id,
                    "child_id": seg.source.child_id,
                    "corpus": seg.source.corpus,
                    "session_id": seg.source.session_id,
                    "chat_text": text,
                }
            )

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "per_child_target": per_child,
        "per_child_pool_size": target,
        "yield_headroom": YIELD_HEADROOM,
        "n_children": len(by_child),
        "n_pool": len(pool),
        "shortfalls": shortfalls,
        "note": (
            "Segment pool only -- contains no model output and no labels. "
            "Stage 2 runs extraction over this pool; stage 3 assigns annotators."
        ),
        "pool": pool,
    }


# --------------------------------------------------------------------------
# Stage 2 -- extraction (real model calls)
# --------------------------------------------------------------------------

async def extract_candidates(
    pool: list[dict[str, Any]],
    models: list[str],
    per_child: int,
    base_url: str = OLLAMA_BASE_URL,
    require: str = "all",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Run each model over the pool, stopping per child once the target is met.

    ``require="all"`` keeps a segment only where *every* model produced a
    reviewable extraction, so each retained segment carries a complete,
    comparable candidate set. That is what the oracle candidate ceiling needs --
    "was any generator correct?" is only answerable where every generator was
    judged on the same segment.

    It is also the expensive option. Single-model yield in the pilot was ~24%,
    so joint yield across N models can fall off a cliff: three models at 24%
    each, if roughly independent, retain about 1.4% of the pool. The returned
    stats report per-model and joint yield so that collapse is visible before
    an annotation budget is committed to it, rather than after.

    ``require="any"`` keeps a segment where at least one model succeeded. Larger
    n, but per-model accuracy denominators then differ and the oracle ceiling is
    no longer computable on a common set.
    """
    providers = {
        m: OllamaExtractionProvider(base_url=base_url, api_key=OLLAMA_API_KEY, model=m)
        for m in models
    }

    kept: list[dict[str, Any]] = []
    kept_per_child: dict[str, int] = defaultdict(int)
    attempted = 0
    per_model_success: dict[str, int] = defaultdict(int)

    for entry in pool:
        child_id = entry["child_id"]
        if kept_per_child[child_id] >= per_child:
            continue

        request = ExtractionRequest(
            source_type=SourceType.CHAT_SEGMENT,
            text=entry["chat_text"],
            child_id=child_id,  # real child, not a placeholder
            session_id=entry["session_id"],
            contributor_role=ContributorRole.INTERVENTIONIST,
            observation_date=date(2026, 8, 28),
            setting=Setting.CLINIC,
        )

        attempted += 1
        candidates: dict[str, Any] = {}
        for model, provider in providers.items():
            result = await provider.extract(request)
            if result.status not in (ExtractionStatus.SUCCESS, ExtractionStatus.PARTIAL):
                continue
            per_model_success[model] += 1
            obs = result.observations[0]
            candidates[model] = {
                "status": result.status.value,
                "confidence": obs.confidence,
                "extracted_fields": {
                    field: (
                        getattr(obs, field).value
                        if hasattr(getattr(obs, field), "value")
                        else getattr(obs, field)
                    )
                    for field in FIELDS
                },
            }

        satisfied = (
            len(candidates) == len(models) if require == "all" else bool(candidates)
        )
        if not satisfied:
            print(
                f"  {entry['segment_id']}: {len(candidates)}/{len(models)} models "
                f"produced output -- skipped (require={require})"
            )
            continue

        kept.append({**entry, "candidates": candidates})
        kept_per_child[child_id] += 1
        n_kept = kept_per_child[child_id]
        print(f"  {entry['segment_id']} [{child_id}]: kept ({n_kept}/{per_child})")

    stats = {
        "require": require,
        "segments_attempted": attempted,
        "segments_kept": len(kept),
        "joint_yield": round(len(kept) / attempted, 4) if attempted else None,
        "per_model_yield": {
            m: round(per_model_success[m] / attempted, 4) if attempted else None
            for m in models
        },
    }
    return kept, stats


# --------------------------------------------------------------------------
# Stage 3 -- annotator assignment (deterministic, no model calls)
# --------------------------------------------------------------------------

def assign_annotators(
    candidates: list[dict[str, Any]],
    annotators: list[str],
    overlap: float,
    seed: int = DEFAULT_SEED,
) -> dict[str, list[str]]:
    """Assign segments to annotators, double-annotating an ``overlap`` fraction.

    ``overlap=1.0`` double-annotates everything, giving a κ over the whole set.
    Lower values split the remainder evenly, trading reliability coverage for
    a larger single-annotated set. Overlap is drawn per child so the reliability
    subset is itself stratified rather than concentrated in whichever children
    happen to sort first.
    """
    if len(annotators) < 2:
        raise ValueError("Inter-rater reliability needs at least two annotators.")

    by_child: dict[str, list[str]] = defaultdict(list)
    for cand in candidates:
        by_child[cand["child_id"]].append(cand["segment_id"])

    assignments: dict[str, list[str]] = {a: [] for a in annotators}
    for child_id in sorted(by_child):
        ids = sorted(by_child[child_id])
        random.Random(f"{seed}:assign:{child_id}").shuffle(ids)

        n_shared = round(len(ids) * overlap)
        for segment_id in ids[:n_shared]:
            for annotator in annotators:
                assignments[annotator].append(segment_id)
        for i, segment_id in enumerate(ids[n_shared:]):
            assignments[annotators[i % len(annotators)]].append(segment_id)

    return {a: sorted(ids) for a, ids in assignments.items()}


# --------------------------------------------------------------------------

def _summarize(label: str, rows: list[dict[str, Any]], key: str = "child_id") -> None:
    counts: dict[str, int] = defaultdict(int)
    for row in rows:
        counts[row[key]] += 1
    print(f"\n{label} (n={len(rows)}, children={len(counts)}):")
    for child_id in sorted(counts):
        print(f"  {child_id:18s} {counts[child_id]:4d}")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-child", type=int, default=DEFAULT_PER_CHILD)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument(
        "--models",
        nargs="+",
        default=["llama3.2:latest"],
        help="One or more Ollama models; each contributes a candidate extraction per segment.",
    )
    parser.add_argument("--annotators", nargs="+", default=["annotator_a", "annotator_b"])
    parser.add_argument(
        "--overlap",
        type=float,
        default=1.0,
        help="Fraction double-annotated for inter-rater reliability (1.0 = all).",
    )
    parser.add_argument(
        "--pool-only",
        action="store_true",
        help="Run stage 1 only -- select the stratified pool without calling any model.",
    )
    parser.add_argument(
        "--require",
        choices=["all", "any"],
        default="all",
        help=(
            "Keep a segment when every model produced output (default, required "
            "for the oracle candidate ceiling) or when any model did."
        ),
    )
    parser.add_argument(
        "--pilot",
        type=int,
        default=None,
        help=(
            "Measure yield on the first N pool segments and stop, without "
            "writing a batch. Run this before committing annotation effort."
        ),
    )
    args = parser.parse_args()

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    pool_payload = build_pool(per_child=args.per_child, seed=args.seed)
    POOL_PATH.write_text(json.dumps(pool_payload, indent=2))
    _summarize("Stratified pool", pool_payload["pool"])
    if pool_payload["shortfalls"]:
        print(f"\n  WARNING -- children below pool target: {pool_payload['shortfalls']}")
    print(f"\nWrote pool to {POOL_PATH}")

    if args.pool_only:
        print("\n--pool-only: stopping before extraction.")
        return

    pool = pool_payload["pool"]
    if args.pilot:
        print(f"\nYIELD PILOT: {args.pilot} segments, models={args.models}, require={args.require}")
        _, stats = await extract_candidates(
            pool[: args.pilot], args.models, per_child=10**6, require=args.require
        )
        print("\nYield:")
        print(f"  attempted        {stats['segments_attempted']}")
        print(f"  kept             {stats['segments_kept']}")
        print(f"  joint yield      {stats['joint_yield']}")
        for model, y in stats["per_model_yield"].items():
            print(f"  {model:24s} {y}")
        needed = args.per_child * pool_payload["n_children"]
        if stats["joint_yield"]:
            print(
                f"\n  To reach {needed} candidates at this yield you would need "
                f"~{round(needed / stats['joint_yield'])} pool segments "
                f"({len(pool)} available)."
            )
        print("\n--pilot: stopping before writing a batch.")
        return

    print(f"\nRunning extraction over the pool with {args.models}...")
    candidates, yield_stats = await extract_candidates(
        pool, args.models, args.per_child, require=args.require
    )
    assignments = assign_annotators(
        candidates, args.annotators, args.overlap, seed=args.seed
    )

    batch = {
        "generated_at": datetime.now(UTC).isoformat(),
        "models": args.models,
        "seed": args.seed,
        "per_child_target": args.per_child,
        "n_candidates": len(candidates),
        "yield": yield_stats,
        "overlap": args.overlap,
        "annotators": args.annotators,
        "assignments": assignments,
        "note": (
            "candidates[*].candidates holds MODEL OUTPUT, not ground truth. Each "
            "annotator independently judges their assigned segments; agreement on "
            "the double-annotated overlap yields the inter-rater reliability "
            "estimate, and disagreements are adjudicated into the final labels."
        ),
        "candidates": candidates,
    }
    BATCH_PATH.write_text(json.dumps(batch, indent=2))

    _summarize("Annotation batch", candidates)
    print("\nAnnotator workload:")
    for annotator, ids in assignments.items():
        print(f"  {annotator:14s} {len(ids):4d} segments")
    print(f"\nWrote batch to {BATCH_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
