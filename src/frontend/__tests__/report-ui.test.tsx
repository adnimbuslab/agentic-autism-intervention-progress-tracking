import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReportViewer } from "@/components/reports/ReportViewer";
import type { ReportResponse } from "@/lib/types";

const baseReport: ReportResponse = {
  id: "r1",
  child_id: "c1",
  review_period_id: "rp1",
  sections: [
    {
      heading: "Summary",
      body: "The child showed progress.",
      evidence_refs: ["rec-1", "rec-2"],
      abstention_note: null,
    },
    {
      heading: "Limitations",
      body: "Setting diversity was low.",
      evidence_refs: [],
      abstention_note: "Some KPIs were withheld due to insufficient data.",
    },
  ],
  provider: "anthropic",
  model: "claude-sonnet-4-20250514",
  prompt_version: "1.0",
  version: 1,
  validation_passed: true,
  validation_errors: null,
  flagged: false,
  flagged_reason: null,
  flagged_by: null,
  generated_at: "2026-06-15T00:00:00Z",
  is_experimental: true,
};

const deterministicReport: ReportResponse = {
  ...baseReport,
  id: "r2",
  provider: "deterministic",
  model: "deterministic_reporter_v1",
  prompt_version: "N/A",
  is_experimental: false,
};

describe("ReportViewer", () => {
  it("labels an LLM report experimental, not merely AI-drafted", () => {
    // The generative layer failed its governance contract, so the banner has
    // to say the report is not operational -- "AI-generated" alone reads as a
    // routine provenance note.
    render(<ReportViewer report={baseReport} />);
    expect(screen.getByText(/Experimental AI Draft/)).toBeInTheDocument();
    expect(screen.getByText(/not an operational report/)).toBeInTheDocument();
  });

  it("shows deterministic banner for deterministic reports", () => {
    render(<ReportViewer report={deterministicReport} />);
    expect(screen.getByText(/Deterministic Evidence Summary/)).toBeInTheDocument();
    expect(screen.getByText(/no language model involved/)).toBeInTheDocument();
    expect(screen.getByText(/Interventionist review is still required/)).toBeInTheDocument();
  });

  it("does not show the experimental banner for deterministic reports", () => {
    render(<ReportViewer report={deterministicReport} />);
    expect(screen.queryByText(/Experimental AI Draft/)).not.toBeInTheDocument();
  });

  it("does not show deterministic banner for LLM reports", () => {
    render(<ReportViewer report={baseReport} />);
    expect(screen.queryByText(/Deterministic Evidence Summary/)).not.toBeInTheDocument();
  });

  it("renders all sections with headings", () => {
    render(<ReportViewer report={baseReport} />);
    expect(screen.getByText("Summary")).toBeInTheDocument();
    expect(screen.getByText("Limitations")).toBeInTheDocument();
    expect(screen.getByText("The child showed progress.")).toBeInTheDocument();
  });

  it("shows evidence reference count", () => {
    render(<ReportViewer report={baseReport} />);
    expect(screen.getByText(/2 source/)).toBeInTheDocument();
  });

  it("shows abstention notes when present", () => {
    render(<ReportViewer report={baseReport} />);
    expect(screen.getByText(/KPIs were withheld/)).toBeInTheDocument();
  });

  it("shows provenance metadata for LLM report", () => {
    render(<ReportViewer report={baseReport} />);
    expect(screen.getByText("anthropic")).toBeInTheDocument();
    expect(screen.getByText("claude-sonnet-4-20250514")).toBeInTheDocument();
    expect(screen.getByText("1.0")).toBeInTheDocument();
  });

  it("shows provenance metadata for deterministic report", () => {
    render(<ReportViewer report={deterministicReport} />);
    expect(screen.getByText("deterministic")).toBeInTheDocument();
    expect(screen.getByText("deterministic_reporter_v1")).toBeInTheDocument();
    expect(screen.getByText("N/A")).toBeInTheDocument();
  });

  it("shows validation status", () => {
    render(<ReportViewer report={baseReport} />);
    expect(screen.getByText("Passed")).toBeInTheDocument();
  });

  it("shows flagged badge when report is flagged", () => {
    const flagged: ReportResponse = {
      ...baseReport,
      flagged: true,
      flagged_reason: "Inaccurate numbers",
    };
    render(<ReportViewer report={flagged} />);
    expect(screen.getByText("Flagged")).toBeInTheDocument();
    expect(screen.getByText("Inaccurate numbers")).toBeInTheDocument();
  });

  it("shows version badge", () => {
    render(<ReportViewer report={baseReport} />);
    expect(screen.getByText("v1")).toBeInTheDocument();
  });
});
