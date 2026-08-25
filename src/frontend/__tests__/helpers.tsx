import React from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { User, Role } from "@/lib/types";

export function createUser(overrides: Partial<User> & { role: Role }): User {
  return {
    id: "user-1",
    email: "test@example.com",
    full_name: "Test User",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

export const interventionist = createUser({ role: "interventionist" });
export const contributor = createUser({
  id: "user-2",
  email: "parent@example.com",
  role: "parent",
});

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

export function renderWithProviders(
  ui: React.ReactElement,
  options?: RenderOptions & { queryClient?: QueryClient },
) {
  const queryClient = options?.queryClient ?? createQueryClient();
  function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  }
  return { ...render(ui, { wrapper: Wrapper, ...options }), queryClient };
}

export const mockFetch = (
  responses: Record<string, { status?: number; body: unknown }>,
) => {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const path = url.replace(/^https?:\/\/[^/]+/, "");
    const method = init?.method ?? "GET";
    const key = `${method} ${path}`;

    const match =
      responses[key] ??
      responses[path] ??
      Object.entries(responses).find(([k]) => path.startsWith(k))?.[1];

    if (!match) {
      return new Response(JSON.stringify({ detail: "Not found" }), {
        status: 404,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response(JSON.stringify(match.body), {
      status: match.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });

  vi.stubGlobal("fetch", fn);
  return fn;
};
