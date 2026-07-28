import { useState, type FC } from 'react'

import { cn, fmt } from '@/lib/utils'
import { VIOLATION_LABELS, type Violation } from '@/types/arbitrage'

interface ViolationCardProps {
  violation: Violation
  /** Rank in the ranked list; 0 is the richest finding. */
  rank: number
}

export const ViolationCard: FC<ViolationCardProps> = ({ violation, rank }) => {
  const [open, setOpen] = useState(rank === 0)
  const net = violation.legs.reduce((sum, leg) => sum + leg.cash_flow, 0)

  return (
    <div className="rounded-md border border-term-border bg-term-bg">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start justify-between gap-4 px-3 py-2.5 text-left hover:bg-term-panel/60"
      >
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="rounded-sm bg-term-warn/15 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-term-warn">
              {VIOLATION_LABELS[violation.kind]}
            </span>
            <span className="text-[11px] text-term-muted">{violation.tau.toFixed(2)}y</span>
          </div>
          <p className="mt-1 truncate text-sm">{violation.summary}</p>
        </div>
        <div className="shrink-0 text-right">
          <div className="font-mono text-base font-semibold tabular-nums text-term-long">
            +{fmt(violation.profit, 4)}
          </div>
          <div className="text-[10px] text-term-muted">locked in</div>
        </div>
      </button>

      {open && (
        <div className="border-t border-term-border px-3 py-3">
          <p className="text-xs leading-relaxed text-term-muted">{violation.detail}</p>

          <table className="mt-3 w-full text-xs">
            <thead>
              <tr className="text-left text-term-muted">
                <th className="pb-1 font-medium">Leg</th>
                <th className="pb-1 text-right font-medium">Qty</th>
                <th className="pb-1 text-right font-medium">Price</th>
                <th className="pb-1 text-right font-medium">Cash today</th>
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums">
              {violation.legs.map((leg, i) => (
                <tr key={`${leg.instrument}-${i}`} className="border-t border-term-border/60">
                  <td className="py-1 pr-2 font-sans">{leg.instrument}</td>
                  <td
                    className={cn(
                      'py-1 text-right',
                      leg.quantity > 0 ? 'text-term-long' : 'text-term-short'
                    )}
                  >
                    {leg.quantity > 0 ? '+' : ''}
                    {fmt(leg.quantity, 4)}
                  </td>
                  <td className="py-1 text-right text-term-muted">{fmt(leg.price, 4)}</td>
                  <td
                    className={cn(
                      'py-1 text-right',
                      leg.cash_flow >= 0 ? 'text-term-long' : 'text-term-short'
                    )}
                  >
                    {leg.cash_flow >= 0 ? '+' : ''}
                    {fmt(leg.cash_flow, 4)}
                  </td>
                </tr>
              ))}
              <tr className="border-t border-term-border">
                <td className="py-1.5 font-sans font-medium" colSpan={3}>
                  Net credit today
                </td>
                <td className="py-1.5 text-right font-semibold text-term-long">
                  +{fmt(net, 4)}
                </td>
              </tr>
            </tbody>
          </table>

          <p className="mt-2 text-[11px] text-term-muted">
            Legs execute at the quotes shown — buys lift the offer, sells hit the bid. Hold to
            expiry and every path cancels; the net credit is the profit.
          </p>
        </div>
      )}
    </div>
  )
}
