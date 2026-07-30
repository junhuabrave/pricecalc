import { useState, type FC } from 'react'

import { PayoffChart } from '@/components/charts/PayoffChart'
import { GreeksGrid } from '@/components/features/pricer/GreeksGrid'
import { LegTable } from '@/components/features/strategy/LegTable'
import { Card } from '@/components/ui/Card'
import { NumberField } from '@/components/ui/NumberField'
import { Stat } from '@/components/ui/Stat'
import { apiErrorMessage } from '@/lib/api'
import { usePresetCatalogue, useStrategyPreset } from '@/lib/strategy'
import { cn, fmt } from '@/lib/utils'
import type { Extreme, PresetId, PresetRequest } from '@/types/strategy'

const DEFAULTS: PresetRequest = {
  preset: 'bull_call_spread',
  spot: 100,
  rate: 0.04,
  div_yield: 0,
  vol: 0.2,
  tau: 0.25,
  width: 0.05,
  span: 0.5,
  steps: 161,
}

/** An unbounded extreme arrives as null, since JSON has no infinity. */
function extremeText(e: Extreme): string {
  if (e.unbounded) return e.value === null ? '∞' : fmt(e.value, 4)
  return fmt(e.value ?? 0, 4)
}

export const StrategyPanel: FC = () => {
  const [request, setRequest] = useState<PresetRequest>(DEFAULTS)
  const catalogue = usePresetCatalogue()
  const analysis = useStrategyPreset(request)

  const set = <K extends keyof PresetRequest>(key: K, next: PresetRequest[K]) =>
    setRequest((prev) => ({ ...prev, [key]: next }))

  const data = analysis.data

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <div className="flex flex-col gap-4">
          <Card title="Structure" subtitle="Built at fair value — no entry edge">
            {catalogue.error && (
              <p className="text-sm text-term-short">{apiErrorMessage(catalogue.error)}</p>
            )}
            <div className="grid grid-cols-2 gap-1.5">
              {(catalogue.data ?? []).map((p) => (
                <button
                  key={p.id}
                  type="button"
                  aria-pressed={request.preset === p.id}
                  onClick={() => set('preset', p.id as PresetId)}
                  title={p.summary}
                  className={cn(
                    'rounded px-2 py-1.5 text-left text-[11px] transition-colors',
                    request.preset === p.id
                      ? 'bg-term-accent/15 text-term-accent'
                      : 'text-term-muted hover:bg-term-bg hover:text-term-text'
                  )}
                >
                  {p.label}
                </button>
              ))}
            </div>
            {data?.summary && (
              <p className="mt-3 border-t border-term-border pt-3 text-[11px] leading-relaxed text-term-muted">
                {data.summary}
              </p>
            )}
          </Card>

          <Card title="Market">
            <div className="grid grid-cols-2 gap-3">
              <NumberField label="Spot" value={request.spot} onChange={(v) => set('spot', v)} step={1} min={0.01} />
              <NumberField
                label="Volatility"
                value={request.vol}
                onChange={(v) => set('vol', v)}
                step={0.01}
                min={0.001}
                hint={`${(request.vol * 100).toFixed(1)}%`}
              />
              <NumberField
                label="Expiry"
                value={request.tau}
                onChange={(v) => set('tau', v)}
                step={0.05}
                min={0.01}
                suffix="yrs"
                hint={`${Math.round(request.tau * 365)} days`}
              />
              <NumberField
                label="Strike width"
                value={request.width}
                onChange={(v) => set('width', v)}
                step={0.01}
                min={0.005}
                max={0.5}
                hint={`±${fmt(request.spot * request.width, 2)} steps`}
              />
              <NumberField
                label="Rate"
                value={request.rate}
                onChange={(v) => set('rate', v)}
                step={0.005}
                hint={`${(request.rate * 100).toFixed(2)}%`}
              />
              <NumberField
                label="Dividend yield"
                value={request.div_yield}
                onChange={(v) => set('div_yield', v)}
                step={0.005}
                min={0}
                hint={`${(request.div_yield * 100).toFixed(2)}%`}
              />
            </div>
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          <Card title="Position" subtitle="Net risk and outcome envelope">
            {analysis.error && (
              <p className="text-sm text-term-short">{apiErrorMessage(analysis.error)}</p>
            )}
            {analysis.isPending && <p className="text-sm text-term-muted">Analysing…</p>}

            {data && (
              <div className="flex flex-col gap-5">
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Stat
                    label={data.net_cost >= 0 ? 'Net debit' : 'Net credit'}
                    value={fmt(Math.abs(data.net_cost), 4)}
                    note="to open, per unit"
                    emphasis
                    valueClassName={data.net_cost >= 0 ? 'text-term-short' : 'text-term-long'}
                  />
                  <Stat
                    label="Max profit"
                    value={extremeText(data.max_profit)}
                    note={data.max_profit.unbounded ? 'unbounded upside' : 'capped'}
                    valueClassName="text-term-long"
                  />
                  <Stat
                    label="Max loss"
                    value={extremeText(data.max_loss)}
                    note={data.max_loss.unbounded ? 'unbounded risk' : 'capped'}
                    valueClassName={data.max_loss.unbounded ? 'text-term-warn' : 'text-term-short'}
                  />
                  <Stat
                    label="Breakevens"
                    value={
                      data.breakevens.length
                        ? data.breakevens.map((b) => fmt(b, 2)).join(' · ')
                        : 'none'
                    }
                    note={data.breakevens.length ? 'terminal spot' : 'never crosses zero'}
                  />
                </div>

                <div className="border-t border-term-border pt-4">
                  <GreeksGrid greeks={data.net_greeks} />
                </div>

                {!data.exact && (
                  <div className="rounded-md border border-term-warn/30 bg-term-warn/10 p-3">
                    <p className="text-xs font-medium text-term-warn">
                      Multiple expiries — figures are searched, not solved
                    </p>
                    <p className="mt-1 text-[11px] leading-relaxed text-term-muted">
                      P&amp;L is taken at the nearest expiry ({fmt(data.horizon_tau, 3)}y), where the
                      longer-dated leg has not settled — it still carries time value, so the curve
                      is smooth rather than kinked and its turning point can sit between strikes.
                      Settling every leg at once would flatten a calendar into a straight line.
                    </p>
                  </div>
                )}

                <div className="flex flex-wrap gap-x-6 gap-y-1 border-t border-term-border pt-3 text-[11px] text-term-muted">
                  <span>upper wing slope {fmt(data.payoff_slope_up, 2)}</span>
                  <span>lower wing slope {fmt(data.payoff_slope_down, 2)}</span>
                  <span>kinks at {data.kinks.map((k) => fmt(k, 2)).join(', ') || '—'}</span>
                </div>
              </div>
            )}
          </Card>

          {data && (
            <Card title="Legs" subtitle="Every position priced at theoretical value">
              <LegTable legs={data.legs} netCost={data.net_cost} />
            </Card>
          )}
        </div>
      </div>

      {data && (
        <Card
          title="Payoff"
          subtitle="At expiry versus mark-to-market today — the gap is time value"
        >
          <PayoffChart curve={data.curve} spot={request.spot} breakevens={data.breakevens} />
        </Card>
      )}
    </div>
  )
}
