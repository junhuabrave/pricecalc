import type { FC } from 'react'

import { cn } from '@/lib/utils'

export interface TabDef {
  id: string
  label: string
  /** Marks a scenario that is scaffolded but not yet implemented. */
  comingSoon?: boolean
}

interface TabsProps {
  tabs: readonly TabDef[]
  active: string
  onSelect: (id: string) => void
}

export const Tabs: FC<TabsProps> = ({ tabs, active, onSelect }) => (
  <nav role="tablist" aria-label="Scenario" className="flex gap-1 border-b border-term-border">
    {tabs.map((tab) => {
      const selected = tab.id === active
      return (
        <button
          key={tab.id}
          role="tab"
          type="button"
          aria-selected={selected}
          onClick={() => onSelect(tab.id)}
          className={cn(
            'relative -mb-px flex items-center gap-2 border-b-2 px-4 py-2.5 text-sm transition-colors',
            selected
              ? 'border-term-accent text-term-text'
              : 'border-transparent text-term-muted hover:text-term-text'
          )}
        >
          {tab.label}
          {tab.comingSoon && (
            <span className="rounded-sm bg-term-border px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-term-muted">
              soon
            </span>
          )}
        </button>
      )
    })}
  </nav>
)
