import { useState, type FC } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { ChartFrame } from '@/components/charts/ChartFrame'
import { AXIS, GRID_STROKE, SERIES, TOOLTIP_STYLE, ZERO_LINE } from '@/components/charts/chartTheme'
import { cn, fmt } from '@/lib/utils'
import type { SweepPoint } from '@/types/pricing'

type GreekKey = 'delta' | 'gamma' | 'vega' | 'theta'

const GREEKS: ReadonlyArray<{ key: GreekKey; label: string; digits: number }> = [
  { key: 'delta', label: 'Delta', digits: 4 },
  { key: 'gamma', label: 'Gamma', digits: 5 },
  { key: 'vega', label: 'Vega', digits: 4 },
  { key: 'theta', label: 'Theta', digits: 4 },
]

interface GreekVsSpotChartProps {
  points: SweepPoint[]
  spot: number
  strike: number
}

export const GreekVsSpotChart: FC<GreekVsSpotChartProps> = ({ points, spot, strike }) => {
  const [selected, setSelected] = useState<GreekKey>('delta')
  const digits = GREEKS.find((g) => g.key === selected)?.digits ?? 4

  return (
    <ChartFrame
      title="Greek vs spot"
      right={
        <div className="flex gap-1">
          {GREEKS.map((g) => (
            <button
              key={g.key}
              type="button"
              aria-pressed={selected === g.key}
              onClick={() => setSelected(g.key)}
              className={cn(
                'rounded px-2 py-0.5 text-[11px] transition-colors',
                selected === g.key
                  ? 'bg-term-accent/15 text-term-accent'
                  : 'text-term-muted hover:text-term-text'
              )}
            >
              {g.label}
            </button>
          ))}
        </div>
      }
    >
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 4, right: 8, bottom: 4, left: -12 }}>
          <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
          <XAxis
            dataKey="spot"
            type="number"
            domain={['dataMin', 'dataMax']}
            tickFormatter={(v: number) => v.toFixed(0)}
            {...AXIS}
          />
          <YAxis tickFormatter={(v: number) => fmt(v, digits > 4 ? 3 : 2)} {...AXIS} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            labelFormatter={(v: unknown) => `Spot ${fmt(Number(v), 2)}`}
            formatter={(v: unknown) => [fmt(Number(v), digits), selected]}
          />
          <ReferenceLine y={0} stroke={ZERO_LINE} />
          <ReferenceLine x={strike} stroke={SERIES.muted} strokeDasharray="4 4" />
          <ReferenceLine x={spot} stroke={SERIES.primary} strokeDasharray="4 4" />
          <Line
            type="monotone"
            dataKey={selected}
            stroke={SERIES.secondary}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartFrame>
  )
}
