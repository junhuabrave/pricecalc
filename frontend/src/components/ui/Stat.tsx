import type { FC } from 'react'

import { cn } from '@/lib/utils'

interface StatProps {
  label: string
  value: string
  /** Unit convention or interpretation, shown small beneath the number. */
  note?: string
  valueClassName?: string
  emphasis?: boolean
}

export const Stat: FC<StatProps> = ({ label, value, note, valueClassName, emphasis }) => (
  <div className="flex flex-col gap-0.5">
    <span className="text-xs text-term-muted">{label}</span>
    <span
      className={cn(
        'font-mono tabular-nums',
        emphasis ? 'text-2xl font-semibold' : 'text-base',
        valueClassName
      )}
    >
      {value}
    </span>
    {note && <span className="text-[11px] text-term-muted">{note}</span>}
  </div>
)
