import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StructuredRecordView } from "@/components/records/StructuredRecordView";
import type { StructuredRecord } from "@/lib/types";

const baseRecord: StructuredRecord = {
  id: "sr1",
  observation_id: "obs1",
  version: 1,
  status: "validated",
  record_data: {
    domain: "social_communication",
    behavior: "Initiated greeting",
    outcome: "success",
    prompt_level: "independent",
  },
  validation_result: { passed: true, errors: [] },
  corrected_by: null,
  correction_reason: null,
  verified_by: null,
  verified_at: null,
  provider: "temporary_llm",
  model: "claude-3-5-sonnet",
  prompt_version: "1.0",
  created_at: "2026-06-15T00:00:00Z",
};

describe("StructuredRecordView", () => {
  it("renders AI-derived label", () => {
    render(<StructuredRecordView record={baseRecord} />);
    expect(screen.getByText(/AI-derived/)).toBeInTheDocument();
  });

  it("says a validated record is excluded from analytics", () => {
    // Validated means schema-conformant and unseen. The badge and the label
    // must not let it read as settled.
    render(<StructuredRecordView record={baseRecord} />);
    expect(
      screen.getByText(/excluded from longitudinal analytics/),
    ).toBeInTheDocument();
  });

  it("shows verification provenance once verified", () => {
    const verified: StructuredRecord = {
      ...baseRecord,
      status: "verified",
      verified_by: "user-9",
      verified_at: "2026-06-16T00:00:00Z",
    };
    render(<StructuredRecordView record={verified} />);
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByText(/Verified by: user-9/)).toBeInTheDocument();
    expect(
      screen.getByText(/included in longitudinal analytics/),
    ).toBeInTheDocument();
  });

  it("renders version badge", () => {
    render(<StructuredRecordView record={baseRecord} />);
    expect(screen.getByText("v1")).toBeInTheDocument();
  });

  it("renders status badge", () => {
    render(<StructuredRecordView record={baseRecord} />);
    expect(screen.getByText("Validated")).toBeInTheDocument();
  });

  it("renders record data fields", () => {
    render(<StructuredRecordView record={baseRecord} />);
    expect(screen.getByText("Domain")).toBeInTheDocument();
    expect(screen.getByText("social_communication")).toBeInTheDocument();
    expect(screen.getByText("Behavior")).toBeInTheDocument();
    expect(screen.getByText("Initiated greeting")).toBeInTheDocument();
  });

  it("renders provenance metadata", () => {
    render(<StructuredRecordView record={baseRecord} />);
    expect(screen.getByText(/Provider: temporary_llm/)).toBeInTheDocument();
    expect(screen.getByText(/Model: claude-3-5-sonnet/)).toBeInTheDocument();
  });

  it("shows correction info when corrected", () => {
    const corrected: StructuredRecord = {
      ...baseRecord,
      version: 2,
      status: "corrected",
      corrected_by: "user-1",
      correction_reason: "Wrong domain",
    };
    render(<StructuredRecordView record={corrected} />);
    expect(screen.getByText("Corrected")).toBeInTheDocument();
    expect(screen.getByText("v2")).toBeInTheDocument();
    expect(screen.getByText(/Corrected by: user-1/)).toBeInTheDocument();
    expect(screen.getByText(/Reason: Wrong domain/)).toBeInTheDocument();
    expect(
      screen.getByText(/included in longitudinal analytics/),
    ).toBeInTheDocument();
  });

  it("shows validation result", () => {
    render(<StructuredRecordView record={baseRecord} />);
    expect(screen.getByText("Validation Result")).toBeInTheDocument();
  });

  it("renders rejected status correctly", () => {
    const rejected: StructuredRecord = {
      ...baseRecord,
      status: "rejected",
    };
    render(<StructuredRecordView record={rejected} />);
    expect(screen.getByText("Rejected")).toBeInTheDocument();
  });
});
