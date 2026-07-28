/** Recharts styling shared by every chart. Kept out of component files so
 *  Fast Refresh stays component-only. Values mirror the palette in index.css. */

export const AXIS = {
  stroke: '#7d8b9a',
  fontSize: 11,
} as const

export const GRID_STROKE = '#1f2933'

export const ZERO_LINE = '#3a4753'

export const SERIES = {
  primary: '#38bdf8',
  secondary: '#34d399',
  muted: '#7d8b9a',
} as const

export const TOOLTIP_STYLE = {
  backgroundColor: '#121820',
  border: '1px solid #1f2933',
  borderRadius: '6px',
  fontSize: '12px',
} as const
