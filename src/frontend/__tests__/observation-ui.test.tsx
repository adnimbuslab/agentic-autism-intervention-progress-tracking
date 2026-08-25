import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { ObservationCard } from "@/components/observations/ObservationCard";
import type { Observation } from "@/lib/types";
import { renderWithProviders } from "./helpers";

const baseObs: Observation = {
  id: "obs-1",
  child_id: "c1",
  submitted_by: "u1",
  raw_text: "The child greeted the teacher independently this morning at circle time.",
  source_type: "conversational",
  setting: "school",
  status: "finalized",
  submitted_at: "2026-06-15T10:00:00Z",
  finalized_at: "2026-06-15T10:05:00Z",
};

describe("ObservationCard", () => {
  it("renders observation text", () => {
    renderWithProviders(
      <ObservationCard observation={baseObs} childId="c1" />,
    );
    expect(
      screen.getByText(/The child greeted the teacher/),
    ).toBeInTheDocument();
  });

  it("renders status badge", () => {
    renderWithProviders(
      <ObservationCard observation={baseObs} childId="c1" />,
    );
    expect(screen.getByText("Finalized")).toBeInTheDocument();
  });

  it("renders setting", () => {
    renderWithProviders(
      <ObservationCard observation={baseObs} childId="c1" />,
    );
    expect(screen.getByText("School")).toBeInTheDocument();
  });

  it("renders failed status", () => {
    const failed: Observation = { ...baseObs, status: "failed" };
    renderWithProviders(
      <ObservationCard observation={failed} childId="c1" />,
    );
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("renders clarifying status", () => {
    const clarifying: Observation = { ...baseObs, status: "clarifying" };
    renderWithProviders(
      <ObservationCard observation={clarifying} childId="c1" />,
    );
    expect(screen.getByText("Clarifying")).toBeInTheDocument();
  });

  it("truncates long observation text", () => {
    const longObs: Observation = {
      ...baseObs,
      raw_text: "A".repeat(200),
    };
    renderWithProviders(
      <ObservationCard observation={longObs} childId="c1" />,
    );
    const text = screen.getByText(/^A+/);
    expect(text.textContent!.length).toBeLessThan(200);
  });
});
