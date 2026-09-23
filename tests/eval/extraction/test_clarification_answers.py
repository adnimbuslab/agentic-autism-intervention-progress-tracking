"""The reviewer answer sheets must not outlive the facts they assert.

`clarification_answers.md` and `clarification_answers_round2.md` are sent to
reviewers as statements of what the system does. They were written against one
state of the repository and are not regenerated from artefacts, so every change
to the code or the results is a chance for one of them to quietly become false
-- and a false answer to a direct reviewer question is worse than no answer.

These check the claims that this session's work has already invalidated once:
the deployed configuration, the reporting default, and whether the held-out
round is finished.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RESULTS = Path(__file__).parent / "results"
ROUND1 = ROOT / "docs/paper/clarification_answers.md"
ROUND2 = ROOT / "docs/paper/clarification_answers_round2.md"

ALL_QUESTIONS = 20  # round 1, section A-E
ROUND2_QUESTIONS = 8


@pytest.fixture(scope="module")
def round1() -> str:
    return ROUND1.read_text()


@pytest.fixture(scope="module")
def round2() -> str:
    return ROUND2.read_text()


class TestCoverage:
    def test_every_round1_question_has_an_answer(self, round1) -> None:
        answered = {int(m) for m in re.findall(r"^### Q(\d+) ", round1, re.M)}
        assert answered == set(range(1, ALL_QUESTIONS + 1)), (
            f"missing: {sorted(set(range(1, ALL_QUESTIONS + 1)) - answered)}"
        )

    def test_every_round2_question_has_an_answer(self, round2) -> None:
        answered = {int(m) for m in re.findall(r"^## Q(\d+) ", round2, re.M)}
        assert answered == set(range(1, ROUND2_QUESTIONS + 1))


class TestAnswersMatchTheCode:
    """Claims about the running system, checked against the running system."""

    def test_the_named_deployed_model_is_the_configured_one(
        self, round2
    ) -> None:
        from src.backend.config import settings

        assert f'"{settings.ollama_model}"' in round2, settings.ollama_model

    def test_the_reporting_default_is_stated_correctly(self, round2) -> None:
        from src.backend.config import settings

        assert settings.reporting_mode == "deterministic"
        assert '`"deterministic"`' in round2

    def test_the_verification_gate_is_described(self, round2) -> None:
        from src.backend.models.observation import RecordStatus

        assert "VERIFIED, CORRECTED" in round2
        assert RecordStatus.VERIFIED.value == "verified"

    def test_no_answer_still_calls_mars_reachable(self, round1, round2) -> None:
        for text in (round1, round2):
            assert "not reachable from" in text or "not in the default path" in text


class TestAnswersMatchTheArtefacts:
    def test_the_holdout_answer_is_not_stale(self, round2) -> None:
        gold = RESULTS / "gold_holdout_labels.json"
        if not gold.exists():
            assert "Adjudication is not complete" in round2
            return
        # Gold exists, so the headline answer must say so. The superseded text
        # is kept deliberately under its own heading; the live answer is the
        # one immediately under "## Q3".
        head = round2.split("## Q3 —", 1)[1].split("---", 1)[0]
        assert "Adjudication is complete" in head
        assert "Adjudication is not complete" not in head

    def test_the_holdout_segment_count_matches_gold(self, round2) -> None:
        gold_path = RESULTS / "gold_holdout_labels.json"
        if not gold_path.exists():
            pytest.skip("held-out gold not built")
        gold = json.loads(gold_path.read_text())
        n = gold["n_segments_in_gold"]
        assert f"all {n} segments entered" in round2.lower()

    def test_the_manifest_counts_are_current(self, round1) -> None:
        manifest = json.loads(
            (ROOT / "docs/paper/artifact_manifest.json").read_text()
        )
        total = len(manifest["artefacts"])
        pinned = sum(1 for a in manifest["artefacts"] if a.get("pinned"))
        assert f"{total} artefacts, {pinned}" in round1, (total, pinned)
