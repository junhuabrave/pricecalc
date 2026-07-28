import { useState, type FC } from 'react'

import { ArbitragePanel } from '@/components/features/arbitrage/ArbitragePanel'
import { MarketMakingPanel } from '@/components/features/marketmaking/MarketMakingPanel'
import { PricerPanel } from '@/components/features/pricer/PricerPanel'
import { StrategyPanel } from '@/components/features/strategy/StrategyPanel'
import { Tabs, type TabDef } from '@/components/ui/Tabs'

const TABS = [
  { id: 'pricer', label: 'Pricer' },
  { id: 'arbitrage', label: 'Arbitrage', comingSoon: true },
  { id: 'strategy', label: 'Strategy', comingSoon: true },
  { id: 'marketmaking', label: 'Market making', comingSoon: true },
] as const satisfies readonly TabDef[]

type TabId = (typeof TABS)[number]['id']

const PANELS: Record<TabId, FC> = {
  pricer: PricerPanel,
  arbitrage: ArbitragePanel,
  strategy: StrategyPanel,
  marketmaking: MarketMakingPanel,
}

export const App: FC = () => {
  const [active, setActive] = useState<TabId>('pricer')
  const Panel = PANELS[active]

  return (
    <div className="min-h-full">
      <header className="border-b border-term-border px-6 py-4">
        <h1 className="text-lg font-semibold tracking-tight">
          pricecalc
          <span className="ml-3 text-xs font-normal text-term-muted">
            options pricing · no-arbitrage · market making
          </span>
        </h1>
      </header>

      <div className="px-6">
        <Tabs tabs={TABS} active={active} onSelect={(id) => setActive(id as TabId)} />
      </div>

      <main className="p-6">
        <Panel />
      </main>
    </div>
  )
}
