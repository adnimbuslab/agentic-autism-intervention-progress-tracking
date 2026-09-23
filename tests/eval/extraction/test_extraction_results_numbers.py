"""Every number in the gold-standard results section, checked against its artefact.

`results_extraction.md` Tables 5-8 are typed prose over figures produced by
`adjudicate`, `score_against_gold` and `mars_evaluation`. A table edited by
hand, or an artefact regenerated under a changed scoring policy, would leave
the two disagreeing with nothing to catch it before submission.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
RESULTS = Path(__file__).parent / "results"
MANUSCRIPT = ROOT / "docs/paper/results_extraction.md"
SCORED = RESULTS / "scored_against_gold.json"
GOLD = RESULTS / "gold_labels.json"
BATCH = RESULTS / "annotation_batch.json"

ACCEPTABLE = ("correct", "correctly_null")


def _require(path: Path) -> dict:
    if not path.exists():
        pytest.skip(f"{path.name} not produced yet")
    return json.loads(path.read_text())


@pytest.fixture(scope="module")
def prose() -> str:
    if not MANUSCRIPT.exists():
        pytest.skip("manuscript not written")
    return MANUSCRIPT.read_text()


@pytest.fixture(scope="module")
def flat(prose) -> str:
    """The manuscript with runs of whitespace collapsed.

    Markdown wraps prose at the column, so a phrase the author wrote as one
    sentence is often split across lines. Asserting multi-word phrases against
    the raw text fails on the line break rather than on the claim.
    """
    return re.sub(r"\s+", " ", prose)


@pytest.fixture(scope="module")
def section(prose) -> str:
    """Just the per-field agreement section, headings excluded."""
    start = prose.index("### Agreement with the reference standard, per field")
    return prose[start:prose.index("\n### ", start + 1)]


@pytest.fixture(scope="module")
def scored() -> dict:
    return _require(SCORED)


@pytest.fixture(scope="module")
def gold() -> dict:
    return _require(GOLD)


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def _cells(pct: str) -> tuple[str, ...]:
    """A percentage as a table cell, plain, bold or italic.

    Matching the bare string would let `8.8%` match inside `78.8%` two sections
    away, which is how a merged figure could survive its own removal test.
    """
    return (f"| {pct} |", f"| **{pct}** |", f"| *{pct}* |")


def _has_cell(section: str, pct: str) -> bool:
    return any(form in section for form in _cells(pct))


class TestGoldComposition:
    def test_every_segment_entered_gold(self, prose, gold) -> None:
        assert gold["n_segments_in_gold"] == 330
        assert gold["counts"].get("unresolved", 0) == 0
        assert "330 of 330 (none excluded)" in prose

    def test_the_adjudicated_and_agreed_counts_match(self, prose, gold) -> None:
        assert gold["counts"]["adjudicated"] == 322
        assert gold["counts"]["agreed"] == 8
        assert "| 322 |" in prose and "| 8 |" in prose

    def test_the_adjudicator_is_recorded_and_named_in_the_prose(
        self, prose, gold
    ) -> None:
        # A gold standard with a blank adjudicator must not reach submission.
        assert gold["adjudicator"], "adjudicator not recorded"
        assert "consensus" in gold["adjudicator"]
        assert "consensus:annotator_a+annotator_b" in prose

    def test_the_null_counts_per_field_match(self, prose, gold) -> None:
        nulls = {
            field: sum(
                1 for v in gold["gold"].values() if v["field_values"][field] is None
            )
            for field in ("domain", "modality", "prompt_level", "outcome")
        }
        assert nulls == {"domain": 3, "modality": 77, "prompt_level": 2, "outcome": 115}
        assert "outcome 115, modality 77, domain 3, prompt_level 2" in prose


MIN_RATEABLE = 20  # domain and prompt_level have 3 and 2 null segments


def _split(counts: dict, field: str) -> tuple[tuple[int, int], tuple[int, int]]:
    """(agreed, n) where the standard records a value, and where it records none.

    The two halves answer different questions and are computed over different
    denominators, which is the whole reason the merged per-field percentage was
    dropped: it averaged them and reported the average as one ability.
    """
    correct = counts.get(f"{field}:correct", 0)
    wrong = counts.get(f"{field}:incorrect", 0)
    absent = counts.get(f"{field}:missing", 0)
    silent = counts.get(f"{field}:correctly_null", 0)
    asserted = counts.get(f"{field}:hallucinated", 0)
    return (correct, correct + wrong + absent), (silent, silent + asserted)


class TestFieldAgreement:
    """Tables 6a and 6b, each over its own denominator.

    Assertions here are scoped to the agreement section. A bare percentage
    checked against the whole document collides with unrelated numbers — "8.8%"
    sits inside "78.8%" two sections away — which would leave the negative
    assertion below unable to fail.
    """

    @pytest.mark.parametrize(
        "model", ["llama3.2:latest", "qwen2.5:3b", "qwen2.5:7b"]
    )
    def test_every_cell_of_tables_6a_and_6b_matches(
        self, section, scored, model
    ) -> None:
        counts = scored["per_field_counts"][model]
        for field in scored["scoring_fields"]:
            (agreed, has_value), (silent, no_value) = _split(counts, field)
            assert has_value + no_value == 330, f"{model} {field}"
            assert f"(n={has_value})" in section, f"6a {model} {field} denominator"
            assert _has_cell(section, _pct(agreed / has_value)), f"6a {model} {field}"
            if no_value >= MIN_RATEABLE:
                assert f"(n={no_value})" in section, f"6b {model} {field} denominator"
                assert _has_cell(section, _pct(silent / no_value)), (
                    f"6b {model} {field}"
                )

    def test_the_unrateable_fields_are_named_rather_than_rated(
        self, flat, scored
    ) -> None:
        counts = scored["per_field_counts"]["qwen2.5:7b"]
        thin = {
            field: _split(counts, field)[1][1]
            for field in scored["scoring_fields"]
            if _split(counts, field)[1][1] < MIN_RATEABLE
        }
        assert thin == {"domain": 3, "prompt_level": 2}
        assert "records no value on only 3 and 2 segments" in flat

    def test_the_human_reference_level_is_stated_beside_the_generators(
        self, section
    ) -> None:
        """The comparison target is a settled value, not ground truth.

        Without the annotators' own first-pass figure in the same table, a
        reader has no scale for what agreement on this task can look like.
        """
        r1 = _require(RESULTS / "reliability_round1.json")["fields"]
        for field in ("domain", "modality", "prompt_level", "outcome"):
            rate = r1[field]["observed_agreement"]
            assert f"*{_pct(rate)}*" in section, field

    def test_no_merged_per_field_figure_is_reported(self, section, scored) -> None:
        """The statistic the section used to lead with is gone, not just moved.

        `acceptable / 330` mixes a right value with a right silence over a
        denominator that includes both, so it cannot be read as either.
        """
        for model in scored["models"]:
            counts = scored["per_field_counts"][model]
            for field in scored["scoring_fields"]:
                acceptable = sum(counts.get(f"{field}:{j}", 0) for j in ACCEPTABLE)
                merged = _pct(acceptable / 330)
                assert not _has_cell(section, merged), (
                    f"merged {model} {field} = {merged}"
                )

    def test_behavior_is_excluded_from_the_scoring_policy(self, scored) -> None:
        assert scored["behavior_match"] == "excluded"
        assert "behavior" not in scored["scoring_fields"]

    def test_the_abstention_caveat_cites_real_counts(self, prose, scored) -> None:
        counts = scored["per_field_counts"]["qwen2.5:3b"]
        assert counts["prompt_level:missing"] == 277
        assert counts["outcome:missing"] == 114
        assert "277 of 330" in prose


class TestUnsupportedExtractions:
    @pytest.mark.parametrize("field", ["modality", "outcome"])
    def test_table_7_counts_and_rates_match(self, prose, scored, field) -> None:
        for model in scored["models"]:
            counts = scored["per_field_counts"][model]
            hallucinated = counts.get(f"{field}:hallucinated", 0)
            opportunities = hallucinated + counts.get(f"{field}:correctly_null", 0)
            assert f"{hallucinated} ({100 * hallucinated / opportunities:.1f}%)" in prose

    def test_the_denominator_equals_the_null_gold_count(self, scored, gold) -> None:
        # Every null in gold is one opportunity to assert an unsupported value.
        for field in ("modality", "outcome"):
            nulls = sum(
                1 for v in gold["gold"].values() if v["field_values"][field] is None
            )
            for model in scored["models"]:
                counts = scored["per_field_counts"][model]
                opportunities = counts.get(f"{field}:hallucinated", 0) + counts.get(
                    f"{field}:correctly_null", 0
                )
                assert opportunities == nulls, f"{model} {field}"

    def test_the_low_n_fields_are_excluded_with_their_counts_stated(
        self, prose
    ) -> None:
        assert "only 3 and 2 nulls" in prose


class TestRecordCeiling:
    def test_whole_record_accuracy_and_ceiling_match(self, prose, scored) -> None:
        from tests.eval.extraction.mars_evaluation import (
            oracle_ceiling,
            per_model_accuracy,
        )

        fields = scored["scoring_fields"]
        accuracy = per_model_accuracy(scored["gold"], scored["models"], fields)
        ceiling = oracle_ceiling(scored["gold"], scored["models"], fields)
        for model, value in accuracy.items():
            assert _pct(value) in prose, model
        assert _pct(ceiling) in prose

    def test_the_headroom_claim_is_arithmetic(self, prose, scored) -> None:
        from tests.eval.extraction.mars_evaluation import (
            oracle_ceiling,
            per_model_accuracy,
        )

        fields = scored["scoring_fields"]
        accuracy = per_model_accuracy(scored["gold"], scored["models"], fields)
        best = max(v for v in accuracy.values() if v is not None)
        ceiling = oracle_ceiling(scored["gold"], scored["models"], fields)
        headroom = 100 * (ceiling - best)
        assert f"{headroom:.1f} percentage points" in prose


class TestBehaviorBand:
    def test_the_human_reference_band_matches(self, prose, gold) -> None:
        from tests.eval.extraction.agreement_report import normalize, token_overlap

        first = _require(RESULTS / "gold_annotator_a.json")
        second = _require(RESULTS / "gold_annotator_b.json")
        ids = [s for s in gold["gold"] if s in first and s in second]
        overlaps = [
            token_overlap(
                normalize(first[s]["field_values"]["behavior"]),
                normalize(second[s]["field_values"]["behavior"]),
            )
            for s in ids
        ]
        assert f"{statistics.median(overlaps):.3f}" in prose
        assert f"{statistics.mean(overlaps):.3f}" in prose

    def test_the_threshold_claim_holds(self, prose, gold) -> None:
        from tests.eval.extraction.agreement_report import normalize, token_overlap

        first = _require(RESULTS / "gold_annotator_a.json")
        second = _require(RESULTS / "gold_annotator_b.json")
        ids = [s for s in gold["gold"] if s in first and s in second]
        overlaps = [
            token_overlap(
                normalize(first[s]["field_values"]["behavior"]),
                normalize(second[s]["field_values"]["behavior"]),
            )
            for s in ids
        ]
        share = 100 * sum(1 for o in overlaps if o >= 0.5) / len(overlaps)
        assert f"{share:.1f}%" in prose

    def test_the_model_medians_match(self, prose, gold, scored) -> None:
        from tests.eval.extraction.agreement_report import normalize, token_overlap

        batch = _require(BATCH)
        entries = {e["segment_id"]: e for e in batch["candidates"]}
        for model in scored["models"]:
            values = []
            for segment, record in gold["gold"].items():
                if segment not in entries:
                    continue
                got = (
                    entries[segment]["candidates"][model].get("extracted_fields") or {}
                ).get("behavior")
                if got:
                    values.append(
                        token_overlap(
                            normalize(got),
                            normalize(record["field_values"]["behavior"]),
                        )
                    )
            assert f"{statistics.median(values):.3f}" in prose, model


class TestHonesty:
    def test_the_partial_run_guard_is_documented(self, flat) -> None:
        # MARS accuracy is now reported over the full batch; what must remain
        # documented is the guard and why it exists.
        assert "refuses to report below 95% outcome coverage" in flat
        assert "artefacts of a 3-segment denominator" in flat

    def test_consensus_adjudication_is_declared_a_limitation(self, flat) -> None:
        assert "Consensus adjudication" in flat


MARS_EVAL = RESULTS / "mars_evaluation.json"
MARS_OUTCOMES = RESULTS / "mars_outcomes.json"
MARS_SUMMARY = RESULTS / "mars_run_summary.json"


@pytest.fixture(scope="module")
def mars() -> dict:
    return _require(MARS_EVAL)


class TestMarsResults:
    """Tables 9-10, against mars_evaluation.json and the run summary."""

    def test_the_run_covers_the_whole_batch(self, mars, gold) -> None:
        # The guard exists because a 3-segment run once produced headline
        # numbers; assert the reported run is not one of those.
        assert mars["mars"]["n_total"] == gold["n_segments_in_gold"] == 330

    def test_the_outcome_profile_matches(self, prose, mars) -> None:
        profile = mars["mars"]
        assert profile["n_returned"] == 265
        for reason, n in profile["abstention_reasons"].items():
            assert f"`{reason}` | {n} |" in prose, reason
        assert f"| {profile['n_returned']} | {profile['coverage']:.1%} |" in prose

    def test_the_abstentions_and_returns_account_for_every_segment(
        self, mars
    ) -> None:
        profile = mars["mars"]
        assert profile["n_returned"] + sum(
            profile["abstention_reasons"].values()
        ) == profile["n_total"]

    def test_the_accuracy_figures_match(self, prose, mars) -> None:
        for key in ("accuracy_over_returned", "accuracy_over_all"):
            assert f"{100 * mars['mars'][key]:.1f}%" in prose, key
        assert f"{100 * mars['best_generator_accuracy']:.1f}%" in prose
        assert f"{100 * mars['oracle_ceiling']:.1f}%" in prose

    def test_no_judge_was_failing_in_the_reported_run(self) -> None:
        # The first full run had a judge discarded on 165 of 165 segments while
        # still counted on the panel. Assert the reported run is not that one.
        summary = _require(MARS_SUMMARY)
        reliability = summary.get("judge_reliability") or {}
        assert reliability, "run summary carries no judge reliability"
        for judge, entry in reliability.items():
            assert entry["discard_rate"] <= 0.05, f"{judge}: {entry}"

    def test_the_panel_was_not_a_single_judge_ablation(self) -> None:
        summary = _require(MARS_SUMMARY)
        assert summary["single_judge_ablation"] is False
        assert summary["min_eligible_judges"] >= 2

    def test_the_paired_comparison_is_reported_as_underpowered(
        self, flat, scored, mars
    ) -> None:
        from tests.eval.extraction.mars_evaluation import is_fully_correct

        outcomes = _require(MARS_OUTCOMES)
        fields = scored["scoring_fields"]
        judged = scored["gold"]
        returned = [
            s for s in outcomes
            if outcomes[s]["status"] == "success" and s in judged
        ]
        best = mars["best_generator"]
        mars_only = generator_only = 0
        for segment in returned:
            selected = (outcomes[segment].get("selected_generator_ids") or [None])[0]
            mars_ok = (
                selected in judged[segment]
                and is_fully_correct(judged[segment][selected], fields)
            )
            gen_ok = best in judged[segment] and is_fully_correct(
                judged[segment][best], fields
            )
            mars_only += mars_ok and not gen_ok
            generator_only += gen_ok and not mars_ok

        # The claim in the prose: MARS never recovered a record the best
        # generator missed, and the discordant count is tiny.
        assert mars_only == 0
        assert f"{mars_only + generator_only} discordant" in flat
        assert "p = 0.25" in flat
        assert "underpowered" in flat

    def test_the_capture_rate_is_not_interpreted_as_performance(
        self, flat, mars
    ) -> None:
        assert mars["oracle_capture_rate"] < 0
        assert "should not be read as a performance figure" in flat

    def test_the_broken_judge_incident_is_disclosed(self, flat) -> None:
        # A reader must be able to tell the reported run from the invalid one.
        assert "165 of 165" in flat
        assert "2048" in flat


SELECTION = RESULTS / "mars_selection_analysis.json"


@pytest.fixture(scope="module")
def selection() -> dict:
    return _require(SELECTION)


class TestSelectionAnalysis:
    """Tables 11-12, against mars_selection_analysis.json."""

    def test_short_circuits_are_excluded_from_the_estimand(
        self, flat, selection
    ) -> None:
        # Selection quality cannot be measured where no selection occurred.
        assert selection["n_judged_segments"] == 142
        assert selection["n_short_circuit"] == 123
        assert selection["n_judged_segments"] + selection["n_short_circuit"] == (
            selection["n_returned"]
        )
        assert "142 judged segments" in flat
        assert "123 single-candidate short-circuits" in flat

    @pytest.mark.parametrize("policy", ["mars", "best_generator", "random_candidate"])
    def test_table_11_cells_match(self, prose, selection, policy) -> None:
        for field in selection["fields"]:
            value = selection["per_field"][field][policy]
            assert f"{100 * value:.1f}%" in prose, f"{policy} {field}"

    def test_the_means_match(self, prose, selection) -> None:
        for value in selection["mean_accuracy"].values():
            assert f"{100 * value:.1f}%" in prose

    @pytest.mark.parametrize(
        "key", ["vs_best_generator", "vs_random_candidate"]
    )
    def test_table_12_intervals_match(self, prose, selection, key) -> None:
        for field in selection["fields"]:
            entry = selection["per_field"][field][key]
            cell = (
                f"{100 * entry['difference']:+.1f} "
                f"[{100 * entry['lower']:+.1f}, {100 * entry['upper']:+.1f}]"
            )
            assert cell.replace("+", "+") in prose.replace("−", "-"), f"{key} {field}"

    def test_the_positive_finding_is_real(self, selection) -> None:
        # "Reranking carries real signal" rests on these two intervals.
        for field in ("modality", "prompt_level"):
            entry = selection["per_field"][field]["vs_random_candidate"]
            assert entry["difference"] > 0 and entry["excludes_zero"], field

    def test_the_negative_finding_is_real(self, selection) -> None:
        # "Reranking does not beat the best generator" rests on domain.
        entry = selection["per_field"]["domain"]["vs_best_generator"]
        assert entry["difference"] < 0 and entry["excludes_zero"]

    def test_mars_beats_random_on_every_field_directionally(self, selection) -> None:
        for field in selection["fields"]:
            assert selection["per_field"][field]["vs_random_candidate"][
                "difference"
            ] > 0, field

    def test_mars_sits_between_the_two_baselines(self, selection) -> None:
        means = selection["mean_accuracy"]
        assert means["random_candidate"] < means["mars"] < means["best_generator"]

    def test_the_mechanism_claim_is_arithmetic(self, flat, selection) -> None:
        # The prose explains domain's deficit by how often MARS departs from
        # the dominant generator. Check the share and the spread it cites.
        share = selection["mars_share_of_best_generator"]
        assert f"{share:.0%} of judged segments" in flat
        best = selection["best_generator"]
        per_gen = selection["per_field"]["domain"]["per_generator"]
        lead = 100 * (per_gen[best] - max(v for m, v in per_gen.items() if m != best))
        assert f"leads the roster by {lead:.0f} points" in flat

    def test_the_finding_is_declared_roster_conditional(self, flat) -> None:
        assert "roster-conditional" in flat or "property of the roster" in flat
        assert "not \"reranking does not work\"" in flat.replace("“", '"').replace("”", '"')
