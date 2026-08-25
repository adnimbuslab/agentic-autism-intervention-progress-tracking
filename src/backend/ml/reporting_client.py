"""Grounded Reporting LLM — generates professional progress-report prose from
an EvidencePacket. All factual content must trace to the evidence packet.

The LLM may only summarize and organize deterministic findings. It must NOT
diagnose, prescribe, make causal claims, invent statistics, or calculate KPIs.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime

from src.backend.config import settings
from src.backend.ml.schemas import EvidencePacket, GeneratedReportData, ReportSection

logger = logging.getLogger(__name__)

REPORTING_SYSTEM_PROMPT = """You are a professional progress-report writer for a longitudinal autism intervention monitoring system.

You will receive an evidence packet containing:
- Review period dates
- Active goals
- Deterministic analytics (pre-computed KPIs)
- Adequacy assessment (evidence sufficiency)
- Validated structured observation records
- Quality flags and limitations

RULES — you MUST follow all of these:

1. ONLY use information from the evidence packet. Do not invent observations, statistics, or details.
2. Reproduce all pre-computed numbers EXACTLY as provided. Do not recalculate, round differently, or invent new statistics.
3. Preserve all abstention messages. If a metric was withheld due to insufficient evidence, state that clearly.
4. If evidence is insufficient or limited, explicitly state this. Do not convert limited evidence into confident conclusions.

PROHIBITED — you must NEVER:
- Diagnose autism or any other condition
- Prescribe or recommend treatment, therapy, or medication
- Recommend changing intervention goals, strategies, or approaches
- Make causal claims (e.g., "improvement was caused by...")
- Claim treatment effectiveness or ineffectiveness
- Use terms like "normal", "abnormal", "delayed", or "deficit"
- Make prognostic statements (e.g., "the child will likely...")
- Invent numerical values not present in the evidence packet
- Calculate new KPIs not already in the analytics

You SHOULD:
- Summarize deterministic findings in professional, readable prose
- Organize evidence by goal area when possible
- Describe observed patterns that are directly supported by the evidence
- Explicitly state evidence limitations and gaps
- Note when observations come from a single contributor or setting
- Use evidence-linked language ("observations indicate...", "records show...")

OUTPUT FORMAT:
Return a JSON array of report sections. Each section has:
- "heading": section title
- "body": prose content
- "evidence_refs": list of record IDs referenced
- "abstention_note": null or explanation of withheld information

Required sections:
1. "Review Period Summary"
2. "Evidence Coverage"
3. "Observed Patterns" (or "Goal-Level Observations" if goals exist)
4. "Evidence Limitations"

Optional sections (include only when data supports):
5. "Progress Indicators"
6. "Cross-Setting Observations"
7. "Items Requiring Interventionist Review"
"""


PROHIBITED_PATTERNS = [
    r"\b(diagnos[ei]s|diagnosed)\b",
    r"\b(recommend|should|must|need to)\b.*\b(therap\w*|treatment|intervention|medication)\b",
    r"\b(caus[ei]s?|caused by|due to|because of)\b.*\b(autism|ASD|condition)\b",
    r"\b(prognosis|outlook|will (likely|probably))\b",
    r"\b(normal|abnormal|delayed|deficit)\b",
    r"\b(change|modify|adjust)\b.*\b(goal|objective|target)\b",
]


def validate_report(
    sections: list[ReportSection],
    evidence_packet: EvidencePacket,
) -> list[str]:
    errors: list[str] = []
    full_text = " ".join(s.body for s in sections)

    for pattern in PROHIBITED_PATTERNS:
        matches = re.findall(pattern, full_text, re.IGNORECASE)
        if matches:
            errors.append(f"Prohibited content detected: pattern '{pattern}' matched")

    if evidence_packet.adequacy.level.value == "insufficient":
        has_limitation_note = any(
            "insufficient" in s.body.lower() or "limited" in s.body.lower()
            for s in sections
        )
        if not has_limitation_note:
            errors.append("Report does not acknowledge insufficient evidence")

    for kpi in (evidence_packet.analytics.kpis if evidence_packet.analytics else []):
        if kpi.abstained and kpi.abstention_reason:
            reason_mentioned = any(
                kpi.name.replace("_", " ") in s.body.lower()
                or "withheld" in s.body.lower()
                or "insufficient" in s.body.lower()
                for s in sections
            )
            if not reason_mentioned:
                errors.append(f"Abstained KPI '{kpi.name}' not acknowledged in report")

    return errors


class ReportingClient:
    """Generates progress reports using the configured LLM provider."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
    ):
        self._api_key = api_key or settings.anthropic_api_key
        self._model = model or settings.reporting_model

    async def generate_report(
        self, evidence_packet: EvidencePacket
    ) -> GeneratedReportData:
        user_message = json.dumps(evidence_packet.model_dump(mode="json"), indent=2)

        try:
            sections = await self._call_llm(user_message)
        except Exception:
            logger.exception("Report generation LLM call failed")
            sections = self._build_fallback_sections(evidence_packet)

        parsed_sections = self._parse_sections(sections)
        validation_errors = validate_report(parsed_sections, evidence_packet)

        return GeneratedReportData(
            child_id=evidence_packet.child_id,
            review_period_id=evidence_packet.review_period_id,
            sections=parsed_sections,
            generated_at=datetime.now(UTC),
            provider="anthropic",
            model=self._model,
            prompt_version=settings.reporting_prompt_version,
            validation_passed=len(validation_errors) == 0,
            validation_errors=validation_errors,
        )

    async def _call_llm(self, user_message: str) -> list[dict]:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        response = await client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=REPORTING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        text = response.content[0].text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
            raise

    def _parse_sections(self, raw_sections: list[dict]) -> list[ReportSection]:
        sections: list[ReportSection] = []
        for s in raw_sections:
            sections.append(
                ReportSection(
                    heading=s.get("heading", "Untitled Section"),
                    body=s.get("body", ""),
                    evidence_refs=s.get("evidence_refs", []),
                    abstention_note=s.get("abstention_note"),
                )
            )
        return sections

    def _build_fallback_sections(
        self, evidence_packet: EvidencePacket
    ) -> list[dict]:
        sections = [
            {
                "heading": "Review Period Summary",
                "body": (
                    f"Review period: {evidence_packet.review_period_start} to "
                    f"{evidence_packet.review_period_end}. "
                    f"Total observations: {evidence_packet.observation_count}. "
                    f"Evidence level: {evidence_packet.adequacy.level.value}."
                ),
                "evidence_refs": [],
                "abstention_note": None,
            },
            {
                "heading": "Evidence Coverage",
                "body": self._build_coverage_text(evidence_packet),
                "evidence_refs": evidence_packet.record_ids,
                "abstention_note": None,
            },
        ]
        if evidence_packet.adequacy.quality_flags:
            sections.append({
                "heading": "Evidence Limitations",
                "body": "The following limitations were identified: "
                + "; ".join(evidence_packet.adequacy.quality_flags) + ".",
                "evidence_refs": [],
                "abstention_note": None,
            })
        return sections

    @staticmethod
    def _build_coverage_text(ep: EvidencePacket) -> str:
        parts = [f"{ep.observation_count} observations were recorded."]
        if ep.contributor_summary:
            contrib = ", ".join(f"{k}: {v}" for k, v in ep.contributor_summary.items())
            parts.append(f"Contributor breakdown: {contrib}.")
        if ep.setting_summary:
            sett = ", ".join(f"{k}: {v}" for k, v in ep.setting_summary.items())
            parts.append(f"Setting breakdown: {sett}.")
        if ep.abstained_count > 0:
            parts.append(f"{ep.abstained_count} observations were abstained.")
        if ep.review_count > 0:
            parts.append(f"{ep.review_count} observations require interventionist review.")
        return " ".join(parts)
