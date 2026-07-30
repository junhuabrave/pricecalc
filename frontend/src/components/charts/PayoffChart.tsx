import type { FC } from 'react'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { ChartFrame } from '@/components/charts/ChartFrame'
import { AXIS, GRID_STROKE, SERIES, TOOLTIP_STYLE, ZERO_LINE } from '@/components/charts/chartTheme'
import { fmt } from '@/lib/utils'
import type { PayoffPoint } from '@/types/strategy'

interface PayoffChartProps {
  curve: PayoffPoint[]
  spot: number
  breakevens: number[]
}

/**
 * P&L at expiry against mark-to-market P&L today.
 *
 * The gap between the two lines is remaining time value — it is widest at the
 * strikes and closes to nothing in the wings, which is the clearest visual
 * statement of what an option position actually owns.
 */
export const PayoffChart: FC<PayoffChartProps> = ({ curve, spot, breakevens }) => (
  <ChartFrame title="P&L vs terminal spot" height={320}>
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={curve} margin={{ top: 4, right: 8, bottom: 4, left: -8 }}>
        <defs>
          <linearGradient id="payoff-positive" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={SERIES.secondary} stopOpacity={0.28} />
            <stop offset="100%" stopColor={SERIES.secondary} stopOpacity={0} />
          </linearGradient>
        </defs>

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

        <ReferenceLine y={0} stroke={ZERO_LINE} />
        {breakevens.map((b) => (
          <ReferenceLine
            key={b}
            x={b}
            stroke={SERIES.muted}
            strokeDasharray="4 4"
            label={{ value: 'BE', fill: SERIES.muted, fontSize: 10, position: 'top' }}
          />
        ))}
        <ReferenceLine
          x={spot}
          stroke={SERIES.primary}
          strokeDasharray="4 4"
          label={{ value: 'S', fill: SERIES.primary, fontSize: 10 }}
        />

        <Area
          type="monotone"
          dataKey="payoff"
          name="At expiry"
          stroke={SERIES.secondary}
          strokeWidth={2}
          fill="url(#payoff-positive)"
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="value"
          name="Today"
          stroke={SERIES.primary}
          strokeWidth={1.75}
          strokeDasharray="5 4"
          dot={false}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  </ChartFrame>
)
