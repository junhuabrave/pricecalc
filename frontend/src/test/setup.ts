import '@testing-library/jest-dom/vitest'

// Recharts' ResponsiveContainer measures its parent, which jsdom reports as 0x0
// and then renders nothing. Stub the observer and force a non-zero box so chart
// children actually mount in tests.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}

globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

for (const [prop, value] of [
  ['offsetWidth', 800],
  ['offsetHeight', 400],
  ['clientWidth', 800],
  ['clientHeight', 400],
] as const) {
  Object.defineProperty(HTMLElement.prototype, prop, { configurable: true, value })
}

HTMLElement.prototype.getBoundingClientRect = function (): DOMRect {
  return {
    width: 800,
    height: 400,
    top: 0,
    left: 0,
    right: 800,
    bottom: 400,
    x: 0,
    y: 0,
    toJSON: () => ({}),
  } as DOMRect
}
