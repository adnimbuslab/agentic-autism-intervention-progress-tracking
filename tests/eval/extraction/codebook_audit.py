"""Final-codebook compliance audit of the 152 unreissued main-batch segments (R10-1).

Round 2 re-issued the 178 segments whose round-1 conflicts the codebook settles.
The other 152 kept their round-1 reference values. This module prepares a
human audit of those values against the three clarified boundaries
(modality, outcome, prompt_level) and handles the bookkeeping afterwards.

It never proposes, infers or adjudicates a label. Every value it writes into a
reference artefact comes from a completed human worksheet.

    build      reconstruct the 152, write the model-blind worksheets, the
               instruction sheet and the (not-for-auditors) key
    compare    read the two returned worksheets; count unchanged / changed per
               field; list specialist disagreements on proposed changes as a
               consensus sheet for the humans; with --consensus, finalise
    apply      only if the final audit changed a label: write a post-audit copy
               of the reference standard into the audit folder (never overwrites)
    recompute  old vs post-audit metrics from the preserved generator and MARS
               outputs -- no model is called

    uv run python -m tests.eval.extraction.codebook_audit build
    uv run python -m tests.eval.extraction.codebook_audit compare
    uv run python -m tests.eval.extraction.codebook_audit compare --consensus <completed consensus csv>
    uv run python -m tests.eval.extraction.codebook_audit apply
    uv run python -m tests.eval.extraction.codebook_audit recompute
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

RESULTS = Path(__file__).parent / "results"
ROOT = Path(__file__).resolve().parents[3]
OUT = RESULTS / "codebook_audit_r10"
CODEBOOK = ROOT / "docs" / "annotation_codebook.md"
FIELDS = ["modality", "outcome", "prompt_level"]
SCORED_FIELDS = ["domain", "modality", "prompt_level", "outcome"]
SPECIALISTS = ["specialist_1", "specialist_2"]
STATUSES = ("compliant", "change_required", "not_applicable")
NULL_WORD = "none"
ALLOWED = {
    "modality": ["verbal", "gestural", "sign", "aac", "written", "multimodal", "unknown", NULL_WORD],
    "outcome": ["correct", "incorrect", "approximation", "no_response", "partial", "unknown", NULL_WORD],
    "prompt_level": ["independent", "gestural", "verbal", "model", "partial_physical", "full_physical", "unknown", NULL_WORD],
}
SEED = 20261010
NO_CHANGE = object()  # distinct from None, which is a legitimate corrected value ("none")
SOURCES = ["gold_labels.json", "reissue_round2_selection.json", "gold_annotator_a_round1.json",
           "gold_annotator_b_round1.json", "adjudications.json", "annotation_batch.json"]


def load(name: str) -> Any:
    return json.loads((RESULTS / name).read_text())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def last_commit(path: Path) -> str:
    return subprocess.run(["git", "log", "-1", "--format=%h %ad", "--date=short", "--", str(path)],
                          cwd=ROOT, capture_output=True, text=True).stdout.strip()


def show(v: Any) -> str:
    return NULL_WORD if v is None else str(v)


def parse(v: str) -> str | None:
    v = (v or "").strip()
    return None if v == NULL_WORD else v


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------

def reconstruct() -> dict[str, Any]:
    gold = load("gold_labels.json")["gold"]
    reissue = load("reissue_round2_selection.json")
    a1, b1 = load("gold_annotator_a_round1.json"), load("gold_annotator_b_round1.json")
    a, b = load("gold_annotator_a.json"), load("gold_annotator_b.json")
    decisions = load("adjudications.json")["decisions"]
    selected = set(reissue["selected"])
    assert len(gold) == 330 and len(selected) == reissue["n_selected"] == 178 and selected <= set(gold)
    unreissued = sorted(set(gold) - selected)
    assert len(unreissued) == 152 and not (set(unreissued) & selected)
    # Their annotator records were never replaced by a round-2 import.
    assert all(a1[s] == a[s] and b1[s] == b[s] for s in unreissued)

    records = {}
    for s in unreissued:
        prov = {}
        for f in FIELDS:
            va, vb, vg = a1[s]["field_values"][f], b1[s]["field_values"][f], gold[s]["field_values"][f]
            if va == vb:
                assert vg == va, (s, f)
                prov[f] = {"source": "round1_agreed", "annotator_a": va, "annotator_b": vb}
            else:
                assert f in decisions.get(s, {}), (s, f)
                prov[f] = {"source": "adjudicated_round1_conflict", "annotator_a": va, "annotator_b": vb}
        records[s] = {"child_id": gold[s]["child_id"], "retained": {f: gold[s]["field_values"][f] for f in FIELDS},
                      "provenance": prov}
    n_prov = {src: sum(r["provenance"][f]["source"] == src for r in records.values() for f in FIELDS)
              for src in ("round1_agreed", "adjudicated_round1_conflict")}
    return {
        "unreissued": unreissued, "records": records,
        "n_gold": len(gold), "n_reissued": len(selected), "n_unreissued": len(unreissued),
        "label_provenance_counts": n_prov,
        "segments_with_round1_categorical_conflict": sum(
            any(a1[s]["field_values"][f] != b1[s]["field_values"][f] for f in SCORED_FIELDS) for s in unreissued),
        "round1_conflicts_by_field": {f: sum(a1[s]["field_values"][f] != b1[s]["field_values"][f] for s in unreissued)
                                      for f in SCORED_FIELDS},
        "segments_with_adjudicated_audit_field": sum(
            any(r["provenance"][f]["source"] != "round1_agreed" for f in FIELDS) for r in records.values()),
    }


INSTRUCTIONS = """FINAL-CODEBOOK COMPLIANCE AUDIT -- INSTRUCTIONS FOR SPECIALISTS

What you are checking
  Each row is one transcript segment and the reference value it currently holds
  for three fields: modality, outcome, prompt_level. Check each value ONLY
  against the three clarified boundaries below (the full codebook text follows).
  Do not re-annotate the segment from scratch, and do not judge domain or behavior.

What you must not see or use
  This sheet contains no model output, model name, score, confidence or
  selection result. Do not look any of these up while auditing. Work
  independently of the other specialist until both sheets are returned.

How to fill each field (three columns per field)
  <field>_retained    the value on record ("none" = the transcript supports no value). Do not edit.
  <field>_status      one of:
                        compliant         the retained value is consistent with the boundary
                        change_required   the retained value conflicts with the boundary
                        not_applicable    the boundary does not bear on this segment/field
  <field>_corrected   ONLY when status is change_required: the value the final
                      codebook requires, from the allowed list below. Leave blank otherwise.
  notes               optional, free text.

Allowed values
  modality:     {modality}
  outcome:      {outcome}
  prompt_level: {prompt_level}
  ("none" = the transcript supports no value / no communicative act / no target)

The three clarified boundaries
  Modality      A communicative gesture must be directed toward a partner; ordinary
                object manipulation alone is not gestural.
  Outcome       correct / incorrect (and approximation, partial, no_response) require an
                identifiable behavioural target; with no target, outcome = none; a target
                whose resolution is not visible is unknown, never incorrect.
  Prompt level  Distinguish an actual prompt/support from an antecedent or opportunity;
                a child-initiated behaviour is independent; where several prompts occur,
                record the most supportive level actually used
                (independent < gestural < verbal < model < partial_physical < full_physical).

If the two specialists disagree
  Only disagreements about a proposed change go to consensus. They are returned to
  you on a separate consensus sheet and resolved by the same human consensus
  procedure used previously. No software or model resolves them.

----------------------------------------------------------------------------
FULL CODEBOOK TEXT (docs/annotation_codebook.md, commit {codebook_commit})
----------------------------------------------------------------------------

{codebook}
"""

HEADER = ["audit_id", "transcript"] + [c for f in FIELDS for c in (f"{f}_retained", f"{f}_status", f"{f}_corrected")] + ["notes"]


def write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        w.writerows(rows)


def build() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rec = reconstruct()
    text = {c["segment_id"]: c["chat_text"] for c in load("annotation_batch.json")["candidates"]}
    order = list(rec["unreissued"])
    random.Random(SEED).shuffle(order)
    audit_id = {s: f"A{i + 1:03d}" for i, s in enumerate(order)}

    rows = []
    for s in order:
        r = {"audit_id": audit_id[s], "transcript": text[s], "notes": ""}
        for f in FIELDS:
            r |= {f"{f}_retained": show(rec["records"][s]["retained"][f]), f"{f}_status": "", f"{f}_corrected": ""}
        rows.append(r)
    for sp in SPECIALISTS:
        write_csv(OUT / f"audit_worksheet_{sp}.csv", HEADER, rows)
    # Model-blindness check on what goes to the auditors.
    blob = (OUT / f"audit_worksheet_{SPECIALISTS[0]}.csv").read_text(encoding="utf-8-sig").lower()
    assert not any(m in blob for m in ("llama", "qwen", "mistral")), "model name in worksheet"
    assert set(next(csv.reader([blob.splitlines()[0]]))) == {h.lower() for h in HEADER}, "unexpected worksheet column"

    (OUT / "AUDIT_INSTRUCTIONS.txt").write_text(INSTRUCTIONS.format(
        codebook=CODEBOOK.read_text(), codebook_commit=last_commit(CODEBOOK),
        **{f: " | ".join(ALLOWED[f]) for f in FIELDS}), encoding="utf-8")

    key = {s: {"audit_id": audit_id[s], **rec["records"][s]} for s in rec["unreissued"]}
    manifest = {
        "generated_at": datetime.now(UTC).isoformat(), "seed_row_order": SEED,
        "rule": "unreissued = segments of gold_labels.json not in reissue_round2_selection.json['selected']",
        "counts": {k: rec[k] for k in ("n_gold", "n_reissued", "n_unreissued", "label_provenance_counts",
                                       "segments_with_round1_categorical_conflict", "round1_conflicts_by_field",
                                       "segments_with_adjudicated_audit_field")},
        "fields_audited": FIELDS, "labels_to_audit": len(FIELDS) * rec["n_unreissued"],
        "sources": {n: {"sha256": sha256(RESULTS / n), "last_commit": last_commit(RESULTS / n)} for n in SOURCES}
                   | {"docs/annotation_codebook.md": {"sha256": sha256(CODEBOOK), "last_commit": last_commit(CODEBOOK)}},
        "unreissued_segment_ids": rec["unreissued"],
        "worksheets": [f"audit_worksheet_{sp}.csv" for sp in SPECIALISTS],
        "worksheet_columns": HEADER,
        "not_for_auditors": ["audit_key.json", "audit_set_152.json"],
    }
    (OUT / "audit_set_152.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (OUT / "audit_key.json").write_text(json.dumps(key, indent=2) + "\n")
    print(json.dumps(manifest["counts"], indent=1))
    print(f"Wrote {OUT}")


# --------------------------------------------------------------------------
# compare
# --------------------------------------------------------------------------

def read_sheet(path: Path, key: dict[str, Any]) -> tuple[dict[str, dict[str, dict[str, Any]]], list[str]]:
    by_audit = {v["audit_id"]: s for s, v in key.items()}
    out, problems = {}, []
    with path.open(encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            aid = row["audit_id"].strip()
            if aid not in by_audit:
                problems.append(f"{path.name}: unknown audit_id {aid}")
                continue
            s = by_audit[aid]
            out[s] = {}
            for f in FIELDS:
                st, corr = row[f"{f}_status"].strip(), row[f"{f}_corrected"].strip()
                retained = key[s]["retained"][f]
                if parse(row[f"{f}_retained"]) != retained:
                    problems.append(f"{path.name} {aid} {f}: retained column was edited")
                if st not in STATUSES:
                    problems.append(f"{path.name} {aid} {f}: status '{st}' not one of {STATUSES}")
                if st == "change_required":
                    if corr not in ALLOWED[f]:
                        problems.append(f"{path.name} {aid} {f}: corrected value '{corr}' not allowed")
                    elif parse(corr) == retained:
                        problems.append(f"{path.name} {aid} {f}: change_required but corrected equals retained")
                elif corr:
                    problems.append(f"{path.name} {aid} {f}: corrected value given without change_required")
                out[s][f] = {"status": st, "corrected": parse(corr) if st == "change_required" else None}
    missing = set(key) - set(out)
    if missing:
        problems.append(f"{path.name}: {len(missing)} segments missing")
    return out, problems


def compare(consensus: Path | None) -> None:
    key = json.loads((OUT / "audit_key.json").read_text())
    sheets, problems = {}, []
    for sp in SPECIALISTS:
        p = OUT / f"audit_worksheet_{sp}_completed.csv"
        if not p.exists():
            raise SystemExit(f"{p.name} not found: return the completed worksheet under this name.")
        sheets[sp], pr = read_sheet(p, key)
        problems += pr
    if problems:
        raise SystemExit("Worksheet problems -- return to the specialists, nothing was counted:\n  " + "\n  ".join(problems))

    agreed, disputed = {}, []
    for s in sorted(key):
        for f in FIELDS:
            e1, e2 = sheets[SPECIALISTS[0]][s][f], sheets[SPECIALISTS[1]][s][f]
            ch1, ch2 = e1["status"] == "change_required", e2["status"] == "change_required"
            if not ch1 and not ch2:
                agreed[(s, f)] = NO_CHANGE
            elif ch1 and ch2 and e1["corrected"] == e2["corrected"]:
                agreed[(s, f)] = e1["corrected"]
            else:
                disputed.append((s, f, e1, e2))

    final = dict(agreed)
    if disputed and consensus is None:
        rows = [{"audit_id": key[s]["audit_id"], "field": f, "retained": show(key[s]["retained"][f]),
                 "specialist_1": f"{e1['status']}" + (f" -> {show(e1['corrected'])}" if e1["corrected"] is not None or e1["status"] == "change_required" else ""),
                 "specialist_2": f"{e2['status']}" + (f" -> {show(e2['corrected'])}" if e2["corrected"] is not None or e2["status"] == "change_required" else ""),
                 "consensus_status": "", "consensus_corrected": ""} for s, f, e1, e2 in disputed]
        write_csv(OUT / "consensus_sheet.csv", list(rows[0]), rows)
        print(f"{len(disputed)} field(s) need human consensus: wrote consensus_sheet.csv. Nothing finalised.")
        return
    if disputed:
        by_audit = {v["audit_id"]: s for s, v in key.items()}
        done = {}
        with consensus.open(encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                s, f = by_audit[row["audit_id"].strip()], row["field"].strip()
                st, corr = row["consensus_status"].strip(), row["consensus_corrected"].strip()
                if st not in STATUSES or (st == "change_required") != bool(corr) or (corr and corr not in ALLOWED[f]):
                    raise SystemExit(f"consensus row {row['audit_id']} {f} is incomplete or invalid")
                done[(s, f)] = parse(corr) if st == "change_required" else NO_CHANGE
        missing = {(s, f) for s, f, *_ in disputed} - set(done)
        if missing:
            raise SystemExit(f"{len(missing)} disputed field(s) have no consensus row")
        final |= done

    changes = [{"segment_id": s, "audit_id": key[s]["audit_id"], "field": f, "old": key[s]["retained"][f], "new": v,
                "old_source": key[s]["provenance"][f]["source"]}
               for (s, f), v in sorted(final.items()) if v is not NO_CHANGE]
    result = {
        "finalised_at": datetime.now(UTC).isoformat(),
        "segments_audited": len(key), "labels_audited": len(final),
        "per_field": {f: {"checked": sum(ff == f for _s, ff in final), "changed": sum(c["field"] == f for c in changes)}
                      for f in FIELDS},
        "segments_changed": sorted({c["segment_id"] for c in changes}),
        "changes": changes,
        "n_disputed_resolved_by_consensus": len(disputed),
        "status_counts": {sp: {f: {st: sum(sheets[sp][s][f]["status"] == st for s in key) for st in STATUSES}
                               for f in FIELDS} for sp in SPECIALISTS},
        "auditors_blind_to_model_output": "worksheets contain transcript and retained reference values only "
                                          "(see audit_set_152.json worksheet_columns); blinding of the auditors' "
                                          "conduct must be confirmed by the study team",
    }
    (OUT / "audit_result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("segments_audited", "labels_audited", "per_field", "segments_changed")}, indent=1))


# --------------------------------------------------------------------------
# apply / recompute
# --------------------------------------------------------------------------

POST_GOLD = "gold_labels_postaudit_r10.json"


def apply() -> None:
    result = json.loads((OUT / "audit_result.json").read_text())
    if not result["changes"]:
        raise SystemExit("The audit changed no label: the reference standard stays as it is and nothing is recomputed.")
    pre = load("gold_labels.json")
    post = json.loads(json.dumps(pre))
    for c in result["changes"]:
        assert post["gold"][c["segment_id"]]["field_values"][c["field"]] == c["old"]
        post["gold"][c["segment_id"]]["field_values"][c["field"]] = c["new"]
    post["codebook_audit_r10"] = {"pre_audit_file": "gold_labels.json", "pre_audit_sha256": sha256(RESULTS / "gold_labels.json"),
                                  "changes": result["changes"], "applied_at": datetime.now(UTC).isoformat(),
                                  "note": "Values changed only where the human final-codebook audit required it."}
    out = OUT / POST_GOLD
    if out.exists():
        raise SystemExit(f"{out.name} exists; refusing to overwrite a post-audit reference.")
    out.write_text(json.dumps(post, indent=2) + "\n")
    print(f"Wrote {out} ({len(result['changes'])} change(s)); results/gold_labels.json untouched.")


def core_metrics(scored_gold: dict, models: list[str], outcomes: dict) -> dict[str, Any]:
    from tests.eval.extraction import mars_evaluation as me
    from tests.eval.extraction.round3_analysis import METRICS
    per_model = {m: {k: round(fn([scored_gold[s][m] for s in scored_gold], SCORED_FIELDS), 4) for k, fn in METRICS.items()}
                 for m in models}
    return {"per_model": per_model,
            "oracle_ceiling": round(me.oracle_ceiling(scored_gold, models, SCORED_FIELDS), 4),
            "mars": {k: (round(v, 4) if isinstance(v, float) else v)
                     for k, v in me.mars_accuracy(scored_gold, outcomes, SCORED_FIELDS).items() if k != "abstention_reasons"}}


def mars_fields(scored: dict) -> dict[str, Any]:
    """Round-4 MARS comparison (mars_clustered), parametrised by the scored reference.

    Same segments (MARS judged, >1 candidate), same comparators, same seeds, so the
    pre-audit side reproduces round4_analysis.json exactly.
    """
    import random
    import statistics
    from collections import defaultdict

    from src.backend.ml.extraction.mars.candidates import build_candidates
    from tests.eval.extraction import round4_analysis as r4
    from tests.eval.extraction.mars_branch_replay import to_result
    from tests.eval.extraction.round3_analysis import ACCEPTABLE, _percentile

    outcomes = load("mars_outcomes.json")
    batch = {c["segment_id"]: c for c in load("annotation_batch.json")["candidates"]}
    child = {s: v["child_id"] for s, v in load("gold_labels.json")["gold"].items()}
    gens = r4.ORIGINAL_GENERATORS
    merged = {m: sum(sum(scored[s][m][f] in ACCEPTABLE for s in scored) for f in SCORED_FIELDS) for m in gens}
    strength = sorted(gens, key=lambda m: -merged[m])
    judged = sorted(s for s, o in outcomes.items() if o.get("status") == "success" and (o.get("candidate_count") or 0) > 1)
    ok = lambda s, m, f: scored[s][m][f] in ACCEPTABLE  # noqa: E731
    rows: dict[str, dict] = {}
    for s in judged:
        entry = batch[s]
        cands = build_candidates([to_result(entry, m, entry["candidates"][m]) for m in gens])
        cand_gens = [list(c.generator_ids) for c in cands]
        reviewable = [g for gs in cand_gens for g in gs]
        pick = outcomes[s]["selected_generator_ids"][0]
        best_rev = next(m for m in strength if m in reviewable)
        rows[s] = {f: {"mars": float(ok(s, pick, f)),
                       "random_expected_reviewable": statistics.mean(float(ok(s, gs[0], f)) for gs in cand_gens),
                       "random_expected_all_generators": statistics.mean(float(ok(s, m, f)) for m in gens),
                       "best_fixed": float(ok(s, strength[0], f)),
                       "best_reviewable_fallback": float(ok(s, best_rev, f))} for f in SCORED_FIELDS}
    by_child = defaultdict(list)
    for s in judged:
        by_child[child[s]].append(s)
    kids = sorted(by_child)

    def boot(comp: str, f: str, tag: str) -> dict[str, Any]:
        rng = random.Random(f"{r4.SEED}:{tag}:{f}")
        value = statistics.mean(rows[s][f]["mars"] - rows[s][f][comp] for s in judged)
        reps = []
        for _ in range(r4.N_BOOT):
            draw = [s for _ in kids for s in by_child[kids[rng.randrange(len(kids))]]]
            reps.append(sum(rows[s][f]["mars"] - rows[s][f][comp] for s in draw) / len(draw))
        lo, hi = _percentile(reps, 0.025), _percentile(reps, 0.975)
        return {"value": round(value, 4), "lower": round(lo, 4), "upper": round(hi, 4), "excludes_zero": lo > 0 or hi < 0}

    comps = {"vs_random_reviewable": "random_expected_reviewable", "vs_random_all_generators": "random_expected_all_generators",
             "vs_best_fixed": "best_fixed", "vs_best_reviewable_fallback": "best_reviewable_fallback"}
    keys = ("mars", "random_expected_reviewable", "random_expected_all_generators", "best_fixed", "best_reviewable_fallback")
    per_field = {}
    for f in SCORED_FIELDS:
        per_field[f] = {k: round(statistics.mean(rows[s][f][k] for s in judged), 4) for k in keys}
        per_field[f] |= {name: boot(comp, f, name) for name, comp in comps.items()}
    return {"n_judged": len(judged), "strength_order": strength, "per_field": per_field,
            "mean": {k: round(statistics.mean(per_field[f][k] for f in SCORED_FIELDS), 4) for k in keys}}


def recompute(gold_path: Path | None = None, out_path: Path | None = None) -> dict[str, Any]:
    from tests.eval.extraction.score_against_gold import DEFAULT_OVERLAP_THRESHOLD, score
    gold_path = gold_path or OUT / POST_GOLD
    if not gold_path.exists():
        raise SystemExit(f"{gold_path.name} not found: run `apply` first (only if the audit changed a label).")
    pre, post = load("gold_labels.json"), json.loads(gold_path.read_text())
    outcomes = load("mars_outcomes.json")
    out: dict[str, Any] = {"post_audit_gold": gold_path.name}
    for name, batch in (("three_generators", load("annotation_batch.json")), ("four_generators", load("annotation_batch_augmented.json"))):
        sc_pre = score(pre, batch, behavior_match="overlap", threshold=DEFAULT_OVERLAP_THRESHOLD)
        sc_post = score(post, batch, behavior_match="overlap", threshold=DEFAULT_OVERLAP_THRESHOLD)
        out[name] = {"pre": core_metrics(sc_pre["gold"], batch["models"], outcomes),
                     "post": core_metrics(sc_post["gold"], batch["models"], outcomes)}
    # The pre-audit side must reproduce the recorded results before the post-audit side is trusted.
    rec = load("mars_evaluation.json")
    assert abs(out["three_generators"]["pre"]["oracle_ceiling"] - rec["oracle_ceiling"]) < 1e-4
    rec4 = load("round4_analysis.json")["same_universe"]["groups"]["main_batch_330"]["per_model"]
    for m, v in out["four_generators"]["pre"]["per_model"].items():
        assert abs(v["merged_agreement"] - rec4[m]["merged_agreement"]["value"]) < 1e-4, m
    three = load("annotation_batch.json")
    sc3 = {k: score(g, three, behavior_match="overlap", threshold=DEFAULT_OVERLAP_THRESHOLD)["gold"] for k, g in (("pre", pre), ("post", post))}
    out["mars_per_field"] = {k: mars_fields(v) for k, v in sc3.items()}
    rec_mc = load("round4_analysis.json")["mars_clustered"]
    for f in SCORED_FIELDS:
        for k, v in out["mars_per_field"]["pre"]["per_field"][f].items():
            r = rec_mc["per_field"][f][k]
            assert (v == r) if not isinstance(v, dict) else all(v[x] == r[x] for x in ("value", "lower", "upper")), (f, k)
    (out_path or OUT / "recompute_pre_vs_post.json").write_text(json.dumps(out, indent=2) + "\n")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    c = sub.add_parser("compare")
    c.add_argument("--consensus", type=Path, default=None)
    sub.add_parser("apply")
    sub.add_parser("recompute")
    args = ap.parse_args()
    if args.cmd == "build":
        build()
    elif args.cmd == "compare":
        compare(args.consensus)
    elif args.cmd == "apply":
        apply()
    else:
        print(json.dumps(recompute(), indent=1))


if __name__ == "__main__":
    main()
