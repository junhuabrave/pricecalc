import type { FC } from 'react'

import { cn, fmt } from '@/lib/utils'
import type { LegOut } from '@/types/strategy'

interface LegTableProps {
  legs: LegOut[]
  netCost: number
}

export const LegTable: FC<LegTableProps> = ({ legs, netCost }) => (
  <div className="overflow-x-auto">
    <table className="w-full min-w-[420px] text-xs">
      <thead>
        <tr className="text-left text-term-muted">
          <th className="pb-1.5 font-medium">Leg</th>
          <th className="pb-1.5 text-right font-medium">Qty</th>
          <th className="pb-1.5 text-right font-medium">Entry</th>
          <th className="pb-1.5 text-right font-medium">Cash</th>
        </tr>
      </thead>
      <tbody className="font-mono tabular-nums">
        {legs.map((leg, i) => {
          const cash = -leg.quantity * leg.entry_price
          return (
            <tr key={`${leg.label}-${i}`} className="border-t border-term-border/60">
              <td className="py-1.5 pr-2 font-sans">{leg.label}</td>
              <td
                className={cn(
                  'py-1.5 text-right',
                  leg.quantity > 0 ? 'text-term-long' : 'text-term-short'
                )}
              >
                {leg.quantity > 0 ? '+' : ''}
                {fmt(leg.quantity, 2)}
              </td>
              <td className="py-1.5 text-right text-term-muted">{fmt(leg.entry_price, 4)}</td>
              <td
                className={cn(
                  'py-1.5 text-right',
                  cash >= 0 ? 'text-term-long' : 'text-term-short'
                )}
              >
                {cash >= 0 ? '+' : ''}
                {fmt(cash, 4)}
              </td>
            </tr>
          )
        })}
        <tr className="border-t border-term-border">
          <td className="py-2 font-sans font-medium" colSpan={3}>
            {netCost >= 0 ? 'Net debit paid' : 'Net credit received'}
          </td>
          <td
            className={cn(
              'py-2 text-right font-semibold',
              netCost >= 0 ? 'text-term-short' : 'text-term-long'
            )}
          >
            {netCost >= 0 ? '−' : '+'}
            {fmt(Math.abs(netCost), 4)}
          </td>
        </tr>
      </tbody>
    </table>
  </div>
)
