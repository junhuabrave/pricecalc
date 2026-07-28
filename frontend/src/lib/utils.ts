import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Merge Tailwind classes, letting later conditional classes win over earlier ones. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

/** Fixed-decimal formatter that keeps `-0.00` from appearing in risk columns. */
export function fmt(value: number, digits = 4): string {
  if (!Number.isFinite(value)) return '—'
  const rounded = Number(value.toFixed(digits))
  return (Object.is(rounded, -0) ? 0 : rounded).toFixed(digits)
}

export function fmtPct(value: number, digits = 2): string {
  if (!Number.isFinite(value)) return '—'
  return `${(value * 100).toFixed(digits)}%`
}

/** Sign-driven colour for P&L and risk figures. */
export function signClass(value: number): string {
  if (value > 0) return 'text-term-long'
  if (value < 0) return 'text-term-short'
  return 'text-term-muted'
}
