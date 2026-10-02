import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  ClarificationRequest,
  Observation,
  ObservationCreateRequest,
  ObservationDetail,
  ObservationSubmitResponse,
} from "@/lib/types";

export function useObservations(childId: string) {
  return useQuery({
    queryKey: ["observations", childId],
    queryFn: () => api.get<Observation[]>(`/children/${childId}/observations`),
    enabled: !!childId,
  });
}

export function useObservation(observationId: string) {
  return useQuery({
    queryKey: ["observation", observationId],
    queryFn: () => api.get<ObservationDetail>(`/observations/${observationId}`),
    enabled: !!observationId,
  });
}

/** A new or finalized observation can create a structured record. */
function invalidateChild(
  queryClient: ReturnType<typeof useQueryClient>,
  childId: string,
) {
  queryClient.invalidateQueries({ queryKey: ["observations", childId] });
  queryClient.invalidateQueries({ queryKey: ["records", childId] });
}

export function useSubmitObservation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ childId, data }: { childId: string; data: ObservationCreateRequest }) =>
      api.post<ObservationSubmitResponse>(`/children/${childId}/observations`, data),
    onSuccess: (_res, { childId }) => invalidateChild(queryClient, childId),
  });
}

export function useClarification() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ obsId, data }: { obsId: string; data: ClarificationRequest }) =>
      api.post<ObservationSubmitResponse>(`/observations/${obsId}/clarifications`, data),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["observation", res.observation.id] });
      invalidateChild(queryClient, res.observation.child_id);
    },
  });
}

export function useFinalizeObservation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ obsId }: { obsId: string; childId: string }) =>
      api.post<Observation>(`/observations/${obsId}/finalize`),
    onSuccess: (_obs, { obsId, childId }) => {
      queryClient.invalidateQueries({ queryKey: ["observation", obsId] });
      invalidateChild(queryClient, childId);
    },
  });
}
