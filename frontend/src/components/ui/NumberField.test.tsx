import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import { NumberField } from '@/components/ui/NumberField'

describe('NumberField', () => {
  it('emits the parsed number as the user types', async () => {
    const onChange = vi.fn()
    render(<NumberField label="Spot" value={100} onChange={onChange} />)

    const input = screen.getByLabelText('Spot')
    await userEvent.clear(input)
    await userEvent.type(input, '125')

    expect(onChange).toHaveBeenLastCalledWith(125)
  })

  it('keeps an in-progress decimal without snapping the caret back', async () => {
    // Binding the number directly would rewrite "0." to "0" mid-keystroke.
    function Harness() {
      const [v, setV] = useState(0.2)
      return <NumberField label="Vol" value={v} onChange={setV} />
    }
    render(<Harness />)

    const input = screen.getByLabelText<HTMLInputElement>('Vol')
    await userEvent.clear(input)
    await userEvent.type(input, '0.35')

    expect(input.value).toBe('0.35')
  })

  it('flags a value below the minimum', async () => {
    render(<NumberField label="Spot" value={100} onChange={vi.fn()} min={0} />)

    const input = screen.getByLabelText('Spot')
    await userEvent.clear(input)
    await userEvent.type(input, '-5')

    expect(input).toHaveAttribute('aria-invalid', 'true')
  })

  it('renders the suffix and hint', () => {
    render(
      <NumberField label="Tau" value={1} onChange={vi.fn()} suffix="yrs" hint="365 days" />
    )
    expect(screen.getByText('yrs')).toBeInTheDocument()
    expect(screen.getByText('365 days')).toBeInTheDocument()
  })
})
