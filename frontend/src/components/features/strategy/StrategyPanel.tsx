import type { FC } from 'react'

import { ComingSoon } from '@/components/ui/ComingSoon'

export const StrategyPanel: FC = () => (
  <ComingSoon
    title="Multi-leg strategy builder"
    summary="Compose spreads and combos, then read the net risk"
    planned={[
      'Leg table: signed quantity, instrument, strike, expiry, fill price',
      'Net Greeks aggregated across legs, in the same trader units as the pricer',
      'Payoff-at-expiry diagram with breakevens solved on the payoff grid',
      'Max profit / max loss, including unbounded detection from the wing slopes',
      'Presets: vertical, straddle, strangle, butterfly, iron condor, calendar',
    ]}
    modules={['core/strategy.py', 'api/routes_strategy.py']}
  />
)
