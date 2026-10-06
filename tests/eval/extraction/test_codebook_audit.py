"""The R10-1 audit tooling: set reconstruction, blindness, counting, and the
post-audit path. Every returned sheet here is synthetic and lives in tmp_path;
the real worksheets and reference standard are never written."""

from __future__ import annotations

import csv
import json

import pytest

from tests.eval.extraction import codebook_audit as ca


@pytest.fixture
def pkg(tmp_path, monkeypatch):
    monkeypatch.setattr(ca, "OUT", tmp_path)
    ca.build()
    return tmp_path


def _fill(pkg, name, edit=None):
    with (pkg / "audit_worksheet_specialist_1.csv").open(encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for f in ca.FIELDS:
            r[f"{f}_status"] = "compliant"
        if edit:
            edit(r)
    ca.write_csv(pkg / name, ca.HEADER, rows)


def test_reconstructs_the_152_disjoint_from_the_178():
    rec = ca.reconstruct()
    sel = set(ca.load("reissue_round2_selection.json")["selected"])
    assert len(rec["unreissued"]) == 152 and not set(rec["unreissued"]) & sel
    assert len(set(rec["unreissued"]) | sel) == 330


def test_worksheet_is_model_blind(pkg):
    text = (pkg / "audit_worksheet_specialist_1.csv").read_text(encoding="utf-8-sig")
    assert text.splitlines()[0].split(",") == ca.HEADER
    for term in ("llama", "qwen", "mistral", "segment_id", "child_id", "session"):
        assert term not in text.lower().splitlines()[0]
    assert not any(m in text.lower() for m in ("llama", "qwen"))


def test_all_compliant_counts_zero_changes_and_apply_refuses(pkg):
    for sp in ca.SPECIALISTS:
        _fill(pkg, f"audit_worksheet_{sp}_completed.csv")
    ca.compare(None)
    res = json.loads((pkg / "audit_result.json").read_text())
    assert res["segments_audited"] == 152 and res["labels_audited"] == 456
    assert all(v == {"checked": 152, "changed": 0} for v in res["per_field"].values())
    with pytest.raises(SystemExit):
        ca.apply()


def test_disagreement_goes_to_consensus_and_is_not_resolved_by_code(pkg):
    def change(r):
        if r["audit_id"] == "A001":
            r["outcome_status"], r["outcome_corrected"] = "change_required", "unknown"
    _fill(pkg, "audit_worksheet_specialist_1_completed.csv", change)
    _fill(pkg, "audit_worksheet_specialist_2_completed.csv")
    ca.compare(None)
    assert (pkg / "consensus_sheet.csv").exists() and not (pkg / "audit_result.json").exists()


def test_invalid_sheet_is_rejected(pkg):
    def bad(r):
        r["modality_status"], r["modality_corrected"] = "change_required", "telepathy"
    _fill(pkg, "audit_worksheet_specialist_1_completed.csv", bad)
    _fill(pkg, "audit_worksheet_specialist_2_completed.csv")
    with pytest.raises(SystemExit):
        ca.compare(None)


def test_agreed_change_applies_to_a_copy_and_recomputes(pkg):
    key = json.loads((pkg / "audit_key.json").read_text())
    sid, v = next((s, v) for s, v in key.items() if v["retained"]["outcome"] == "correct")

    def change(r):
        if r["audit_id"] == v["audit_id"]:
            r["outcome_status"], r["outcome_corrected"] = "change_required", "unknown"
    for sp in ca.SPECIALISTS:
        _fill(pkg, f"audit_worksheet_{sp}_completed.csv", change)
    ca.compare(None)
    res = json.loads((pkg / "audit_result.json").read_text())
    assert res["changes"] == [{"segment_id": sid, "audit_id": v["audit_id"], "field": "outcome", "old": "correct",
                               "new": "unknown", "old_source": v["provenance"]["outcome"]["source"]}]
    before = (ca.RESULTS / "gold_labels.json").read_bytes()
    ca.apply()
    assert (ca.RESULTS / "gold_labels.json").read_bytes() == before
    post = json.loads((pkg / ca.POST_GOLD).read_text())
    assert post["gold"][sid]["field_values"]["outcome"] == "unknown"
    out = ca.recompute(out_path=pkg / "recompute.json")
    assert out["three_generators"]["pre"] != out["three_generators"]["post"]


def test_change_to_none_counts_as_a_change(pkg):
    key = json.loads((pkg / "audit_key.json").read_text())
    sid, v = next((s, v) for s, v in key.items() if v["retained"]["outcome"] is not None)

    def change(r):
        if r["audit_id"] == v["audit_id"]:
            r["outcome_status"], r["outcome_corrected"] = "change_required", "none"
    for sp in ca.SPECIALISTS:
        _fill(pkg, f"audit_worksheet_{sp}_completed.csv", change)
    ca.compare(None)
    res = json.loads((pkg / "audit_result.json").read_text())
    assert res["per_field"]["outcome"]["changed"] == 1
    assert res["changes"][0]["segment_id"] == sid and res["changes"][0]["new"] is None
