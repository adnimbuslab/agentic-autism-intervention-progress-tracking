import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { GoalCard } from "@/components/goals/GoalCard";
import { GoalForm } from "@/components/goals/GoalForm";
import type { Goal } from "@/lib/types";

const baseGoal: Goal = {
  id: "g1",
  child_id: "c1",
  goal_type: "short_term",
  domain: "social_communication",
  title: "Initiate greetings",
  description: "Child will greet peers independently",
  criteria: null,
  parent_goal_id: null,
  is_active: true,
  start_date: null,
  target_date: "2026-09-01",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("GoalCard", () => {
  it("renders goal title and description", () => {
    render(<GoalCard goal={baseGoal} />);
    expect(screen.getByText("Initiate greetings")).toBeInTheDocument();
    expect(screen.getByText("Child will greet peers independently")).toBeInTheDocument();
  });

  it("renders domain badge", () => {
    render(<GoalCard goal={baseGoal} />);
    expect(screen.getByText("Social communication")).toBeInTheDocument();
  });

  it("renders active badge", () => {
    render(<GoalCard goal={baseGoal} />);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("renders inactive badge", () => {
    render(<GoalCard goal={{ ...baseGoal, is_active: false }} />);
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("renders target date", () => {
    render(<GoalCard goal={baseGoal} />);
    expect(screen.getByText(/Target/)).toBeInTheDocument();
  });
});

describe("GoalForm", () => {
  it("renders form fields", () => {
    render(<GoalForm onSubmit={vi.fn()} />);
    expect(screen.getByLabelText("Goal Title")).toBeInTheDocument();
    expect(screen.getByLabelText("Domain")).toBeInTheDocument();
    expect(screen.getByLabelText("Type")).toBeInTheDocument();
    expect(screen.getByLabelText("Description")).toBeInTheDocument();
  });

  it("submits with entered data", async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(<GoalForm onSubmit={onSubmit} />);

    fireEvent.change(screen.getByLabelText("Goal Title"), {
      target: { value: "New Goal" },
    });
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Test description" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create Goal" }));

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          title: "New Goal",
          description: "Test description",
          domain: "social_communication",
          goal_type: "short_term",
        }),
      );
    });
  });

  it("shows loading state", () => {
    render(<GoalForm onSubmit={vi.fn()} loading />);
    const btn = screen.getByRole("button", { name: /Create Goal/i });
    expect(btn).toBeDisabled();
  });
});
