import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient, mockFetch } from "./helpers";
import ReportsPage from "@/app/children/[childId]/reports/page";

const CHILD_ID = "00000000-0000-0000-0000-000000000010";
const PERIOD_ID = "rp-aaa";
const PERIOD_ID_2 = "rp-bbb";

const mockPeriods = [
  {
    id: PERIOD_ID,
    child_id: CHILD_ID,
    start_date: "2026-06-27",
    end_date: "2026-08-26",
    is_active: true,
    created_at: "2026-06-27T00:00:00Z",
  },
  {
    id: PERIOD_ID_2,
    child_id: CHILD_ID,
    start_date: "2026-03-01",
    end_date: "2026-05-31",
    is_active: false,
    created_at: "2026-03-01T00:00:00Z",
  },
];

const mockReportResponse = {
  id: "report-1",
  child_id: CHILD_ID,
  review_period_id: PERIOD_ID,
  sections: [{ heading: "Summary", body: "Test.", evidence_refs: [], abstention_note: null }],
  provider: "temporary_llm",
  model: "claude-sonnet-4-20250514",
  prompt_version: "1.0",
  version: 1,
  validation_passed: true,
  validation_errors: null,
  flagged: false,
  flagged_reason: null,
  flagged_by: null,
  generated_at: "2026-08-01T00:00:00Z",
};

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), back: vi.fn(), prefetch: vi.fn() }),
  usePathname: () => "/children/" + CHILD_ID + "/reports",
  useParams: () => ({ childId: CHILD_ID }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/link", () => ({
  __esModule: true,
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

function renderPage() {
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <ReportsPage />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("ReportsPage: review period selector", () => {
  it("displays existing review periods as human-readable date ranges", async () => {
    mockFetch({
      [`GET /children/${CHILD_ID}/reports`]: { body: [] },
      [`GET /children/${CHILD_ID}/review-periods`]: { body: mockPeriods },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Generate Report")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Generate Report"));

    await waitFor(() => {
      expect(screen.getByText(/Jun 27, 2026/)).toBeInTheDocument();
    });
    expect(screen.getByText(/Aug 26, 2026/)).toBeInTheDocument();
    expect(screen.getByText(/Mar 1, 2026/)).toBeInTheDocument();
    expect(screen.getByText(/May 31, 2026/)).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Inactive")).toBeInTheDocument();
  });

  it("does not show a raw UUID input field", async () => {
    mockFetch({
      [`GET /children/${CHILD_ID}/reports`]: { body: [] },
      [`GET /children/${CHILD_ID}/review-periods`]: { body: mockPeriods },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Generate Report")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Generate Report"));

    await waitFor(() => {
      expect(screen.getByText(/Jun 27, 2026/)).toBeInTheDocument();
    });

    expect(screen.queryByLabelText("Review Period ID")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Enter review period ID")).not.toBeInTheDocument();
  });

  it("selecting a period enables the Generate button", async () => {
    mockFetch({
      [`GET /children/${CHILD_ID}/reports`]: { body: [] },
      [`GET /children/${CHILD_ID}/review-periods`]: { body: mockPeriods },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Generate Report")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Generate Report"));

    await waitFor(() => {
      expect(screen.getByTestId(`report-period-${PERIOD_ID}`)).toBeInTheDocument();
    });

    const generateBtn = screen.getByText("Generate");
    expect(generateBtn).toBeDisabled();

    fireEvent.click(screen.getByTestId(`report-period-${PERIOD_ID}`));

    expect(generateBtn).not.toBeDisabled();
  });

  it("passes the selected period id to the generate-report mutation", async () => {
    const fetchMock = mockFetch({
      [`GET /children/${CHILD_ID}/reports`]: { body: [] },
      [`GET /children/${CHILD_ID}/review-periods`]: { body: mockPeriods },
      [`POST /children/${CHILD_ID}/reports/generate`]: { status: 201, body: mockReportResponse },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Generate Report")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Generate Report"));

    await waitFor(() => {
      expect(screen.getByTestId(`report-period-${PERIOD_ID}`)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByTestId(`report-period-${PERIOD_ID}`));
    fireEvent.click(screen.getByText("Generate"));

    await waitFor(() => {
      const postCall = fetchMock.mock.calls.find(
        ([url, init]: [string, RequestInit | undefined]) =>
          url.includes("/reports/generate") && init?.method === "POST",
      );
      expect(postCall).toBeDefined();
      const body = JSON.parse(postCall![1]!.body as string);
      expect(body.review_period_id).toBe(PERIOD_ID);
    });
  });

  it("shows message directing to Analytics when no periods exist", async () => {
    mockFetch({
      [`GET /children/${CHILD_ID}/reports`]: { body: [] },
      [`GET /children/${CHILD_ID}/review-periods`]: { body: [] },
    });
    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Generate Report")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Generate Report"));

    await waitFor(() => {
      expect(screen.getByTestId("no-periods-message")).toBeInTheDocument();
    });
    expect(screen.getByText("Analytics")).toBeInTheDocument();
    expect(screen.getByText(/No review periods available/)).toBeInTheDocument();
  });
});
