import { useState, type FC } from 'react'

import { AttributionChart } from '@/components/charts/AttributionChart'
import { InventoryChart } from '@/components/charts/InventoryChart'
import { SweepChart } from '@/components/charts/SweepChart'
import { Card } from '@/components/ui/Card'
import { NumberField } from '@/components/ui/NumberField'
import { Stat } from '@/components/ui/Stat'
import { apiErrorMessage } from '@/lib/api'
import { useRiskAversionSweep, useSimulation } from '@/lib/marketmaking'
import { cn, fmt, signClass } from '@/lib/utils'
import type { SimulateRequest } from '@/types/marketmaking'

const DEFAULTS: SimulateRequest = {
  spot: 100,
  drift: 0,
  rate: 0.04,
  div_yield: 0,
  strike: 100,
  expiry: 0.25,
  option_type: 'call',
  horizon: 1 / 52,
  steps: 300,
  risk_aversion: 0.1,
  order_flow_intensity: 6000,
  order_flow_decay: 8,
  min_half_spread: 0.01,
  max_position: 25,
  hedge_delta: true,
  hedge_threshold: 0.5,
  hedge_cost_bps: 1,
  atm_vol: 0.2,
  skew: -0.12,
  curvature: 0.4,
  seed: 42,
}

const SWEEP_PATHS = 12

export const MarketMakingPanel: FC = () => {
  const [request, setRequest] = useState<SimulateRequest>(DEFAULTS)
  const [sweepOn, setSweepOn] = useState(false)

  const sim = useSimulation(request)
  const sweep = useRiskAversionSweep(request, SWEEP_PATHS, sweepOn)

  const set = <K extends keyof SimulateRequest>(key: K, next: SimulateRequest[K]) =>
    setRequest((prev) => ({ ...prev, [key]: next }))

  const data = sim.data
  const a = data?.attribution

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <div className="flex flex-col gap-4">
          <Card title="Maker" subtitle="Avellaneda-Stoikov quoting">
            <div className="grid grid-cols-2 gap-3">
              <NumberField
                label="Risk aversion"
                value={request.risk_aversion}
                onChange={(v) => set('risk_aversion', v)}
                step={0.05}
                min={0}
                className="col-span-2"
                hint={request.risk_aversion === 0 ? 'naive: no skew, no widening' : 'skews and widens'}
              />
              <NumberField
                label="Flow rate"
                value={request.order_flow_intensity}
                onChange={(v) => set('order_flow_intensity', v)}
                step={500}
                min={1}
                hint="arrivals / year"
              />
              <NumberField
                label="Flow decay"
                value={request.order_flow_decay}
                onChange={(v) => set('order_flow_decay', v)}
                step={0.5}
                min={0.1}
                hint="impatience"
              />
              <NumberField
                label="Min half-spread"
                value={request.min_half_spread}
                onChange={(v) => set('min_half_spread', v)}
                step={0.005}
                min={0}
              />
              <NumberField
                label="Position limit"
                value={request.max_position}
                onChange={(v) => set('max_position', v)}
                step={5}
                min={1}
              />
            </div>
          </Card>

          <Card title="Hedging">
            <div className="flex flex-col gap-3">
              <button
                type="button"
                aria-pressed={request.hedge_delta}
                onClick={() => set('hedge_delta', !request.hedge_delta)}
                className={cn(
                  'rounded-md border px-3 py-1.5 text-sm transition-colors',
                  request.hedge_delta
                    ? 'border-term-accent/40 bg-term-accent/15 text-term-accent'
                    : 'border-term-border text-term-muted hover:text-term-text'
                )}
              >
                Delta hedging {request.hedge_delta ? 'on' : 'off'}
              </button>
              <div className="grid grid-cols-2 gap-3">
                <NumberField
                  label="Threshold"
                  value={request.hedge_threshold}
                  onChange={(v) => set('hedge_threshold', v)}
                  step={0.1}
                  min={0.01}
                  hint="delta band"
                />
                <NumberField
                  label="Cost"
                  value={request.hedge_cost_bps}
                  onChange={(v) => set('hedge_cost_bps', v)}
                  step={0.5}
                  min={0}
                  suffix="bps"
                />
              </div>
            </div>
          </Card>

          <Card title="Market">
            <div className="grid grid-cols-2 gap-3">
              <NumberField label="Spot" value={request.spot} onChange={(v) => set('spot', v)} step={1} min={0.01} />
              <NumberField label="Strike" value={request.strike} onChange={(v) => set('strike', v)} step={1} min={0.01} />
              <NumberField
                label="ATM vol"
                value={request.atm_vol}
                onChange={(v) => set('atm_vol', v)}
                step={0.01}
                min={0.001}
                hint={`${(request.atm_vol * 100).toFixed(1)}%`}
              />
              <NumberField
                label="Expiry"
                value={request.expiry}
                onChange={(v) => set('expiry', v)}
                step={0.05}
                min={0.02}
                suffix="yrs"
              />
              <NumberField
                label="Session"
                value={request.horizon}
                onChange={(v) => set('horizon', v)}
                step={0.005}
                min={0.001}
                hint={`${(request.horizon * 365).toFixed(1)} days`}
              />
              <NumberField
                label="Steps"
                value={request.steps}
                onChange={(v) => set('steps', Math.round(v))}
                step={50}
                min={10}
                max={2000}
              />
              <NumberField
                label="Seed"
                value={request.seed}
                onChange={(v) => set('seed', Math.max(0, Math.round(v)))}
                step={1}
                min={0}
                className="col-span-2"
                hint="same seed replays the same flow"
              />
            </div>
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          <Card title="Session" subtitle="P&L split by where it came from">
            {sim.error && <p className="text-sm text-term-short">{apiErrorMessage(sim.error)}</p>}
            {sim.isPending && <p className="text-sm text-term-muted">Running…</p>}

            {data && a && (
              <div className="flex flex-col gap-5">
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Stat
                    label="Total P&L"
                    value={fmt(a.total_pnl, 3)}
                    note="per contract unit"
                    emphasis
                    valueClassName={signClass(a.total_pnl)}
                  />
                  <Stat
                    label="Spread capture"
                    value={fmt(a.spread_pnl, 3)}
                    note="the business"
                    valueClassName="text-term-long"
                  />
                  <Stat
                    label="Inventory"
                    value={fmt(a.inventory_pnl, 3)}
                    note="cost of doing it"
                    valueClassName={signClass(a.inventory_pnl)}
                  />
                  <Stat
                    label="Hedge"
                    value={fmt(a.hedge_pnl, 3)}
                    note={`${data.hedge_trades} trades`}
                    valueClassName={signClass(a.hedge_pnl)}
                  />
                </div>

                <div className="grid grid-cols-2 gap-4 border-t border-term-border pt-4 sm:grid-cols-4">
                  <Stat label="Fills" value={String(data.fills)} note={`${data.buys} buy / ${data.sells} sell`} />
                  <Stat label="Edge per fill" value={fmt(data.capture_per_fill, 4)} note="average" />
                  <Stat
                    label="Peak inventory"
                    value={fmt(data.max_abs_inventory, 1)}
                    note={`ended ${fmt(data.ending_inventory, 1)}`}
                  />
                  <Stat
                    label="Realised vol"
                    value={`${(data.realised_vol * 100).toFixed(1)}%`}
                    note={`implied ${(data.implied_vol_at_open * 100).toFixed(1)}%`}
                  />
                </div>

                {a.spread_pnl > 0 && Math.abs(a.inventory_pnl) > a.spread_pnl && (
                  <div className="rounded-md border border-term-warn/30 bg-term-warn/10 p-3">
                    <p className="text-xs font-medium text-term-warn">
                      Inventory dominates this session
                    </p>
                    <p className="mt-1 text-[11px] leading-relaxed text-term-muted">
                      Mark-to-market moved this P&amp;L more than spread capture did, so the result
                      says more about which way the underlying went than about the quoting. Raise
                      risk aversion, or run the sweep to see the average across paths — a single
                      session is not evidence either way.
                    </p>
                  </div>
                )}
              </div>
            )}
          </Card>

          {data && (
            <Card title="Path">
              <div className="grid gap-6 xl:grid-cols-2">
                <InventoryChart steps={data.steps} />
                <AttributionChart steps={data.steps} />
              </div>
            </Card>
          )}
        </div>
      </div>

      <Card
        title="Is the skew worth it?"
        subtitle="One session proves nothing — average many paths per setting"
        actions={
          <button
            type="button"
            onClick={() => setSweepOn(true)}
            disabled={sweepOn && sweep.isFetching}
            className="rounded-md border border-term-border px-3 py-1 text-xs text-term-muted hover:text-term-text disabled:opacity-50"
          >
            {sweepOn && sweep.isFetching ? 'Running…' : 'Run sweep'}
          </button>
        }
      >
        {!sweepOn && (
          <p className="text-xs leading-relaxed text-term-muted">
            Sweeps risk aversion from 0 (naive symmetric quoting) upward, averaging{' '}
            {SWEEP_PATHS} paths at each setting. Expect an interior optimum: quoting wider earns
            more per fill but wins fewer of them, so caution pays only up to a point. This runs
            several hundred simulations and takes a moment.
          </p>
        )}
        {sweep.error && <p className="text-sm text-term-short">{apiErrorMessage(sweep.error)}</p>}
        {sweepOn && sweep.isFetching && !sweep.data && (
          <p className="text-sm text-term-muted">Averaging paths…</p>
        )}
        {sweep.data && <SweepChart points={sweep.data.points} paths={sweep.data.paths_per_point} />}
      </Card>
    </div>
  )
}
