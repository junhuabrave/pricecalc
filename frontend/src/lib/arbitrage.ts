import { useQuery, type UseQueryResult } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type { ScanRequest, ScanResponse } from '@/types/arbitrage'

export const arbitrageKeys = {
  all: ['arbitrage'] as const,
  scan: (req: ScanRequest) => ['arbitrage', 'scan', req] as const,
}

/**
 * A scan is fully determined by its request — the chain is generated from the
 * seed — so a given parameter set always yields the same findings and the
 * result never goes stale.
 */
export function useArbitrageScan(req: ScanRequest): UseQueryResult<ScanResponse> {
  return useQuery({
    queryKey: arbitrageKeys.scan(req),
    queryFn: async () => (await api.post<ScanResponse>('/arbitrage/scan', req)).data,
    staleTime: Infinity,
    gcTime: 10 * 60 * 1000,
    retry: false,
  })
}
