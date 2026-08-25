import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient, mockFetch } from "./helpers";
import { LoadingState } from "@/components/common/LoadingState";
import { ErrorState } from "@/components/common/ErrorState";
import { EmptyState } from "@/components/common/EmptyState";
import { ConfirmDialog } from "@/components/common/ConfirmDialog";

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("Resilience: loading states", () => {
  it("LoadingState renders with spinner", () => {
    render(<LoadingState />);
    expect(screen.getAllByRole("status").length).toBeGreaterThanOrEqual(1);
  });

  it("LoadingState renders with custom message", () => {
    render(<LoadingState message="Computing analytics..." />);
    expect(screen.getByText("Computing analytics...")).toBeInTheDocument();
  });
});

describe("Resilience: error states", () => {
  it("ErrorState renders error message from object", () => {
    render(<ErrorState error={{ message: "Not authorized" }} />);
    expect(screen.getByText("Not authorized")).toBeInTheDocument();
  });

  it("ErrorState renders fallback for non-object errors", () => {
    render(<ErrorState error="string error" />);
    expect(screen.getByText("An unexpected error occurred.")).toBeInTheDocument();
  });

  it("ErrorState renders retry button", () => {
    const retry = vi.fn();
    render(<ErrorState error={{ message: "Fail" }} onRetry={retry} />);
    expect(screen.getByText("Retry")).toBeInTheDocument();
  });
});

describe("Resilience: empty states", () => {
  it("EmptyState renders title and description", () => {
    render(<EmptyState title="No data" description="Start adding" />);
    expect(screen.getByText("No data")).toBeInTheDocument();
    expect(screen.getByText("Start adding")).toBeInTheDocument();
  });
});

describe("Resilience: HTTP status handling", () => {
  it("handles 401 by clearing session", async () => {
    mockFetch({
      "GET /auth/me": { status: 401, body: { detail: "Unauthorized" } },
    });

    const originalHref = window.location.href;
    Object.defineProperty(window, "location", {
      value: { ...window.location, href: originalHref },
      writable: true,
    });

    const { api } = await import("@/lib/api");
    try {
      await api.get("/auth/me");
    } catch (e) {
      expect((e as any).status).toBe(401);
    }
    expect(localStorage.removeItem).toHaveBeenCalledWith("auth_token");
  });

  it("handles 403 as ApiError", async () => {
    mockFetch({
      "GET /forbidden": { status: 403, body: { detail: "Forbidden" } },
    });

    const { api, ApiError } = await import("@/lib/api");
    await expect(api.get("/forbidden")).rejects.toThrow(ApiError);
  });

  it("handles 404 as ApiError", async () => {
    mockFetch({});
    const { api, ApiError } = await import("@/lib/api");
    await expect(api.get("/not-found")).rejects.toThrow(ApiError);
  });

  it("handles 422 as ApiError", async () => {
    mockFetch({
      "POST /validate": { status: 422, body: { detail: "Validation" } },
    });

    const { api, ApiError } = await import("@/lib/api");
    await expect(api.post("/validate", {})).rejects.toThrow(ApiError);
  });

  it("handles 500 as ApiError", async () => {
    mockFetch({
      "GET /server-error": { status: 500, body: { detail: "Internal" } },
    });

    const { api, ApiError } = await import("@/lib/api");
    await expect(api.get("/server-error")).rejects.toThrow(ApiError);
  });
});

describe("Resilience: confirm dialog", () => {
  it("renders when open", () => {
    render(
      <ConfirmDialog
        open={true}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        title="Delete?"
        message="This is permanent."
      />,
    );
    expect(screen.getByText("Delete?")).toBeInTheDocument();
    expect(screen.getByText("This is permanent.")).toBeInTheDocument();
  });

  it("does not render when closed", () => {
    render(
      <ConfirmDialog
        open={false}
        onClose={vi.fn()}
        onConfirm={vi.fn()}
        title="Delete?"
        message="This is permanent."
      />,
    );
    expect(screen.queryByText("Delete?")).not.toBeInTheDocument();
  });
});
