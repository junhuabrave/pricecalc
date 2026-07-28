/** Wire types mirroring `pricecalc.api.schemas_arbitrage`. */

export type ViolationKind =
  | 'absolute_bound'
  | 'put_call_parity'
  | 'vertical_monotonicity'
  | 'vertical_cap'
  | 'butterfly_convexity'
  | 'calendar_monotonicity'

export interface ScanRequest {
  spot: number
  rate: number
  div_yield: number
  expiries: number[]
  strike_count: number
  strike_span: number
  atm_vol: number
  skew: number
  curvature: number
  spread_bps: number
  n_violations: number
  seed: number
  min_edge: number
}

export interface ChainQuote {
  tau: number
  strike: number
  option_type: 'call' | 'put'
  bid: number
  ask: number
  mid: number
}

export interface ChainOut {
  spot: number
  rate: number
  div_yield: number
  quotes: ChainQuote[]
}

/** One position in the replicating trade. Negative quantity is short. */
export interface ViolationLeg {
  instrument: string
  quantity: number
  price: number
  /** Cash today; negative is an outflow. Legs must sum to `Violation.profit`. */
  cash_flow: number
}

export interface Violation {
  kind: ViolationKind
  summary: string
  detail: string
  profit: number
  tau: number
  strikes: number[]
  legs: ViolationLeg[]
}

export interface ScanSummary {
  quotes_scanned: number
  violations_found: number
  total_edge: number
  by_kind: Record<string, number>
  calendar_checks_skipped: boolean
}

export interface ScanResponse {
  chain: ChainOut
  violations: Violation[]
  summary: ScanSummary
  /** Mispricings deliberately injected — lets you verify the scanner found them. */
  planted: string[]
}

export const VIOLATION_LABELS: Record<ViolationKind, string> = {
  absolute_bound: 'Absolute bound',
  put_call_parity: 'Put-call parity',
  vertical_monotonicity: 'Vertical monotonicity',
  vertical_cap: 'Vertical cap',
  butterfly_convexity: 'Butterfly convexity',
  calendar_monotonicity: 'Calendar monotonicity',
}
