import { describe, expect, it } from 'vitest'

import { cn, fmt, fmtPct, signClass } from '@/lib/utils'

describe('cn', () => {
  it('lets a later class override an earlier one in the same group', () => {
    expect(cn('px-2 text-sm', 'px-4')).toBe('text-sm px-4')
  })

  it('drops falsy entries', () => {
    expect(cn('a', false, undefined, 'b')).toBe('a b')
  })
})

describe('fmt', () => {
  it('pads to the requested precision', () => {
    expect(fmt(1.5, 4)).toBe('1.5000')
  })

  it('normalises negative zero so risk columns never show -0.00', () => {
    expect(fmt(-0.00001, 2)).toBe('0.00')
    expect(fmt(-0, 2)).toBe('0.00')
  })

  it('renders non-finite input as an em dash rather than NaN', () => {
    expect(fmt(Number.NaN)).toBe('—')
    expect(fmt(Number.POSITIVE_INFINITY)).toBe('—')
  })
})

describe('fmtPct', () => {
  it('scales a decimal rate into percent', () => {
    expect(fmtPct(0.2)).toBe('20.00%')
  })
})

describe('signClass', () => {
  it('maps sign to the long/short palette', () => {
    expect(signClass(1)).toContain('long')
    expect(signClass(-1)).toContain('short')
    expect(signClass(0)).toContain('muted')
  })
})
