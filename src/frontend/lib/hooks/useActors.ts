import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { ActorAssignment, ActorInviteRequest } from "@/lib/types";

export function useActors(childId: string) {
  return useQuery({
    queryKey: ["actors", childId],
    queryFn: () => api.get<ActorAssignment[]>(`/children/${childId}/actors`),
    enabled: !!childId,
  });
}

export function useInviteActor() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ childId, data }: { childId: string; data: ActorInviteRequest }) =>
      api.post<ActorAssignment>(`/children/${childId}/actors`, data),
    onSuccess: (_actor, { childId }) => {
      queryClient.invalidateQueries({ queryKey: ["actors", childId] });
    },
  });
}

export function useRevokeActor() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ actorId }: { actorId: string; childId: string }) =>
      api.delete<ActorAssignment>(`/actors/${actorId}`),
    onSuccess: (_actor, { childId }) => {
      queryClient.invalidateQueries({ queryKey: ["actors", childId] });
    },
  });
}
