import { useQuery, type UseQueryResult } from '@tanstack/react-query'

import { api } from '@/lib/api'
import type {
  EvaluateRequest,
  EvaluateResponse,
  ImpliedVolRequest,
  ImpliedVolResponse,
  SweepRequest,
  SweepResponse,
} from '@/types/pricing'

export const pricingKeys = {
  all: ['pricing'] as const,
  evaluate: (req: EvaluateRequest) => ['pricing', 'evaluate', req] as const,
  sweep: (req: SweepRequest) => ['pricing', 'sweep', req] as const,
  impliedVol: (req: ImpliedVolRequest) => ['pricing', 'implied-vol', req] as const,
}

/**
 * Pricing is a pure function of its inputs, so results never go stale and a
 * revisited parameter set is served from cache instantly.
 */
const PURE_FUNCTION_CACHE = {
  staleTime: Infinity,
  gcTime: 10 * 60 * 1000,
  retry: false,
} as const

export function useEvaluate(req: EvaluateRequest): UseQueryResult<EvaluateResponse> {
  return useQuery({
    queryKey: pricingKeys.evaluate(req),
    queryFn: async () => (await api.post<EvaluateResponse>('/pricing/evaluate', req)).data,
    ...PURE_FUNCTION_CACHE,
  })
}

export function useSweep(req: SweepRequest): UseQueryResult<SweepResponse> {
  return useQuery({
    queryKey: pricingKeys.sweep(req),
    queryFn: async () => (await api.post<SweepResponse>('/pricing/sweep', req)).data,
    ...PURE_FUNCTION_CACHE,
  })
}

export function useImpliedVol(
  req: ImpliedVolRequest,
  enabled: boolean
): UseQueryResult<ImpliedVolResponse> {
  return useQuery({
    queryKey: pricingKeys.impliedVol(req),
    queryFn: async () => (await api.post<ImpliedVolResponse>('/pricing/implied-vol', req)).data,
    enabled,
    ...PURE_FUNCTION_CACHE,
  })
}
