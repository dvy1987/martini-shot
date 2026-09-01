/** Truthful reachability probe against the unauthenticated /api/v1/health endpoint. */

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/api/client";

export function useBackendHealth() {
  return useQuery({
    queryKey: ["backend-health"],
    queryFn: () => apiFetch<unknown>("/api/v1/health"),
    refetchInterval: 30_000,
    retry: 1,
  });
}
