import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { Child } from "@/lib/types";

export function useChildren() {
  return useQuery({
    queryKey: ["children"],
    queryFn: () => api.get<Child[]>("/children/"),
  });
}

export function useChild(childId: string) {
  return useQuery({
    queryKey: ["children", childId],
    queryFn: () => api.get<Child>(`/children/${childId}`),
    enabled: !!childId,
  });
}
