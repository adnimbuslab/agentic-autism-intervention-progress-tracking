"""Shared test fixtures."""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest


@pytest.fixture
def sample_chat_content() -> str:
    return dedent("""\
        @UTF8
        @Begin
        @Languages:	eng
        @Participants:	CHI Target_Child, INV Investigator
        @ID:	eng|rollins|CHI|3;6.15|male|||Target_Child|||
        @ID:	eng|rollins|INV|||||Investigator|||
        @Date:	15-JAN-2000
        @Location:	Lab
        *INV:	what are you doing ?
        %spa:	$q:a
        *CHI:	I play with car .
        %spa:	$r:a $des
        %act:	picks up toy car
        %gpx:	reaching
        *INV:	oh that's a nice car .
        %spa:	$c:a
        *CHI:	xxx .
        *CHI:	0 .
        *CHI:	my car [+ trn] .
        @End
    """)


@pytest.fixture
def sample_chat_file(sample_chat_content: str, tmp_path: Path) -> Path:
    file_path = tmp_path / "test_session.cha"
    file_path.write_text(sample_chat_content, encoding="utf-8")
    return file_path


@pytest.fixture
def minimal_chat_content() -> str:
    return dedent("""\
        @UTF8
        @Begin
        @Participants:	CHI Target_Child
        *CHI:	hello .
        @End
    """)


@pytest.fixture
def minimal_chat_file(minimal_chat_content: str, tmp_path: Path) -> Path:
    file_path = tmp_path / "minimal.cha"
    file_path.write_text(minimal_chat_content, encoding="utf-8")
    return file_path


@pytest.fixture
def multiline_chat_content() -> str:
    return dedent("""\
        @UTF8
        @Begin
        @Participants:	CHI Target_Child, MOT Mother
        @Date:	2001-03-15
        *MOT:	can you tell me what you did
        	at school today ?
        %spa:	$q:a $req
        *CHI:	I went to the playground and
        	I played on the swings .
        %spa:	$r:a $des
        %act:	gestures toward window
        @End
    """)


@pytest.fixture
def multiline_chat_file(multiline_chat_content: str, tmp_path: Path) -> Path:
    file_path = tmp_path / "multiline.cha"
    file_path.write_text(multiline_chat_content, encoding="utf-8")
    return file_path
