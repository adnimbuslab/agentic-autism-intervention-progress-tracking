import type { User } from "@/lib/types";

/**
 * UI-side role checks. These only decide what to render; the backend enforces
 * the same boundaries on every endpoint.
 *
 * Only the primary interventionist is professional. A secondary
 * interventionist contributes observations like any other contributor.
 */
export function isInterventionist(user: User | null | undefined): boolean {
  return user?.role === "interventionist";
}

export function isContributor(user: User | null | undefined): boolean {
  return !!user && user.role !== "interventionist";
}
