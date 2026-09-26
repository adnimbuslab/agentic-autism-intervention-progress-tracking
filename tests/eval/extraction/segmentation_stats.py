"""Describe what the segmentation pipeline produces, measured on the corpus.

Answers "what does one model input represent" with counts rather than prose:
utterances in, episodes out, how long episodes are, whether they overlap,
which episode types exist before and after the balanced selection, what is
excluded on the way, and whether two runs agree exactly.

Needs the ASDBank corpora locally (exp-data/). Writes counts only -- no
transcript text -- to results/segmentation_stats.json.

    uv run python -m tests.eval.extraction.segmentation_stats
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from data.pipeline import segment_episodes as seg
from data.pipeline.build_dataset import FLUSBERG_CHILDREN, ROLLINS_CHILDREN
from data.pipeline.chat_parser import parse_corpus_directory
from data.pipeline.deidentify import deidentify_sessions
from data.pipeline.select_segments import select_segments
from tests.eval.extraction.sample_real_segments import ROLLINS_DIR, ensure_flusberg_extracted

OUT = Path(__file__).parent / "results" / "segmentation_stats.json"


def run_pipeline():
    sessions = (parse_corpus_directory(ROLLINS_DIR, "rollins", ROLLINS_CHILDREN)
                + parse_corpus_directory(ensure_flusberg_extracted(), "flusberg", FLUSBERG_CHILDREN))
    deid = deidentify_sessions(sessions).sessions
    return sessions, deid, seg.segment_sessions(deid)


def fingerprint(episodes) -> str:
    h = hashlib.sha256()
    for e in episodes:
        h.update(f"{e.episode_id}|{e.source_file}|{e.start_line}|{e.end_line}|{e.episode_type.value}\n".encode())
    return h.hexdigest()


def main() -> None:
    sessions, deid, episodes = run_pipeline()
    _, _, episodes_again = run_pipeline()

    # Candidate windows before the two exclusion rules, re-derived with the
    # pipeline's own boundary function.
    windows = short = no_child = 0
    for s in deid:
        if len(s.utterances) < seg.MIN_EPISODE_TURNS:
            continue
        for start, end in seg._find_episode_boundaries(s.utterances):
            windows += 1
            chunk = s.utterances[start:end]
            if len(chunk) < seg.MIN_EPISODE_TURNS:
                short += 1
            elif not seg._has_child_turn(chunk):
                no_child += 1

    overlaps = 0
    by_session: dict[str, list] = {}
    for e in episodes:
        by_session.setdefault(e.session_id, []).append(e)
    for eps in by_session.values():
        eps.sort(key=lambda e: e.start_line)
        overlaps += sum(1 for a, b in zip(eps, eps[1:]) if b.start_line <= a.end_line)

    lengths = Counter(len(e.utterances) for e in episodes)
    speakers = Counter(u.speaker for e in episodes for u in e.utterances)
    tiers = Counter(t.tier_type for e in episodes for u in e.utterances for t in u.dependent_tiers)
    selected = {cap: select_segments(episodes, max_segments=cap) for cap in (3000, 5000)}

    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "n_sessions": len(sessions),
        "n_utterances": sum(len(s.utterances) for s in sessions),
        "n_candidate_windows": windows,
        "excluded_shorter_than_min_turns": short,
        "excluded_no_child_turn": no_child,
        "n_episodes": len(episodes),
        "min_turns": seg.MIN_EPISODE_TURNS,
        "max_turns": seg.MAX_EPISODE_TURNS,
        "episode_length_distribution": dict(sorted(lengths.items())),
        "mean_episode_length": round(sum(k * v for k, v in lengths.items()) / len(episodes), 2),
        "adjacent_episode_pairs_sharing_an_utterance": overlaps,
        "episode_types_all": dict(Counter(e.episode_type.value for e in episodes).most_common()),
        "episode_types_selected_cap3000": dict(Counter(
            e.episode_type.value for e in _selected_episodes(episodes, 3000)).most_common()),
        "n_selected": {str(k): len(v) for k, v in selected.items()},
        "speakers_in_episodes": dict(speakers.most_common()),
        "dependent_tiers_parsed": dict(tiers.most_common()),
        "dependent_tiers_rendered_to_model": ["spa", "act", "gpx"],
        "deterministic": fingerprint(episodes) == fingerprint(episodes_again),
        "episode_fingerprint_sha256": fingerprint(episodes),
    }
    OUT.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "generated_at"}, indent=1))


def _selected_episodes(episodes, cap: int):
    """The episodes `select_segments` keeps, by the same rule, as Episode objects.

    `select_segments` returns segments, which no longer carry episode type or
    line numbers; this reapplies its per-child cap and per-type quota and is
    checked against it by count.
    """
    import math

    from data.pipeline import select_segments as sel

    by_child: dict[str, list] = {}
    for e in episodes:
        by_child.setdefault(e.child_id, []).append(e)
    per_child = math.ceil(cap / len(by_child))
    chosen = [e for es in by_child.values() for e in sel._select_for_child(es, per_child)][:cap]
    assert len(chosen) == len(select_segments(episodes, max_segments=cap))
    return chosen


if __name__ == "__main__":
    main()
