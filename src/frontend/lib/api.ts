/**
 * Thin fetch wrapper for the FastAPI backend.
 *
 * Attaches the bearer token from localStorage, sends JSON, and turns every
 * non-2xx response into an ApiError carrying the status and FastAPI's
 * `detail`. A 401 clears the stored session so the next render falls back to
 * the login page.
 */

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const TOKEN_KEY = "auth_token";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(ApiError.describe(status, detail));
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }

  private static describe(status: number, detail: unknown): string {
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      // FastAPI request-validation errors: [{loc, msg, type}, ...]
      return detail
        .map((d) =>
          d && typeof d === "object" && "msg" in d ? String(d.msg) : String(d),
        )
        .join("; ");
    }
    return `Request failed with status ${status}`;
  }
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

async function request<T>(
  method: string,
  path: string,
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const init: RequestInit = { method, headers };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }

  const res = await fetch(`${API_BASE_URL}${path}`, init);

  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = (await res.json())?.detail ?? null;
    } catch {
      // Non-JSON error body; the status alone is reported.
    }
    if (res.status === 401 && typeof window !== "undefined") {
      window.localStorage.removeItem(TOKEN_KEY);
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export const api = {
  get: <T = unknown>(path: string) => request<T>("GET", path),
  post: <T = unknown>(path: string, body?: unknown) =>
    request<T>("POST", path, body),
  patch: <T = unknown>(path: string, body?: unknown) =>
    request<T>("PATCH", path, body),
  delete: <T = unknown>(path: string) => request<T>("DELETE", path),
};
