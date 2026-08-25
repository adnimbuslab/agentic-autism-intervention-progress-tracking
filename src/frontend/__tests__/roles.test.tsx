import { describe, it, expect } from "vitest";
import {
  isInterventionist,
  isContributor,
} from "@/lib/utils/roleGuards";
import { createUser } from "./helpers";

describe("Role guards", () => {
  it("identifies interventionist role", () => {
    const user = createUser({ role: "interventionist" });
    expect(isInterventionist(user)).toBe(true);
    expect(isContributor(user)).toBe(false);
  });

  it("identifies parent as contributor", () => {
    const user = createUser({ role: "parent" });
    expect(isInterventionist(user)).toBe(false);
    expect(isContributor(user)).toBe(true);
  });

  it("identifies teacher as contributor", () => {
    const user = createUser({ role: "teacher" });
    expect(isInterventionist(user)).toBe(false);
    expect(isContributor(user)).toBe(true);
  });

  it("identifies trainer as contributor", () => {
    const user = createUser({ role: "trainer" });
    expect(isContributor(user)).toBe(true);
  });

  it("identifies epa as contributor", () => {
    const user = createUser({ role: "epa" });
    expect(isContributor(user)).toBe(true);
  });

  it("identifies secondary_interventionist as contributor", () => {
    const user = createUser({ role: "secondary_interventionist" });
    expect(isContributor(user)).toBe(true);
  });
});
