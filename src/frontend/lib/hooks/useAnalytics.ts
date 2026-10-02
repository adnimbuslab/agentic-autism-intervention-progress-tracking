import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { AnalyticsResponse } from "@/lib/types";

/**
 * Analytics are computed server-side on request (POST), deterministically,
 * for one review period. Nothing is fetched until a period is chosen.
 *
 * The backend reports the adequacy level in lowercase ("insufficient");
 * the analytics views compare against uppercase ("INSUFFICIENT"), so the
 * level is normalised here, once, before any component sees it.
 */
export function useAnalytics(childId: string, reviewPeriodId: string, goalId?: string) {
  return useQuery({
    queryKey: ["analytics", childId, reviewPeriodId, goalId ?? null],
    queryFn: async () => {
      const res = await api.post<AnalyticsResponse>(`/children/${childId}/analytics`, {
        review_period_id: reviewPeriodId,
        goal_id: goalId ?? null,
      });
      return { ...res, adequacy: { ...res.adequacy, level: res.adequacy.level.toUpperCase() } };
    },
    enabled: !!childId && !!reviewPeriodId,
  });
}
