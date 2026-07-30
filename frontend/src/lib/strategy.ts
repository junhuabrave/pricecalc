import { useQuery, type UseQueryResult } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { AnalyseResponse, PresetInfo, PresetRequest } from '@/types/strategy'

export const strategyKeys = {
  all: ['strategy'] as const,
  presets: ['strategy', 'presets'] as const,
  preset: (req: PresetRequest) => ['strategy', 'preset', req] as const,
}

/** The catalogue is static for the life of the server. */
export function usePresetCatalogue(): UseQueryResult<PresetInfo[]> {
  return useQuery({
    queryKey: strategyKeys.presets,
    queryFn: async () => (await api.get<PresetInfo[]>('/strategy/presets')).data,
    staleTime: Infinity,
    retry: false,
  })
}

/** Structure analytics are a pure function of the request, so results never stale. */
export function useStrategyPreset(req: PresetRequest): UseQueryResult<AnalyseResponse> {
  return useQuery({
    queryKey: strategyKeys.preset(req),
    queryFn: async () => (await api.post<AnalyseResponse>('/strategy/preset', req)).data,
    staleTime: Infinity,
    gcTime: 10 * 60 * 1000,
    retry: false,
  })
}
