import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider, useAuth, RequireAuth } from "@/lib/auth";
import { createQueryClient, mockFetch } from "./helpers";

function AuthStatus() {
  const { user, isLoading } = useAuth();
  if (isLoading) return <div>loading</div>;
  if (!user) return <div>logged-out</div>;
  return <div>logged-in as {user.email}</div>;
}

function LoginButton() {
  const { login } = useAuth();
  return (
    <button onClick={() => login("test@test.com", "pass")}>Login</button>
  );
}

function LogoutButton() {
  const { logout } = useAuth();
  return <button onClick={() => logout()}>Logout</button>;
}

function Wrapper({ children }: { children: React.ReactNode }) {
  return (
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("Authentication", () => {
  it("shows logged-out state when no token exists", async () => {
    mockFetch({});
    render(<AuthStatus />, { wrapper: Wrapper });
    await waitFor(() => {
      expect(screen.getByText("logged-out")).toBeInTheDocument();
    });
  });

  it("logs in successfully and stores token", async () => {
    mockFetch({
      "POST /auth/login": {
        body: { access_token: "tok123" },
      },
      "GET /auth/me": {
        body: {
          id: "u1",
          email: "test@test.com",
          full_name: "Test",
          role: "interventionist",
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
        },
      },
    });

    render(
      <>
        <AuthStatus />
        <LoginButton />
      </>,
      { wrapper: Wrapper },
    );

    await waitFor(() => {
      expect(screen.getByText("logged-out")).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText("Login"));

    await waitFor(() => {
      expect(screen.getByText("logged-in as test@test.com")).toBeInTheDocument();
    });
    expect(localStorage.setItem).toHaveBeenCalledWith("auth_token", "tok123");
  });

  it("clears session on logout", async () => {
    mockFetch({
      "POST /auth/login": { body: { access_token: "tok" } },
      "GET /auth/me": {
        body: {
          id: "u1",
          email: "t@t.com",
          full_name: "T",
          role: "parent",
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
        },
      },
    });

    render(
      <>
        <AuthStatus />
        <LoginButton />
        <LogoutButton />
      </>,
      { wrapper: Wrapper },
    );

    await waitFor(() => expect(screen.getByText("logged-out")).toBeInTheDocument());
    fireEvent.click(screen.getByText("Login"));
    await waitFor(() => expect(screen.getByText(/logged-in/)).toBeInTheDocument());

    fireEvent.click(screen.getByText("Logout"));
    await waitFor(() => expect(screen.getByText("logged-out")).toBeInTheDocument());
    expect(localStorage.removeItem).toHaveBeenCalledWith("auth_token");
  });

  it("RequireAuth renders children when authenticated", async () => {
    mockFetch({
      "POST /auth/login": { body: { access_token: "tok" } },
      "GET /auth/me": {
        body: {
          id: "u1",
          email: "t@t.com",
          full_name: "T",
          role: "interventionist",
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
        },
      },
    });

    render(
      <>
        <LoginButton />
        <RequireAuth>
          <div>protected-content</div>
        </RequireAuth>
      </>,
      { wrapper: Wrapper },
    );

    await waitFor(() => expect(screen.queryByText("protected-content")).not.toBeInTheDocument());

    fireEvent.click(screen.getByText("Login"));
    await waitFor(() => expect(screen.getByText("protected-content")).toBeInTheDocument());
  });
});
