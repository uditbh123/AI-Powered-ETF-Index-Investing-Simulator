import { useEffect, useMemo, useState } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ArrowLeft, FlaskConical } from 'lucide-react'
import { Link, useParams } from 'react-router-dom'
import { fetchJSON } from '../api'
import { usePageTitle } from '../hooks/usePageTitle'

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const PRICE_RANGES = [
  { key: '1Y', days: 252 },
  { key: '3Y', days: 756 },
  { key: '5Y', days: 1260 },
  { key: 'MAX', days: Infinity },
]

// Cap on points fed to a chart. Recharts renders every point, so a 25-year
// daily series (~6,300 bars) is downsampled to at most this many by keeping
// every Nth row (plus the last, so the latest close is never dropped).
const MAX_CHART_POINTS = 600

function fmtPrice(value) {
  if (value == null || !Number.isFinite(value)) return '—'
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function fmtPct(value, { signed = true, digits = 2 } = {}) {
  if (value == null || !Number.isFinite(value)) return '—'
  const prefix = signed && value >= 0 ? '+' : ''
  return `${prefix}${value.toFixed(digits)}%`
}

function fmtAxisPrice(value) {
  if (value == null || !Number.isFinite(value)) return ''
  if (Math.abs(value) >= 1000) return `${(value / 1000).toFixed(1)}k`
  return `${Math.round(value)}`
}

function fmtAxisDate(date) {
  const parsed = new Date(date)
  if (Number.isNaN(parsed.getTime())) return date
  return parsed.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
}

function toneClass(value) {
  if (value == null || !Number.isFinite(value)) return 'text-ink-faint'
  return value >= 0 ? 'text-pos' : 'text-neg'
}

/** Downsample to at most ``max`` points, always keeping the first and last. */
function downsample(rows, max) {
  if (!rows || rows.length <= max) return rows || []
  const step = Math.ceil(rows.length / max)
  const out = rows.filter((_, i) => i % step === 0)
  const last = rows[rows.length - 1]
  if (out[out.length - 1] !== last) out.push(last)
  return out
}

/**
 * Diverging cell background for a heatmap, built from the pos/neg CSS tokens.
 *
 * ``value`` is mixed over white toward ``--up`` (positive) or ``--down``
 * (negative) at a strength proportional to |value| / ``maxAbs`` (capped at 72%
 * so ink stays legible on the strongest cell). Returns ``{ background, text }``
 * where ``text`` is a Tailwind class, keeping every colour token sourced from
 * tailwind.config.js rather than an inline hex.
 */
function divergingColor(value, maxAbs) {
  if (value == null || !Number.isFinite(value) || maxAbs <= 0) {
    return { background: 'var(--chart-grid)', text: 'text-ink-faint' }
  }
  const strength = Math.min(72, (Math.abs(value) / maxAbs) * 72)
  const hue = value >= 0 ? 'var(--up)' : 'var(--down)'
  return {
    background: `color-mix(in srgb, ${hue} ${strength.toFixed(1)}%, white)`,
    // Past ~40% strength the mixed background is dark enough that ink text
    // loses contrast, so flip to the white-on-dark label.
    text: strength > 40 ? 'text-white' : 'text-ink',
  }
}

function PanelHeading({ title, hint }) {
  return (
    <div className="panel-title">
      <span>{title}</span>
      {hint ? <span className="font-mono normal-case tracking-normal text-ink-faint">{hint}</span> : null}
    </div>
  )
}

function PriceTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="border border-ink bg-base-panel px-2 py-1.5">
      <div className="text-[11px] uppercase tracking-widest text-ink-faint">{label}</div>
      <div className="num mt-0.5 text-sm text-ink">{fmtPrice(payload[0].value)}</div>
    </div>
  )
}

function VolumeTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const value = payload[0].value
  return (
    <div className="border border-ink bg-base-panel px-2 py-1.5">
      <div className="text-[11px] uppercase tracking-widest text-ink-faint">{label}</div>
      <div className="num mt-0.5 text-sm text-ink">
        {value == null ? '—' : Number(value).toLocaleString()}
      </div>
    </div>
  )
}

function SignedBarTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload
  const value = row.total
  return (
    <div className="border border-ink bg-base-panel px-2 py-1.5">
      <div className="text-[11px] uppercase tracking-widest text-ink-faint">{label}</div>
      <div className={`num mt-0.5 text-sm ${toneClass(value)}`}>{fmtPct(value)}</div>
      {row.annualized != null && (
        <div className="num text-[11px] text-ink-soft">ann. {fmtPct(row.annualized)}</div>
      )}
    </div>
  )
}

function BinTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const row = payload[0].payload
  return (
    <div className="border border-ink bg-base-panel px-2 py-1.5">
      <div className="num text-[11px] text-ink-faint">
        {row.start.toFixed(2)}% → {row.end.toFixed(2)}%
      </div>
      <div className="num mt-0.5 text-sm text-ink">{row.count} days</div>
    </div>
  )
}

function DrawdownTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="border border-ink bg-base-panel px-2 py-1.5">
      <div className="text-[11px] uppercase tracking-widest text-ink-faint">{label}</div>
      <div className="num mt-0.5 text-sm text-neg">{fmtPct(payload[0].value)}</div>
    </div>
  )
}

function Stat({ label, value, tone = '', hint }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-edge-subtle px-3 py-2 last:border-b-0">
      <span className="text-[11px] uppercase tracking-widest text-ink-faint">{label}</span>
      <span className={`num text-sm ${tone}`}>{value}</span>
      {hint ? <span className="text-[11px] leading-tight text-ink-dim">{hint}</span> : null}
    </div>
  )
}

/** Year-by-month return heatmap (rows = years, cols = Jan..Dec). */
function MonthlyHeatmap({ cells }) {
  const byKey = useMemo(() => {
    const map = new Map()
    for (const cell of cells) map.set(`${cell.year}-${cell.month}`, cell.return_pct)
    return map
  }, [cells])

  const years = useMemo(() => {
    const set = new Set(cells.map((c) => c.year))
    return [...set].sort((a, b) => b - a) // newest year first
  }, [cells])

  const maxAbs = useMemo(() => {
    let max = 0
    for (const c of cells) max = Math.max(max, Math.abs(c.return_pct))
    return max || 1
  }, [cells])

  return (
    <div className="overflow-x-auto p-4">
      <div
        className="grid min-w-[520px] gap-[3px]"
        style={{ gridTemplateColumns: `44px repeat(${MONTHS.length}, minmax(0, 1fr))` }}
      >
        <div />
        {MONTHS.map((m) => (
          <div
            key={m}
            className="pb-1 text-center text-[10px] font-semibold uppercase tracking-widest text-ink-faint"
          >
            {m}
          </div>
        ))}
        {years.map((year) => (
          <div key={year} className="contents">
            <div className="num flex items-center pr-2 text-[11px] text-ink-soft">{year}</div>
            {MONTHS.map((_, index) => {
              const month = index + 1
              const value = byKey.get(`${year}-${month}`)
              const color = divergingColor(value, maxAbs)
              return (
                <div
                  key={month}
                  title={
                    value == null
                      ? `${year}-${MONTHS[index]}: no data`
                      : `${year}-${MONTHS[index]}: ${fmtPct(value)}`
                  }
                  className={`flex h-7 items-center justify-center text-[10px] ${color.text}`}
                  style={{ backgroundColor: color.background }}
                >
                  {value == null ? '·' : value.toFixed(1)}
                </div>
              )
            })}
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-3 text-[11px] text-ink-faint">
        <span>Return %</span>
        <span className="text-neg">−{maxAbs.toFixed(1)}</span>
        <span
          className="inline-block h-3 w-24"
          style={{
            background: `linear-gradient(to right, color-mix(in srgb, var(--down) 72%, white), white, color-mix(in srgb, var(--up) 72%, white))`,
          }}
        />
        <span className="text-pos">+{maxAbs.toFixed(1)}</span>
      </div>
    </div>
  )
}

/** Correlation heatmap: symbols down the side and across the top. */
function CorrelationHeatmap({ symbols, matrix }) {
  const maxAbs = useMemo(() => {
    let max = 0
    for (const row of matrix) for (const v of row) if (v != null) max = Math.max(max, Math.abs(v))
    return max || 1
  }, [matrix])

  return (
    <div className="overflow-x-auto p-4">
      <div
        className="grid min-w-[560px] gap-[3px]"
        style={{ gridTemplateColumns: `64px repeat(${symbols.length}, minmax(0, 1fr))` }}
      >
        <div />
        {symbols.map((s) => (
          <div
            key={`col-${s}`}
            className="flex h-10 items-end justify-center pb-1"
            style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
          >
            <span className="num text-[10px] text-ink-soft">{s}</span>
          </div>
        ))}
        {symbols.map((rowSymbol, i) => (
          <div key={`row-${rowSymbol}`} className="contents">
            <div className="num flex items-center pr-2 text-[11px] text-ink-soft">{rowSymbol}</div>
            {symbols.map((colSymbol, j) => {
              const value = matrix[i][j]
              const color = divergingColor(value, maxAbs)
              return (
                <div
                  key={`${rowSymbol}-${colSymbol}`}
                  title={`${rowSymbol} ↔ ${colSymbol}: ${value == null ? 'n/a' : value.toFixed(3)}`}
                  className={`flex h-7 items-center justify-center text-[10px] ${color.text}`}
                  style={{ backgroundColor: color.background }}
                >
                  {value == null ? '·' : value.toFixed(2)}
                </div>
              )
            })}
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-3 text-[11px] text-ink-faint">
        <span>Correlation</span>
        <span className="text-neg">−{maxAbs.toFixed(1)}</span>
        <span
          className="inline-block h-3 w-24"
          style={{
            background: `linear-gradient(to right, color-mix(in srgb, var(--down) 72%, white), white, color-mix(in srgb, var(--up) 72%, white))`,
          }}
        />
        <span className="text-pos">+{maxAbs.toFixed(1)}</span>
      </div>
    </div>
  )
}

export default function EtfDetail() {
  const { symbol } = useParams()
  const [result, setResult] = useState(null) // { symbol, analysis, prices, error? } once settled
  const [range, setRange] = useState('MAX')

  usePageTitle(`${symbol ?? 'ETF'} — ETF Simulator`)

  useEffect(() => {
    let cancelled = false

    Promise.all([
      fetchJSON(`/tickers/${encodeURIComponent(symbol)}/analysis`),
      fetchJSON(`/tickers/${encodeURIComponent(symbol)}/prices?limit=10000`),
    ])
      .then(([analysisData, priceData]) => {
        if (cancelled) return
        setResult({ symbol, analysis: analysisData, prices: priceData.prices || [] })
      })
      .catch((e) => {
        if (cancelled) return
        setResult({ symbol, analysis: null, prices: [], error: e.message })
      })

    return () => {
      cancelled = true
    }
  }, [symbol])

  // A result for a different (previous) symbol still counts as loading, so no
  // synchronous setState is needed in the effect above when the route changes.
  const stale = !result || result.symbol !== symbol
  const loading = stale
  const error = stale ? null : result.error
  const analysis = stale ? null : result.analysis

  const chartData = useMemo(() => {
    const rows = !stale ? result.prices : []
    const rangeDef = PRICE_RANGES.find((r) => r.key === range) || PRICE_RANGES[3]
    if (!Number.isFinite(rangeDef.days)) return downsample(rows, MAX_CHART_POINTS)
    const cutoff = rows.length - rangeDef.days
    const sliced = cutoff > 0 ? rows.slice(cutoff) : rows
    return downsample(sliced, MAX_CHART_POINTS)
  }, [result, stale, range])

  const volumeData = chartData.map((p) => ({ date: p.date, volume: p.volume ?? 0 }))

  const trailingData = useMemo(
    () =>
      (analysis?.trailing_returns || []).map((t) => ({
        label: t.label,
        total: t.return_pct,
        annualized: t.annualized,
      })),
    [analysis],
  )

  const histogramData = useMemo(
    () =>
      (analysis?.returns_histogram || []).map((bin) => ({
        start: bin.start_pct,
        end: bin.end_pct,
        mid: (bin.start_pct + bin.end_pct) / 2,
        count: bin.count,
      })),
    [analysis],
  )

  const extremesData = useMemo(() => {
    const s = analysis?.stats
    if (!s) return []
    return [
      { label: 'Best day', total: s.best_day_pct },
      { label: 'Worst day', total: s.worst_day_pct },
      { label: 'Best month', total: s.best_month_pct },
      { label: 'Worst month', total: s.worst_month_pct },
    ]
  }, [analysis])

  const stats = analysis?.stats

  if (loading) {
    return (
      <div className="space-y-4">
        <div className="panel space-y-2 p-4">
          <div className="h-4 w-1/3 bg-base-hover" />
          <div className="h-9 bg-base-hover" />
          <div className="h-9 bg-base-hover" />
          <div className="h-40 bg-base-hover" />
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="space-y-4">
        <Link to="/etfs" className="btn">
          <ArrowLeft size={14} strokeWidth={2} />
          Back to screener
        </Link>
        <div className="panel px-4 py-3 text-sm text-neg">
          Error loading {symbol}: {error}
        </div>
      </div>
    )
  }

  const hasData = stats !== null && stats !== undefined

  return (
    <div className="space-y-4">
      {/* ---- Header ---- */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link to="/etfs" className="btn" title="Back to screener">
            <ArrowLeft size={14} strokeWidth={2} />
            Screener
          </Link>
          <div className="min-w-0">
            <div className="flex items-baseline gap-2">
              <span className="num text-xl font-semibold text-accent">
                {analysis?.symbol ?? symbol}
              </span>
              <span className="truncate text-sm text-ink-soft">{analysis?.name}</span>
            </div>
            <div className="mt-0.5 flex items-center gap-2">
              {analysis?.sector && <span className="chip">{analysis.sector}</span>}
              {hasData && (
                <span className="num text-xs text-ink-faint">
                  {fmtPrice(stats.latest_close)}{' '}
                  <span className={toneClass(stats.one_day_change_pct)}>
                    {fmtPct(stats.one_day_change_pct)}
                  </span>
                </span>
              )}
            </div>
          </div>
        </div>
        <Link to={`/simulator?ticker=${encodeURIComponent(symbol)}`} className="btn-primary">
          <FlaskConical size={14} strokeWidth={2} />
          Simulate
        </Link>
      </div>

      {!hasData && (
        <div className="panel px-4 py-6 text-sm text-ink-soft">
          {analysis?.symbol ?? symbol} is tracked but has no stored price history yet, so there is
          nothing to analyze.
          <p className="mt-2 text-xs text-ink-faint">
            Ingest historical prices, then reload: python -m app.scripts.ingest
          </p>
        </div>
      )}

      {hasData && (
        <>
          {/* ---- Key stats ---- */}
          <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
            <div className="panel">
              <PanelHeading title="Key stats" hint={stats.last_date} />
              <Stat label="1Y return" value={fmtPct(stats.one_year_total_return_pct)} tone={toneClass(stats.one_year_total_return_pct)} />
              <Stat label="Ann. volatility" value={fmtPct(stats.annualized_volatility_pct, { signed: false })} />
              <Stat label="Sharpe (ann.)" value={stats.sharpe_annualized == null ? '—' : stats.sharpe_annualized.toFixed(2)} />
              <Stat label="Max DD (1Y)" value={fmtPct(stats.max_drawdown_pct)} tone="text-neg" />
            </div>

            <div className="panel">
              <PanelHeading title="Range & extremes" hint="trailing year" />
              <Stat label="Best day" value={fmtPct(stats.best_day_pct)} tone={toneClass(stats.best_day_pct)} />
              <Stat label="Worst day" value={fmtPct(stats.worst_day_pct)} tone={toneClass(stats.worst_day_pct)} />
              <Stat label="Best month" value={fmtPct(stats.best_month_pct)} tone={toneClass(stats.best_month_pct)} />
              <Stat label="Worst month" value={fmtPct(stats.worst_month_pct)} tone={toneClass(stats.worst_month_pct)} />
            </div>

            <div className="panel">
              <PanelHeading title="Drawdown & history" />
              <Stat
                label="Max DD (all)"
                value={fmtPct(stats.full_max_drawdown_pct)}
                tone="text-neg"
              />
              <Stat label="Latest close" value={fmtPrice(stats.latest_close)} />
              <Stat label="Data points" value={stats.price_rows.toLocaleString()} />
              <Stat
                label="History"
                value={`${stats.first_date} → ${stats.last_date}`}
                hint="stored daily closes"
              />
            </div>

            <div className="panel">
              <PanelHeading title="Trailing returns" hint="total, ann. in tooltip" />
              <div className="h-[150px] w-full px-2 py-2">
                {trailingData.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={trailingData} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
                      <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                      <XAxis
                        dataKey="label"
                        tick={{ fill: 'var(--chart-axis)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                        tickLine={false}
                        axisLine={{ stroke: 'var(--chart-grid)' }}
                        interval={0}
                      />
                      <YAxis
                        tick={{ fill: 'var(--chart-axis)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                        tickLine={false}
                        axisLine={false}
                        tickFormatter={(v) => `${Math.round(v)}%`}
                        width={44}
                      />
                      <ReferenceLine y={0} stroke="var(--chart-axis)" />
                      <Tooltip content={<SignedBarTooltip />} cursor={{ fillOpacity: 0.06 }} isAnimationActive={false} />
                      <Bar dataKey="total" isAnimationActive={false}>
                        {trailingData.map((row) => (
                          <Cell
                            key={row.label}
                            fill={
                              row.total == null
                                ? 'var(--chart-grid)'
                                : row.total >= 0
                                  ? 'var(--up)'
                                  : 'var(--down)'
                            }
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-ink-faint">
                    Not enough history
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* ---- Price + volume ---- */}
          <div className="panel">
            <div className="panel-title">
              <span>Price &amp; volume</span>
              <div className="flex gap-1">
                {PRICE_RANGES.map((r) => (
                  <button
                    key={r.key}
                    type="button"
                    onClick={() => setRange(r.key)}
                    className={[
                      'border px-2 py-0.5 font-mono text-[11px] transition-colors',
                      range === r.key
                        ? 'border-accent bg-accent/10 text-accent'
                        : 'border-edge-subtle text-ink-soft hover:text-ink',
                    ].join(' ')}
                  >
                    {r.key}
                  </button>
                ))}
              </div>
            </div>
            <div className="px-3 pb-1 pt-3">
              <div className="h-[260px] w-full" role="img" aria-label={`Price chart for ${symbol}`}>
                {chartData.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 4, left: 0 }}>
                      <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tick={{ fill: 'var(--chart-axis)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
                        tickLine={false}
                        axisLine={{ stroke: 'var(--chart-grid)' }}
                        minTickGap={72}
                        height={20}
                        tickFormatter={fmtAxisDate}
                      />
                      <YAxis
                        domain={['auto', 'auto']}
                        tick={{ fill: 'var(--chart-axis)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
                        tickLine={false}
                        axisLine={false}
                        width={52}
                        tickFormatter={fmtAxisPrice}
                      />
                      <Tooltip
                        content={<PriceTooltip />}
                        isAnimationActive={false}
                        cursor={{ stroke: 'var(--chart-axis)', strokeWidth: 1, strokeOpacity: 0.6 }}
                      />
                      <Area
                        type="monotone"
                        dataKey="close"
                        stroke="var(--chart-line)"
                        strokeWidth={1.5}
                        fill="var(--chart-line)"
                        fillOpacity={0.04}
                        dot={false}
                        activeDot={{ r: 2.5, fill: 'var(--chart-line)', stroke: 'var(--chart-surface)', strokeWidth: 1 }}
                        isAnimationActive={false}
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-sm text-ink-faint">
                    No price history.
                  </div>
                )}
              </div>
              <div className="h-[80px] w-full" role="img" aria-label={`Volume chart for ${symbol}`}>
                {volumeData.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={volumeData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                      <XAxis
                        dataKey="date"
                        tick={{ fill: 'var(--chart-axis)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                        tickLine={false}
                        axisLine={{ stroke: 'var(--chart-grid)' }}
                        minTickGap={72}
                        height={18}
                        tickFormatter={fmtAxisDate}
                      />
                      <YAxis
                        tick={{ fill: 'var(--chart-axis)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                        tickLine={false}
                        axisLine={false}
                        width={52}
                        tickFormatter={(v) => (v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : `${Math.round(v / 1e3)}k`)}
                      />
                      <Tooltip content={<VolumeTooltip />} cursor={{ fillOpacity: 0.08 }} isAnimationActive={false} />
                      <Bar dataKey="volume" fill="var(--chart-line)" fillOpacity={0.35} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-ink-faint">
                    No volume data.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* ---- Monthly returns heatmap ---- */}
          <div className="panel">
            <PanelHeading
              title="Monthly returns"
              hint={analysis.monthly_returns.length ? `${analysis.monthly_returns.length} months` : undefined}
            />
            {analysis.monthly_returns.length ? (
              <MonthlyHeatmap cells={analysis.monthly_returns} />
            ) : (
              <div className="px-4 py-6 text-sm text-ink-faint">Not enough history for monthly returns.</div>
            )}
          </div>

          {/* ---- Histogram + extremes ---- */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
            <div className="panel">
              <PanelHeading title="Daily return distribution" hint="log return %, trailing year" />
              <div className="h-[220px] w-full px-2 py-2">
                {histogramData.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={histogramData} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
                      <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                      <XAxis
                        dataKey="mid"
                        tick={{ fill: 'var(--chart-axis)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                        tickLine={false}
                        axisLine={{ stroke: 'var(--chart-grid)' }}
                        tickFormatter={(v) => `${Number(v).toFixed(1)}`}
                      />
                      <YAxis
                        allowDecimals={false}
                        tick={{ fill: 'var(--chart-axis)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                        tickLine={false}
                        axisLine={false}
                        width={44}
                      />
                      <Tooltip content={<BinTooltip />} cursor={{ fillOpacity: 0.06 }} isAnimationActive={false} />
                      <Bar dataKey="count" isAnimationActive={false}>
                        {histogramData.map((row) => (
                          <Cell
                            key={`${row.start}-${row.end}`}
                            fill={row.mid >= 0 ? 'var(--up)' : 'var(--down)'}
                            fillOpacity={0.75}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-ink-faint">
                    Not enough history.
                  </div>
                )}
              </div>
            </div>

            <div className="panel">
              <PanelHeading title="Best / worst periods" hint="trailing year" />
              <div className="h-[220px] w-full px-2 py-2">
                {extremesData.length ? (
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart
                      data={extremesData}
                      layout="vertical"
                      margin={{ top: 6, right: 12, bottom: 0, left: 8 }}
                    >
                      <CartesianGrid stroke="var(--chart-grid)" horizontal={false} />
                      <XAxis
                        type="number"
                        tick={{ fill: 'var(--chart-axis)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                        tickLine={false}
                        axisLine={{ stroke: 'var(--chart-grid)' }}
                        tickFormatter={(v) => `${Number(v).toFixed(0)}%`}
                      />
                      <YAxis
                        type="category"
                        dataKey="label"
                        tick={{ fill: 'var(--chart-axis)', fontSize: 11, fontFamily: 'var(--font-sans)' }}
                        tickLine={false}
                        axisLine={false}
                        width={86}
                      />
                      <ReferenceLine x={0} stroke="var(--chart-axis)" />
                      <Tooltip content={<SignedBarTooltip />} cursor={{ fillOpacity: 0.06 }} isAnimationActive={false} />
                      <Bar dataKey="total" isAnimationActive={false}>
                        {extremesData.map((row) => (
                          <Cell
                            key={row.label}
                            fill={row.total == null ? 'var(--chart-grid)' : row.total >= 0 ? 'var(--up)' : 'var(--down)'}
                          />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <div className="flex h-full items-center justify-center text-xs text-ink-faint">
                    Not enough history.
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* ---- Drawdown ---- */}
          <div className="panel">
            <PanelHeading title="Drawdown" hint="from running peak, month-end" />
            <div className="h-[180px] w-full px-2 py-2">
              {analysis.drawdown_series.length ? (
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={analysis.drawdown_series} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
                    <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                    <XAxis
                      dataKey="date"
                      tick={{ fill: 'var(--chart-axis)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                      tickLine={false}
                      axisLine={{ stroke: 'var(--chart-grid)' }}
                      minTickGap={72}
                      height={18}
                      tickFormatter={fmtAxisDate}
                    />
                    <YAxis
                      tick={{ fill: 'var(--chart-axis)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                      tickLine={false}
                      axisLine={false}
                      width={44}
                      tickFormatter={(v) => `${Math.round(v)}%`}
                    />
                    <Tooltip
                      content={<DrawdownTooltip />}
                      isAnimationActive={false}
                      cursor={{ stroke: 'var(--chart-axis)', strokeWidth: 1, strokeOpacity: 0.6 }}
                    />
                    <Area
                      type="monotone"
                      dataKey="drawdown_pct"
                      stroke="var(--down)"
                      strokeWidth={1.5}
                      fill="var(--down)"
                      fillOpacity={0.12}
                      dot={false}
                      isAnimationActive={false}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              ) : (
                <div className="flex h-full items-center justify-center text-xs text-ink-faint">
                  Not enough history.
                </div>
              )}
            </div>
          </div>

          {/* ---- Correlation heatmap ---- */}
          <div className="panel">
            <PanelHeading
              title="Correlation vs tracked ETFs"
              hint={
                analysis.correlation
                  ? `${analysis.correlation.symbols.length} instruments · monthly returns`
                  : undefined
              }
            />
            {analysis.correlation ? (
              <CorrelationHeatmap
                symbols={analysis.correlation.symbols}
                matrix={analysis.correlation.matrix}
              />
            ) : (
              <div className="px-4 py-6 text-sm text-ink-faint">
                Not enough overlapping history to compute correlations.
              </div>
            )}
          </div>

          <p className="text-[11px] leading-snug text-ink-faint">
            All figures are computed from stored daily closes (adjusted basis; see
            docs/data_methodology.md) and may exclude dividend reinvestment. Educational tool only,
            not financial advice.
          </p>
        </>
      )}
    </div>
  )
}
