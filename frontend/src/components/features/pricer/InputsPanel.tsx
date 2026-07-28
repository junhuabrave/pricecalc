import type { FC } from 'react'

import { NumberField } from '@/components/ui/NumberField'
import { cn } from '@/lib/utils'
import { useMarketStore } from '@/stores/useMarketStore'
import type { OptionType } from '@/types/pricing'

const OPTION_TYPES: readonly OptionType[] = ['call', 'put']

export const InputsPanel: FC = () => {
  const { spot, strike, rate, divYield, vol, tauYears, optionType, set, reset } = useMarketStore()

  return (
    <div className="flex flex-col gap-4">
      <div role="group" aria-label="Option type" className="flex rounded-md border border-term-border p-0.5">
        {OPTION_TYPES.map((t) => (
          <button
            key={t}
            type="button"
            aria-pressed={optionType === t}
            onClick={() => set('optionType', t)}
            className={cn(
              'flex-1 rounded px-3 py-1.5 text-sm capitalize transition-colors',
              optionType === t
                ? 'bg-term-accent/15 text-term-accent'
                : 'text-term-muted hover:text-term-text'
            )}
          >
            {t}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <NumberField label="Spot (S)" value={spot} onChange={(v) => set('spot', v)} step={1} min={0.0001} />
        <NumberField
          label="Strike (K)"
          value={strike}
          onChange={(v) => set('strike', v)}
          step={1}
          min={0.0001}
        />
        <NumberField
          label="Volatility (σ)"
          value={vol}
          onChange={(v) => set('vol', v)}
          step={0.01}
          min={0.0001}
          max={10}
          hint={`${(vol * 100).toFixed(1)}% annualised`}
        />
        <NumberField
          label="Time to expiry (τ)"
          value={tauYears}
          onChange={(v) => set('tauYears', v)}
          step={0.25}
          min={0}
          suffix="yrs"
          hint={`${Math.round(tauYears * 365)} days`}
        />
        <NumberField
          label="Risk-free rate (r)"
          value={rate}
          onChange={(v) => set('rate', v)}
          step={0.005}
          min={-0.5}
          max={1}
          hint={`${(rate * 100).toFixed(2)}%`}
        />
        <NumberField
          label="Dividend yield (q)"
          value={divYield}
          onChange={(v) => set('divYield', v)}
          step={0.005}
          min={-0.5}
          max={1}
          hint={`${(divYield * 100).toFixed(2)}%`}
        />
      </div>

      <button
        type="button"
        onClick={reset}
        className="self-start text-xs text-term-muted underline underline-offset-2 hover:text-term-text"
      >
        Reset to defaults
      </button>
    </div>
  )
}
