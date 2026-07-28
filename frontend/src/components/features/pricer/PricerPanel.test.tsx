import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { PricerPanel } from '@/components/features/pricer/PricerPanel'
import { api } from '@/lib/api'
import { useMarketStore } from '@/stores/useMarketStore'

// The maths is covered by the backend suite; here we only assert that the panel
// sends the store's state vector and renders what comes back.
const EVALUATE_RESPONSE = {
  price: 10.450583572185565,
  greeks: {
    delta: 0.6368,
    gamma: 0.0187,
    vega: 0.3752,
    theta: -0.0176,
    rho: 0.5323,
    vanna: -0.0028,
    volga: 0.0008,
  },
  d1: 0.35,
  d2: 0.15,
  forward: 105.127,
  intrinsic: 0,
  time_value: 10.450583572185565,
  moneyness: 0.05,
}

const SWEEP_RESPONSE = {
  points: [
    { spot: 60, price: 0.2, intrinsic: 0, delta: 0.03, gamma: 0.004, vega: 0.05, theta: -0.004 },
    { spot: 100, price: 10.45, intrinsic: 0, delta: 0.64, gamma: 0.019, vega: 0.38, theta: -0.018 },
    { spot: 140, price: 42.1, intrinsic: 40, delta: 0.97, gamma: 0.002, vega: 0.05, theta: -0.004 },
  ],
}

function renderPanel(): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  render(<PricerPanel />, { wrapper })
}

describe('PricerPanel', () => {
  beforeEach(() => {
    useMarketStore.getState().reset()
    vi.spyOn(api, 'post').mockImplementation((url: string) => {
      if (url === '/pricing/evaluate') return Promise.resolve({ data: EVALUATE_RESPONSE })
      if (url === '/pricing/sweep') return Promise.resolve({ data: SWEEP_RESPONSE })
      if (url === '/pricing/implied-vol') return Promise.reject(new Error('not used here'))
      throw new Error(`Unexpected request to ${url}`)
    })
  })

  it('prices the option currently in the store', async () => {
    renderPanel()

    // Scoped to the Valuation card: "10.4506" is also the time value here,
    // because an ATM call has zero intrinsic.
    const valuation = await screen.findByRole('region', { name: 'Valuation' })
    await waitFor(() => {
      expect(within(valuation).getByText('Model value')).toBeInTheDocument()
    })
    expect(within(valuation).getAllByText('10.4506')).toHaveLength(2)

    expect(api.post).toHaveBeenCalledWith('/pricing/evaluate', {
      spot: 100,
      strike: 100,
      rate: 0.05,
      div_yield: 0,
      vol: 0.2,
      tau_years: 1,
      option_type: 'call',
    })
  })

  it('renders every Greek with its unit convention', async () => {
    renderPanel()

    // Scoped: the risk-profile chart has its own Delta/Gamma/Vega/Theta toggles.
    const valuation = await screen.findByRole('region', { name: 'Valuation' })
    await waitFor(() => expect(within(valuation).getByText('Delta')).toBeInTheDocument())

    for (const label of ['Delta', 'Gamma', 'Vega', 'Theta', 'Rho', 'Vanna', 'Volga']) {
      expect(within(valuation).getByText(label)).toBeInTheDocument()
    }
    expect(within(valuation).getByText('per 1 vol point')).toBeInTheDocument()
    expect(within(valuation).getByText('per calendar day')).toBeInTheDocument()
  })

  it('requests a denser grid for the sweep than the default', async () => {
    renderPanel()

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/pricing/sweep',
        expect.objectContaining({ steps: 121 })
      )
    })
  })
})
