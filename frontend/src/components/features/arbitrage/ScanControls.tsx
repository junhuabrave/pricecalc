import type { FC } from 'react'

import { NumberField } from '@/components/ui/NumberField'
import type { ScanRequest } from '@/types/arbitrage'

interface ScanControlsProps {
  value: ScanRequest
  onChange: <K extends keyof ScanRequest>(key: K, next: ScanRequest[K]) => void
}

export const ScanControls: FC<ScanControlsProps> = ({ value, onChange }) => (
  <div className="flex flex-col gap-4">
    <div className="grid grid-cols-2 gap-3">
      <NumberField label="Spot" value={value.spot} onChange={(v) => onChange('spot', v)} step={1} min={0.01} />
      <NumberField
        label="ATM vol"
        value={value.atm_vol}
        onChange={(v) => onChange('atm_vol', v)}
        step={0.01}
        min={0.001}
        hint={`${(value.atm_vol * 100).toFixed(1)}%`}
      />
      <NumberField
        label="Rate"
        value={value.rate}
        onChange={(v) => onChange('rate', v)}
        step={0.005}
        hint={`${(value.rate * 100).toFixed(2)}%`}
      />
      <NumberField
        label="Dividend yield"
        value={value.div_yield}
        onChange={(v) => onChange('div_yield', v)}
        step={0.005}
        min={0}
        hint={value.div_yield > 0 ? 'disables calendar checks' : 'calendar checks active'}
      />
      <NumberField
        label="Skew"
        value={value.skew}
        onChange={(v) => onChange('skew', v)}
        step={0.02}
        hint="negative = equity skew"
      />
      <NumberField
        label="Curvature"
        value={value.curvature}
        onChange={(v) => onChange('curvature', v)}
        step={0.05}
        min={0}
      />
      <NumberField
        label="Strikes"
        value={value.strike_count}
        onChange={(v) => onChange('strike_count', Math.round(v))}
        step={2}
        min={3}
        max={41}
      />
      <NumberField
        label="Spread"
        value={value.spread_bps}
        onChange={(v) => onChange('spread_bps', v)}
        step={10}
        min={0}
        suffix="bps"
      />
    </div>

    <div className="border-t border-term-border pt-4">
      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-term-muted">
        Scanner
      </p>
      <div className="grid grid-cols-2 gap-3">
        <NumberField
          label="Planted mispricings"
          value={value.n_violations}
          onChange={(v) => onChange('n_violations', Math.max(0, Math.round(v)))}
          step={1}
          min={0}
          max={12}
          hint="0 = arbitrage-free chain"
        />
        <NumberField
          label="Min edge"
          value={value.min_edge}
          onChange={(v) => onChange('min_edge', v)}
          step={0.01}
          min={0}
          hint="ignore findings below this"
        />
        <NumberField
          label="Seed"
          value={value.seed}
          onChange={(v) => onChange('seed', Math.max(0, Math.round(v)))}
          step={1}
          min={0}
          className="col-span-2"
          hint="same seed reproduces the same chain"
        />
      </div>
    </div>
  </div>
)
