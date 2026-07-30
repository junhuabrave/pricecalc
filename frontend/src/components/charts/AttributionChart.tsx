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
import { AXIS, GRID_STROKE, SERIES, TOOLTIP_STYLE, ZERO_LINE } from '@/components/charts/chartTheme'
import { fmt } from '@/lib/utils'
import type { MMStep } from '@/types/marketmaking'

interface AttributionChartProps {
  steps: MMStep[]
}

/**
 * Cumulative P&L split by source.
 *
 * The total on its own answers nothing. Spread capture climbing steadily while
 * inventory P&L wanders around zero is a market-making business; a flat spread
 * line and a total driven by inventory is a directional bet wearing a market
 * maker's clothes, and it will reverse.
 */
export const AttributionChart: FC<AttributionChartProps> = ({ steps }) => (
  <ChartFrame title="P&L attribution">
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={steps} margin={{ top: 4, right: 8, bottom: 4, left: -12 }}>
        <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
        <XAxis
          dataKey="t"
          type="number"
          domain={['dataMin', 'dataMax']}
          tickFormatter={(v: number) => (v * 365).toFixed(1)}
          {...AXIS}
        />
        <YAxis tickFormatter={(v: number) => v.toFixed(1)} {...AXIS} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          labelFormatter={(v: unknown) => `Day ${fmt(Number(v) * 365, 2)}`}
          formatter={(v: unknown, name: unknown) => [fmt(Number(v), 4), String(name)]}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <ReferenceLine y={0} stroke={ZERO_LINE} />
        <Line
          type="monotone"
          dataKey="spread_pnl"
          name="Spread capture"
          stroke={SERIES.secondary}
          strokeWidth={1.75}
          dot={false}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="inventory_pnl"
          name="Inventory"
          stroke="#fbbf24"
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="hedge_pnl"
          name="Hedge"
          stroke={SERIES.muted}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
        <Line
          type="monotone"
          dataKey="total_pnl"
          name="Total"
          stroke={SERIES.primary}
          strokeWidth={2.25}
          dot={false}
          isAnimationActive={false}
        />
      </LineChart>
    </ResponsiveContainer>
  </ChartFrame>
)
