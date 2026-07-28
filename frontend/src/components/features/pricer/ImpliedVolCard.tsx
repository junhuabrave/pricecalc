import { useState, type FC } from 'react'

import { Card } from '@/components/ui/Card'
import { NumberField } from '@/components/ui/NumberField'
import { Stat } from '@/components/ui/Stat'
import { apiErrorMessage } from '@/lib/api'
import { useImpliedVol } from '@/lib/pricing'
import { fmt, fmtPct } from '@/lib/utils'
import { useMarketStore } from '@/stores/useMarketStore'

/**
 * Inverts an observed premium back to volatility.
 *
 * The interesting case is failure: a quote outside the no-arbitrage band has
 * no implied vol at all, and the backend says so with a 422 rather than
 * clamping. That rejection is the first arbitrage signal in the app.
 */
export const ImpliedVolCard: FC = () => {
  const { spot, strike, rate, divYield, tauYears, optionType } = useMarketStore()
  const [premium, setPremium] = useState(10.45)

  const { data, error, isFetching } = useImpliedVol(
    {
      spot,
      strike,
      rate,
      div_yield: divYield,
      tau_years: tauYears,
      option_type: optionType,
      price: premium,
    },
    premium > 0 && tauYears > 0
  )

  return (
    <Card title="Implied volatility" subtitle="Back out σ from an observed premium">
      <div className="flex flex-col gap-4">
        <NumberField
          label="Market premium"
          value={premium}
          onChange={setPremium}
          step={0.25}
          min={0}
        />

        {error && (
          <div className="rounded-md border border-term-short/40 bg-term-short/10 p-3">
            <p className="text-xs font-medium text-term-short">No implied volatility exists</p>
            <p className="mt-1 text-[11px] leading-relaxed text-term-muted">
              {apiErrorMessage(error)}
            </p>
          </div>
        )}

        {data && !error && (
          <div className="grid grid-cols-2 gap-4">
            <Stat
              label="Implied σ"
              value={fmtPct(data.implied_vol)}
              note="annualised"
              emphasis
              valueClassName="text-term-accent"
            />
            <Stat label="Implied delta" value={fmt(data.greeks.delta, 4)} note="per $1 of spot" />
            <Stat
              label="No-arb band"
              value={`${fmt(data.lower_bound, 2)} – ${fmt(data.upper_bound, 2)}`}
              note="premiums outside are arbitrage"
            />
            <Stat label="Implied vega" value={fmt(data.greeks.vega, 4)} note="per 1 vol point" />
          </div>
        )}

        {isFetching && !data && <p className="text-xs text-term-muted">Solving…</p>}
      </div>
    </Card>
  )
}
