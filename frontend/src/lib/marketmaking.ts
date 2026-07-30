import { useQuery, type UseQueryResult } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { SimulateRequest, SimulateResponse, SweepResponse } from '@/types/marketmaking'

export const mmKeys = {
  all: ['marketmaking'] as const,
  simulate: (req: SimulateRequest) => ['marketmaking', 'simulate', req] as const,
  sweep: (req: SimulateRequest, paths: number) =>
    ['marketmaking', 'sweep', req, paths] as const,
}

/** Seeded end to end, so a request replays the same session — flow included. */
export function useSimulation(req: SimulateRequest): UseQueryResult<SimulateResponse> {
  return useQuery({
    queryKey: mmKeys.simulate(req),
    queryFn: async () => (await api.post<SimulateResponse>('/marketmaking/simulate', req)).data,
    staleTime: Infinity,
    gcTime: 10 * 60 * 1000,
    retry: false,
  })
}

/**
 * Averages many paths per setting, so it is far slower than a single run.
 * Kept as a separate query so the session view stays responsive while it runs.
 */
export function useRiskAversionSweep(
  req: SimulateRequest,
  paths: number,
  enabled: boolean
): UseQueryResult<SweepResponse> {
  return useQuery({
    queryKey: mmKeys.sweep(req, paths),
    queryFn: async () =>
      (await api.post<SweepResponse>(`/marketmaking/sweep?paths=${paths}`, req)).data,
    enabled,
    staleTime: Infinity,
    gcTime: 10 * 60 * 1000,
    retry: false,
  })
}
