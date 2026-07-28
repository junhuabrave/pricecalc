import type { FC } from 'react'

import { ComingSoon } from '@/components/ui/ComingSoon'

export const ArbitragePanel: FC = () => (
  <ComingSoon
    title="Arbitrage scanner"
    summary="Static no-arbitrage violations across a live option chain"
    planned={[
      'Put-call parity: flag when C − P ≠ S·e^(−qτ) − K·e^(−rτ) beyond the bid/ask',
      'Vertical spread bounds: C(K₁) ≥ C(K₂) and C(K₁) − C(K₂) ≤ (K₂ − K₁)·e^(−rτ)',
      'Butterfly convexity: C(K₁) − 2C(K₂) + C(K₃) ≥ 0 for equally spaced strikes',
      'Calendar monotonicity: longer-dated calls dominate shorter-dated at the same strike',
      'Each violation reported with the replicating trade and its locked-in profit',
    ]}
    modules={['core/arbitrage.py', 'core/chain.py', 'api/routes_arbitrage.py']}
  />
)
