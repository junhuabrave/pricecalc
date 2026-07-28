import { useEffect, useId, useState, type FC } from 'react'

import { cn } from '@/lib/utils'

interface NumberFieldProps {
  label: string
  value: number
  onChange: (value: number) => void
  step?: number
  min?: number
  max?: number
  /** Trailing unit shown inside the field, e.g. "%" or "yrs". */
  suffix?: string
  hint?: string
  className?: string
}

/**
 * Number input that keeps its own draft string while focused.
 *
 * Binding a number straight to the DOM value makes intermediate states like
 * "0." or "-" unrepresentable, so the field fights the user mid-typing. We
 * hold the raw text, push up only parseable values, and re-sync from props
 * whenever the committed number changes from outside.
 */
export const NumberField: FC<NumberFieldProps> = ({
  label,
  value,
  onChange,
  step = 1,
  min,
  max,
  suffix,
  hint,
  className,
}) => {
  const id = useId()
  const [draft, setDraft] = useState(String(value))

  useEffect(() => {
    if (Number.parseFloat(draft) !== value) setDraft(String(value))
    // Re-syncing on `draft` would clobber typing; the committed value is the source of truth.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  const commit = (raw: string) => {
    setDraft(raw)
    const parsed = Number.parseFloat(raw)
    if (Number.isFinite(parsed)) onChange(parsed)
  }

  const invalid =
    draft.trim() !== '' &&
    (!Number.isFinite(Number.parseFloat(draft)) ||
      (min !== undefined && Number.parseFloat(draft) < min) ||
      (max !== undefined && Number.parseFloat(draft) > max))

  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <label htmlFor={id} className="text-xs font-medium text-term-muted">
        {label}
      </label>
      <div className="relative">
        <input
          id={id}
          type="number"
          inputMode="decimal"
          value={draft}
          step={step}
          onChange={(e) => commit(e.target.value)}
          onBlur={() => setDraft(String(value))}
          aria-invalid={invalid}
          className={cn(
            'w-full rounded-md border bg-term-bg px-2.5 py-1.5 text-right text-sm',
            'focus:outline-none focus:ring-1',
            suffix && 'pr-9',
            invalid
              ? 'border-term-short focus:ring-term-short'
              : 'border-term-border focus:border-term-accent focus:ring-term-accent'
          )}
        />
        {suffix && (
          <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-xs text-term-muted">
            {suffix}
          </span>
        )}
      </div>
      {hint && <p className="text-[11px] text-term-muted">{hint}</p>}
    </div>
  )
}
