import { describe, it, expect, vi, beforeEach } from "vitest";
import { api, ApiError } from "@/lib/api";
import { mockFetch } from "./helpers";

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("API Client", () => {
  it("attaches bearer token from localStorage", async () => {
    const fetchFn = mockFetch({
      "GET /test": { body: { ok: true } },
    });
    (localStorage.getItem as ReturnType<typeof vi.fn>).mockReturnValue("my-token");

    await api.get("/test");

    expect(fetchFn).toHaveBeenCalledWith(
      expect.stringContaining("/test"),
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer my-token",
        }),
      }),
    );
  });

  it("makes GET request without body", async () => {
    const fetchFn = mockFetch({
      "GET /items": { body: [{ id: 1 }] },
    });

    const result = await api.get("/items");
    expect(result).toEqual([{ id: 1 }]);
    expect(fetchFn).toHaveBeenCalledWith(
      expect.stringContaining("/items"),
      expect.objectContaining({ method: "GET" }),
    );
  });

  it("makes POST request with JSON body", async () => {
    const fetchFn = mockFetch({
      "POST /items": { status: 201, body: { id: 2 } },
    });

    const result = await api.post("/items", { name: "test" });
    expect(result).toEqual({ id: 2 });
    expect(fetchFn).toHaveBeenCalledWith(
      expect.stringContaining("/items"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "test" }),
      }),
    );
  });

  it("throws ApiError on 422", async () => {
    mockFetch({
      "POST /bad": { status: 422, body: { detail: "Validation error" } },
    });

    await expect(api.post("/bad", {})).rejects.toThrow(ApiError);
    try {
      await api.post("/bad", {});
    } catch (e) {
      expect((e as ApiError).status).toBe(422);
    }
  });

  it("throws ApiError on 404", async () => {
    mockFetch({});
    await expect(api.get("/nonexistent")).rejects.toThrow(ApiError);
  });

  it("throws ApiError on 500", async () => {
    mockFetch({
      "GET /error": { status: 500, body: { detail: "Server error" } },
    });
    await expect(api.get("/error")).rejects.toThrow(ApiError);
  });

  it("makes PATCH request", async () => {
    mockFetch({
      "PATCH /items/1": { body: { id: 1, name: "updated" } },
    });

    const result = await api.patch("/items/1", { name: "updated" });
    expect(result).toEqual({ id: 1, name: "updated" });
  });

  it("makes DELETE request", async () => {
    mockFetch({
      "DELETE /items/1": { body: { message: "deleted" } },
    });

    const result = await api.delete("/items/1");
    expect(result).toEqual({ message: "deleted" });
  });
});
