import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { RecordCorrectionRequest, StructuredRecord } from "@/lib/types";

export function useRecords(childId: string) {
  return useQuery({
    queryKey: ["records", childId],
    queryFn: () => api.get<StructuredRecord[]>(`/children/${childId}/records`),
    enabled: !!childId,
  });
}

export function useRecord(recordId: string) {
  return useQuery({
    queryKey: ["record", recordId],
    queryFn: () => api.get<StructuredRecord>(`/records/${recordId}`),
    enabled: !!recordId,
  });
}

export function useRecordVersions(recordId: string) {
  return useQuery({
    queryKey: ["record", recordId, "history"],
    queryFn: () => api.get<StructuredRecord[]>(`/records/${recordId}/history`),
    enabled: !!recordId,
  });
}

/**
 * Verifying or correcting a record changes which records are admitted to
 * analytics, so every record, analytics and report query is refetched.
 */
function invalidateReviewState(queryClient: ReturnType<typeof useQueryClient>) {
  queryClient.invalidateQueries({ queryKey: ["record"] });
  queryClient.invalidateQueries({ queryKey: ["records"] });
  queryClient.invalidateQueries({ queryKey: ["observation"] });
  queryClient.invalidateQueries({ queryKey: ["analytics"] });
  queryClient.invalidateQueries({ queryKey: ["reports"] });
}

export function useCorrectRecord() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ recordId, data }: { recordId: string; data: RecordCorrectionRequest }) =>
      api.post<StructuredRecord>(`/records/${recordId}/correct`, data),
    onSuccess: () => invalidateReviewState(queryClient),
  });
}

export function useVerifyRecord() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ recordId }: { recordId: string }) =>
      api.post<StructuredRecord>(`/records/${recordId}/verify`),
    onSuccess: () => invalidateReviewState(queryClient),
  });
}
