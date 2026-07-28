import { create } from 'zustand'

import type { OptionType } from '@/types/pricing'

/**
 * The market state vector, held globally because every scenario tab reads the
 * same underlying/rate/expiry. The pricer writes it; the arbitrage, strategy
 * and market-making tabs will read it as they land.
 */
export interface MarketState {
  spot: number
  strike: number
  rate: number
  divYield: number
  vol: number
  tauYears: number
  optionType: OptionType

  set: <K extends keyof MarketInputFields>(key: K, value: MarketInputFields[K]) => void
  reset: () => void
}

type MarketInputFields = Omit<MarketState, 'set' | 'reset'>

/** SPX-like defaults: 1-year ATM call, 5% rates, 20% vol. */
const DEFAULTS: MarketInputFields = {
  spot: 100,
  strike: 100,
  rate: 0.05,
  divYield: 0,
  vol: 0.2,
  tauYears: 1,
  optionType: 'call',
}

export const useMarketStore = create<MarketState>()((set) => ({
  ...DEFAULTS,
  set: (key, value) => set({ [key]: value } as Pick<MarketInputFields, typeof key>),
  reset: () => set(DEFAULTS),
}))

export { DEFAULTS as MARKET_DEFAULTS }
export type { MarketInputFields }
