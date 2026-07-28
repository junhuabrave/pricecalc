import type { FC } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { ChartFrame } from '@/components/charts/ChartFrame'
import { AXIS, GRID_STROKE, SERIES, TOOLTIP_STYLE } from '@/components/charts/chartTheme'
import { fmt } from '@/lib/utils'
import type { SweepPoint } from '@/types/pricing'

interface PriceVsSpotChartProps {
  points: SweepPoint[]
  spot: number
  strike: number
}

/**
 * Model value against payoff-at-expiry. The gap between the two lines is time
 * value — it peaks at the strike and decays to zero in both wings.
 */
export const PriceVsSpotChart: FC<PriceVsSpotChartProps> = ({ points, spot, strike }) => (
  <ChartFrame title="Value vs spot">
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
        <YAxis tickFormatter={(v: number) => v.toFixed(1)} {...AXIS} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          labelFormatter={(v: unknown) => `Spot ${fmt(Number(v), 2)}`}
          formatter={(v: unknown, name: unknown) => [fmt(Number(v), 4), String(name)]}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <ReferenceLine x={strike} stroke={SERIES.muted} strokeDasharray="4 4" label={{ value: 'K', fill: SERIES.muted, fontSize: 10 }} />
        <ReferenceLine x={spot} stroke={SERIES.primary} strokeDasharray="4 4" label={{ value: 'S', fill: SERIES.primary, fontSize: 10 }} />
        <Line
          type="monotone"
          dataKey="intrinsic"
          name="Intrinsic"
          stroke={SERIES.muted}
          strokeWidth={1.5}
          strokeDasharray="5 4"
          dot={false}
        />
        <Line
          type="monotone"
          dataKey="price"
          name="Model value"
          stroke={SERIES.primary}
          strokeWidth={2}
          dot={false}
        />
      </LineChart>
    </ResponsiveContainer>
  </ChartFrame>
)
