/** Wire types mirroring `pricecalc.api.schemas_strategy`. */

import type { Greeks } from '@/types/pricing'

export type LegKind = 'call' | 'put' | 'underlying'

export type PresetId =
  | 'long_call'
  | 'long_put'
  | 'bull_call_spread'
  | 'bear_put_spread'
  | 'straddle'
  | 'strangle'
  | 'butterfly'
  | 'iron_condor'
  | 'covered_call'
  | 'collar'
  | 'calendar'

export interface PresetInfo {
  id: PresetId
  label: string
  summary: string
}

export interface PresetRequest {
  preset: PresetId
  spot: number
  rate: number
  div_yield: number
  vol: number
  tau: number
  width: number
  span: number
  steps: number
}

export interface LegOut {
  kind: LegKind
  label: string
  quantity: number
  entry_price: number
  strike: number | null
  tau: number | null
  vol: number | null
}

/** `value` is null when the extreme is unbounded — JSON cannot carry infinity. */
export interface Extreme {
  value: number | null
  spot: number | null
  unbounded: boolean
}

export interface PayoffPoint {
  spot: number
  /** P&L at expiry — piecewise linear, kinked at the strikes. */
  payoff: number
  /** Mark-to-market P&L today; the gap to `payoff` is remaining time value. */
  value: number
}

export interface AnalyseResponse {
  legs: LegOut[]
  /** Positive is a debit paid, negative a credit received. */
  net_cost: number
  net_greeks: Greeks
  breakevens: number[]
  max_profit: Extreme
  max_loss: Extreme
  payoff_slope_up: number
  payoff_slope_down: number
  kinks: number[]
  /** Nearest expiry. Legs living beyond it are marked, not settled. */
  horizon_tau: number
  /** False when a leg outlives the horizon, making the curve smooth and searched. */
  exact: boolean
  curve: PayoffPoint[]
  preset: PresetId | null
  summary: string | null
}
