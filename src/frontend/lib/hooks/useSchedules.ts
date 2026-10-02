import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Schedule, ScheduleCreateRequest } from "@/lib/types";

export function useSchedules(childId: string) {
  return useQuery({
    queryKey: ["schedules", childId],
    queryFn: () => api.get<Schedule[]>(`/children/${childId}/schedules`),
    enabled: !!childId,
  });
}

export function useCreateSchedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ childId, data }: { childId: string; data: ScheduleCreateRequest }) =>
      api.post<Schedule>(`/children/${childId}/schedules`, data),
    onSuccess: (_schedule, { childId }) => {
      queryClient.invalidateQueries({ queryKey: ["schedules", childId] });
    },
  });
}
