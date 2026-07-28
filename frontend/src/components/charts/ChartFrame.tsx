import type { FC, ReactNode } from 'react'

/** Shared chart chrome: title row, optional controls, and a fixed plot height. */
interface ChartFrameProps {
  title: string
  right?: ReactNode
  height?: number
  children: ReactNode
}

export const ChartFrame: FC<ChartFrameProps> = ({ title, right, height = 260, children }) => (
  <div className="flex flex-col gap-2">
    <div className="flex items-center justify-between gap-4">
      <h3 className="text-xs font-medium uppercase tracking-wide text-term-muted">{title}</h3>
      {right}
    </div>
    <div style={{ height }}>{children}</div>
  </div>
)
