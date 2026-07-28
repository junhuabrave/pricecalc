import type { FC } from 'react'

import { ComingSoon } from '@/components/ui/ComingSoon'

export const MarketMakingPanel: FC = () => (
  <ComingSoon
    title="Market-making simulation"
    summary="Quote a book, take flow, manage the inventory you accumulate"
    planned={[
      'Fair value from a fitted vol surface, then a spread widened by inventory risk',
      'Quote skew that leans against the position to pull inventory back to flat',
      'Poisson order flow with fill probability decaying in distance from fair',
      'Inventory, delta and vega tracked per step, with optional delta hedging',
      'P&L attribution: spread capture vs gamma/theta vs hedge slippage',
    ]}
    modules={[
      'core/surface.py',
      'core/marketdata/simulated.py',
      'core/mm/quoting.py',
      'core/mm/simulator.py',
    ]}
  />
)
