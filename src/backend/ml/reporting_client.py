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


# @spec REPORT-020, REPORT-021, REPORT-022
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
    """Generates progress reports using the configured LLM provider.

    ``provider`` selects the vendor SDK ``_call_llm`` uses ("anthropic" or
    "ollama" -- an OpenAI-compatible endpoint, Ollama by default). The
    method signature and return shape of ``_call_llm`` are identical across
    both, so callers (and tests that patch ``_call_llm`` directly) are
    unaffected by which provider is active.
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        provider: str | None = None,
        base_url: str | None = None,
        mode: str | None = None,
    ):
        self._mode = mode or settings.reporting_mode
        self._provider = provider or settings.reporting_provider
        if self._provider == "ollama":
            self._api_key = api_key or settings.ollama_api_key
            self._model = model or settings.ollama_model
            self._base_url = base_url or settings.ollama_base_url
        else:
            self._api_key = api_key or settings.anthropic_api_key
            self._model = model or settings.reporting_model
            self._base_url = base_url

    # @spec REPORT-001, REPORT-010, REPORT-011, REPORT-012
    #
    # Two modes. "deterministic" is operational: the sections are rendered
    # from the evidence packet in code, so every number in them is a number
    # the analytics engine computed and every withheld analysis is named.
    # "generative_experimental" calls the reporting LLM; in evaluation that
    # layer produced no prohibited content but failed the governance contract
    # on all 11 reports by omitting that an analysis had been withheld, so its
    # output is returned marked experimental and falls back to the
    # deterministic reporter if the call fails.
    async def generate_report(
        self, evidence_packet: EvidencePacket
    ) -> GeneratedReportData:
        used_llm = False
        if self._mode == "generative_experimental":
            user_message = json.dumps(
                evidence_packet.model_dump(mode="json"), indent=2
            )
            try:
                sections = await self._call_llm(user_message)
                used_llm = True
            except Exception:
                logger.exception(
                    "Report generation LLM call failed, using deterministic reporter"
                )
                sections = self._build_deterministic_sections(evidence_packet)
        else:
            sections = self._build_deterministic_sections(evidence_packet)

        parsed_sections = self._parse_sections(sections)
        validation_errors = validate_report(parsed_sections, evidence_packet)

        if used_llm:
            provider = self._provider
            model = self._model
            prompt_version = settings.reporting_prompt_version
        else:
            provider = "deterministic"
            model = "deterministic_reporter_v1"
            prompt_version = "N/A"

        return GeneratedReportData(
            child_id=evidence_packet.child_id,
            review_period_id=evidence_packet.review_period_id,
            sections=parsed_sections,
            generated_at=datetime.now(UTC),
            provider=provider,
            model=model,
            prompt_version=prompt_version,
            validation_passed=len(validation_errors) == 0,
            validation_errors=validation_errors,
            is_experimental=used_llm,
        )

    # Schema the reporting model's output must conform to. Supplying it as a
    # decoding constraint rather than an instruction is the difference between
    # a usable report and prose: asked in the prompt alone, locally served
    # models returned narrative summaries and every generation fell back to the
    # deterministic template. Constrained, the same models produce conformant
    # sections.
    REPORT_SCHEMA: dict = {
        "type": "object",
        "properties": {
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string"},
                        "body": {"type": "string"},
                        "evidence_refs": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "abstention_note": {"type": ["string", "null"]},
                    },
                    "required": ["heading", "body", "evidence_refs"],
                },
            }
        },
        "required": ["sections"],
    }

    async def _call_llm(self, user_message: str) -> list[dict]:
        if self._provider == "ollama":
            text = await self._call_llm_ollama_native(user_message)
        else:
            text = await self._call_llm_anthropic(user_message)

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            json_match = re.search(r"\[.*\]", text, re.DOTALL)
            if not json_match:
                raise
            parsed = json.loads(json_match.group())

        # The schema wraps the sections in an object; an unconstrained model
        # may still return the bare array. Accept both rather than failing on
        # the shape the constraint produces.
        if isinstance(parsed, dict):
            return parsed.get("sections") or []
        return parsed

    async def _call_llm_anthropic(self, user_message: str) -> str:
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        response = await client.messages.create(
            model=self._model,
            max_tokens=4096,
            system=REPORTING_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text

    async def _call_llm_ollama_native(self, user_message: str) -> str:
        """Call Ollama's own /api/chat so the schema constraint is honoured.

        Ollama's OpenAI-compatible /v1 endpoint silently drops `format`, as it
        drops other native options, so the constraint has to go through the
        native API. Falls back to the compatible endpoint if the native one is
        unreachable, which keeps a non-Ollama OpenAI-compatible server working.
        """
        import httpx

        base = self._base_url.rstrip("/")
        native = base[: -len("/v1")] if base.endswith("/v1") else base
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": REPORTING_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "format": self.REPORT_SCHEMA,
            "options": {"num_ctx": settings.reporting_num_ctx},
        }
        try:
            async with httpx.AsyncClient(timeout=settings.reporting_timeout_s) as client:
                response = await client.post(f"{native}/api/chat", json=payload)
                response.raise_for_status()
                return (response.json().get("message") or {}).get("content") or ""
        except Exception:
            logger.warning(
                "Ollama native endpoint unavailable; falling back to the "
                "OpenAI-compatible endpoint, which cannot enforce the schema."
            )
            return await self._call_llm_openai_compatible(user_message)

    async def _call_llm_openai_compatible(self, user_message: str) -> str:
        import openai

        client = openai.AsyncOpenAI(base_url=self._base_url, api_key=self._api_key)
        response = await client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": REPORTING_SYSTEM_PROMPT},
                {"role": "user", "content": user_message},
            ],
        )
        return response.choices[0].message.content

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

    def _build_deterministic_sections(
        self, evidence_packet: EvidencePacket
    ) -> list[dict]:
        ep = evidence_packet
        kpis = self._kpi_lookup(ep)
        sections: list[dict] = []

        sections.append(self._deterministic_summary(ep))
        sections.append(self._deterministic_coverage(ep, kpis))

        key_indicators = self._deterministic_key_indicators(kpis)
        if key_indicators:
            sections.append(key_indicators)

        patterns = self._deterministic_patterns(kpis)
        if patterns:
            sections.append(patterns)

        progress = self._deterministic_progress(kpis)
        if progress:
            sections.append(progress)

        cross = self._deterministic_cross_observations(kpis)
        if cross:
            sections.append(cross)

        sections.append(self._deterministic_limitations(ep, kpis))

        return sections

    @staticmethod
    def _kpi_lookup(ep: EvidencePacket) -> dict[str, KpiResult]:
        if not ep.analytics:
            return {}
        return {k.name: k for k in ep.analytics.kpis}

    @staticmethod
    def _fmt_pct(value: float) -> str:
        return f"{value * 100:.1f}%"

    def _deterministic_summary(self, ep: EvidencePacket) -> dict:
        parts = [
            f"Review period: {ep.review_period_start} to {ep.review_period_end}.",
            f"Total observations: {ep.observation_count}.",
            f"Evidence level: {ep.adequacy.level.value}.",
        ]
        if ep.goals:
            goal_items = []
            for g in ep.goals:
                label = g.get("title", "Untitled")
                domain = g.get("domain")
                if domain:
                    label += f" ({domain})"
                goal_items.append(label)
            parts.append(f"Active goals: {'; '.join(goal_items)}.")
        return {
            "heading": "Review Period Summary",
            "body": " ".join(parts),
            "evidence_refs": [],
            "abstention_note": None,
        }

    def _deterministic_coverage(self, ep: EvidencePacket, kpis: dict) -> dict:
        parts = [f"{ep.observation_count} observations were recorded."]
        if ep.contributor_summary:
            contrib = ", ".join(f"{k}: {v}" for k, v in ep.contributor_summary.items())
            parts.append(f"Contributor breakdown: {contrib}.")
        if ep.setting_summary:
            sett = ", ".join(f"{k}: {v}" for k, v in ep.setting_summary.items())
            parts.append(f"Setting breakdown: {sett}.")
        missing = kpis.get("missing_data_rate")
        if missing and not missing.abstained and missing.value is not None:
            parts.append(
                f"Missing data rate: {self._fmt_pct(missing.value)} "
                f"({int(missing.numerator)} of {int(missing.denominator)} key fields)."
            )
        if ep.abstained_count > 0:
            parts.append(f"{ep.abstained_count} observations were withheld (abstained).")
        if ep.review_count > 0:
            parts.append(f"{ep.review_count} observations require interventionist review.")
        return {
            "heading": "Evidence Coverage",
            "body": " ".join(parts),
            "evidence_refs": ep.record_ids,
            "abstention_note": None,
        }

    def _deterministic_key_indicators(self, kpis: dict) -> dict | None:
        parts: list[str] = []
        abstention_notes: list[str] = []

        indep = kpis.get("independence_rate")
        if indep:
            if indep.abstained:
                abstention_notes.append(
                    f"Independence rate was withheld: {indep.abstention_reason}."
                )
            elif indep.display_eligible and indep.value is not None:
                parts.append(
                    f"Independent responses were recorded in {int(indep.numerator)} of "
                    f"{int(indep.denominator)} observations with applicable prompt data "
                    f"({self._fmt_pct(indep.value)})."
                )

        pos = kpis.get("positive_outcome_rate")
        if pos:
            if pos.abstained:
                abstention_notes.append(
                    f"Positive outcome rate was withheld: {pos.abstention_reason}."
                )
            elif pos.display_eligible and pos.value is not None:
                parts.append(
                    f"Positive outcomes were recorded in {int(pos.numerator)} of "
                    f"{int(pos.denominator)} observations with outcome data "
                    f"({self._fmt_pct(pos.value)})."
                )

        if not parts and not abstention_notes:
            return None
        return {
            "heading": "Key Indicators",
            "body": " ".join(parts + abstention_notes),
            "evidence_refs": [],
            "abstention_note": " ".join(abstention_notes) if abstention_notes else None,
        }

    def _deterministic_patterns(self, kpis: dict) -> dict | None:
        parts: list[str] = []

        for kpi_name, label in [
            ("domain_distribution", "goal domains"),
            ("modality_distribution", "modalities"),
            ("prompt_level_distribution", "prompt levels"),
            ("outcome_distribution", "outcomes"),
        ]:
            kpi = kpis.get(kpi_name)
            if kpi and not kpi.abstained and kpi.display_eligible and kpi.value is not None:
                parts.append(
                    f"Observations covered {int(kpi.value)} distinct {label} "
                    f"across {int(kpi.denominator)} applicable records."
                )

        if not parts:
            return None
        return {
            "heading": "Observed Patterns",
            "body": " ".join(parts),
            "evidence_refs": [],
            "abstention_note": None,
        }

    def _deterministic_progress(self, kpis: dict) -> dict | None:
        parts: list[str] = []
        abstention_notes: list[str] = []

        prompt_trend = kpis.get("prompt_support_trend")
        if prompt_trend:
            if prompt_trend.abstained:
                abstention_notes.append(
                    f"Prompt support trend was withheld: {prompt_trend.abstention_reason}."
                )
            elif prompt_trend.display_eligible and prompt_trend.value is not None:
                direction = "increased" if prompt_trend.value > 0 else (
                    "decreased" if prompt_trend.value < 0 else "remained unchanged"
                )
                parts.append(
                    f"Independence rate {direction} by "
                    f"{abs(prompt_trend.value):.4f} between the first and second halves "
                    f"of the review period."
                )

        outcome_trend = kpis.get("outcome_trend")
        if outcome_trend:
            if outcome_trend.abstained:
                abstention_notes.append(
                    f"Outcome trend was withheld: {outcome_trend.abstention_reason}."
                )
            elif outcome_trend.display_eligible and outcome_trend.value is not None:
                direction = "increased" if outcome_trend.value > 0 else (
                    "decreased" if outcome_trend.value < 0 else "remained unchanged"
                )
                parts.append(
                    f"Positive outcome rate {direction} by "
                    f"{abs(outcome_trend.value):.4f} between the first and second halves "
                    f"of the review period."
                )

        if not parts and not abstention_notes:
            return None
        return {
            "heading": "Progress Indicators",
            "body": " ".join(parts + abstention_notes),
            "evidence_refs": [],
            "abstention_note": " ".join(abstention_notes) if abstention_notes else None,
        }

    def _deterministic_cross_observations(self, kpis: dict) -> dict | None:
        parts: list[str] = []
        abstention_notes: list[str] = []

        cs = kpis.get("cross_setting_comparison")
        if cs:
            if cs.abstained:
                abstention_notes.append(
                    f"Cross-setting comparison was withheld: {cs.abstention_reason}."
                )
            elif cs.display_eligible and cs.value is not None:
                parts.append(
                    f"Observations were recorded across {int(cs.value)} distinct settings "
                    f"({int(cs.denominator)} applicable records)."
                )

        cc = kpis.get("cross_contributor_comparison")
        if cc:
            if cc.abstained:
                abstention_notes.append(
                    f"Cross-contributor comparison was withheld: {cc.abstention_reason}."
                )
            elif cc.display_eligible and cc.value is not None:
                parts.append(
                    f"Observations were provided by {int(cc.value)} distinct contributor roles "
                    f"({int(cc.denominator)} applicable records)."
                )

        if not parts and not abstention_notes:
            return None
        return {
            "heading": "Cross-Setting and Cross-Contributor Observations",
            "body": " ".join(parts + abstention_notes),
            "evidence_refs": [],
            "abstention_note": " ".join(abstention_notes) if abstention_notes else None,
        }

    def _deterministic_limitations(self, ep: EvidencePacket, kpis: dict) -> dict:
        parts: list[str] = []

        if ep.adequacy.quality_flags:
            parts.append(
                "The following limitations were identified: "
                + "; ".join(ep.adequacy.quality_flags) + "."
            )

        abstained_kpis = [
            k for k in kpis.values()
            if k.abstained and k.abstention_reason and k.name != "all_analytics"
        ]
        if abstained_kpis:
            items = [f"{k.name.replace('_', ' ')}: {k.abstention_reason}" for k in abstained_kpis]
            parts.append("Withheld indicators: " + "; ".join(items) + ".")

        missing = kpis.get("missing_data_rate")
        if missing and not missing.abstained and missing.value is not None and missing.value > 0:
            parts.append(
                f"{self._fmt_pct(missing.value)} of key data fields were missing or unknown."
            )

        if ep.adequacy.level.value in ("limited", "insufficient"):
            parts.append(
                f"Overall evidence level was assessed as {ep.adequacy.level.value}."
            )

        if not parts:
            parts.append("No significant evidence limitations were identified for this review period.")

        return {
            "heading": "Evidence Limitations",
            "body": " ".join(parts),
            "evidence_refs": [],
            "abstention_note": None,
        }
