import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { AuditEvent } from "@/lib/types";

export function useAuditTrail(childId: string, limit = 100, offset = 0) {
  return useQuery({
    queryKey: ["audit", childId, limit, offset],
    queryFn: () =>
      api.get<AuditEvent[]>(`/children/${childId}/audit?limit=${limit}&offset=${offset}`),
    enabled: !!childId,
  });
}
