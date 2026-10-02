import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  EvidencePacket,
  ReportFlagRequest,
  ReportGenerateRequest,
  ReportListItem,
  ReportResponse,
} from "@/lib/types";

export function useReports(childId: string) {
  return useQuery({
    queryKey: ["reports", childId],
    queryFn: () => api.get<ReportListItem[]>(`/children/${childId}/reports`),
    enabled: !!childId,
  });
}

export function useReport(reportId: string) {
  return useQuery({
    queryKey: ["report", reportId],
    queryFn: () => api.get<ReportResponse>(`/reports/${reportId}`),
    enabled: !!reportId,
  });
}

export function useEvidencePacket(reportId: string) {
  return useQuery({
    queryKey: ["report", reportId, "evidence"],
    queryFn: () => api.get<EvidencePacket>(`/reports/${reportId}/evidence`),
    enabled: !!reportId,
  });
}

export function useGenerateReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ childId, data }: { childId: string; data: ReportGenerateRequest }) =>
      api.post<ReportResponse>(`/children/${childId}/reports/generate`, data),
    onSuccess: (_report, { childId }) => {
      queryClient.invalidateQueries({ queryKey: ["reports", childId] });
    },
  });
}

export function useFlagReport() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ reportId, data }: { reportId: string; data: ReportFlagRequest }) =>
      api.post<ReportResponse>(`/reports/${reportId}/flag`, data),
    onSuccess: (report) => {
      queryClient.invalidateQueries({ queryKey: ["report", report.id] });
      queryClient.invalidateQueries({ queryKey: ["reports", report.child_id] });
    },
  });
}
