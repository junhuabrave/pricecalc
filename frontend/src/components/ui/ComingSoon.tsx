import type { FC } from 'react'

import { Card } from '@/components/ui/Card'

interface ComingSoonProps {
  title: string
  summary: string
  /** The concrete pieces this scenario still needs — a spec, not a placeholder. */
  planned: readonly string[]
  /** Backend modules to be added under `pricecalc.core`. */
  modules: readonly string[]
}

export const ComingSoon: FC<ComingSoonProps> = ({ title, summary, planned, modules }) => (
  <Card title={title} subtitle={summary}>
    <div className="grid gap-6 md:grid-cols-2">
      <div>
        <h3 className="text-xs font-medium uppercase tracking-wide text-term-muted">Planned</h3>
        <ul className="mt-2 flex flex-col gap-1.5">
          {planned.map((item) => (
            <li key={item} className="flex gap-2 text-sm text-term-text">
              <span aria-hidden className="text-term-border">
                ▸
              </span>
              {item}
            </li>
          ))}
        </ul>
      </div>
      <div>
        <h3 className="text-xs font-medium uppercase tracking-wide text-term-muted">
          Backend modules
        </h3>
        <ul className="mt-2 flex flex-col gap-1.5">
          {modules.map((m) => (
            <li key={m} className="font-mono text-xs text-term-muted">
              {m}
            </li>
          ))}
        </ul>
      </div>
    </div>
  </Card>
)
