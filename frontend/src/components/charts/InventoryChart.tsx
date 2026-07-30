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
import type { MMStep } from '@/types/marketmaking'

interface InventoryChartProps {
  steps: MMStep[]
}

/**
 * Inventory against the skew it produces.
 *
 * These two lines are the model's whole thesis and should mirror each other:
 * inventory rising pushes skew negative, which marks the quotes down and
 * attracts the flow that brings inventory back. If they ever move together,
 * the maker is adding to its own position instead of laying it off.
 */
export const InventoryChart: FC<InventoryChartProps> = ({ steps }) => (
  <ChartFrame title="Inventory and quote skew">
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={steps} margin={{ top: 4, right: 8, bottom: 4, left: -12 }}>
        <defs>
          <linearGradient id="inventory-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={SERIES.primary} stopOpacity={0.25} />
            <stop offset="100%" stopColor={SERIES.primary} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
        <XAxis
          dataKey="t"
          type="number"
          domain={['dataMin', 'dataMax']}
          tickFormatter={(v: number) => (v * 365).toFixed(1)}
          {...AXIS}
        />
        <YAxis yAxisId="inv" tickFormatter={(v: number) => v.toFixed(0)} {...AXIS} />
        <YAxis
          yAxisId="skew"
          orientation="right"
          tickFormatter={(v: number) => v.toFixed(2)}
          {...AXIS}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          labelFormatter={(v: unknown) => `Day ${fmt(Number(v) * 365, 2)}`}
          formatter={(v: unknown, name: unknown) => [fmt(Number(v), 4), String(name)]}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <ReferenceLine yAxisId="inv" y={0} stroke={ZERO_LINE} />
        <Area
          yAxisId="inv"
          type="stepAfter"
          dataKey="inventory"
          name="Inventory"
          stroke={SERIES.primary}
          strokeWidth={1.75}
          fill="url(#inventory-fill)"
          isAnimationActive={false}
        />
        <Line
          yAxisId="skew"
          type="monotone"
          dataKey="skew"
          name="Skew"
          stroke={SERIES.secondary}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  </ChartFrame>
)
