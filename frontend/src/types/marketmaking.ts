/** Wire types mirroring `pricecalc.api.schemas_mm`. */

export interface SimulateRequest {
  spot: number
  drift: number
  rate: number
  div_yield: number
  strike: number
  expiry: number
  option_type: 'call' | 'put'
  horizon: number
  steps: number
  risk_aversion: number
  order_flow_intensity: number
  order_flow_decay: number
  min_half_spread: number
  max_position: number
  hedge_delta: boolean
  hedge_threshold: number
  hedge_cost_bps: number
  atm_vol: number
  skew: number
  curvature: number
  seed: number
}

export interface MMStep {
  t: number
  spot: number
  fair_value: number
  bid: number
  ask: number
  reservation: number
  /** Reservation less fair. Negative when long — quotes marked down to attract flattening flow. */
  skew: number
  inventory: number
  delta_exposure: number
  hedge_position: number
  spread_pnl: number
  inventory_pnl: number
  hedge_pnl: number
  total_pnl: number
}

/** The three components sum to the total by construction. */
export interface Attribution {
  spread_pnl: number
  inventory_pnl: number
  hedge_pnl: number
  total_pnl: number
}

export interface SimulateResponse {
  attribution: Attribution
  steps: MMStep[]
  fills: number
  buys: number
  sells: number
  hedge_trades: number
  max_abs_inventory: number
  ending_inventory: number
  realised_vol: number
  implied_vol_at_open: number
  capture_per_fill: number
}

export interface SweepPoint {
  risk_aversion: number
  fills: number
  spread_pnl: number
  inventory_pnl: number
  hedge_pnl: number
  total_pnl: number
  max_abs_inventory: number
  ending_inventory: number
}

export interface SweepResponse {
  points: SweepPoint[]
  paths_per_point: number
}
