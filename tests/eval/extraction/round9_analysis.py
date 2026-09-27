"""Facts answering the round-9 technical information request. No model is called.

    R9-1  prompt chronology     git dates of the extraction prompt, codebook and
                                generator artefacts; codebook rules present in the prompt
    R9-2  reporter contract     withheld KPIs per packet; validator acknowledgement rule
    R9-3  reporter context      token count of the complete model-visible input per
                                packet (Qwen2.5 BPE tokenizer, checked against the
                                local GGUF vocabulary; needs `tokenizers` and `gguf`)
    R9-4  review context        goals, review period and every adequacy check per packet
    R9-5  field-level unsupported assertion, 330 / 132 / 121
    R9-7  universe selection    per-child, per-type available vs selected counts;
                                toy example run through the real selection function
    R9-8  oracle ceiling        numerator/denominator under each candidate definition

    uv run --with tokenizers --with gguf python -m tests.eval.extraction.round9_analysis
"""

from __future__ import annotations

import json
import math
import os
import subprocess
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from data.pipeline.select_segments import _select_for_child
from src.backend.ml.extraction.mars.candidates import build_candidates
from src.backend.ml.reporting_client import REPORTING_SYSTEM_PROMPT, ReportingClient
from tests.eval.extraction import round4_analysis as r4
from tests.eval.extraction.mars_branch_replay import to_result
from tests.eval.reporting.groundedness import build_packet, load_records

ROOT = Path(__file__).resolve().parents[3]
RESULTS = Path(__file__).parent / "results"
OUT = RESULTS / "round9_analysis.json"
FIELDS = r4.FIELDS
GEN3 = r4.ORIGINAL_GENERATORS
MODELS = GEN3 + ["qwen3:14b"]
ACCEPTABLE = {"correct", "correctly_null"}
REPORT_RUN_COMMIT = "9ecc330"


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()


def first_last(path: str) -> dict[str, str]:
    log = git("log", "--format=%h|%ad", "--date=iso-strict", "--follow", "--", path).splitlines()
    return {"first_commit": log[-1].split("|")[0], "first_date": log[-1].split("|")[1],
            "last_commit": log[0].split("|")[0], "last_date": log[0].split("|")[1]} if log else {}


# --------------------------------------------------------------------------
# R9-1
# --------------------------------------------------------------------------

def chronology() -> dict[str, Any]:
    from src.backend.ml.extraction.prompts import PROMPT_VERSION, build_system_prompt, build_user_prompt_chat_segment

    batch = r4.load("annotation_batch.json")
    aug = r4.load("annotation_batch_augmented.json")
    prompt_text = build_system_prompt() + "\n" + build_user_prompt_chat_segment("<SEGMENT>")
    # Distinctive terms of each codebook clarification (docs/annotation_codebook.md sections 1-3).
    rules = {"communicative_gesture_vs_object_manipulation": ["communicative", "object", "manipulat"],
             "identifiable_target_for_correct_incorrect": ["target"],
             "prompt_vs_antecedent_opportunity": ["antecedent", "opportunity"]}
    return {
        "extraction_prompt_file": "src/backend/ml/extraction/prompts.py",
        "prompt_version_constant": PROMPT_VERSION,
        "prompt_file_history": first_last("src/backend/ml/extraction/prompts.py"),
        "observation_enum_history": first_last("src/backend/schemas/observation_schema.py"),
        "ollama_provider_history": first_last("src/backend/ml/extraction/ollama_llm.py"),
        "codebook_history": first_last("docs/annotation_codebook.md"),
        "three_generator_batch": {"generated_at": batch["generated_at"], **first_last("tests/eval/extraction/results/annotation_batch.json"),
                                  "models": batch["models"], "prompt_version_recorded": any(
                                      "prompt_version" in (c or {}) for e in batch["candidates"] for c in e["candidates"].values())},
        "qwen3_14b": {"augmented_at": aug["augmented_at"], **first_last("tests/eval/extraction/results/annotation_batch_augmented.json"),
                      "script": "tests/eval/extraction/add_generator.py", "provider": "OllamaExtractionProvider"},
        "codebook_rule_terms_in_prompt": {k: {t: t in prompt_text.lower() for t in terms} for k, terms in rules.items()},
        "prototype_default_model": _default_model(),
        "prompt_changed_after_batch": git("log", "--format=%h", f"--since={batch['generated_at']}", "--",
                                          "src/backend/ml/extraction/prompts.py") != "",
    }


def _default_model() -> str:
    from src.backend.config import Settings
    return Settings.model_fields["ollama_model"].default


# --------------------------------------------------------------------------
# R9-2 / R9-3 / R9-4 -- the 11 reporter packets, rebuilt deterministically
# --------------------------------------------------------------------------

def render_chat(user: str) -> str:
    """The qwen2.5 Ollama chat template for one system and one user message, no tools."""
    return (f"<|im_start|>system\n{REPORTING_SYSTEM_PROMPT}<|im_end|>\n"
            f"<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n")


def tokenizer():
    try:
        import gguf
        from tokenizers import Tokenizer
    except ImportError:
        return None, {"available": False}
    manifest = json.loads((Path.home() / ".ollama/models/manifests/registry.ollama.ai/library/qwen2.5/7b").read_text())
    digest = next(l["digest"] for l in manifest["layers"] if l["mediaType"].endswith(".model"))
    reader = gguf.GGUFReader(str(Path.home() / ".ollama/models/blobs" / digest.replace(":", "-")))
    f = reader.fields["tokenizer.ggml.tokens"]
    ggml = [bytes(f.parts[i]).decode("utf-8", "replace") for i in f.data]
    tok = Tokenizer.from_pretrained("Qwen/Qwen2.5-7B-Instruct")
    vocab = tok.get_vocab()
    real = [(i, s) for i, s in enumerate(ggml) if i < len(vocab)]
    assert all(vocab.get(s) == i for i, s in real), "tokenizer does not match the local model vocabulary"
    return tok, {"available": True, "tokenizer": "Qwen/Qwen2.5-7B-Instruct (Hugging Face tokenizers)",
                 "check": f"ids 0..{len(vocab) - 1} identical to local GGUF {digest[:19]}; "
                          f"GGUF has {len(ggml) - len(vocab)} further padding ids"}


def packets() -> dict[str, Any]:
    recs = load_records()
    tok, tok_info = tokenizer()
    rows = {}
    for c in sorted(recs):
        packet = build_packet(c, recs[c])
        user = json.dumps(packet.model_dump(mode="json"), indent=2)
        full = render_chat(user)
        withheld = {k.name: k.abstention_reason for k in (packet.analytics.kpis if packet.analytics else []) if k.abstained}
        rows[c] = {
            "n_records": len(recs[c]),
            "goals": packet.goals,
            "review_period": [packet.review_period_start, packet.review_period_end],
            "n_sessions": len({r["session_id"] for r in recs[c]}),
            "adequacy_level": packet.adequacy.level.value,
            "adequacy_checks": {ch.check.value: {"passed": ch.passed, "detail": ch.detail} for ch in packet.adequacy.checks},
            "partial_abstentions": packet.adequacy.partial_abstentions,
            "withheld_kpis": withheld,
            "kpis_computed": [k.name for k in packet.analytics.kpis if not k.abstained] if packet.analytics else [],
            "chars_user": len(user), "chars_system": len(REPORTING_SYSTEM_PROMPT),
            "tokens_full_input": len(tok.encode(full, add_special_tokens=False).ids) if tok else None,
            "withheld_names_present_in_input": all(n in user for n in withheld),
        }
    toks = sorted(v["tokens_full_input"] for v in rows.values()) if tok else []
    return {
        "tokenizer": tok_info, "packets": rows,
        "token_summary": ({"min": toks[0], "median": toks[len(toks) // 2], "max": toks[-1],
                           "max_child": max(rows, key=lambda c: rows[c]["tokens_full_input"])} if toks else None),
        "reporter_code": {"file": "src/backend/ml/reporting_client.py", "commit": REPORT_RUN_COMMIT,
                          "request_options": {"num_ctx": 8192}, "format": ReportingClient.REPORT_SCHEMA,
                          "stream": False},
        "ollama_model_info": _ollama_show("qwen2.5:7b"),
    }


def _ollama_show(model: str) -> dict[str, Any]:
    try:
        import httpx
        d = httpx.post("http://127.0.0.1:11434/api/show", json={"model": model}, timeout=10).json()
        tags = httpx.get("http://127.0.0.1:11434/api/tags", timeout=10).json()["models"]
        ver = httpx.get("http://127.0.0.1:11434/api/version", timeout=10).json().get("version")
    except Exception as exc:  # noqa: BLE001
        return {"error": repr(exc)}
    t = next(m for m in tags if m["name"] == model)
    return {"digest": t["digest"], "modified_at": t["modified_at"], "quantization": t["details"].get("quantization_level"),
            "modelfile_parameters": d.get("parameters"), "context_length_trained": d.get("model_info", {}).get("qwen2.context_length"),
            "ollama_version_now": ver,
            "template_has_format_placeholder": ".Format" in (d.get("template") or "")}


# --------------------------------------------------------------------------
# R9-5
# --------------------------------------------------------------------------

def field_unsupported(pool, fkey) -> dict[str, Any]:
    sb = r4.load("scored_against_gold_augmented.json")["gold"]
    sh = r4.load("scored_holdout.json")["gold"]
    vals = {c["segment_id"]: c["candidates"] for c in r4.load("annotation_batch_augmented.json")["candidates"]}
    vals.update({c["segment_id"]: c["candidates"] for c in r4.load("holdout_batch.json")["candidates"]})
    value = lambda s, m, f: ((vals[s].get(m) or {}).get("extracted_fields") or {}).get(f)  # noqa: E731
    frozen = [s["segment_id"] for s in r4.load("holdout_set.json")["segments"]]
    sets = {"main_batch_330": (sb, list(sb)), "frozen_132": (sh, frozen),
            "overlap_excluded_121": (sh, [s for s in frozen if fkey[s] not in pool])}
    out = {}
    for name, (sc, segs) in sets.items():
        per_model = {}
        for m in MODELS:
            per_field = {}
            for f in FIELDS:
                h = sum(sc[s][m][f] == "hallucinated" for s in segs)
                n = h + sum(sc[s][m][f] == "correctly_null" for s in segs)
                u = sum(sc[s][m][f] == "hallucinated" and value(s, m, f) == "unknown" for s in segs)
                per_field[f] = {"hallucinated": h, "gold_null": n, "rate": round(h / n, 4) if n else None,
                                "sparse": n < 20, "hallucinated_value_unknown": u}
            H = sum(v["hallucinated"] for v in per_field.values())
            N = sum(v["gold_null"] for v in per_field.values())
            per_model[m] = {"per_field": per_field, "pooled": {"hallucinated": H, "gold_null": N, "rate": round(H / N, 4)},
                            "unweighted_mean_of_fields": round(sum(v["rate"] for v in per_field.values() if v["rate"] is not None)
                                                               / sum(v["rate"] is not None for v in per_field.values()), 4)}
        nulls = {f: per_model["qwen3:14b"]["per_field"][f]["gold_null"] for f in FIELDS}
        assert all(per_model[m]["per_field"][f]["gold_null"] == nulls[f] for m in MODELS for f in FIELDS)
        out[name] = {"n": len(segs), "gold_null_by_field": nulls, "per_model": per_model}
    rec = r4.load("round4_analysis.json")["same_universe"]["groups"]
    for name in ("main_batch_330", "frozen_132", "overlap_excluded_121"):
        for m in MODELS:
            assert abs(out[name]["per_model"][m]["pooled"]["rate"] - rec[name]["per_model"][m]["unsupported_rate"]["value"]) < 1e-4
    return out


# --------------------------------------------------------------------------
# R9-7
# --------------------------------------------------------------------------

def selection(episodes) -> dict[str, Any]:
    by_child = defaultdict(list)
    for e in episodes:
        by_child[e.child_id].append(e)
    out = {"n_children": len(by_child), "caps": {}}
    for max_segments in (3000, 5000):
        cap = math.ceil(max_segments / len(by_child))
        per_child = {}
        for c, eps in sorted(by_child.items()):
            avail = Counter(e.episode_type.value for e in eps)
            order = list(dict.fromkeys(e.episode_type.value for e in eps))
            sel = _select_for_child(eps, cap)
            got = Counter(e.episode_type.value for e in sel)
            per_type = math.ceil(cap / len(avail))
            per_child[c] = {"types_in_first_appearance_order": order, "available": dict(avail),
                            "quota_per_type": per_type, "selected": {t: got.get(t, 0) for t in order},
                            "n_selected": len(sel), "sum_min_quota_available": sum(min(per_type, avail[t]) for t in order),
                            "truncated_by_cap": sum(min(per_type, avail[t]) for t in order) > cap}
        out["caps"][str(max_segments)] = {"per_child_cap": cap, "per_child": per_child,
                                          "total": sum(v["n_selected"] for v in per_child.values())}
    assert out["caps"]["3000"]["total"] == 2442 and out["caps"]["5000"]["total"] == 3371

    # Toy child run through the real function; it only reads `episode_type`, so strings stand in for enums.
    toy = [SimpleNamespace(episode_type=t, i=i) for i, t in
           enumerate(["play"] * 9 + ["request"] * 2 + ["play"] * 3 + ["other"] * 8 + ["response"] * 5)]
    toy_sel = _select_for_child(toy, 10)
    out["toy_example"] = {"cap": 10, "episodes_in_order": [e.episode_type for e in toy],
                          "selected_indices": [e.i for e in toy_sel], "selected_types": [e.episode_type for e in toy_sel]}
    return out


# --------------------------------------------------------------------------
# R9-8
# --------------------------------------------------------------------------

def oracle() -> dict[str, Any]:
    s3 = r4.load("scored_against_gold.json")["gold"]
    s4 = r4.load("scored_against_gold_augmented.json")["gold"]
    batch = {c["segment_id"]: c for c in r4.load("annotation_batch.json")["candidates"]}
    aug = {c["segment_id"]: c for c in r4.load("annotation_batch_augmented.json")["candidates"]}
    outcomes = r4.load("mars_outcomes.json")
    full = lambda j: all(j[f] in ACCEPTABLE for f in FIELDS)  # noqa: E731

    def reviewable(entry, models):
        res = [to_result(entry, m, entry["candidates"][m]) for m in models]
        cands = build_candidates(res)
        return {g for c in cands for g in c.generator_ids}

    def count(scored, src, models, subset=None, only_reviewable=False):
        segs = subset if subset is not None else list(scored)
        hits = 0
        for s in segs:
            ms = reviewable(src[s], models) if only_reviewable else set(models)
            hits += any(full(scored[s][m]) for m in ms)
        return {"numerator": hits, "denominator": len(segs), "rate": round(hits / len(segs), 4)}

    rerank = [s for s, o in outcomes.items() if (o.get("candidate_count") or 0) > 1]
    returned = [s for s, o in outcomes.items() if o.get("status") == "success"]
    out = {
        "three_generators_all_outputs_330": count(s3, batch, GEN3),
        "three_generators_reviewable_only_330": count(s3, batch, GEN3, only_reviewable=True),
        "three_generators_all_outputs_mars_returned": count(s3, batch, GEN3, subset=returned),
        "three_generators_all_outputs_rerank_required": count(s3, batch, GEN3, subset=rerank),
        "four_generators_all_outputs_330": count(s4, aug, MODELS),
        "recorded_mars_evaluation": r4.load("mars_evaluation.json")["oracle_ceiling"],
        "status_counts_3gen": dict(Counter(batch[s]["candidates"][m]["status"] for s in s3 for m in GEN3)),
    }
    assert abs(out["three_generators_all_outputs_330"]["rate"] - out["recorded_mars_evaluation"]) < 1e-4
    return out


def build() -> dict[str, Any]:
    _s, _d, episodes = r4.run_pipeline()
    u3000, u5000 = r4.universe(episodes, 3000), r4.universe(episodes, 5000)
    fa = r4.frame_audit(u5000, u3000)
    return {"generated_at": datetime.now(UTC).isoformat(),
            "r9_1_chronology": chronology(), "r9_2_3_4_packets": packets(),
            "r9_5_field_unsupported": field_unsupported(fa["_keys"]["pool"], fa["_keys"]["frozen"]),
            "r9_7_selection": selection(episodes), "r9_8_oracle": oracle()}


def main() -> None:
    report = build()
    OUT.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({k: (v if k != "r9_2_3_4_packets" else v["token_summary"]) for k, v in report.items()
                      if k in ("r9_1_chronology", "r9_8_oracle", "r9_2_3_4_packets")}, indent=1, default=str)[:4000])
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
