"""Freeze a model-independent held-out test set.

The annotation batch is conditioned on model output: segments were retained
only where all three generators produced an admissible response. That is
defensible for the purpose it served -- every batch item carries a complete
candidate set, which is what the three-way comparison needs -- but it means
accuracy measured on it is accuracy on segments the models could all handle.
A reviewer is entitled to ask what happens on a sample drawn without reference
to model behaviour, and this builds that sample.

**The exclusion rule is deliberately strict.** Every segment in the original
stratified pool is excluded, not merely the 330 that reached the batch. The
batch build consumed 506 pool segments to retain 330, and no record survives of
which 176 it rejected; sampling the remainder of the pool would therefore
enrich the set with segments a generator had already failed on -- contamination
in the opposite direction, and harder to argue away than the original.
Sampling outside the pool entirely avoids the question.

**Freeze before generating.** This writes the segment set and nothing else. No
model is called here. Running generators over it is a separate step, and the
order matters: a set frozen after inspection of generator output is not a
held-out set.

**Abstention is data.** When the generators are later run over this set, a
model that produces nothing must be recorded as an abstention, not dropped.
Dropping it would reintroduce exactly the conditioning this set exists to
avoid.

Usage:
    uv run python -m tests.eval.extraction.build_holdout_set --per-child 12
"""

from __future__ import annotations

import argparse
import json
import random
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tests.eval.extraction.sample_real_segments import (
    load_real_segments,
    render_segment_to_chat_text,
)

RESULTS_DIR = Path(__file__).parent / "results"
POOL_PATH = RESULTS_DIR / "annotation_pool.json"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"
OUT_PATH = RESULTS_DIR / "holdout_set.json"

DEFAULT_SEED = 20260916
MIN_CHAT_CHARS = 20


def excluded_ids() -> tuple[set[str], set[str]]:
    """(pool ids, batch ids). The pool is the exclusion set; the batch is a subset."""
    pool: set[str] = set()
    if POOL_PATH.exists():
        payload = json.loads(POOL_PATH.read_text())
        pool = {s["segment_id"] for s in payload.get("pool", [])}
    batch: set[str] = set()
    if BATCH_PATH.exists():
        batch = {
            e["segment_id"]
            for e in json.loads(BATCH_PATH.read_text())["candidates"]
        }
    return pool, batch


def build(per_child: int, seed: int, max_segments: int) -> dict[str, Any]:
    segments = load_real_segments(max_segments=max_segments)
    pool, batch = excluded_ids()

    by_child: dict[str, list[dict[str, Any]]] = {}
    skipped_short = 0
    for segment in segments:
        chat_text = render_segment_to_chat_text(segment)
        if len(chat_text) <= MIN_CHAT_CHARS or not segment.source.turns:
            skipped_short += 1
            continue
        if segment.segment_id in pool:
            continue
        # Child, corpus and session live on the episode the segment came from.
        episode = segment.source
        by_child.setdefault(episode.child_id, []).append(
            {
                "segment_id": segment.segment_id,
                "child_id": episode.child_id,
                "corpus": episode.corpus,
                "session_id": episode.session_id,
                "chat_text": chat_text,
            }
        )

    rng = random.Random(seed)
    selected: list[dict[str, Any]] = []
    shortfalls: dict[str, int] = {}
    for child_id in sorted(by_child):
        available = by_child[child_id]
        rng.shuffle(available)
        take = available[:per_child]
        if len(take) < per_child:
            shortfalls[child_id] = per_child - len(take)
        selected.extend(take)

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "seed": seed,
        "per_child_target": per_child,
        "n_segments": len(selected),
        "n_children": len(by_child),
        "n_eligible_after_exclusion": sum(len(v) for v in by_child.values()),
        "n_excluded_pool": len(pool),
        "n_excluded_batch_subset_of_pool": len(batch),
        "n_skipped_too_short": skipped_short,
        "shortfalls": shortfalls,
        "per_child_counts": dict(
            sorted(Counter(s["child_id"] for s in selected).items())
        ),
        "selection_rule": (
            "Stratified by child from behavioural segments outside the original "
            "annotation pool. No model output was consulted. Frozen before any "
            "generator is run over it."
        ),
        "scoring_rule": (
            "When generators are run over this set, a model producing no "
            "admissible response is recorded as an abstention and the segment "
            "is retained. Segments are never dropped for model failure."
        ),
        "segments": selected,
    }


def render(report: dict[str, Any]) -> None:
    print(f"Held-out set: {report['n_segments']} segments "
          f"across {report['n_children']} children")
    print(f"  per-child target        : {report['per_child_target']}")
    print(f"  eligible after exclusion: {report['n_eligible_after_exclusion']}")
    print(f"  excluded (original pool): {report['n_excluded_pool']} "
          f"(of which {report['n_excluded_batch_subset_of_pool']} reached the batch)")
    print(f"  skipped as too short    : {report['n_skipped_too_short']}")
    if report["shortfalls"]:
        print(f"  shortfalls              : {report['shortfalls']}")
    print(f"  per child               : {report['per_child_counts']}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--per-child", type=int, default=12)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--max-segments", type=int, default=5000)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    if args.out.exists():
        raise SystemExit(
            f"{args.out} already exists. A held-out set is frozen once; "
            "re-drawing it after seeing results is how a held-out set stops "
            "being one. Delete it deliberately if you really mean to."
        )

    report = build(args.per_child, args.seed, args.max_segments)
    render(report)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(f"\nWrote {args.out}")
    print(
        "\nNext: annotate these segments under the final codebook, then run "
        "all generators over them.\nDo not run generators first."
    )


if __name__ == "__main__":
    main()
