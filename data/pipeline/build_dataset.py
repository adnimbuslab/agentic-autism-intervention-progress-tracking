"""Merge Rollins + Flusberg corpora into one unified long-format dataset.

Produces a CSV/DataFrame with one row per utterance, standardized columns,
disambiguated child IDs, and computed relative_month values.

Target: ~75,003 rows from 11 children across 85 sessions.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

from data.pipeline.chat_parser import parse_corpus_directory
from data.pipeline.models import Session, UnifiedRow

ROLLINS_CHILDREN: dict[str, list[str]] = {
    "carl": ["carl"],
    "roger_rollins": ["roger"],
    "sid": ["sid"],
    "mars": ["mars"],
    "josh": ["josh"],
}

FLUSBERG_CHILDREN: dict[str, list[str]] = {
    "jack": ["jack"],
    "rick": ["rick"],
    "mark": ["mark"],
    "brett": ["brett"],
    "stuart": ["stuart"],
    "roger_flusberg": ["roger"],
}


def build_unified_dataset(
    rollins_dir: Path,
    flusberg_dir: Path,
    output_path: Optional[Path] = None,
) -> pd.DataFrame:
    """Parse both corpora and merge into a unified dataset."""
    rollins_sessions = parse_corpus_directory(rollins_dir, "rollins", ROLLINS_CHILDREN)
    flusberg_sessions = parse_corpus_directory(flusberg_dir, "flusberg", FLUSBERG_CHILDREN)

    all_sessions = rollins_sessions + flusberg_sessions
    rows = _sessions_to_rows(all_sessions)
    df = pd.DataFrame([row.model_dump() for row in rows])

    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(output_path, index=False)
        print(f"Wrote {len(df)} rows to {output_path}")

    return df


def _sessions_to_rows(sessions: list[Session]) -> list[UnifiedRow]:
    """Convert parsed sessions into flat unified rows."""
    earliest_dates: dict[str, date] = {}
    for session in sessions:
        if session.header.date is not None:
            key = f"{session.corpus}_{session.child_id}"
            if key not in earliest_dates or session.header.date < earliest_dates[key]:
                earliest_dates[key] = session.header.date

    rows: list[UnifiedRow] = []
    for session in sessions:
        session_id = f"{session.corpus}_{session.child_id}_{session.source_file}"
        relative_month = _compute_relative_month(
            session.header.date,
            earliest_dates.get(f"{session.corpus}_{session.child_id}"),
        )

        for utterance in session.utterances:
            tier_spa = None
            tier_act = None
            tier_gpx = None
            for tier in utterance.dependent_tiers:
                if tier.tier_type == "spa":
                    tier_spa = tier.content
                elif tier.tier_type == "act":
                    tier_act = tier.content
                elif tier.tier_type == "gpx":
                    tier_gpx = tier.content

            rows.append(
                UnifiedRow(
                    corpus=session.corpus,
                    child_id=session.child_id,
                    session_id=session_id,
                    source_file=session.source_file,
                    date=session.header.date,
                    relative_month=relative_month,
                    speaker=utterance.speaker,
                    utterance_text=utterance.text,
                    line_number=utterance.line_number,
                    tier_spa=tier_spa,
                    tier_act=tier_act,
                    tier_gpx=tier_gpx,
                )
            )

    return rows


def _compute_relative_month(
    session_date: Optional[date],
    earliest_date: Optional[date],
) -> Optional[int]:
    """Compute months elapsed since the child's earliest session."""
    if session_date is None or earliest_date is None:
        return None
    delta = session_date - earliest_date
    return max(0, delta.days // 30)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python -m data.pipeline.build_dataset <rollins_dir> <flusberg_dir> [output.csv]")
        sys.exit(1)

    rollins = Path(sys.argv[1])
    flusberg = Path(sys.argv[2])
    output = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("data/output/unified_dataset.csv")

    df = build_unified_dataset(rollins, flusberg, output)
    print(f"\nDataset summary:")
    print(f"  Total rows: {len(df)}")
    print(f"  Unique children: {df['child_id'].nunique()}")
    print(f"  Unique sessions: {df['session_id'].nunique()}")
    print(f"  Corpora: {df['corpus'].unique().tolist()}")
    print(f"  Speakers: {df['speaker'].unique().tolist()}")
