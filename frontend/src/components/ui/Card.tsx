import type { FC, ReactNode } from 'react'

import { cn } from '@/lib/utils'

interface CardProps {
  title?: string
  subtitle?: string
  actions?: ReactNode
  className?: string
  children: ReactNode
}

export const Card: FC<CardProps> = ({ title, subtitle, actions, className, children }) => (
  <section
    aria-label={title}
    className={cn(
      'rounded-lg border border-term-border bg-term-panel shadow-sm shadow-black/40',
      className
    )}
  >
    {(title ?? actions) && (
      <header className="flex items-start justify-between gap-4 border-b border-term-border px-4 py-3">
        <div>
          {title && <h2 className="text-sm font-semibold tracking-wide">{title}</h2>}
          {subtitle && <p className="mt-0.5 text-xs text-term-muted">{subtitle}</p>}
        </div>
        {actions}
      </header>
    )}
    <div className="p-4">{children}</div>
  </section>
)
