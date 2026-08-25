import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { AdequacyBanner } from "@/components/analytics/AdequacyBanner";
import { KpiCard } from "@/components/analytics/KpiCard";
import { DataQualityPanel } from "@/components/analytics/DataQualityPanel";
import type { AdequacyResponse, KpiResult, AnalyticsResponse } from "@/lib/types";

const adequateResult: AdequacyResponse = {
  level: "ADEQUATE",
  eligible: true,
  checks: [
    { check: "record_count", passed: true, detail: "OK", value: 10, threshold: 5 },
    { check: "temporal", passed: true, detail: "OK", value: 3, threshold: 2 },
  ],
  partial_abstentions: {},
  quality_flags: [],
};

const limitedResult: AdequacyResponse = {
  level: "LIMITED",
  eligible: true,
  checks: [
    { check: "record_count", passed: true, detail: "OK", value: 6, threshold: 5 },
    { check: "setting_diversity", passed: false, detail: "Only 1 setting", value: 1, threshold: 2 },
  ],
  partial_abstentions: {},
  quality_flags: ["Low setting diversity"],
};

const insufficientResult: AdequacyResponse = {
  level: "INSUFFICIENT",
  eligible: false,
  checks: [
    { check: "record_count", passed: false, detail: "Only 2 records", value: 2, threshold: 5 },
  ],
  partial_abstentions: {},
  quality_flags: [],
};

describe("AdequacyBanner", () => {
  it("renders ADEQUATE with green styling", () => {
    render(<AdequacyBanner adequacy={adequateResult} />);
    expect(screen.getByText("ADEQUATE")).toBeInTheDocument();
    const banner = screen.getByRole("status");
    expect(banner.className).toContain("border-green-200");
  });

  it("renders LIMITED with failed checks listed", () => {
    render(<AdequacyBanner adequacy={limitedResult} />);
    expect(screen.getByText("LIMITED")).toBeInTheDocument();
    expect(screen.getByText(/setting_diversity/)).toBeInTheDocument();
    expect(screen.getByText(/Only 1 setting/)).toBeInTheDocument();
  });

  it("renders INSUFFICIENT with warning message", () => {
    render(<AdequacyBanner adequacy={insufficientResult} />);
    expect(screen.getByText("INSUFFICIENT")).toBeInTheDocument();
    expect(screen.getByText(/withheld/)).toBeInTheDocument();
  });
});

describe("KpiCard", () => {
  it("renders computed KPI with value", () => {
    const kpi: KpiResult = {
      name: "behavior_rate",
      numerator: 8,
      denominator: 10,
      value: 0.8,
      abstained: false,
      abstention_reason: null,
      display_eligible: true,
    };
    render(<KpiCard kpi={kpi} />);
    expect(screen.getByText("Behavior rate")).toBeInTheDocument();
    expect(screen.getByText("80.0%")).toBeInTheDocument();
    expect(screen.getByText("8 / 10")).toBeInTheDocument();
  });

  it("renders abstained KPI with reason", () => {
    const kpi: KpiResult = {
      name: "independence_rate",
      numerator: 0,
      denominator: 0,
      value: null,
      abstained: true,
      abstention_reason: "No records with outcome data",
      display_eligible: false,
    };
    render(<KpiCard kpi={kpi} />);
    expect(screen.getByText("Independence rate")).toBeInTheDocument();
    expect(screen.getByText("Withheld")).toBeInTheDocument();
    expect(screen.getByText("No records with outcome data")).toBeInTheDocument();
  });

  it("renders abstained KPI with default reason", () => {
    const kpi: KpiResult = {
      name: "prompt_distribution",
      numerator: 0,
      denominator: 0,
      value: null,
      abstained: true,
      abstention_reason: null,
      display_eligible: false,
    };
    render(<KpiCard kpi={kpi} />);
    expect(screen.getByText("Withheld")).toBeInTheDocument();
    expect(screen.getByText(/Insufficient data/)).toBeInTheDocument();
  });
});

describe("DataQualityPanel", () => {
  it("renders quality summary", () => {
    const analytics: AnalyticsResponse = {
      child_id: "c1",
      review_period_id: "rp1",
      goal_id: null,
      kpis: [
        { name: "k1", numerator: 1, denominator: 2, value: 0.5, abstained: false, abstention_reason: null, display_eligible: true },
        { name: "k2", numerator: 0, denominator: 0, value: null, abstained: true, abstention_reason: "N/A", display_eligible: false },
      ],
      adequacy: adequateResult,
      computed_at: "2026-06-15T00:00:00Z",
    };
    render(<DataQualityPanel analytics={analytics} />);
    expect(screen.getByText("Data Quality Summary")).toBeInTheDocument();
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
    expect(screen.getByText("ADEQUATE")).toBeInTheDocument();
  });

  it("renders quality flags when present", () => {
    const analytics: AnalyticsResponse = {
      child_id: "c1",
      review_period_id: "rp1",
      goal_id: null,
      kpis: [],
      adequacy: limitedResult,
      computed_at: "2026-06-15T00:00:00Z",
    };
    render(<DataQualityPanel analytics={analytics} />);
    expect(screen.getByText("Low setting diversity")).toBeInTheDocument();
  });
});
