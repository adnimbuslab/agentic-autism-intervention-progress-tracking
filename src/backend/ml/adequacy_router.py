"""Adequacy & Representation Assessment — deterministic evidence sufficiency checks.

All logic is pure Python. No LLM involvement.
"""

from __future__ import annotations

from collections import Counter
from datetime import date

from src.backend.config import settings
from src.backend.ml.schemas import (
    AdequacyCheck,
    AdequacyCheckResult,
    AdequacyLevel,
    AdequacyResult,
)
from src.backend.schemas.observation_schema import LLM_EXTRACTED_FIELDS


class AdequacyRouter:
    """Deterministic assessment of whether accumulated evidence is sufficient
    and representative enough for longitudinal analytics and reporting."""

    def assess(
        self,
        records: list[dict],
        goals: list[dict],
        review_start: date,
        review_end: date,
        expected_observation_count: int | None = None,
    ) -> AdequacyResult:
        checks: list[AdequacyCheckResult] = []
        quality_flags: list[str] = []
        partial_abstentions: dict[str, str] = {}

        checks.append(self._check_coverage(records, expected_observation_count))
        checks.append(self._check_temporal_distribution(records, review_start, review_end))
        checks.append(self._check_contributor_representation(records))
        checks.append(self._check_setting_representation(records))
        checks.append(self._check_goal_coverage(records, goals))
        checks.append(self._check_field_completeness(records))

        for check in checks:
            if not check.passed:
                flag = f"{check.check.value}: {check.detail}"
                quality_flags.append(flag)

        contributor_check = next(
            (c for c in checks if c.check == AdequacyCheck.CONTRIBUTOR_REPRESENTATION), None
        )
        if contributor_check and not contributor_check.passed:
            partial_abstentions["cross_contributor_comparison"] = contributor_check.detail

        setting_check = next(
            (c for c in checks if c.check == AdequacyCheck.SETTING_REPRESENTATION), None
        )
        if setting_check and not setting_check.passed:
            partial_abstentions["cross_setting_comparison"] = setting_check.detail

        level = self._compute_level(checks, len(records))
        eligible = level != AdequacyLevel.INSUFFICIENT

        return AdequacyResult(
            level=level,
            eligible=eligible,
            checks=checks,
            partial_abstentions=partial_abstentions,
            quality_flags=quality_flags,
        )

    def _compute_level(
        self, checks: list[AdequacyCheckResult], record_count: int
    ) -> AdequacyLevel:
        if record_count == 0:
            return AdequacyLevel.INSUFFICIENT

        failed_checks = [c for c in checks if not c.passed]
        critical_checks = {AdequacyCheck.COVERAGE, AdequacyCheck.FIELD_COMPLETENESS}
        critical_failed = [c for c in failed_checks if c.check in critical_checks]

        if critical_failed:
            if record_count < settings.adequacy_limited_observations:
                return AdequacyLevel.INSUFFICIENT
            return AdequacyLevel.LIMITED

        if len(failed_checks) > 2:
            return AdequacyLevel.LIMITED

        if record_count < settings.adequacy_limited_observations:
            return AdequacyLevel.LIMITED

        if record_count >= settings.adequacy_min_observations and not failed_checks:
            return AdequacyLevel.ADEQUATE

        return AdequacyLevel.LIMITED

    def _check_coverage(
        self, records: list[dict], expected: int | None
    ) -> AdequacyCheckResult:
        count = len(records)
        threshold = expected or settings.adequacy_min_observations

        if count >= threshold:
            return AdequacyCheckResult(
                check=AdequacyCheck.COVERAGE,
                passed=True,
                detail=f"{count}/{threshold} observations received",
                value=float(count),
                threshold=float(threshold),
            )
        return AdequacyCheckResult(
            check=AdequacyCheck.COVERAGE,
            passed=False,
            detail=f"Only {count}/{threshold} observations received",
            value=float(count),
            threshold=float(threshold),
        )

    def _check_temporal_distribution(
        self, records: list[dict], review_start: date, review_end: date
    ) -> AdequacyCheckResult:
        if len(records) < 2:
            return AdequacyCheckResult(
                check=AdequacyCheck.TEMPORAL_DISTRIBUTION,
                passed=len(records) == 0,
                detail="Insufficient observations for temporal analysis" if records else "No observations",
                value=0.0,
            )

        dates = []
        for r in records:
            obs_date = r.get("observation_date")
            if obs_date:
                if isinstance(obs_date, str):
                    try:
                        obs_date = date.fromisoformat(obs_date)
                    except ValueError:
                        continue
                dates.append(obs_date)

        if not dates:
            return AdequacyCheckResult(
                check=AdequacyCheck.TEMPORAL_DISTRIBUTION,
                passed=False,
                detail="No valid observation dates found",
                value=0.0,
            )

        date_counts = Counter(dates)
        max_same_day = max(date_counts.values())
        cluster_ratio = max_same_day / len(dates)
        passed = cluster_ratio <= settings.adequacy_temporal_cluster_max_ratio

        return AdequacyCheckResult(
            check=AdequacyCheck.TEMPORAL_DISTRIBUTION,
            passed=passed,
            detail=f"Temporal cluster ratio {cluster_ratio:.2f} (max {max_same_day} on same day out of {len(dates)})",
            value=cluster_ratio,
            threshold=settings.adequacy_temporal_cluster_max_ratio,
        )

    def _check_contributor_representation(
        self, records: list[dict]
    ) -> AdequacyCheckResult:
        if not records:
            return AdequacyCheckResult(
                check=AdequacyCheck.CONTRIBUTOR_REPRESENTATION,
                passed=False,
                detail="No records to assess contributor representation",
            )

        contributors = Counter(r.get("contributor_role", "unknown") for r in records)
        unique = len(contributors)

        if unique >= 2:
            return AdequacyCheckResult(
                check=AdequacyCheck.CONTRIBUTOR_REPRESENTATION,
                passed=True,
                detail=f"{unique} distinct contributor roles represented",
                value=float(unique),
            )
        role = list(contributors.keys())[0]
        return AdequacyCheckResult(
            check=AdequacyCheck.CONTRIBUTOR_REPRESENTATION,
            passed=False,
            detail=f"All {len(records)} observations from single contributor role: {role}",
            value=1.0,
        )

    def _check_setting_representation(
        self, records: list[dict]
    ) -> AdequacyCheckResult:
        if not records:
            return AdequacyCheckResult(
                check=AdequacyCheck.SETTING_REPRESENTATION,
                passed=False,
                detail="No records to assess setting representation",
            )

        settings_counter = Counter(r.get("setting", "unknown") for r in records)
        unique = len(settings_counter)

        if unique >= 2:
            return AdequacyCheckResult(
                check=AdequacyCheck.SETTING_REPRESENTATION,
                passed=True,
                detail=f"{unique} distinct settings represented",
                value=float(unique),
            )
        setting = list(settings_counter.keys())[0]
        return AdequacyCheckResult(
            check=AdequacyCheck.SETTING_REPRESENTATION,
            passed=False,
            detail=f"All observations from single setting: {setting}",
            value=1.0,
        )

    def _check_goal_coverage(
        self, records: list[dict], goals: list[dict]
    ) -> AdequacyCheckResult:
        if not goals:
            return AdequacyCheckResult(
                check=AdequacyCheck.GOAL_COVERAGE,
                passed=True,
                detail="No active goals defined",
            )

        goal_domains = {g.get("domain") for g in goals if g.get("domain")}
        record_domains = {r.get("domain") for r in records if r.get("domain")}
        covered = goal_domains & record_domains
        coverage_ratio = len(covered) / len(goal_domains) if goal_domains else 0.0

        if coverage_ratio >= 0.5:
            return AdequacyCheckResult(
                check=AdequacyCheck.GOAL_COVERAGE,
                passed=True,
                detail=f"{len(covered)}/{len(goal_domains)} goal domains have observations",
                value=coverage_ratio,
                threshold=0.5,
            )
        missing = goal_domains - record_domains
        return AdequacyCheckResult(
            check=AdequacyCheck.GOAL_COVERAGE,
            passed=False,
            detail=f"Missing observations for goal domains: {', '.join(sorted(missing))}",
            value=coverage_ratio,
            threshold=0.5,
        )

    def _check_field_completeness(
        self, records: list[dict]
    ) -> AdequacyCheckResult:
        if not records:
            return AdequacyCheckResult(
                check=AdequacyCheck.FIELD_COMPLETENESS,
                passed=False,
                detail="No records to assess",
                value=0.0,
                threshold=settings.adequacy_field_completeness_threshold,
            )

        critical_fields = {"behavior", "domain", "outcome"}
        total_checks = len(records) * len(critical_fields)
        present = 0
        for r in records:
            for f in critical_fields:
                val = r.get(f)
                if val is not None and val != "unknown":
                    present += 1

        completeness = present / total_checks if total_checks > 0 else 0.0
        passed = completeness >= settings.adequacy_field_completeness_threshold

        return AdequacyCheckResult(
            check=AdequacyCheck.FIELD_COMPLETENESS,
            passed=passed,
            detail=f"Critical field completeness: {completeness:.0%} ({present}/{total_checks})",
            value=completeness,
            threshold=settings.adequacy_field_completeness_threshold,
        )
