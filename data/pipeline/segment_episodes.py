"""Episode segmentation of CHAT session data (Step 4).

Identifies coherent behavioral episodes of 2-8 consecutive turns from
parsed sessions. Each episode is centered on a communicative or behavioral
event involving the child (CHI speaker).
"""

from __future__ import annotations

import re

from data.pipeline.models import (
    DependentTier,
    Episode,
    EpisodeType,
    Session,
    Utterance,
)

MIN_EPISODE_TURNS = 2
MAX_EPISODE_TURNS = 8


def segment_sessions(sessions: list[Session]) -> list[Episode]:
    """Segment all sessions into behavioral episodes."""
    episodes: list[Episode] = []
    for session in sessions:
        session_id = f"{session.corpus}_{session.child_id}_{session.source_file}"
        session_episodes = _segment_single_session(session, session_id)
        episodes.extend(session_episodes)
    return episodes


def _segment_single_session(session: Session, session_id: str) -> list[Episode]:
    """Extract episodes from a single session."""
    utterances = session.utterances
    if len(utterances) < MIN_EPISODE_TURNS:
        return []

    boundaries = _find_episode_boundaries(utterances)
    episodes: list[Episode] = []
    seq = 0

    for start, end in boundaries:
        chunk = utterances[start:end]
        if len(chunk) < MIN_EPISODE_TURNS:
            continue
        if not _has_child_turn(chunk):
            continue

        episode_type = _classify_episode(chunk)
        seq += 1
        episode = Episode(
            episode_id=f"{session.child_id}_{session_id}_ep_{seq:03d}",
            corpus=session.corpus,
            child_id=session.child_id,
            session_id=session_id,
            source_file=session.source_file,
            episode_type=episode_type,
            utterances=chunk,
            start_line=chunk[0].line_number,
            end_line=chunk[-1].line_number,
        )
        episodes.append(episode)

    return episodes


def _find_episode_boundaries(utterances: list[Utterance]) -> list[tuple[int, int]]:
    """Find (start, end) index pairs for episode boundaries."""
    boundaries: list[tuple[int, int]] = []
    current_start: int | None = None

    for i, utt in enumerate(utterances):
        if current_start is None:
            if _is_episode_start(utt, utterances, i):
                current_start = max(0, i - 1) if i > 0 else i
        else:
            turns_so_far = i - current_start + 1
            if turns_so_far >= MAX_EPISODE_TURNS or _is_episode_end(utt, utterances, i, current_start):
                boundaries.append((current_start, i + 1))
                current_start = None

    if current_start is not None:
        boundaries.append((current_start, len(utterances)))

    return boundaries


def _is_episode_start(utt: Utterance, utterances: list[Utterance], idx: int) -> bool:
    """A child turn that follows a gap or topic shift starts a new episode."""
    if utt.speaker != "CHI":
        return False
    if _has_behavioral_annotation(utt):
        return True
    if idx == 0:
        return True
    prev = utterances[idx - 1]
    if prev.speaker != "CHI":
        return True
    return False


def _is_episode_end(
    utt: Utterance,
    utterances: list[Utterance],
    idx: int,
    start: int,
) -> bool:
    """Check whether the current position should end the episode."""
    turns = idx - start + 1
    if turns >= MAX_EPISODE_TURNS:
        return True

    remaining = utterances[idx + 1:] if idx + 1 < len(utterances) else []
    if not remaining:
        return True

    chi_in_remaining_window = any(
        u.speaker == "CHI" for u in remaining[:3]
    )
    if not chi_in_remaining_window and turns >= MIN_EPISODE_TURNS:
        return True

    return False


def _has_child_turn(utterances: list[Utterance]) -> bool:
    """Check if any utterance is from the child speaker."""
    return any(u.speaker == "CHI" for u in utterances)


def _has_behavioral_annotation(utt: Utterance) -> bool:
    """Check if an utterance has spa, act, or gpx tier annotations."""
    return any(
        t.tier_type in ("spa", "act", "gpx") for t in utt.dependent_tiers
    )


def _classify_episode(utterances: list[Utterance]) -> EpisodeType:
    """Determine the episode type from utterance content and tier annotations."""
    all_spa = _collect_tier_content(utterances, "spa")
    all_act = _collect_tier_content(utterances, "act")
    all_gpx = _collect_tier_content(utterances, "gpx")

    spa_upper = all_spa.upper()
    gpx_lower = all_gpx.lower()
    act_lower = all_act.lower()
    all_text = " ".join(u.text.lower() for u in utterances)

    if _matches_request(spa_upper):
        return EpisodeType.REQUEST

    if _matches_imitation(spa_upper):
        return EpisodeType.IMITATION

    if _matches_protest(spa_upper, gpx_lower):
        return EpisodeType.PROTEST

    if _matches_joint_attention(gpx_lower):
        return EpisodeType.JOINT_ATTENTION

    if _matches_response(spa_upper):
        return EpisodeType.RESPONSE

    if _matches_play(act_lower, gpx_lower, all_text):
        return EpisodeType.PLAY

    if _matches_initiation(utterances):
        return EpisodeType.INITIATION

    return EpisodeType.OTHER


def _collect_tier_content(utterances: list[Utterance], tier_type: str) -> str:
    """Concatenate all content of a given tier type across utterances."""
    parts: list[str] = []
    for utt in utterances:
        for tier in utt.dependent_tiers:
            if tier.tier_type == tier_type:
                parts.append(tier.content)
    return " ".join(parts)


def _matches_request(spa: str) -> bool:
    return bool(re.search(r"\bREQ\b|\bQN\b|\$Q:", spa, re.IGNORECASE))


def _matches_imitation(spa: str) -> bool:
    return bool(re.search(r"\bIM\b|\$IM", spa, re.IGNORECASE))


def _matches_protest(spa: str, gpx: str) -> bool:
    if re.search(r"\bNO\b|\bPR\b", spa):
        return True
    if re.search(r"push\w*\s+away|turn\w*\s+away|shak\w*\s+head", gpx):
        return True
    return False


def _matches_joint_attention(gpx: str) -> bool:
    return bool(re.search(r"point|show|referenc|look\w*\s+at|gaze", gpx))


def _matches_response(spa: str) -> bool:
    return bool(re.search(r"\bAN\b|\bRP\b|\$R:", spa, re.IGNORECASE))


def _matches_play(act: str, gpx: str, text: str) -> bool:
    play_terms = r"play|toy|block|ball|doll|puzzle|game|pretend|stack|build"
    return bool(re.search(play_terms, act) or re.search(play_terms, gpx) or re.search(play_terms, text))


def _matches_initiation(utterances: list[Utterance]) -> bool:
    """Child-initiated when the first CHI turn precedes any adult response."""
    for utt in utterances:
        if utt.speaker == "CHI":
            return True
        if utt.speaker != "CHI":
            return False
    return False


if __name__ == "__main__":
    print("Episode segmentation pipeline (Step 4)")
    print("=" * 40)
    print()
    print("Usage:")
    print("  from data.pipeline.deidentify import deidentify_sessions")
    print("  from data.pipeline.segment_episodes import segment_sessions")
    print()
    print("  result = deidentify_sessions(sessions)")
    print("  episodes = segment_sessions(result.sessions)")
    print("  for ep in episodes:")
    print("      print(ep.episode_id, ep.episode_type, len(ep.utterances))")
    print()
    print("API:")
    print("  segment_sessions(sessions: list[Session]) -> list[Episode]")
    print("    - Identifies 2-8 turn behavioral episodes")
    print("    - Each episode contains at least one CHI turn")
    print("    - Classifies episodes: request, imitation, joint_attention,")
    print("      protest, response, initiation, play, other")
    print("    - Episode IDs: {child_id}_{session_id}_ep_{seq:03d}")
