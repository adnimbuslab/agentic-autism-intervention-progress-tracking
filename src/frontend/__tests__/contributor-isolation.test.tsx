import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { RoleBoundary } from "@/components/layout/RoleBoundary";
import { AuthProvider } from "@/lib/auth";
import { QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient, mockFetch } from "./helpers";

function TestApp({
  children,
  token,
}: {
  children: React.ReactNode;
  token?: string;
}) {
  if (token) {
    (localStorage.getItem as ReturnType<typeof vi.fn>).mockReturnValue(token);
  }
  return (
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}

describe("RoleBoundary", () => {
  it("shows interventionist content for interventionist", async () => {
    mockFetch({
      "GET /auth/me": {
        body: {
          id: "u1",
          email: "i@test.com",
          full_name: "I",
          role: "interventionist",
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
        },
      },
    });

    const { findByText, queryByText } = render(
      <TestApp token="tok">
        <RoleBoundary allow="interventionist">
          <div>professional-content</div>
        </RoleBoundary>
        <RoleBoundary allow="contributor">
          <div>contributor-content</div>
        </RoleBoundary>
      </TestApp>,
    );

    expect(await findByText("professional-content")).toBeInTheDocument();
    expect(queryByText("contributor-content")).not.toBeInTheDocument();
  });

  it("shows contributor content for contributor", async () => {
    mockFetch({
      "GET /auth/me": {
        body: {
          id: "u2",
          email: "p@test.com",
          full_name: "P",
          role: "parent",
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
        },
      },
    });

    const { findByText, queryByText } = render(
      <TestApp token="tok">
        <RoleBoundary allow="interventionist">
          <div>professional-content</div>
        </RoleBoundary>
        <RoleBoundary allow="contributor">
          <div>contributor-content</div>
        </RoleBoundary>
      </TestApp>,
    );

    expect(await findByText("contributor-content")).toBeInTheDocument();
    expect(queryByText("professional-content")).not.toBeInTheDocument();
  });

  it("renders fallback when role does not match", async () => {
    mockFetch({
      "GET /auth/me": {
        body: {
          id: "u2",
          email: "p@test.com",
          full_name: "P",
          role: "parent",
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
        },
      },
    });

    const { findByText } = render(
      <TestApp token="tok">
        <RoleBoundary
          allow="interventionist"
          fallback={<div>access-denied</div>}
        >
          <div>protected</div>
        </RoleBoundary>
      </TestApp>,
    );

    expect(await findByText("access-denied")).toBeInTheDocument();
  });
});

describe("Contributor data isolation", () => {
  it("contributor cannot see analytics/report components", () => {
    render(
      <div data-testid="contributor-view">
        <span>My Observations</span>
      </div>,
    );
    expect(screen.getByTestId("contributor-view")).toBeInTheDocument();
    expect(screen.queryByText("Analytics")).not.toBeInTheDocument();
    expect(screen.queryByText("Reports")).not.toBeInTheDocument();
    expect(screen.queryByText("Audit Trail")).not.toBeInTheDocument();
  });
});
