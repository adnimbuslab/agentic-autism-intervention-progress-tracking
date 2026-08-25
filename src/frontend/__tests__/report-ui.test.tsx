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
  provider: "temporary_llm",
  model: "claude-3-5-sonnet",
  prompt_version: "1.0",
  version: 1,
  validation_passed: true,
  validation_errors: null,
  flagged: false,
  flagged_reason: null,
  flagged_by: null,
  generated_at: "2026-06-15T00:00:00Z",
};

describe("ReportViewer", () => {
  it("shows AI-generated draft banner", () => {
    render(<ReportViewer report={baseReport} />);
    expect(screen.getByText(/AI-Generated Draft/)).toBeInTheDocument();
    expect(screen.getByText(/interventionist review/)).toBeInTheDocument();
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

  it("shows provenance metadata", () => {
    render(<ReportViewer report={baseReport} />);
    expect(screen.getByText("temporary_llm")).toBeInTheDocument();
    expect(screen.getByText("claude-3-5-sonnet")).toBeInTheDocument();
    expect(screen.getByText("1.0")).toBeInTheDocument();
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
