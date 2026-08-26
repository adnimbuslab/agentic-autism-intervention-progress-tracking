"""CHAT pipeline E2E: synthetic .cha → parse → deidentify → segment →
select → ExtractionRequest → mocked LLM → provisional extraction.

Uses ONLY synthetic CHAT data. No real transcripts or participant data.
"""
from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from data.pipeline.chat_parser import parse_chat_file
from data.pipeline.deidentify import deidentify_sessions
from data.pipeline.models import BehavioralSegment, Episode, EpisodeType, Session
from data.pipeline.segment_episodes import segment_sessions
from data.pipeline.select_segments import select_segments
from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    ExtractionResult,
    ExtractionStatus,
    SourceType,
)
from src.backend.schemas.observation_schema import (
    ContributorRole,
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    Setting,
    StructuredObservation,
)

SYNTHETIC_CHA = """\
@UTF8
@Begin
@Languages:\teng
@Participants:\tCHI Child Target_Child, INV Investigator Investigator
@ID:\teng|Test|CHI|3;06.||||Target_Child|||
@ID:\teng|Test|INV||||||Investigator|||
@Date:\t01-JAN-2025
*INV:\twhat do you want ?
%spa:\t$q:y
*CHI:\twant cookie .
%spa:\t$r:aa
*INV:\tcan you say cookie please ?
%spa:\t$q:y
*CHI:\tcookie please .
%spa:\t$r:aa
*INV:\tgood job saying cookie please .
%spa:\t$f:ab
*CHI:\tmore cookie .
%spa:\t$r:aa
*INV:\twhat color is this ?
%spa:\t$q:y
*CHI:\tred .
%spa:\t$r:aa
*INV:\tyeah that is red .
%spa:\t$f:ab
*CHI:\tplay ball .
%spa:\t$r:aa
*INV:\tdo you want to play with the ball ?
%spa:\t$q:y
*CHI:\tyes play ball .
%spa:\t$r:aa
@End
"""


@pytest.mark.integration
class TestChatPipelineE2E:

    @pytest.fixture
    def synthetic_cha_file(self, tmp_path):
        p = tmp_path / "synthetic_test.cha"
        p.write_text(SYNTHETIC_CHA, encoding="utf-8")
        return p

    def test_parse_synthetic_cha(self, synthetic_cha_file):
        session = parse_chat_file(synthetic_cha_file, corpus="TestCorpus", child_id="SYN001")
        assert session.corpus == "TestCorpus"
        assert session.child_id == "SYN001"
        assert session.source_file == "synthetic_test.cha"
        assert session.utterance_count >= 10
        speakers = {u.speaker for u in session.utterances}
        assert "CHI" in speakers
        assert "INV" in speakers

    def test_deidentify_synthetic(self, synthetic_cha_file):
        session = parse_chat_file(synthetic_cha_file, corpus="TestCorpus", child_id="SYN001")
        result = deidentify_sessions([session])
        assert len(result.sessions) == 1
        deidentified = result.sessions[0]
        assert deidentified.child_id == "SYN001"
        for u in deidentified.utterances:
            assert "123-45-6789" not in u.text
            assert u.text is not None

    def test_segment_synthetic(self, synthetic_cha_file):
        session = parse_chat_file(synthetic_cha_file, corpus="TestCorpus", child_id="SYN001")
        result = deidentify_sessions([session])
        episodes = segment_sessions(result.sessions)
        assert len(episodes) >= 1
        for ep in episodes:
            assert ep.child_id == "SYN001"
            assert ep.corpus == "TestCorpus"
            assert len(ep.utterances) >= 2
            assert ep.episode_type in [e for e in EpisodeType]

    def test_select_segments_synthetic(self, synthetic_cha_file):
        session = parse_chat_file(synthetic_cha_file, corpus="TestCorpus", child_id="SYN001")
        result = deidentify_sessions([session])
        episodes = segment_sessions(result.sessions)
        segments = select_segments(episodes, max_segments=100)
        assert len(segments) >= 1
        for seg in segments:
            assert seg.segment_id is not None
            assert seg.source.corpus == "TestCorpus"
            assert seg.source.child_id == "SYN001"
            assert len(seg.source.turns) >= 1

    def test_full_pipeline_provenance(self, synthetic_cha_file):
        session = parse_chat_file(synthetic_cha_file, corpus="TestCorpus", child_id="SYN001")
        deidentified = deidentify_sessions([session])
        episodes = segment_sessions(deidentified.sessions)
        segments = select_segments(episodes, max_segments=100)

        for seg in segments:
            assert seg.source.corpus == "TestCorpus"
            assert seg.source.child_id == "SYN001"
            assert seg.source.source_file == "synthetic_test.cha"
            assert seg.provisional_extraction.status == "provisional_llm"
            assert seg.provisional_extraction.structured_record is None

    def test_segment_to_extraction_request(self, synthetic_cha_file):
        session = parse_chat_file(synthetic_cha_file, corpus="TestCorpus", child_id="SYN001")
        deidentified = deidentify_sessions([session])
        episodes = segment_sessions(deidentified.sessions)
        segments = select_segments(episodes, max_segments=100)
        assert len(segments) >= 1

        seg = segments[0]
        text = "\n".join(f"{t.speaker}: {t.text}" for t in seg.source.turns)
        request = ExtractionRequest(
            source_type=SourceType.CHAT_SEGMENT,
            text=text,
            child_id=seg.source.child_id,
            session_id=seg.source.session_id,
            contributor_role=ContributorRole.INTERVENTIONIST,
            observation_date=date.today(),
            setting=Setting.CLINIC,
        )
        assert request.source_type == SourceType.CHAT_SEGMENT
        assert request.child_id == "SYN001"
        assert len(request.text) > 0

    async def test_mocked_extraction_from_segment(self, synthetic_cha_file):
        session = parse_chat_file(synthetic_cha_file, corpus="TestCorpus", child_id="SYN001")
        deidentified = deidentify_sessions([session])
        episodes = segment_sessions(deidentified.sessions)
        segments = select_segments(episodes, max_segments=100)
        assert len(segments) >= 1

        seg = segments[0]
        text = "\n".join(f"{t.speaker}: {t.text}" for t in seg.source.turns)
        request = ExtractionRequest(
            source_type=SourceType.CHAT_SEGMENT,
            text=text,
            child_id=seg.source.child_id,
            session_id=seg.source.session_id,
            contributor_role=ContributorRole.INTERVENTIONIST,
            observation_date=date.today(),
            setting=Setting.CLINIC,
        )

        mock_provider = AsyncMock()

        async def _mock_extract(req):
            obs = StructuredObservation(
                child_id=req.child_id,
                session_id=req.session_id,
                contributor_role=req.contributor_role,
                observation_date=req.observation_date,
                setting=req.setting,
                domain=Domain.SOCIAL_COMMUNICATION,
                behavior="requested cookie using verbal modality",
                modality=Modality.VERBAL,
                prompt_level=PromptLevel.INDEPENDENT,
                outcome=Outcome.CORRECT,
                confidence=0.82,
            )
            return ExtractionResult(
                status=ExtractionStatus.SUCCESS,
                observations=[obs],
                provider="test_mock",
                model="mock-v1",
                prompt_version="test-1.0",
            )

        mock_provider.extract = AsyncMock(side_effect=_mock_extract)
        result = await mock_provider.extract(request)

        assert result.status == ExtractionStatus.SUCCESS
        assert result.observations[0].child_id == "SYN001"
        assert result.observations[0].setting == Setting.CLINIC
        assert result.observations[0].contributor_role == ContributorRole.INTERVENTIONIST
        assert result.observations[0].behavior is not None

    def test_deidentification_removes_pii(self, synthetic_cha_file):
        cha_with_pii = SYNTHETIC_CHA.replace(
            "*CHI:\twant cookie .",
            "*CHI:\tmy name is John and I live at 123 Main Street .",
        )
        pii_file = synthetic_cha_file.parent / "pii_test.cha"
        pii_file.write_text(cha_with_pii, encoding="utf-8")

        session = parse_chat_file(pii_file, corpus="TestCorpus", child_id="SYN001")
        result = deidentify_sessions([session])
        deidentified = result.sessions[0]

        all_text = " ".join(u.text for u in deidentified.utterances)
        assert "123 Main Street" not in all_text
