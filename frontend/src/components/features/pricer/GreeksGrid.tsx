import type { FC } from 'react'

import { Stat } from '@/components/ui/Stat'
import { fmt, signClass } from '@/lib/utils'
import type { Greeks } from '@/types/pricing'

interface GreeksGridProps {
  greeks: Greeks
}

/** Unit notes matter more than the numbers here — they are the usual source of confusion. */
const ROWS: ReadonlyArray<{ key: keyof Greeks; label: string; note: string; digits: number }> = [
  { key: 'delta', label: 'Delta', note: 'per $1 of spot', digits: 4 },
  { key: 'gamma', label: 'Gamma', note: 'delta per $1 of spot', digits: 5 },
  { key: 'vega', label: 'Vega', note: 'per 1 vol point', digits: 4 },
  { key: 'theta', label: 'Theta', note: 'per calendar day', digits: 4 },
  { key: 'rho', label: 'Rho', note: 'per 1% of rate', digits: 4 },
  { key: 'vanna', label: 'Vanna', note: 'delta per vol point', digits: 5 },
  { key: 'volga', label: 'Volga', note: 'vega per vol point', digits: 5 },
]

export const GreeksGrid: FC<GreeksGridProps> = ({ greeks }) => (
  <div className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-4">
    {ROWS.map(({ key, label, note, digits }) => (
      <Stat
        key={key}
        label={label}
        value={fmt(greeks[key], digits)}
        note={note}
        valueClassName={signClass(greeks[key])}
      />
    ))}
  </div>
)
