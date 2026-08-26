import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient, mockFetch } from "./helpers";
import AnalyticsPage from "@/app/children/[childId]/analytics/page";

const CHILD_ID = "00000000-0000-0000-0000-000000000010";
const PERIOD_ID = "rp-111";

const mockPeriods = [
  {
    id: PERIOD_ID,
    child_id: CHILD_ID,
    start_date: "2026-06-01",
    end_date: "2026-07-31",
    is_active: true,
    created_at: "2026-06-01T00:00:00Z",
  },
  {
    id: "rp-222",
    child_id: CHILD_ID,
    start_date: "2026-04-01",
    end_date: "2026-05-31",
    is_active: false,
    created_at: "2026-04-01T00:00:00Z",
  },
];

const mockAnalytics = {
  child_id: CHILD_ID,
  review_period_id: PERIOD_ID,
  goal_id: null,
  kpis: [
    {
      name: "observation_count",
      numerator: 8,
      denominator: 1,
      value: 8,
      abstained: false,
      abstention_reason: null,
      display_eligible: true,
    },
  ],
  adequacy: {
    level: "ADEQUATE",
    eligible: true,
    checks: [
      { check: "coverage", passed: true, detail: "OK", value: 8, threshold: 5 },
    ],
    partial_abstentions: {},
    quality_flags: [],
  },
  computed_at: "2026-08-01T00:00:00Z",
};

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/children/" + CHILD_ID + "/analytics",
  useParams: () => ({ childId: CHILD_ID }),
  useSearchParams: () => new URLSearchParams(),
}));

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AnalyticsPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("AnalyticsPage: review period selector", () => {
  it("displays existing review periods when they exist", async () => {
    mockFetch({
      [`GET /children/${CHILD_ID}/review-periods`]: { body: mockPeriods },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Jun 1, 2026/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Jul 31, 2026/)).toBeInTheDocument();
    expect(screen.getByText(/Apr 1, 2026/)).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("shows empty state when no periods exist", async () => {
    mockFetch({
      [`GET /children/${CHILD_ID}/review-periods`]: { body: [] },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No review periods")).toBeInTheDocument();
    });
    expect(screen.getByText("Create Review Period")).toBeInTheDocument();
  });

  it("selecting a period loads analytics", async () => {
    mockFetch({
      [`GET /children/${CHILD_ID}/review-periods`]: { body: mockPeriods },
      [`POST /children/${CHILD_ID}/analytics`]: { body: mockAnalytics },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Jun 1, 2026/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId(`period-${PERIOD_ID}`));

    await waitFor(() => {
      expect(screen.getByText("Observation count")).toBeInTheDocument();
    });
    expect(screen.getAllByText("ADEQUATE").length).toBeGreaterThanOrEqual(1);
  });

  it("shows Create New Period button alongside existing periods", async () => {
    mockFetch({
      [`GET /children/${CHILD_ID}/review-periods`]: { body: mockPeriods },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Create New Period")).toBeInTheDocument();
    });
  });

  it("create form still works when no periods exist", async () => {
    mockFetch({
      [`GET /children/${CHILD_ID}/review-periods`]: { body: [] },
      [`POST /children/${CHILD_ID}/review-periods`]: {
        status: 201,
        body: mockPeriods[0],
      },
      [`POST /children/${CHILD_ID}/analytics`]: { body: mockAnalytics },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Create Review Period")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Create Review Period"));

    await waitFor(() => {
      expect(screen.getByText("Start Date")).toBeInTheDocument();
    });
    expect(screen.getByText("End Date")).toBeInTheDocument();
    expect(screen.getByText(/Create & Compute/)).toBeInTheDocument();
  });

  it("Change Period returns to selector", async () => {
    mockFetch({
      [`GET /children/${CHILD_ID}/review-periods`]: { body: mockPeriods },
      [`POST /children/${CHILD_ID}/analytics`]: { body: mockAnalytics },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByTestId(`period-${PERIOD_ID}`)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId(`period-${PERIOD_ID}`));

    await waitFor(() => {
      expect(screen.getByText("Change Period")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Change Period"));

    await waitFor(() => {
      expect(screen.getByText(/Jun 1, 2026/)).toBeInTheDocument();
    });
  });
});
