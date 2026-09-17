"""Run an additional generator over the frozen batch and record its candidates.

The annotation design is model-independent: gold holds field values authored
from the transcript, not judgements of any model's output. That was the point
of authoring it that way, and this is where it pays -- a fourth generator can
be scored against the existing gold standard at no additional annotation cost.

The frozen batch is **not** modified. This writes a separate augmented batch so
the original artefact, and its checksum, stay exactly as the annotators saw it.

Usage:
    uv run python -m tests.eval.extraction.add_generator --model qwen3:14b
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from src.backend.ml.extraction.ollama_llm import OllamaExtractionProvider
from src.backend.ml.extraction.schemas import ExtractionRequest, SourceType
from src.backend.schemas.observation_schema import ContributorRole, Setting

RESULTS_DIR = Path(__file__).parent / "results"
BATCH_PATH = RESULTS_DIR / "annotation_batch.json"
OUT_PATH = RESULTS_DIR / "annotation_batch_augmented.json"

OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
FIELDS = ["domain", "behavior", "modality", "prompt_level", "outcome"]


def as_candidate(result: Any) -> dict[str, Any]:
    """Match the candidate shape the frozen batch already uses."""
    observation = result.observations[0] if result.observations else None
    extracted: dict[str, Any] = {}
    confidence: float | None = None
    if observation is not None:
        dumped = observation.model_dump(mode="json")
        extracted = {f: dumped.get(f) for f in FIELDS}
        # Confidence is a property of the extracted observation, not of the
        # envelope; the frozen batch records it at the candidate level.
        confidence = dumped.get("confidence")
    return {
        "status": result.status.value,
        "confidence": confidence,
        "extracted_fields": extracted or None,
        "abstention_reason": (
            observation.abstention_reason if observation is not None else None
        ),
    }


def write(batch: dict[str, Any], out: Path) -> None:
    """Write atomically, so a kill mid-write cannot corrupt the checkpoint."""
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(batch, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(out)


async def run(
    source: Path, model: str, limit: int | None, out: Path, every: int
) -> dict[str, Any]:
    batch = json.loads(source.read_text())
    entries = batch["candidates"][: limit or None]
    provider = OllamaExtractionProvider(
        base_url=OLLAMA_BASE_URL, api_key="ollama", model=model
    )

    # Resume: a segment already carrying a non-failed candidate for this model
    # is not re-run. A large local model can be killed by memory pressure
    # partway through 330 segments, and losing a completed half-hour to that
    # is avoidable.
    done = sum(
        1
        for e in entries
        if (e["candidates"].get(model) or {}).get("status") not in (None, "failed")
    )
    if done:
        print(f"Resuming: {done} of {len(entries)} already recorded for {model}")

    statuses: dict[str, int] = {}
    for index, entry in enumerate(entries, start=1):
        existing = entry["candidates"].get(model)
        if existing and existing.get("status") not in (None, "failed"):
            statuses[existing["status"]] = statuses.get(existing["status"], 0) + 1
            continue
        request = ExtractionRequest(
            source_type=SourceType.CHAT_SEGMENT,
            text=entry["chat_text"],
            child_id=entry["child_id"],
            session_id=entry["session_id"],
            contributor_role=ContributorRole.INTERVENTIONIST,
            observation_date=date(2026, 8, 28),
            setting=Setting.CLINIC,
        )
        try:
            result = await provider.extract(request)
            candidate = as_candidate(result)
        except Exception as exc:  # noqa: BLE001 - one failure must not end the run
            candidate = {
                "status": "failed",
                "extracted_fields": None,
                "confidence": None,
                "abstention_reason": repr(exc),
            }
        entry["candidates"][model] = candidate
        statuses[candidate["status"]] = statuses.get(candidate["status"], 0) + 1
        if index % every == 0 or index == len(entries):
            if model not in batch["models"]:
                batch["models"].append(model)
            write(batch, out)
            print(f"  [{index}/{len(entries)}] {statuses}  (checkpointed)", flush=True)

    if model not in batch["models"]:
        batch["models"].append(model)
    batch["augmented_at"] = datetime.now(UTC).isoformat()
    batch["augmented_with"] = model
    batch["augmentation_note"] = (
        "Generated after annotation, scored against the same model-independent "
        "gold standard. The frozen batch the annotators saw is unchanged; this "
        "is a separate artefact."
    )
    return batch


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    parser.add_argument(
        "--every", type=int, default=10,
        help="Checkpoint every N segments. Re-running resumes from the "
             "last checkpoint rather than starting over.",
    )
    args = parser.parse_args()

    if not BATCH_PATH.exists():
        raise SystemExit(f"{BATCH_PATH} not found.")

    # Build on an existing augmented batch when one is present, so several
    # generators can be added without re-running the ones already recorded.
    source = args.out if (args.out.exists() and args.out != BATCH_PATH) else BATCH_PATH
    if source != BATCH_PATH:
        print(f"Extending {source.name}")

    batch = asyncio.run(
        run(source, args.model, args.limit, args.out, args.every)
    )
    write(batch, args.out)
    print(f"\nGenerators now in {args.out.name}: {batch['models']}")
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()
