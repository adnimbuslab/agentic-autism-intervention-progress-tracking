"""Frozen governance end-to-end run: pin the build, run, write the run record.

Refuses to run on a working tree with uncommitted changes, so the commit in
the record is exactly the code that was tested. Runs the whole integration
package -- the governance scenarios against the live extractor plus the
existing mocked-LLM integration tests -- and writes
``docs/paper/governance_e2e_run.json``.

Requires: Postgres on localhost:5433 (``docker compose -f docker/docker-compose.yml up -d db``)
and Ollama serving qwen2.5:7b.

    uv run python scripts/run_governance_e2e.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "paper" / "governance_e2e_run.json"
MODEL = "qwen2.5:7b"
OLLAMA = "http://127.0.0.1:11434"

# Failures found while preparing the frozen run, fixed before it. Kept in the
# record so the run is not presented as having passed first time.
PRE_RUN_FIXES = [
    {
        "found": "2026-09-25",
        "tests": [
            "tests/phase6/integration/test_reporting_provenance_e2e.py::"
            "TestReportingProvenanceE2E::test_reporting_client_generates_valid_report",
            "tests/phase6/integration/test_reporting_provenance_e2e.py::"
            "TestReportingProvenanceE2E::test_reporting_client_catches_prohibited",
        ],
        "cause": "Stale tests. Both exercise the generative reporter but did not request it; "
                 "since commit 63a73a6 the default reporting_mode is 'deterministic', so the LLM "
                 "was never called. The unit tests were updated in 63a73a6; this integration "
                 "package had been excluded from that run.",
        "fix": "Pass mode='generative_experimental' explicitly. No application code changed.",
    },
]

SCENARIOS = {
    "S0": "Frozen configuration: extractor is ollama/qwen2.5:7b; reporting mode is deterministic",
    "S1": "Unverified-block: AI-extracted records not professionally verified never enter analytics",
    "S2": "Verify/correct: only VERIFIED or CORRECTED records become analytics-eligible; "
          "a PENDING record cannot be verified as written (409)",
    "S3": "Correction propagation: analytics/reporting use the corrected version; the original "
          "record version and source observation are preserved",
    "S4": "Insufficient evidence: affected analytics withheld (no value, reason given), not forced",
    "S5": "Reporting preservation: the operational deterministic report names every withheld analysis",
    "S6": "Authorization negative: contributors (parent, teacher) cannot verify, correct, "
          "compute analytics or generate reports (403)",
}
TEST_TO_SCENARIO = {
    "test_s0_frozen_configuration": ["S0"],
    "test_s1_unverified_records_are_blocked": ["S1"],
    "test_s2_verify_or_correct_makes_eligible": ["S2"],
    "test_s3_correction_propagates_and_original_is_preserved": ["S3"],
    "test_s4_s5_insufficient_evidence_withheld_and_named_in_report": ["S4", "S5"],
    "test_s6_contributor_cannot_verify_or_access_analytics": ["S6"],
}


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def ollama(path: str) -> dict:
    with urllib.request.urlopen(f"{OLLAMA}{path}", timeout=10) as r:
        return json.load(r)


def main() -> int:
    dirty = git("status", "--porcelain", "--untracked-files=no")
    if dirty and "--allow-dirty" not in sys.argv:
        print("Refusing to run: uncommitted changes to tracked files.\n" + dirty)
        return 2

    model = next((m for m in ollama("/api/tags")["models"] if m["name"] == MODEL), None)
    if model is None:
        print(f"{MODEL} is not available in Ollama.")
        return 2

    tmp = Path(tempfile.mkdtemp())
    junit, record = tmp / "junit.xml", tmp / "scenarios.jsonl"
    env = {**os.environ, "GOVERNANCE_E2E": "1", "EXTRACTION_PROVIDER": "ollama",
           "OLLAMA_MODEL": MODEL, "REPORTING_MODE": "deterministic",
           "GOVERNANCE_E2E_RECORD": str(record)}
    started = datetime.now(UTC)
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/phase6/integration", "-q", "-p", "no:cacheprovider",
         f"--junitxml={junit}"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    finished = datetime.now(UTC)

    cases = []
    for tc in ET.parse(junit).getroot().iter("testcase"):
        outcome = "passed"
        for child in tc:
            if child.tag in ("failure", "error"):
                outcome = "failed"
            elif child.tag == "skipped":
                outcome = "skipped"
        cases.append({"test": f"{tc.get('classname')}::{tc.get('name')}", "outcome": outcome,
                      "seconds": round(float(tc.get("time", 0)), 2)})
    evidence = {}
    if record.exists():
        for line in record.read_text().splitlines():
            row = json.loads(line)
            evidence[row.pop("scenario")] = row

    gov = {c["test"].rsplit("::", 1)[1]: c["outcome"] for c in cases
           if "test_governance_e2e" in c["test"]}
    scenarios = []
    for test, ids in TEST_TO_SCENARIO.items():
        for sid in ids:
            scenarios.append({"id": sid, "description": SCENARIOS[sid], "test": test,
                              "outcome": gov.get(test, "not run"), "observed": evidence.get(sid)})

    totals = {k: sum(c["outcome"] == k for c in cases) for k in ("passed", "failed", "skipped")}
    all_gov_passed = all(s["outcome"] == "passed" for s in scenarios)
    result = {
        "run": "Frozen governance-critical end-to-end run",
        "started_utc": started.isoformat(timespec="seconds"),
        "finished_utc": finished.isoformat(timespec="seconds"),
        "build": {
            "branch": git("rev-parse", "--abbrev-ref", "HEAD"),
            "commit": git("rev-parse", "HEAD"),
            "commit_short": git("rev-parse", "--short", "HEAD"),
            "commit_date": git("show", "-s", "--format=%cI", "HEAD"),
            "working_tree_clean": not dirty,
        },
        "extractor": {
            "provider": "ollama", "model": MODEL, "ollama_digest": model["digest"][:12],
            "ollama_version": ollama("/api/version").get("version"),
            "quantization": model.get("details", {}).get("quantization_level"),
            "parameter_size": model.get("details", {}).get("parameter_size"),
            "how_configured": "Environment for this run (EXTRACTION_PROVIDER=ollama, OLLAMA_MODEL="
                              f"{MODEL}). The application's code default is unchanged.",
            "mocked": False,
        },
        "reporting_mode": "deterministic",
        "test_data": "Controlled synthetic observations written for the suite (six contributor "
                     "notes: three home, three school). No corpus-derived text.",
        "scenarios": scenarios,
        "integration_package": {"totals": totals, "cases": cases},
        "pre_run_fixes": PRE_RUN_FIXES,
        "overall": (
            "All predefined governance-critical E2E scenarios passed"
            if all_gov_passed and totals["failed"] == 0 else
            "FAILED -- see scenarios and cases"
        ),
    }
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    print(proc.stdout[-1500:])
    print(f"\n{result['overall']}  ({totals})\nCommit {result['build']['commit_short']}  "
          f"model {MODEL} @ {result['extractor']['ollama_digest']}\nWrote {OUT}")
    return 0 if result["overall"].startswith("All") else 1


if __name__ == "__main__":
    sys.exit(main())
