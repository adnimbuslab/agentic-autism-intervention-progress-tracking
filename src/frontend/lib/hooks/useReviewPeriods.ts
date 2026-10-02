import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ReviewPeriod, ReviewPeriodCreateRequest } from "@/lib/types";

export function useReviewPeriods(childId: string) {
  return useQuery({
    queryKey: ["review-periods", childId],
    queryFn: () => api.get<ReviewPeriod[]>(`/children/${childId}/review-periods`),
    enabled: !!childId,
  });
}

export function useCreateReviewPeriod() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ childId, data }: { childId: string; data: ReviewPeriodCreateRequest }) =>
      api.post<ReviewPeriod>(`/children/${childId}/review-periods`, data),
    onSuccess: (_period, { childId }) => {
      queryClient.invalidateQueries({ queryKey: ["review-periods", childId] });
    },
  });
}
