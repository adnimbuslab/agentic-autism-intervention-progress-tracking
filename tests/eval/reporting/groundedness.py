"""Is the reporting LLM's prose grounded in the evidence packet it was given?

The system's stated guarantee is that every factual statement in a progress
report traces back to source evidence, and that the reporting model summarises
deterministic findings rather than producing its own. `validate_report` already
enforces part of this: prohibited content (diagnosis, treatment advice, causal
and prognostic claims) and acknowledgement of abstained metrics.

It does not check the one rule most likely to be broken quietly. The system
prompt forbids inventing "numerical values not present in the evidence packet",
and nothing verifies it. A report that states an independence rate the
analytics engine never computed is indistinguishable, to the existing
validator, from one that quotes it correctly.

This module measures four properties per report:

    prohibited_content      via validate_report -- diagnosis, treatment advice,
                            causal/prognostic claims, stigmatising terms
    numeric_groundedness    every number in the prose appears in the packet
    evidence_ref_validity   every cited record id exists in the packet
    abstention_preserved    withheld metrics are acknowledged, not filled in

**Reports produced by the deterministic fallback are excluded from scoring.**
`ReportingClient.generate_report` falls back to template prose when the model
call fails, and that fallback is grounded by construction -- scoring it would
measure the template and report the result as the model's.

**What the evidence packets are.** They are assembled from the adjudicated gold
records, grouped by child, through the production `AdequacyRouter` and
`AnalyticsEngine`. The app-known metadata those engines require -- observation
date, setting, contributor role -- is *derived from the corpus structure*, not
from real intervention records: Rollins sessions are child-investigator and are
mapped to a clinic setting with an interventionist contributor, Flusberg
sessions are child-parent and map to home and parent, and session order within
a child supplies a monotone date sequence. This is stated because it bounds the
claim: what is measured is whether the reporting layer invents facts absent
from its input, which does not depend on the input being a real clinical
record. It is not a clinical evaluation of report quality.

Usage:
    uv run python -m tests.eval.reporting.groundedness
    uv run python -m tests.eval.reporting.groundedness --model qwen2.5:7b
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from src.backend.ml.adequacy_router import AdequacyRouter
from src.backend.ml.analytics_engine import AnalyticsEngine
from src.backend.ml.reporting_client import ReportingClient
from src.backend.ml.schemas import EvidencePacket

RESULTS_DIR = Path(__file__).parent / "results"
EXTRACTION_RESULTS = Path(__file__).parents[1] / "extraction" / "results"
GOLD_PATH = EXTRACTION_RESULTS / "gold_labels.json"
BATCH_PATH = EXTRACTION_RESULTS / "annotation_batch.json"
OUT_PATH = RESULTS_DIR / "reporting_groundedness.json"

REVIEW_START = date(2026, 1, 5)
DEFAULT_MODEL = "qwen2.5:7b"

# Corpus structure -> the app-known metadata the engines require. Derived, and
# recorded in the output so a reader can see it is derived rather than real.
CORPUS_SETTING = {"rollins": "clinic", "flusberg": "home"}
CORPUS_ROLE = {"rollins": "interventionist", "flusberg": "parent"}

# A number in prose is grounded if some packet value *rounds to* it at the
# precision the prose printed. A fixed tolerance fails here: the report renders
# a stored 0.9412 as "94.1%", and any tolerance tight enough to catch a
# fabricated 94.1 also rejects that legitimate rounding. Matching at the
# printed precision is the same rule the manuscript number checks use.
#
# The deterministic fallback calibrates this: its prose is grounded by
# construction, so any number it asserts that this rule rejects is a false
# positive of the rule rather than a finding. Before the rounding fix the
# fallback scored 0.85-0.97; it should score 1.0.

# Years, ordinals and small counts that prose uses structurally rather than as
# claims ("four sections", "the first goal"). Counting these as ungrounded
# would measure English, not the model.
STRUCTURAL_NUMBERS = {0, 1, 2, 3, 4, 5, 100}


def load_records() -> dict[str, list[dict[str, Any]]]:
    """Adjudicated gold records per child, with derived app-known metadata."""
    gold = json.loads(GOLD_PATH.read_text())["gold"]
    batch = {
        entry["segment_id"]: entry
        for entry in json.loads(BATCH_PATH.read_text())["candidates"]
    }

    by_child: dict[str, list[dict[str, Any]]] = {}
    for segment_id, record in sorted(gold.items()):
        entry = batch.get(segment_id)
        if entry is None:
            continue
        corpus = entry["corpus"]
        by_child.setdefault(entry["child_id"], []).append(
            {
                "segment_id": segment_id,
                "session_id": entry["session_id"],
                "corpus": corpus,
                "field_values": record["field_values"],
            }
        )

    prepared: dict[str, list[dict[str, Any]]] = {}
    for child_id, rows in by_child.items():
        sessions = sorted({r["session_id"] for r in rows})
        session_day = {s: i for i, s in enumerate(sessions)}
        records = []
        for index, row in enumerate(rows):
            corpus = row["corpus"]
            observed = REVIEW_START + timedelta(days=7 * session_day[row["session_id"]])
            records.append(
                {
                    "record_id": f"{child_id}-{index:03d}",
                    "version": 1,
                    "child_id": child_id,
                    "observation_date": observed.isoformat(),
                    "setting": CORPUS_SETTING.get(corpus, "other"),
                    "contributor_role": CORPUS_ROLE.get(corpus, "interventionist"),
                    "session_id": row["session_id"],
                    **{k: v for k, v in row["field_values"].items()},
                }
            )
        prepared[child_id] = records
    return prepared


def build_packet(child_id: str, records: list[dict[str, Any]]) -> EvidencePacket:
    dates = sorted(r["observation_date"] for r in records)
    review_start = date.fromisoformat(dates[0])
    review_end = date.fromisoformat(dates[-1])

    adequacy = AdequacyRouter().assess(
        records=records, goals=[], review_start=review_start, review_end=review_end
    )
    analytics = AnalyticsEngine().compute(
        child_id=child_id,
        review_period_id=f"{child_id}-review",
        records=records,
        adequacy=adequacy,
    )

    contributors: dict[str, int] = {}
    settings_seen: dict[str, int] = {}
    for record in records:
        contributors[record["contributor_role"]] = (
            contributors.get(record["contributor_role"], 0) + 1
        )
        settings_seen[record["setting"]] = settings_seen.get(record["setting"], 0) + 1

    return EvidencePacket(
        child_id=child_id,
        review_period_id=f"{child_id}-review",
        review_period_start=review_start.isoformat(),
        review_period_end=review_end.isoformat(),
        goals=[],
        structured_records=records,
        record_ids=[r["record_id"] for r in records],
        record_versions={r["record_id"]: 1 for r in records},
        analytics=analytics,
        adequacy=adequacy,
        quality_flags=list(adequacy.quality_flags),
        contributor_summary=contributors,
        setting_summary=settings_seen,
        observation_count=len(records),
    )


def grounded_numbers(packet: EvidencePacket) -> set[float]:
    """Every numeric value the packet contains, plus percentage renderings."""
    values: set[float] = set()

    def walk(node: Any) -> None:
        if isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            number = float(node)
            values.add(number)
            # Prose states direction in words and magnitude in digits -- a
            # packet delta of -0.5333 is written "decreased by 0.5333" -- so
            # the magnitude is what a printed number must be matched against.
            values.add(abs(number))
            for scaled in (number, abs(number)):
                if 0.0 <= scaled <= 1.0:
                    values.add(round(scaled * 100, 4))
            return
        if isinstance(node, dict):
            for item in node.values():
                walk(item)
        elif isinstance(node, list):
            for item in node:
                walk(item)
        elif isinstance(node, str):
            for token in re.findall(r"-?\d+(?:\.\d+)?", node):
                try:
                    values.add(float(token))
                except ValueError:
                    continue

    walk(packet.model_dump(mode="json"))
    return values


def prose_numbers(text: str) -> list[str]:
    """Numbers asserted in prose, as written.

    Returned as strings because the printed precision is what the grounding
    test needs; parsing to float first would discard it. Record ids and ISO
    dates are stripped: their digits are identifiers, not claims.
    """
    cleaned = re.sub(r"\b[a-z_]+-\d{3}\b", " ", text, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", cleaned)
    return re.findall(r"\d+(?:\.\d+)?", cleaned)


def is_grounded(printed: str, grounded: set[float]) -> bool:
    """Does any packet value round to `printed` at the precision it shows?"""
    try:
        value = float(printed)
    except ValueError:
        return False
    decimals = len(printed.split(".")[1]) if "." in printed else 0
    return any(round(candidate, decimals) == value for candidate in grounded)


def score_report(report: Any, packet: EvidencePacket) -> dict[str, Any]:
    grounded = grounded_numbers(packet)
    body = " ".join(section.body for section in report.sections)

    asserted = prose_numbers(body)
    ungrounded = [
        printed
        for printed in asserted
        if float(printed) not in STRUCTURAL_NUMBERS
        and not is_grounded(printed, grounded)
    ]

    valid_ids = set(packet.record_ids)
    cited = [ref for section in report.sections for ref in section.evidence_refs]
    bad_refs = [ref for ref in cited if ref not in valid_ids]

    return {
        "child_id": packet.child_id,
        "provider": report.provider,
        "model": report.model,
        "used_fallback": report.provider == "deterministic_fallback",
        "n_sections": len(report.sections),
        "validation_passed": report.validation_passed,
        "validation_errors": report.validation_errors,
        "n_numbers_asserted": len(asserted),
        "n_numbers_ungrounded": len(ungrounded),
        "ungrounded_examples": sorted(set(ungrounded))[:8],
        "detector_calibration": (
            "fallback reports are grounded by construction; a non-zero "
            "ungrounded count on one is a false positive of the rule"
        ),
        "numeric_groundedness": (
            round(1 - len(ungrounded) / len(asserted), 4) if asserted else None
        ),
        "n_evidence_refs": len(cited),
        "n_invalid_refs": len(bad_refs),
        "invalid_ref_examples": bad_refs[:5],
        "adequacy_level": packet.adequacy.level.value,
        "n_records": packet.observation_count,
    }


async def run(model: str, limit: int | None) -> dict[str, Any]:
    by_child = load_records()
    children = sorted(by_child)[: limit or None]
    client = ReportingClient(provider="ollama", model=model)

    scored: list[dict[str, Any]] = []
    for index, child_id in enumerate(children, start=1):
        packet = build_packet(child_id, by_child[child_id])
        try:
            report = await client.generate_report(packet)
        except Exception as exc:  # noqa: BLE001 - a failed child must not stop the run
            scored.append({"child_id": child_id, "error": repr(exc)})
            print(f"  [{index}/{len(children)}] {child_id}: ERROR {exc!r}")
            continue
        entry = score_report(report, packet)
        scored.append(entry)
        state = "fallback" if entry["used_fallback"] else "llm"
        print(
            f"  [{index}/{len(children)}] {child_id}: {state}, "
            f"{entry['n_sections']} sections, "
            f"groundedness {entry['numeric_groundedness']}, "
            f"{entry['n_invalid_refs']} bad refs, "
            f"{len(entry['validation_errors'])} validation errors"
        )

    llm_reports = [e for e in scored if not e.get("used_fallback") and "error" not in e]
    rates = [
        e["numeric_groundedness"]
        for e in llm_reports
        if e["numeric_groundedness"] is not None
    ]
    return {
        "model": model,
        "n_children": len(children),
        "n_llm_reports": len(llm_reports),
        "n_fallback_reports": sum(1 for e in scored if e.get("used_fallback")),
        "n_errors": sum(1 for e in scored if "error" in e),
        "metadata_note": (
            "Evidence packets built from adjudicated gold records; observation "
            "date, setting and contributor role derived from corpus structure, "
            "not from real intervention records."
        ),
        "summary": {
            # Pooled over assertions, which is what a count and a denominator
            # imply. The mean of per-report rates is a different estimator and
            # gives a different number (each report weighted equally rather
            # than each assertion); it is kept, labelled, for reference rather
            # than reported beside a count.
            "numeric_assertions": sum(e["n_numbers_asserted"] for e in llm_reports),
            "numeric_ungrounded": sum(
                e["n_numbers_ungrounded"] for e in llm_reports
            ),
            "pooled_ungrounded_rate": (
                round(
                    sum(e["n_numbers_ungrounded"] for e in llm_reports)
                    / sum(e["n_numbers_asserted"] for e in llm_reports),
                    4,
                )
                if sum(e["n_numbers_asserted"] for e in llm_reports)
                else None
            ),
            "evidence_references": sum(e["n_evidence_refs"] for e in llm_reports),
            "evidence_references_invalid": sum(
                e["n_invalid_refs"] for e in llm_reports
            ),
            "pooled_invalid_reference_rate": (
                round(
                    sum(e["n_invalid_refs"] for e in llm_reports)
                    / sum(e["n_evidence_refs"] for e in llm_reports),
                    4,
                )
                if sum(e["n_evidence_refs"] for e in llm_reports)
                else None
            ),
            "mean_of_per_report_groundedness": (
                round(sum(rates) / len(rates), 4) if rates else None
            ),
            "mean_numeric_groundedness": (
                round(sum(rates) / len(rates), 4) if rates else None
            ),
            "reports_fully_grounded": sum(
                1 for e in llm_reports if e["n_numbers_ungrounded"] == 0
            ),
            "total_numbers_asserted": sum(e["n_numbers_asserted"] for e in llm_reports),
            "total_numbers_ungrounded": sum(
                e["n_numbers_ungrounded"] for e in llm_reports
            ),
            "reports_with_invalid_refs": sum(
                1 for e in llm_reports if e["n_invalid_refs"] > 0
            ),
            "total_invalid_refs": sum(e["n_invalid_refs"] for e in llm_reports),
            "reports_passing_validation": sum(
                1 for e in llm_reports if e["validation_passed"]
            ),
            "prohibited_content_reports": sum(
                1
                for e in llm_reports
                if any("Prohibited" in err for err in e["validation_errors"])
            ),
        },
        "per_child": scored,
    }


def render(report: dict[str, Any]) -> None:
    s = report["summary"]
    n = report["n_llm_reports"]
    print(f"\nReporting groundedness -- {report['model']}")
    print(f"  reports scored (LLM)      : {n} of {report['n_children']} children")
    print(f"  fallback (excluded)       : {report['n_fallback_reports']}")
    print(f"  errors                    : {report['n_errors']}")
    if not n:
        print("\n  No LLM-generated report to score.")
        return
    print("\n  content safety")
    print(f"    reports with prohibited content : "
          f"{s['prohibited_content_reports']}/{n}")
    print("\n  evidence grounding")
    print(f"    ungrounded numeric assertions   : {s['numeric_ungrounded']}/"
          f"{s['numeric_assertions']} ({100 * (s['pooled_ungrounded_rate'] or 0):.1f}%)")
    print(f"    invalid evidence references     : "
          f"{s['evidence_references_invalid']}/{s['evidence_references']} "
          f"({100 * (s['pooled_invalid_reference_rate'] or 0):.1f}%)")
    print(f"    reports with no ungrounded value: "
          f"{s['reports_fully_grounded']}/{n}")
    print("\n  abstention / governance preservation")
    print(f"    reports passing governance check: "
          f"{s['reports_passing_validation']}/{n}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    for path in (GOLD_PATH, BATCH_PATH):
        if not path.exists():
            raise SystemExit(f"{path} not found.")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    report = asyncio.run(run(args.model, args.limit))
    render(report)
    OUT_PATH.write_text(json.dumps(report, indent=2) + "\n")
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
