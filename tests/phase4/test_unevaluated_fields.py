"""The three extracted fields that have no reference standard.

The extraction provider is asked for eight fields. Five of them -- behavior,
domain, modality, prompt_level and outcome -- were scored against an
adjudicated gold standard. The other three were not: `goal_context`,
`prompt_context` and `duration_seconds` have no reference standard in this
study, so nothing is known about how often a model invents them.

An unevaluated field is not forbidden, but it must not drive a number. These
tests pin where the three are allowed to go: into no KPI, into no adequacy
check, and into no deterministically rendered report. They reach the evidence
packet, and from there the experimental generative reporter can see them --
which is one more reason that path is not operational.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.backend.ml import (
    adequacy_router,
    analytics_engine,
    forecasting_engine,
    reporting_client,
)
from src.backend.services import analytics_service

EVALUATED = ("behavior", "domain", "modality", "prompt_level", "outcome")
UNEVALUATED = ("goal_context", "prompt_context", "duration_seconds")

# Modules that turn record fields into numbers a professional would read.
NUMERIC_SURFACES = (
    analytics_engine,
    adequacy_router,
    forecasting_engine,
    analytics_service,
)


def _source(module) -> str:
    return Path(module.__file__).read_text()


@pytest.mark.parametrize("field", UNEVALUATED)
@pytest.mark.parametrize(
    "module", NUMERIC_SURFACES, ids=lambda m: m.__name__.rsplit(".", 1)[-1]
)
def test_no_unevaluated_field_reaches_analytics(module, field) -> None:
    assert not re.search(rf'["\']{field}["\']', _source(module)), (
        f"{module.__name__} reads '{field}', which has no reference standard "
        "in this study; a KPI computed from it would carry an accuracy nobody "
        "has measured"
    )


@pytest.mark.parametrize("field", EVALUATED)
def test_the_evaluated_fields_are_the_ones_analytics_uses(field) -> None:
    # The converse: the five scored fields are scored because they are the
    # ones that drive numbers. If this fails, the evaluation scope and the
    # analytics scope have drifted apart.
    combined = "".join(_source(m) for m in NUMERIC_SURFACES)
    assert re.search(rf'["\']{field}["\']', combined)


@pytest.mark.parametrize("field", UNEVALUATED)
def test_the_deterministic_reporter_never_renders_them(field) -> None:
    # The operational reporting path builds prose from KPIs and packet-level
    # counts, not from arbitrary record fields.
    assert not re.search(rf'["\']{field}["\']', _source(reporting_client))
