import { useState, type FC } from 'react'

import { ScanControls } from '@/components/features/arbitrage/ScanControls'
import { ViolationCard } from '@/components/features/arbitrage/ViolationCard'
import { Card } from '@/components/ui/Card'
import { Stat } from '@/components/ui/Stat'
import { apiErrorMessage } from '@/lib/api'
import { useArbitrageScan } from '@/lib/arbitrage'
import { fmt } from '@/lib/utils'
import { VIOLATION_LABELS, type ScanRequest, type ViolationKind } from '@/types/arbitrage'

const DEFAULTS: ScanRequest = {
  spot: 100,
  rate: 0.04,
  div_yield: 0,
  expiries: [0.08, 0.25, 0.5, 1.0],
  strike_count: 11,
  strike_span: 0.3,
  atm_vol: 0.2,
  skew: -0.12,
  curvature: 0.45,
  spread_bps: 80,
  n_violations: 3,
  seed: 42,
  min_edge: 0.01,
}

export const ArbitragePanel: FC = () => {
  const [request, setRequest] = useState<ScanRequest>(DEFAULTS)
  const scan = useArbitrageScan(request)

  const set = <K extends keyof ScanRequest>(key: K, next: ScanRequest[K]) =>
    setRequest((prev) => ({ ...prev, [key]: next }))

  const summary = scan.data?.summary
  const clean = summary?.violations_found === 0

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 lg:grid-cols-[320px_1fr]">
        <Card title="Chain" subtitle="Simulated market, seeded and reproducible">
          <ScanControls value={request} onChange={set} />
        </Card>

        <div className="flex flex-col gap-4">
          <Card title="Scan result" subtitle="Model-free static arbitrage">
            {scan.error && <p className="text-sm text-term-short">{apiErrorMessage(scan.error)}</p>}
            {scan.isPending && <p className="text-sm text-term-muted">Scanning…</p>}

            {summary && (
              <div className="flex flex-col gap-4">
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <Stat
                    label="Violations"
                    value={String(summary.violations_found)}
                    note={`of ${summary.quotes_scanned} quotes`}
                    emphasis
                    valueClassName={clean ? 'text-term-long' : 'text-term-warn'}
                  />
                  <Stat
                    label="Total edge"
                    value={fmt(summary.total_edge, 4)}
                    note="riskless, per unit"
                    valueClassName={summary.total_edge > 0 ? 'text-term-long' : ''}
                  />
                  <Stat
                    label="Planted"
                    value={String(scan.data?.planted.length ?? 0)}
                    note="known mispricings"
                  />
                  <Stat
                    label="Calendar checks"
                    value={summary.calendar_checks_skipped ? 'skipped' : 'active'}
                    note={summary.calendar_checks_skipped ? 'dividends present' : 'q = 0'}
                    valueClassName={summary.calendar_checks_skipped ? 'text-term-muted' : ''}
                  />
                </div>

                {clean && (
                  <div className="rounded-md border border-term-long/30 bg-term-long/10 p-3">
                    <p className="text-xs font-medium text-term-long">
                      No arbitrage — the chain is internally consistent
                    </p>
                    <p className="mt-1 text-[11px] leading-relaxed text-term-muted">
                      Prices come from one smile, so every static bound holds by construction. This
                      is the scanner&apos;s own regression test: a finding here would be a bug in
                      the scanner, not a signal. Plant a mispricing to see it work.
                    </p>
                  </div>
                )}

                {Object.keys(summary.by_kind).length > 0 && (
                  <div className="flex flex-wrap gap-2 border-t border-term-border pt-3">
                    {Object.entries(summary.by_kind).map(([kind, count]) => (
                      <span
                        key={kind}
                        className="rounded-sm border border-term-border px-2 py-0.5 text-[11px] text-term-muted"
                      >
                        {VIOLATION_LABELS[kind as ViolationKind] ?? kind}
                        <span className="ml-1.5 font-mono text-term-text">{count}</span>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </Card>

          {scan.data && scan.data.planted.length > 0 && (
            <Card title="Ground truth" subtitle="What was deliberately broken">
              <ul className="flex flex-col gap-1.5">
                {scan.data.planted.map((p) => (
                  <li key={p} className="flex gap-2 text-xs text-term-muted">
                    <span aria-hidden className="text-term-warn">
                      ▸
                    </span>
                    {p}
                  </li>
                ))}
              </ul>
              <p className="mt-3 text-[11px] leading-relaxed text-term-muted">
                Each plant is solved against the bound it targets, so it is guaranteed detectable.
                One stale quote often trips several checks at once — faithful to how these appear
                on a real screen.
              </p>
            </Card>
          )}
        </div>
      </div>

      {scan.data && scan.data.violations.length > 0 && (
        <Card
          title="Findings"
          subtitle="Ranked by locked-in profit — expand for the replicating trade"
        >
          <div className="flex flex-col gap-2">
            {scan.data.violations.map((v, i) => (
              <ViolationCard
                key={`${v.kind}-${v.tau}-${v.strikes.join('-')}-${i}`}
                violation={v}
                rank={i}
              />
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
