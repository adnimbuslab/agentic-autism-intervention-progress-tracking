"""Deterministic Analytics Engine — all KPIs computed by code, never by LLM.

Every computation is deterministic and reproducible for identical inputs.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from src.backend.ml.schemas import (
    AdequacyResult,
    AnalyticsResult,
    KpiResult,
)


class AnalyticsEngine:
    """Computes longitudinal analytics over validated, version-current
    StructuredRecords. Only runs when adequacy allows."""

    def compute(
        self,
        child_id: str,
        review_period_id: str,
        records: list[dict],
        adequacy: AdequacyResult,
        goal_id: str | None = None,
    ) -> AnalyticsResult:
        kpis: list[KpiResult] = []

        if not adequacy.eligible:
            return AnalyticsResult(
                child_id=child_id,
                review_period_id=review_period_id,
                goal_id=goal_id,
                kpis=[
                    KpiResult(
                        name="all_analytics",
                        numerator=0,
                        denominator=0,
                        abstained=True,
                        abstention_reason=f"Evidence level: {adequacy.level.value}",
                        prerequisites_met=False,
                        display_eligible=False,
                    )
                ],
                adequacy=adequacy,
            )

        kpis.append(self._observation_count(records))
        kpis.append(self._domain_distribution(records))
        kpis.append(self._modality_distribution(records))
        kpis.append(self._prompt_level_distribution(records))
        kpis.append(self._outcome_distribution(records))
        kpis.append(self._independence_rate(records))
        kpis.append(self._contributor_distribution(records))
        kpis.append(self._setting_distribution(records))
        kpis.append(self._missing_data_rate(records))
        kpis.append(self._positive_outcome_rate(records))
        kpis.append(self._prompt_support_trend(records))
        kpis.append(self._outcome_trend(records))

        cross_setting = self._cross_setting_comparison(records, adequacy)
        kpis.append(cross_setting)
        cross_contributor = self._cross_contributor_comparison(records, adequacy)
        kpis.append(cross_contributor)

        return AnalyticsResult(
            child_id=child_id,
            review_period_id=review_period_id,
            goal_id=goal_id,
            kpis=kpis,
            adequacy=adequacy,
        )

    def _observation_count(self, records: list[dict]) -> KpiResult:
        return KpiResult(
            name="observation_count",
            numerator=float(len(records)),
            denominator=1.0,
            value=float(len(records)),
        )

    def _domain_distribution(self, records: list[dict]) -> KpiResult:
        counts = Counter(r.get("domain") for r in records if r.get("domain"))
        total = sum(counts.values())
        dist = {k: round(v / total, 4) for k, v in sorted(counts.items())} if total else {}
        return KpiResult(
            name="domain_distribution",
            numerator=float(len(counts)),
            denominator=float(total),
            value=float(len(counts)),
        )

    def _modality_distribution(self, records: list[dict]) -> KpiResult:
        counts = Counter(r.get("modality") for r in records if r.get("modality"))
        total = sum(counts.values())
        return KpiResult(
            name="modality_distribution",
            numerator=float(len(counts)),
            denominator=float(total),
            value=float(len(counts)),
        )

    def _prompt_level_distribution(self, records: list[dict]) -> KpiResult:
        counts = Counter(r.get("prompt_level") for r in records if r.get("prompt_level"))
        total = sum(counts.values())
        return KpiResult(
            name="prompt_level_distribution",
            numerator=float(len(counts)),
            denominator=float(total),
            value=float(len(counts)),
        )

    def _outcome_distribution(self, records: list[dict]) -> KpiResult:
        counts = Counter(r.get("outcome") for r in records if r.get("outcome"))
        total = sum(counts.values())
        return KpiResult(
            name="outcome_distribution",
            numerator=float(len(counts)),
            denominator=float(total),
            value=float(len(counts)),
        )

    def _independence_rate(self, records: list[dict]) -> KpiResult:
        with_prompt = [r for r in records if r.get("prompt_level")]
        if not with_prompt:
            return KpiResult(
                name="independence_rate",
                numerator=0,
                denominator=0,
                abstained=True,
                abstention_reason="No records with prompt level data",
                prerequisites_met=False,
                display_eligible=False,
            )
        independent = sum(1 for r in with_prompt if r.get("prompt_level") == "independent")
        rate = independent / len(with_prompt)
        return KpiResult(
            name="independence_rate",
            numerator=float(independent),
            denominator=float(len(with_prompt)),
            value=round(rate, 4),
        )

    def _contributor_distribution(self, records: list[dict]) -> KpiResult:
        counts = Counter(r.get("contributor_role") for r in records if r.get("contributor_role"))
        total = sum(counts.values())
        return KpiResult(
            name="contributor_distribution",
            numerator=float(len(counts)),
            denominator=float(total),
            value=float(len(counts)),
        )

    def _setting_distribution(self, records: list[dict]) -> KpiResult:
        counts = Counter(r.get("setting") for r in records if r.get("setting"))
        total = sum(counts.values())
        return KpiResult(
            name="setting_distribution",
            numerator=float(len(counts)),
            denominator=float(total),
            value=float(len(counts)),
        )

    def _missing_data_rate(self, records: list[dict]) -> KpiResult:
        key_fields = ["behavior", "domain", "modality", "prompt_level", "outcome"]
        total = len(records) * len(key_fields)
        if total == 0:
            return KpiResult(
                name="missing_data_rate",
                numerator=0,
                denominator=0,
                value=0.0,
            )
        missing = 0
        for r in records:
            for f in key_fields:
                val = r.get(f)
                if val is None or val == "unknown":
                    missing += 1
        rate = missing / total
        return KpiResult(
            name="missing_data_rate",
            numerator=float(missing),
            denominator=float(total),
            value=round(rate, 4),
        )

    def _positive_outcome_rate(self, records: list[dict]) -> KpiResult:
        with_outcome = [r for r in records if r.get("outcome") and r["outcome"] != "unknown"]
        if not with_outcome:
            return KpiResult(
                name="positive_outcome_rate",
                numerator=0,
                denominator=0,
                abstained=True,
                abstention_reason="No records with outcome data",
                prerequisites_met=False,
                display_eligible=False,
            )
        positive = sum(
            1 for r in with_outcome
            if r["outcome"] in ("correct", "approximation", "partial")
        )
        rate = positive / len(with_outcome)
        return KpiResult(
            name="positive_outcome_rate",
            numerator=float(positive),
            denominator=float(len(with_outcome)),
            value=round(rate, 4),
        )

    def _cross_setting_comparison(
        self, records: list[dict], adequacy: AdequacyResult
    ) -> KpiResult:
        if "cross_setting_comparison" in adequacy.partial_abstentions:
            return KpiResult(
                name="cross_setting_comparison",
                numerator=0,
                denominator=0,
                abstained=True,
                abstention_reason=adequacy.partial_abstentions["cross_setting_comparison"],
                prerequisites_met=False,
                display_eligible=False,
            )
        settings_counter = Counter(r.get("setting") for r in records if r.get("setting"))
        return KpiResult(
            name="cross_setting_comparison",
            numerator=float(len(settings_counter)),
            denominator=float(sum(settings_counter.values())),
            value=float(len(settings_counter)),
        )

    def _cross_contributor_comparison(
        self, records: list[dict], adequacy: AdequacyResult
    ) -> KpiResult:
        if "cross_contributor_comparison" in adequacy.partial_abstentions:
            return KpiResult(
                name="cross_contributor_comparison",
                numerator=0,
                denominator=0,
                abstained=True,
                abstention_reason=adequacy.partial_abstentions["cross_contributor_comparison"],
                prerequisites_met=False,
                display_eligible=False,
            )
        contributor_counter = Counter(
            r.get("contributor_role") for r in records if r.get("contributor_role")
        )
        return KpiResult(
            name="cross_contributor_comparison",
            numerator=float(len(contributor_counter)),
            denominator=float(sum(contributor_counter.values())),
            value=float(len(contributor_counter)),
        )

    def _prompt_support_trend(self, records: list[dict]) -> KpiResult:
        dated = self._sort_by_date(records)
        with_prompt = [(d, r) for d, r in dated if r.get("prompt_level")]
        if len(with_prompt) < 4:
            return KpiResult(
                name="prompt_support_trend",
                numerator=0,
                denominator=0,
                abstained=True,
                abstention_reason="Insufficient data for trend (need >=4 records with prompt level)",
                prerequisites_met=False,
                display_eligible=False,
            )
        mid = len(with_prompt) // 2
        first_half = with_prompt[:mid]
        second_half = with_prompt[mid:]
        first_indep = sum(1 for _, r in first_half if r["prompt_level"] == "independent")
        second_indep = sum(1 for _, r in second_half if r["prompt_level"] == "independent")
        first_rate = first_indep / len(first_half)
        second_rate = second_indep / len(second_half)
        change = round(second_rate - first_rate, 4)
        return KpiResult(
            name="prompt_support_trend",
            numerator=float(second_indep),
            denominator=float(len(second_half)),
            value=change,
        )

    def _outcome_trend(self, records: list[dict]) -> KpiResult:
        dated = self._sort_by_date(records)
        with_outcome = [
            (d, r) for d, r in dated
            if r.get("outcome") and r["outcome"] != "unknown"
        ]
        if len(with_outcome) < 4:
            return KpiResult(
                name="outcome_trend",
                numerator=0,
                denominator=0,
                abstained=True,
                abstention_reason="Insufficient data for trend (need >=4 records with outcome)",
                prerequisites_met=False,
                display_eligible=False,
            )
        mid = len(with_outcome) // 2
        first_half = with_outcome[:mid]
        second_half = with_outcome[mid:]
        positive = ("correct", "approximation", "partial")
        first_pos = sum(1 for _, r in first_half if r["outcome"] in positive)
        second_pos = sum(1 for _, r in second_half if r["outcome"] in positive)
        first_rate = first_pos / len(first_half)
        second_rate = second_pos / len(second_half)
        change = round(second_rate - first_rate, 4)
        return KpiResult(
            name="outcome_trend",
            numerator=float(second_pos),
            denominator=float(len(second_half)),
            value=change,
        )

    @staticmethod
    def _sort_by_date(records: list[dict]) -> list[tuple[date, dict]]:
        result: list[tuple[date, dict]] = []
        for r in records:
            obs_date = r.get("observation_date")
            if obs_date:
                if isinstance(obs_date, str):
                    try:
                        obs_date = date.fromisoformat(obs_date)
                    except ValueError:
                        continue
                result.append((obs_date, r))
        result.sort(key=lambda x: x[0])
        return result
