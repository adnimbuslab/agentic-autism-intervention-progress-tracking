import { describe, it, expect } from "vitest";
import {
  formatDate,
  formatDateTime,
  formatPercent,
  capitalize,
  truncate,
} from "@/lib/utils/formatters";

describe("formatters", () => {
  it("formatPercent formats 0-1 as percentage", () => {
    expect(formatPercent(0.75)).toBe("75.0%");
    expect(formatPercent(0)).toBe("0.0%");
    expect(formatPercent(1)).toBe("100.0%");
  });

  it("capitalize replaces underscores and capitalizes", () => {
    expect(capitalize("social_communication")).toBe("Social communication");
    expect(capitalize("home")).toBe("Home");
    expect(capitalize("")).toBe("");
  });

  it("truncate shortens long strings", () => {
    expect(truncate("hello", 10)).toBe("hello");
    expect(truncate("hello world!", 5)).toBe("hell…");
  });

  it("formatDate produces readable date", () => {
    const result = formatDate("2026-06-15T10:00:00Z");
    expect(result).toContain("2026");
    expect(result).toContain("Jun");
  });

  it("formatDateTime includes time", () => {
    const result = formatDateTime("2026-06-15T14:30:00Z");
    expect(result).toContain("2026");
  });
});
