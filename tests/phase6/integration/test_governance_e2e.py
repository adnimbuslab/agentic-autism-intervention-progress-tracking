"""Governance-critical end-to-end scenarios, run against the live extractor.

Unlike the rest of this package, nothing on the extraction path is mocked:
observations go through the configured ExtractionProvider (Ollama,
``qwen2.5:7b``), deterministic validation, routing, persistence, the
verification gate, the adequacy router, the analytics engine and the
operational deterministic reporter, all over HTTP against a real database.

Inputs are short synthetic observations written for this suite. No corpus
text is used. The model's field values are not asserted -- this suite tests
governance, not extraction quality -- so the scenarios hold whatever the model
extracts.

Scenarios (each on its own freshly created child, so they cannot interact):

    S1  unverified AI-extracted records never reach longitudinal analytics
    S2  verify-as-written and correct both make a record analytics-eligible;
        nothing else does, and a PENDING record cannot be verified as written
    S3  after a correction, analytics and reporting use the corrected version;
        the original record version and source observation are preserved
    S4  insufficient evidence -> affected analytics withheld, not forced
    S5  the operational (deterministic) report names every withheld analysis
    S6  a contributor cannot verify, correct or reach professional analytics

Run through ``scripts/run_governance_e2e.py``, which pins the build and the
model digest and writes the run record. Skipped unless GOVERNANCE_E2E=1.
"""
from __future__ import annotations

import json
import os
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from src.backend.config import settings

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("GOVERNANCE_E2E") != "1",
        reason="live-extractor governance run; use scripts/run_governance_e2e.py",
    ),
]

EXPECTED_MODEL = "qwen2.5:7b"
RECORD_PATH = os.environ.get("GOVERNANCE_E2E_RECORD")


def _log(scenario: str, **facts: Any) -> None:
    """Append what a scenario observed to the run record, when one is being written."""
    if RECORD_PATH:
        with open(RECORD_PATH, "a") as fh:
            fh.write(json.dumps({"scenario": scenario, **facts}) + "\n")

# Synthetic observations: invented for this suite, no corpus-derived text.
HOME = [
    "At snack time the child pointed at the juice box and said 'juice please' without any help.",
    "When I held up two toys the child reached for the car after I modeled the word 'car'.",
    "During bath time the child handed me the cup and said 'more water' on his own.",
]
SCHOOL = [
    "In circle time the child answered 'blue' when the teacher asked the colour of the ball.",
    "At recess the child waved and said 'hi' to a classmate after a verbal reminder.",
    "During art the child asked for 'glue' by signing after the aide pointed to the table.",
]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _new_child(client: AsyncClient, i_token: str, name: str, *, contributors: bool = True) -> str:
    resp = await client.post("/children/", headers=_auth(i_token), json={"display_name": name})
    assert resp.status_code == 201, resp.text
    child_id = resp.json()["id"]
    if contributors:
        for email, role in (("test-parent@example.com", "parent"), ("test-teacher@example.com", "teacher")):
            r = await client.post(f"/children/{child_id}/actors", headers=_auth(i_token),
                                  json={"email": email, "role": role})
            assert r.status_code == 201, r.text
    r = await client.post(f"/children/{child_id}/goals", headers=_auth(i_token), json={
        "goal_type": "long_term", "domain": "social_communication",
        "title": "Functional requesting", "description": "Synthetic goal for the governance run.",
    })
    assert r.status_code == 201, r.text
    return child_id


async def _review_period(client: AsyncClient, i_token: str, child_id: str) -> str:
    r = await client.post(f"/children/{child_id}/review-periods", headers=_auth(i_token), json={
        "start_date": (date.today() - timedelta(days=30)).isoformat(),
        "end_date": date.today().isoformat(),
    })
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _submit(client: AsyncClient, token: str, i_token: str, child_id: str,
                  text: str, setting: str) -> dict[str, Any]:
    """Submit through the live extractor and return what it produced.

    A clarification request is closed with /finalize (the contributor
    declines to add detail), which is a normal path in the application and
    still yields an unreviewed record.

    A rejection is a legitimate outcome, not a test failure: the model
    occasionally returns no observation at all (about 1 in 30 on these notes,
    measured 2026-09-25), and the pipeline must then persist nothing. That is
    asserted here, and the caller works with the records that were produced.
    """
    r = await client.post(f"/children/{child_id}/observations", headers=_auth(token),
                          json={"raw_text": text, "setting": setting, "source_type": "conversational"})
    assert r.status_code == 201, r.text
    body = r.json()
    obs_id = body["observation"]["id"]
    if body["routing_decision"] == "reject":
        d = await client.get(f"/observations/{obs_id}", headers=_auth(i_token))
        assert d.status_code == 200, d.text
        assert d.json()["status"] == "failed"
        assert d.json()["structured_record"] is None  # nothing unvalidated persisted
        assert d.json()["raw_text"] == text  # source evidence still preserved
        return {"observation_id": obs_id, "raw_text": text, "routing": "reject", "record": None}
    if body["routing_decision"] == "clarify":
        f = await client.post(f"/observations/{obs_id}/finalize", headers=_auth(token))
        assert f.status_code == 200, f.text
    d = await client.get(f"/observations/{obs_id}", headers=_auth(i_token))
    assert d.status_code == 200, d.text
    detail = d.json()
    record = detail["structured_record"]
    assert record is not None, f"no record produced for {text!r}"
    return {"observation_id": obs_id, "raw_text": detail["raw_text"],
            "routing": body["routing_decision"], "record": record}


async def _analytics(client: AsyncClient, token: str, child_id: str, period: str):
    return await client.post(f"/children/{child_id}/analytics", headers=_auth(token),
                             json={"review_period_id": period})


async def _report(client: AsyncClient, i_token: str, child_id: str, period: str) -> tuple[dict, dict]:
    r = await client.post(f"/children/{child_id}/reports/generate", headers=_auth(i_token),
                          json={"review_period_id": period})
    assert r.status_code == 201, r.text
    report = r.json()
    e = await client.get(f"/reports/{report['id']}/evidence", headers=_auth(i_token))
    assert e.status_code == 200, e.text
    return report, e.json()


async def _submit_mixed(client, parent_token, teacher_token, i_token, child_id) -> list[dict]:
    out = []
    for text in HOME:
        out.append(await _submit(client, parent_token, i_token, child_id, text, "home"))
    for text in SCHOOL:
        out.append(await _submit(client, teacher_token, i_token, child_id, text, "school"))
    return out


def _with_records(subs: list[dict], minimum: int) -> list[dict]:
    ok = [s for s in subs if s["record"] is not None]
    assert len(ok) >= minimum, (
        f"only {len(ok)} of {len(subs)} synthetic notes produced a record; scenario needs {minimum}")
    return ok


async def _first_record(client, token, i_token, child_id, n: int = 1) -> list[dict]:
    """Submit notes from one contributor in one setting until n records exist."""
    got = []
    for text in HOME + SCHOOL:
        s = await _submit(client, token, i_token, child_id, text, "home")
        if s["record"] is not None:
            got.append(s)
            if len(got) == n:
                return got
    raise AssertionError(f"fewer than {n} records from all synthetic notes")


@pytest.mark.usefixtures("override_db")
class TestGovernanceE2E:

    async def test_s0_frozen_configuration(self):
        """The run uses the intended extractor and the operational reporter."""
        assert settings.extraction_provider == "ollama"
        assert settings.ollama_model == EXPECTED_MODEL
        assert settings.reporting_mode == "deterministic"

    async def test_s1_unverified_records_are_blocked(
        self, client: AsyncClient, interventionist_token, parent_token, teacher_token,
    ):
        child = await _new_child(client, interventionist_token, "Governance S1")
        period = await _review_period(client, interventionist_token, child)
        subs = await _submit_mixed(client, parent_token, teacher_token, interventionist_token, child)

        recs = _with_records(subs, 1)
        for s in recs:
            assert s["record"]["model"] == EXPECTED_MODEL, s["record"]["model"]
            assert s["record"]["status"] in ("validated", "pending"), s["record"]["status"]

        r = await _analytics(client, interventionist_token, child, period)
        assert r.status_code == 200, r.text
        analytics = r.json()
        assert analytics["adequacy"]["level"] == "insufficient"
        assert all(k["abstained"] for k in analytics["kpis"]), analytics["kpis"]

        _, evidence = await _report(client, interventionist_token, child, period)
        assert evidence["record_ids"] == []
        assert evidence["observation_count"] == 0
        _log("S1", observations=len(subs), routing=[s["routing"] for s in subs],
             record_status=[s["record"]["status"] for s in recs],
             models=sorted({s["record"]["model"] for s in recs}),
             admitted_to_analytics=len(evidence["record_ids"]),
             adequacy=analytics["adequacy"]["level"])

    async def test_s2_verify_or_correct_makes_eligible(
        self, client: AsyncClient, interventionist_token, parent_token, teacher_token,
    ):
        child = await _new_child(client, interventionist_token, "Governance S2")
        period = await _review_period(client, interventionist_token, child)
        subs = await _submit_mixed(client, parent_token, teacher_token, interventionist_token, child)

        recs = _with_records(subs, 5)
        eligible: set[str] = set()
        excluded: set[str] = set()
        verified_n = corrected_n = pending_n = 0
        for i, s in enumerate(recs):
            rec = s["record"]
            if rec["status"] == "pending":
                # Routed for review because evidence was inadequate: accepting it
                # unchanged would undo the router, so the API must refuse.
                v = await client.post(f"/records/{rec['id']}/verify", headers=_auth(interventionist_token))
                assert v.status_code == 409, v.text
                pending_n += 1
            if i in (0, 3) or rec["status"] == "pending":
                data = dict(rec["record_data"])
                data["prompt_level"] = "verbal"
                c = await client.post(f"/records/{rec['id']}/correct", headers=_auth(interventionist_token),
                                      json={"record_data": data, "correction_reason": "Governance run correction."})
                assert c.status_code == 200, c.text
                assert c.json()["status"] == "corrected"
                eligible.add(c.json()["id"])
                excluded.add(rec["id"])
                corrected_n += 1
            elif i in (1, 2):
                v = await client.post(f"/records/{rec['id']}/verify", headers=_auth(interventionist_token))
                assert v.status_code == 200, v.text
                assert v.json()["status"] == "verified"
                assert v.json()["verified_by"] is not None and v.json()["verified_at"] is not None
                assert v.json()["version"] == rec["version"]  # verification creates no new version
                eligible.add(rec["id"])
                verified_n += 1
            else:
                excluded.add(rec["id"])  # left unreviewed

        assert verified_n >= 1 and corrected_n >= 2
        assert len(recs) - verified_n - corrected_n >= 1, "no record left unreviewed to test exclusion"
        _, evidence = await _report(client, interventionist_token, child, period)
        assert set(evidence["record_ids"]) == eligible
        assert not (set(evidence["record_ids"]) & excluded)
        _log("S2", observations=len(subs), routing=[s["routing"] for s in subs],
             verified=verified_n, corrected=corrected_n, pending_refused_409=pending_n,
             rejected_by_pipeline=len(subs) - len(recs),
             left_unreviewed=len(recs) - verified_n - corrected_n,
             admitted_to_analytics=len(evidence["record_ids"]))

    async def test_s3_correction_propagates_and_original_is_preserved(
        self, client: AsyncClient, interventionist_token, parent_token, teacher_token,
    ):
        child = await _new_child(client, interventionist_token, "Governance S3")
        period = await _review_period(client, interventionist_token, child)
        subs = await _submit_mixed(client, parent_token, teacher_token, interventionist_token, child)

        recs = _with_records(subs, 2)
        target = recs[0]
        original = target["record"]
        new_prompt = "full_physical" if original["record_data"].get("prompt_level") != "full_physical" else "gestural"
        data = dict(original["record_data"])
        data["prompt_level"] = new_prompt
        c = await client.post(f"/records/{original['id']}/correct", headers=_auth(interventionist_token),
                              json={"record_data": data, "correction_reason": "Interventionist correction."})
        assert c.status_code == 200, c.text
        corrected = c.json()
        assert corrected["version"] == original["version"] + 1
        assert corrected["record_data"]["prompt_level"] == new_prompt
        for s in recs[1:]:
            if s["record"]["status"] != "pending":
                v = await client.post(f"/records/{s['record']['id']}/verify", headers=_auth(interventionist_token))
                assert v.status_code == 200, v.text

        _, evidence = await _report(client, interventionist_token, child, period)
        assert corrected["id"] in evidence["record_ids"]
        assert original["id"] not in evidence["record_ids"]

        # Original record version untouched.
        o = await client.get(f"/records/{original['id']}", headers=_auth(interventionist_token))
        assert o.status_code == 200
        assert o.json()["record_data"] == original["record_data"]
        assert o.json()["version"] == original["version"]
        # Full version history retained.
        h = await client.get(f"/records/{corrected['id']}/history", headers=_auth(interventionist_token))
        assert [x["version"] for x in h.json()] == [original["version"], corrected["version"]]
        # Source observation text unchanged.
        ob = await client.get(f"/observations/{target['observation_id']}", headers=_auth(interventionist_token))
        assert ob.json()["raw_text"] == target["raw_text"]
        _log("S3", corrected_field="prompt_level",
             original_value=original["record_data"].get("prompt_level"), corrected_value=new_prompt,
             analytics_uses_version=corrected["version"], original_version_preserved=True,
             source_text_unchanged=True)

    async def test_s4_s5_insufficient_evidence_withheld_and_named_in_report(
        self, client: AsyncClient, interventionist_token, parent_token, teacher_token,
    ):
        child = await _new_child(client, interventionist_token, "Governance S4")
        period = await _review_period(client, interventionist_token, child)
        # Two professionally accepted records from one contributor in one
        # setting: below every adequacy threshold.
        for s in await _first_record(client, parent_token, interventionist_token, child, n=2):
            rec = s["record"]
            if rec["status"] == "pending":
                data = dict(rec["record_data"])
                r = await client.post(f"/records/{rec['id']}/correct", headers=_auth(interventionist_token),
                                      json={"record_data": data, "correction_reason": "Accepted after review."})
            else:
                r = await client.post(f"/records/{rec['id']}/verify", headers=_auth(interventionist_token))
            assert r.status_code == 200, r.text

        a = await _analytics(client, interventionist_token, child, period)
        assert a.status_code == 200, a.text
        analytics = a.json()
        assert analytics["adequacy"]["level"] in ("insufficient", "limited")
        withheld = [k for k in analytics["kpis"] if k["abstained"]]
        assert withheld, "adequacy failed but no analytics were withheld"
        for k in withheld:
            assert k["value"] is None, f"{k['name']} withheld but a value was still produced"
            assert k["abstention_reason"], f"{k['name']} withheld without a reason"

        report, evidence = await _report(client, interventionist_token, child, period)
        assert evidence["observation_count"] == 2
        # S5 -- the operational reporter, not the experimental LLM path.
        assert report["provider"] == "deterministic"
        assert report["is_experimental"] is False
        assert report["validation_passed"] is True, report.get("validation_errors")
        prose = " ".join(s["body"] for s in report["sections"]).lower()
        assert "withheld" in prose or "insufficient" in prose
        named = [k for k in withheld if k["name"].replace("_", " ") in prose or k["abstention_reason"].lower() in prose]
        assert len(named) == len(withheld), (
            f"report silent about withheld analyses: "
            f"{[k['name'] for k in withheld if k not in named]}")
        _log("S4", adequacy=analytics["adequacy"]["level"],
             withheld=[k["name"] for k in withheld],
             produced=[k["name"] for k in analytics["kpis"] if not k["abstained"]])
        _log("S5", report_provider=report["provider"], is_experimental=report["is_experimental"],
             validation_passed=report["validation_passed"], withheld_named=len(named),
             withheld_total=len(withheld))

    async def test_s6_contributor_cannot_verify_or_access_analytics(
        self, client: AsyncClient, interventionist_token, parent_token, teacher_token,
    ):
        child = await _new_child(client, interventionist_token, "Governance S6")
        period = await _review_period(client, interventionist_token, child)
        (s,) = await _first_record(client, parent_token, interventionist_token, child, n=1)
        rec = s["record"]

        for token in (parent_token, teacher_token):
            v = await client.post(f"/records/{rec['id']}/verify", headers=_auth(token))
            assert v.status_code == 403, v.text
            c = await client.post(f"/records/{rec['id']}/correct", headers=_auth(token),
                                  json={"record_data": rec["record_data"], "correction_reason": "x"})
            assert c.status_code == 403, c.text
            a = await _analytics(client, token, child, period)
            assert a.status_code == 403, a.text
            g = await client.post(f"/children/{child}/reports/generate", headers=_auth(token),
                                  json={"review_period_id": period})
            assert g.status_code == 403, g.text

        # The refused verification left the record unreviewed and ineligible.
        after = await client.get(f"/records/{rec['id']}", headers=_auth(interventionist_token))
        assert after.json()["status"] == rec["status"]
        assert after.json()["verified_by"] is None
        _log("S6", roles=["parent", "teacher"],
             refused=["verify", "correct", "analytics", "report"], status_code=403,
             record_unchanged=True)
