import type { FC } from 'react'
import {
  Bar,
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
import type { SweepPoint } from '@/types/marketmaking'

interface SweepChartProps {
  points: SweepPoint[]
  paths: number
}

/**
 * Average P&L and inventory against risk aversion.
 *
 * The interesting shape is the interior optimum. Quoting wider earns more per
 * fill but wins fewer of them, so caution pays only up to a point — after which
 * the maker is simply not trading. A monotone curve here would mean one of the
 * two effects is missing from the model.
 */
export const SweepChart: FC<SweepChartProps> = ({ points, paths }) => (
  <ChartFrame title={`Risk aversion sweep — mean of ${paths} paths per setting`} height={300}>
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={points} margin={{ top: 4, right: 8, bottom: 4, left: -12 }}>
        <CartesianGrid stroke={GRID_STROKE} strokeDasharray="3 3" />
        <XAxis
          dataKey="risk_aversion"
          type="number"
          scale="linear"
          domain={['dataMin', 'dataMax']}
          tickFormatter={(v: number) => v.toFixed(2)}
          {...AXIS}
        />
        <YAxis yAxisId="pnl" tickFormatter={(v: number) => v.toFixed(1)} {...AXIS} />
        <YAxis
          yAxisId="inv"
          orientation="right"
          tickFormatter={(v: number) => v.toFixed(0)}
          {...AXIS}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          labelFormatter={(v: unknown) => `Risk aversion ${fmt(Number(v), 2)}`}
          formatter={(v: unknown, name: unknown) => [fmt(Number(v), 3), String(name)]}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <ReferenceLine yAxisId="pnl" y={0} stroke={ZERO_LINE} />
        <Bar
          yAxisId="inv"
          dataKey="max_abs_inventory"
          name="Peak inventory"
          fill={SERIES.muted}
          fillOpacity={0.25}
          isAnimationActive={false}
        />
        <Line
          yAxisId="pnl"
          type="monotone"
          dataKey="spread_pnl"
          name="Spread capture"
          stroke={SERIES.secondary}
          strokeWidth={1.5}
          dot={{ r: 2 }}
          isAnimationActive={false}
        />
        <Line
          yAxisId="pnl"
          type="monotone"
          dataKey="total_pnl"
          name="Total P&L"
          stroke={SERIES.primary}
          strokeWidth={2.25}
          dot={{ r: 3 }}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  </ChartFrame>
)
