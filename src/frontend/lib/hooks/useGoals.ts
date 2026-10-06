import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Goal, GoalCreateRequest } from "@/lib/types";

export function useGoals(childId: string) {
  return useQuery({
    queryKey: ["goals", childId],
    queryFn: () => api.get<Goal[]>(`/children/${childId}/goals`),
    enabled: !!childId,
  });
}

export function useCreateGoal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ childId, data }: { childId: string; data: GoalCreateRequest }) =>
      api.post<Goal>(`/children/${childId}/goals`, data),
    onSuccess: (_goal, { childId }) => {
      queryClient.invalidateQueries({ queryKey: ["goals", childId] });
    },
  });
}
