/** Wire types mirroring `pricecalc.api.schemas`. Keep in sync with the backend. */

export type OptionType = 'call' | 'put'

/** The Black-Scholes state vector shared by every pricing request. */
export interface MarketInputs {
  spot: number
  strike: number
  rate: number
  div_yield: number
  tau_years: number
  option_type: OptionType
}

export interface EvaluateRequest extends MarketInputs {
  vol: number
}

/**
 * Greeks in trader units: vega per vol point, theta per calendar day,
 * rho per 1% of rate. Delta and gamma are per $1 of spot.
 */
export interface Greeks {
  delta: number
  gamma: number
  vega: number
  theta: number
  rho: number
  vanna: number
  volga: number
}

export interface EvaluateResponse {
  price: number
  greeks: Greeks
  d1: number
  d2: number
  forward: number
  intrinsic: number
  time_value: number
  moneyness: number
}

export interface ImpliedVolRequest extends MarketInputs {
  price: number
}

export interface ImpliedVolResponse {
  implied_vol: number
  lower_bound: number
  upper_bound: number
  greeks: Greeks
}

export interface SweepRequest extends EvaluateRequest {
  spot_min?: number
  spot_max?: number
  steps?: number
}

export interface SweepPoint {
  spot: number
  price: number
  intrinsic: number
  delta: number
  gamma: number
  vega: number
  theta: number
}

export interface SweepResponse {
  points: SweepPoint[]
}

/** Shape of the 422 body the implied-vol endpoint returns for un-invertible quotes. */
export interface NoImpliedVolDetail {
  message: string
  lower_bound: number
  upper_bound: number
}
