import type { FC } from 'react'

import { GreekVsSpotChart } from '@/components/charts/GreekVsSpotChart'
import { PriceVsSpotChart } from '@/components/charts/PriceVsSpotChart'
import { GreeksGrid } from '@/components/features/pricer/GreeksGrid'
import { ImpliedVolCard } from '@/components/features/pricer/ImpliedVolCard'
import { InputsPanel } from '@/components/features/pricer/InputsPanel'
import { Card } from '@/components/ui/Card'
import { Stat } from '@/components/ui/Stat'
import { apiErrorMessage } from '@/lib/api'
import { useEvaluate, useSweep } from '@/lib/pricing'
import { fmt, signClass } from '@/lib/utils'
import { useMarketStore } from '@/stores/useMarketStore'
import type { EvaluateRequest } from '@/types/pricing'

export const PricerPanel: FC = () => {
  const { spot, strike, rate, divYield, vol, tauYears, optionType } = useMarketStore()

  const request: EvaluateRequest = {
    spot,
    strike,
    rate,
    div_yield: divYield,
    vol,
    tau_years: tauYears,
    option_type: optionType,
  }

  const evaluate = useEvaluate(request)
  const sweep = useSweep({ ...request, steps: 121 })

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <Card title="Inputs" subtitle="Black-Scholes-Merton state vector">
          <InputsPanel />
        </Card>

        <div className="flex flex-col gap-4">
          <Card title="Valuation" subtitle={`European ${optionType}`}>
            {evaluate.error && (
              <p className="text-sm text-term-short">{apiErrorMessage(evaluate.error)}</p>
            )}
            {evaluate.data && (
              <div className="flex flex-col gap-5">
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Stat
                    label="Model value"
                    value={fmt(evaluate.data.price, 4)}
                    note="per contract unit"
                    emphasis
                    valueClassName="text-term-accent"
                  />
                  <Stat label="Intrinsic" value={fmt(evaluate.data.intrinsic, 4)} note="if expiring now" />
                  <Stat
                    label="Time value"
                    value={fmt(evaluate.data.time_value, 4)}
                    note="optionality premium"
                    valueClassName={signClass(evaluate.data.time_value)}
                  />
                  <Stat
                    label="Forward"
                    value={fmt(evaluate.data.forward, 4)}
                    note={`log(F/K) = ${fmt(evaluate.data.moneyness, 4)}`}
                  />
                </div>

                <div className="border-t border-term-border pt-4">
                  <GreeksGrid greeks={evaluate.data.greeks} />
                </div>

                <div className="flex gap-6 border-t border-term-border pt-3 text-[11px] text-term-muted">
                  <span>d₁ = {fmt(evaluate.data.d1, 4)}</span>
                  <span>d₂ = {fmt(evaluate.data.d2, 4)}</span>
                  <span>N(d₂) ≈ risk-neutral P(ITM)</span>
                </div>
              </div>
            )}
            {evaluate.isPending && <p className="text-sm text-term-muted">Pricing…</p>}
          </Card>

          <ImpliedVolCard />
        </div>
      </div>

      <Card title="Risk profile" subtitle="Swept across a ±40% spot band">
        {sweep.error && <p className="text-sm text-term-short">{apiErrorMessage(sweep.error)}</p>}
        {sweep.data && (
          <div className="grid gap-6 xl:grid-cols-2">
            <PriceVsSpotChart points={sweep.data.points} spot={spot} strike={strike} />
            <GreekVsSpotChart points={sweep.data.points} spot={spot} strike={strike} />
          </div>
        )}
        {sweep.isPending && <p className="text-sm text-term-muted">Computing sweep…</p>}
      </Card>
    </div>
  )
}
