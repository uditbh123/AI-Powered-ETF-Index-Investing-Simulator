import { useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  Activity,
  Calculator,
  Gauge,
  History,
  Percent,
  Play,
  Plus,
  Scale,
  Sparkles,
  Trash,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import { fetchJSON } from '../api'
import { usePageTitle } from '../hooks/usePageTitle'

const DEFAULT_HOLDINGS = [{ symbol: 'SPY', weight: 100 }]

const CRISIS_OPTIONS = [
  { value: 'dot_com_2000', label: 'Dot-com bust (2000–2002)' },
  { value: 'gfc_2008', label: 'Global financial crisis (2007–2009)' },
  { value: 'covid_2020', label: 'COVID crash (2020)' },
]

function crisisLabel(value) {
  return CRISIS_OPTIONS.find((c) => c.value === value)?.label ?? value
}

function formatCurrency(value) {
  return value.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  })
}

function formatReturn(value) {
  const pct = value * 100
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(2)}%`
}

function FieldSlider({ icon: Icon, label, value, min, max, step, onChange, render }) {
  return (
    <label className="block">
      <span className="field-label">
        <span className="flex items-center gap-1.5">
          <Icon size={11} strokeWidth={1.8} />
          {label}
        </span>
        <span className="field-value tabular-nums">{render(value)}</span>
      </span>
      <input
        type="range"
        className="slider"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={onChange}
      />
    </label>
  )
}

function FanTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  const rows = [
    { label: '90th', value: point.high, tone: 'text-pos' },
    { label: 'median', value: point.median, tone: 'text-accent' },
    { label: '10th', value: point.low, tone: 'text-neg' },
  ]
  return (
    <div className="border border-edge bg-base px-3 py-2">
      <div className="text-xs text-ink-faint">
        Year {Math.floor(point.month / 12)} · month {point.month % 12}
      </div>
      <div className="mt-1 space-y-0.5 font-mono text-xs tabular-nums">
        {rows.map(({ label, value, tone }) => (
          <div key={label} className="flex items-center justify-between gap-5">
            <span className="text-ink-faint">{label}</span>
            <span className={tone}>{formatCurrency(value)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function CrisisFanTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  const rows = [
    { label: '90th', value: point.high, tone: 'text-pos' },
    { label: 'median', value: point.median, tone: 'text-accent' },
    { label: '10th', value: point.low, tone: 'text-neg' },
    { label: 'actual', value: point.actual, tone: 'text-pos' },
  ]
  return (
    <div className="border border-edge bg-base px-3 py-2">
      <div className="text-xs text-ink-faint">Crisis month {point.month}</div>
      <div className="mt-1 space-y-0.5 font-mono text-xs tabular-nums">
        {rows.map(({ label, value, tone }) => (
          <div key={label} className="flex items-center justify-between gap-5">
            <span className="text-ink-faint">{label}</span>
            <span className={tone}>{formatCurrency(value)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function HistogramTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  return (
    <div className="border border-edge bg-base px-3 py-2">
      <div className="text-xs text-ink-faint">
        {formatCurrency(point.low)} – {formatCurrency(point.high)}
      </div>
      <div className="mt-1 font-mono text-xs tabular-nums">
        {point.count} {point.count === 1 ? 'path' : 'paths'}
      </div>
    </div>
  )
}

function ToggleSwitch({ checked, onChange, title, subtitle }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-center justify-between gap-3 border border-edge bg-white/5 px-2.5 py-2 text-left transition-colors hover:border-white/30"
    >
      <span className="min-w-0">
        <span className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-ink-soft">
          <Sparkles
            size={11}
            strokeWidth={1.8}
            className={checked ? 'text-accent' : 'text-ink-dim'}
          />
          {title}
        </span>
        <span className="mt-0.5 block text-xs leading-snug text-ink-dim">
          {subtitle}
        </span>
      </span>
      <span
        className={[
          'relative h-4 w-8 shrink-0 border',
          checked ? 'border-accent bg-accent/25' : 'border-white/20 bg-white/5',
        ].join(' ')}
      >
        <span
          className={[
            'absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2',
            checked ? 'left-[15px] bg-accent' : 'left-0.5 bg-ink-faint',
          ].join(' ')}
        />
      </span>
    </button>
  )
}

export default function Simulator() {
  usePageTitle('Simulator — ETF Simulator')

  const { search } = useLocation()
  const [tickers, setTickers] = useState([])
  const [name, setName] = useState('My Portfolio')
  const [contribution, setContribution] = useState(200)
  const [initialBalance, setInitialBalance] = useState(10000)
  const [horizonYears, setHorizonYears] = useState(10)
  const [holdings, setHoldings] = useState(() => {
    const preSelected = new URLSearchParams(search).get('ticker')
    return preSelected ? [{ symbol: preSelected, weight: 100 }] : DEFAULT_HOLDINGS
  })
  const [useSentiment, setUseSentiment] = useState(false)

  const [phase, setPhase] = useState('idle') // idle | running | done
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [portfolioId, setPortfolioId] = useState(null)
  const [crisis, setCrisis] = useState('covid_2020')
  const [crisisData, setCrisisData] = useState(null)
  const [crisisLoading, setCrisisLoading] = useState(false)
  const [crisisError, setCrisisError] = useState(null)
  const [monthlyReturns, setMonthlyReturns] = useState(null)
  const [monthlyReturnsError, setMonthlyReturnsError] = useState(null)

  useEffect(() => {
    fetchJSON('/tickers')
      .then(setTickers)
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (!portfolioId || phase !== 'done') return
    let cancelled = false
    fetchJSON(`/portfolios/${portfolioId}/monthly-returns`)
      .then((rows) => {
        if (!cancelled) setMonthlyReturns(rows)
      })
      .catch((e) => {
        if (!cancelled) setMonthlyReturnsError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [portfolioId, phase])

  function updateSetting(setter) {
    return (event) => setter(event.target.value)
  }

  function updateHolding(index, field, value) {
    setHoldings((rows) =>
      rows.map((row, i) => (i === index ? { ...row, [field]: value } : row)),
    )
  }

  function addHolding() {
    setHoldings((rows) => [...rows, { symbol: 'SPY', weight: 0 }])
  }

  function removeHolding(index) {
    setHoldings((rows) => (rows.length > 1 ? rows.filter((_, i) => i !== index) : rows))
  }

  async function runSimulation(event) {
    event.preventDefault()
    setPhase('running')
    setError(null)
    setCrisisData(null)
    try {
      const portfolio = await fetchJSON('/portfolios', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim() || 'My Portfolio',
          monthly_contribution: Number(contribution),
          holdings,
        }),
      })
      setPortfolioId(portfolio.id)
      const sim = await fetchJSON(`/portfolios/${portfolio.id}/simulate`, {
        method: 'POST',
        body: JSON.stringify({
          initial_balance: Number(initialBalance),
          horizon_months: Number(horizonYears) * 12,
          use_sentiment: useSentiment,
        }),
      })
      setResult(sim)
      setPhase('done')
    } catch (e) {
      setError(e.message)
      setPhase('idle')
    }
  }

  async function replayCrisis() {
    if (!portfolioId) return
    setCrisisLoading(true)
    setCrisisError(null)
    try {
      const data = await fetchJSON(`/portfolios/${portfolioId}/crisis-replay`, {
        method: 'POST',
        body: JSON.stringify({
          crisis,
          initial_balance: Number(initialBalance),
        }),
      })
      setCrisisData(data)
    } catch (e) {
      setCrisisError(e.message)
    } finally {
      setCrisisLoading(false)
    }
  }

  const bandPath = (level) =>
    result?.percentiles.find((p) => p.level === level)?.path ?? []
  const lowBand = bandPath(10)
  const medianBand = bandPath(50)
  const highBand = bandPath(90)
  const chartData = medianBand.map((value, month) => {
    const low = Math.round(lowBand[month] ?? value)
    const high = Math.round(highBand[month] ?? value)
    return { month, low, median: Math.round(value), high, band: [low, high] }
  })

  const crisisLevel = (level) =>
    crisisData?.percentiles.find((p) => p.level === level)?.path ?? []
  const crisisLow = crisisLevel(10)
  const crisisMed = crisisLevel(50)
  const crisisHigh = crisisLevel(90)
  const crisisChart = crisisMed.map((value, month) => {
    const low = Math.round(crisisLow[month] ?? value)
    const high = Math.round(crisisHigh[month] ?? value)
    return {
      month,
      low,
      median: Math.round(value),
      high,
      actual: crisisData?.real_path ? Math.round(crisisData.real_path[month]) : null,
      band: [low, high],
    }
  })

  const statCards = result
    ? [
        { icon: TrendingUp, label: 'Best case (90th)', value: result.summary.best_case_final_value, tone: 'tick-up' },
        { icon: Gauge, label: 'Median outcome', value: result.summary.median_final_value, tone: 'text-accent' },
        { icon: TrendingDown, label: 'Worst case (10th)', value: result.summary.worst_case_final_value, tone: 'tick-down' },
      ]
    : []

  const stats = result?.stats
  const insightCards = stats
    ? [
        {
          icon: Percent,
          label: 'Probability of profit',
          value: `${(stats.probability_of_profit * 100).toFixed(0)}%`,
          tone: stats.probability_of_profit >= 0.5 ? 'text-pos' : 'text-neg',
        },
        {
          icon: Gauge,
          label: 'Median final value',
          value: formatCurrency(stats.final_percentiles.p50),
          tone: 'text-accent',
        },
        {
          icon: TrendingDown,
          label: 'Worst case (p10)',
          value: formatCurrency(stats.final_percentiles.p10),
          tone: 'text-ink',
        },
        {
          icon: Scale,
          label: 'Upside / downside',
          value:
            stats.upside_downside_ratio === null
              ? '—'
              : `${stats.upside_downside_ratio.toFixed(2)}×`,
          tone:
            stats.upside_downside_ratio === null
              ? 'text-ink-dim'
              : stats.upside_downside_ratio >= 1
                ? 'text-pos'
                : 'text-neg',
        },
        {
          icon: Activity,
          label: 'Median max drawdown',
          value: `${(stats.median_max_drawdown * 100).toFixed(1)}%`,
          tone: 'text-ink',
        },
      ]
    : []

  const histogramData = stats
    ? stats.histogram.bin_edges.slice(0, -1).map((low, i) => {
        const high = stats.histogram.bin_edges[i + 1]
        const mid = (low + high) / 2
        return {
          count: stats.histogram.counts[i],
          low,
          high,
          label: `${Math.round(mid / 1000)}k`,
          value: mid,
        }
      })
    : []

  const histogramBucketFor = (value) => {
    if (!histogramData.length) return null
    const edges = stats.histogram.bin_edges
    if (value < edges[0] || value > edges[edges.length - 1]) return null
    const index = edges.findIndex((e) => e >= value)
    const bucket = histogramData[Math.min(Math.max(index - 1, 0), histogramData.length - 1)]
    return bucket?.label ?? null
  }

  const heatmapYears = {}
  for (const row of monthlyReturns ?? []) {
    heatmapYears[row.year] ??= Array(12).fill(null)
    heatmapYears[row.year][row.month - 1] = row.return
  }
  const heatYears = Object.keys(heatmapYears).map(Number).sort((a, b) => a - b)

  function heatCellStyle(value) {
    if (value === null) return {}
    const intensity = Math.min(Math.abs(value) / 0.05, 1)
    if (value >= 0) {
      return { backgroundColor: `color-mix(in srgb, var(--up) ${Math.round(intensity * 100)}%, transparent)` }
    }
    return { backgroundColor: `color-mix(in srgb, var(--down) ${Math.round(intensity * 100)}%, transparent)` }
  }

  function heatCellText(value) {
    if (value === null) return 'text-ink-dim'
    return Math.abs(value) / 0.05 >= 0.6 ? 'text-black' : 'text-ink'
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Simulator</h1>
        <p className="mt-1 max-w-prose text-sm text-ink-soft">
          Configure a hypothetical portfolio and run a Monte Carlo simulation to
          chart its median growth trajectory.
        </p>
      </div>

      <div className="grid grid-cols-1 items-start gap-4 lg:grid-cols-[300px_minmax(0,1fr)]">
        {/* ---- Control panel ---- */}
        <aside className="panel">
          <div className="panel-title">
            <span>Controls</span>
            {phase === 'running' && (
              <span className="flex items-center gap-1 font-mono text-xs normal-case text-accent">
                <span className="h-1.5 w-1.5 bg-accent" />
                running
              </span>
            )}
          </div>

          <form className="space-y-5 p-4" onSubmit={runSimulation}>
            <label className="block">
              <span className="field-label">Portfolio name</span>
              <input
                type="text"
                className="input"
                value={name}
                onChange={updateSetting(setName)}
              />
            </label>

            <FieldSlider
              icon={Wallet}
              label="Current balance"
              value={initialBalance}
              min={0}
              max={500000}
              step={1000}
              onChange={updateSetting(setInitialBalance)}
              render={(v) => formatCurrency(Number(v))}
            />

            <FieldSlider
              icon={TrendingUp}
              label="Monthly contribution"
              value={contribution}
              min={0}
              max={2000}
              step={25}
              onChange={updateSetting(setContribution)}
              render={(v) => `${v} /mo`}
            />

            <FieldSlider
              icon={Gauge}
              label="Investment horizon"
              value={horizonYears}
              min={1}
              max={50}
              step={1}
              onChange={updateSetting(setHorizonYears)}
              render={(v) => `${v} yr`}
            />

            <div>
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-widest text-ink-faint">
                Holdings
              </span>
              <div className="space-y-2">
                {holdings.map((holding, index) => (
                  <div key={index} className="flex items-center gap-1.5">
                    <select
                      className="select h-8 min-w-0 flex-1"
                      value={holding.symbol}
                      onChange={(e) => updateHolding(index, 'symbol', e.target.value)}
                    >
                      {tickers
                        .filter((t) => t.price_rows > 0)
                        .map((t) => (
                          <option key={t.symbol} value={t.symbol}>
                            {t.symbol} — {t.name}
                          </option>
                        ))}
                    </select>
                    <div className="flex h-8 w-16 items-center gap-0.5 border border-edge bg-base-elevated px-1.5 focus-within:border-accent-dim">
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="1"
                        className="w-full bg-transparent text-right font-mono text-sm text-ink outline-none"
                        value={holding.weight}
                        onChange={(e) => updateHolding(index, 'weight', e.target.value)}
                      />
                      <span className="text-xs text-ink-faint">%</span>
                    </div>
                    <button
                      type="button"
                      className="btn btn-danger-ghost h-8 w-8 items-center justify-center p-0"
                      onClick={() => removeHolding(index)}
                      disabled={holdings.length <= 1}
                      aria-label="Remove holding"
                    >
                      <Trash size={13} strokeWidth={1.8} />
                    </button>
                  </div>
                ))}
              </div>
              <button type="button" className="btn mt-2 w-full" onClick={addHolding}>
                <Plus size={13} strokeWidth={2} />
                Add holding
              </button>
            </div>

            <ToggleSwitch
              checked={useSentiment}
              onChange={setUseSentiment}
              title="AI Sentiment Adjustment (Includes Geopolitical Risk)"
              subtitle="Scales historical volatility by recent FinBERT news sentiment."
            />

            {error && <p className="text-xs text-neg">Error: {error}</p>}

            <button
              type="submit"
              className="btn btn-primary w-full py-2"
              disabled={phase === 'running'}
            >
              <Play size={14} strokeWidth={2} fill="currentColor" />
              {phase === 'running' ? 'Simulating…' : 'Run simulation'}
            </button>
          </form>
        </aside>

        {/* ---- Chart area ---- */}
        <section className="space-y-4">
          {!result ? (
            <div className="panel flex flex-col gap-3 px-6 py-14">
              <span className="flex h-12 w-12 items-center justify-center border border-edge bg-base-elevated text-ink-dim">
                <Calculator size={20} strokeWidth={1.6} />
              </span>
              <p className="max-w-prose text-sm text-ink-soft">
                No portfolio yet. Set a balance, monthly contribution, and
                holdings above, then press{' '}
                <span className="font-medium text-accent">Run simulation</span> —
                it creates the portfolio and charts the 10th–90th percentile
                growth fan.
              </p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                {statCards.map(({ icon: Icon, label, value, tone }) => (
                  <div key={label} className="panel flex items-center gap-3 px-4 py-3">
                    <span
                      className={`flex h-8 w-8 shrink-0 items-center justify-center border border-edge bg-base-elevated ${tone}`}
                    >
                      <Icon size={15} strokeWidth={1.8} />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-xs font-medium uppercase tracking-widest text-ink-faint">
                        {label}
                      </span>
                      <span className="block truncate font-mono text-xl text-ink tabular-nums">
                        {formatCurrency(value)}
                      </span>
                    </span>
                  </div>
                ))}
              </div>

              {stats ? (
                <div className="panel bg-base">
                  <div className="panel-title">
                    <span>Outcome insights</span>
                    <span className="font-mono text-xs normal-case text-ink-faint">
                      {(result.params.n_simulations ?? 1000).toLocaleString()} simulated paths
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-5 p-4 sm:grid-cols-3 xl:grid-cols-5">
                    {insightCards.map(({ icon: Icon, label, value, tone }) => (
                      <div key={label}>
                        <span className="flex items-center gap-1.5 text-11px font-semibold uppercase tracking-widest text-ink-faint">
                          <Icon size={12} strokeWidth={1.8} />
                          {label}
                        </span>
                        <span className={`mt-1 block font-mono text-xl tabular-nums ${tone}`}>
                          {value}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="border-t border-edge px-4 pb-4 pt-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-xs font-semibold uppercase tracking-widest text-ink-soft">
                        Final value distribution
                      </span>
                      <span className="flex items-center gap-3 font-mono text-xs text-ink-faint">
                        <span className="flex items-center gap-1.5">
                          <span className="h-0.5 w-4 bg-accent" />
                          median
                        </span>
                        <span className="flex items-center gap-1.5">
                          <span className="h-0.5 w-4 border-b border-dashed border-ink-dim" />
                          total contributed
                        </span>
                      </span>
                    </div>
                    <div className="mt-3 h-40">
                      <div
                        className="h-full w-full"
                        role="img"
                        aria-label="Histogram of simulated final portfolio values"
                      >
                        <ResponsiveContainer width="100%" height="100%">
                          <BarChart data={histogramData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
                            <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" vertical={false} />
                            <XAxis
                              dataKey="label"
                              tick={{ fill: 'var(--chart-axis)', fontSize: 10 }}
                              tickLine={false}
                              axisLine={{ stroke: 'var(--chart-grid)' }}
                              interval={Math.max(1, Math.floor(histogramData.length / 6))}
                            />
                            <YAxis tick={false} tickLine={false} axisLine={false} width={2} />
                            <Tooltip
                              cursor={{ fill: 'rgba(255, 255, 255, 0.05)' }}
                              content={<HistogramTooltip />}
                            />
                            <Bar dataKey="count" fill="var(--chart-line)" fillOpacity={0.75} isAnimationActive={false} />
                            {histogramBucketFor(stats.final_percentiles.p50) && (
                              <ReferenceLine
                                x={histogramBucketFor(stats.final_percentiles.p50)}
                                stroke="var(--chart-line)"
                                strokeWidth={1.5}
                              />
                            )}
                            {histogramBucketFor(stats.total_contributed) && (
                              <ReferenceLine
                                x={histogramBucketFor(stats.total_contributed)}
                                stroke="var(--ink-dim)"
                                strokeDasharray="4 3"
                              />
                            )}
                          </BarChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="panel flex flex-col gap-3 px-6 py-10">
                  <h3 className="text-base font-semibold text-ink">Outcome insights</h3>
                  <p className="max-w-prose text-sm text-ink-soft">
                    This run predates the insights backend. Re-run the simulation to see
                    outcome statistics, the final-value distribution, and the monthly-returns heatmap.
                  </p>
                </div>
              )}

              <div className="panel bg-base">
                <div className="panel-title">
                  <span>Growth fan chart · 10th–90th percentile</span>
                  <span className="flex items-center gap-2 font-mono text-xs normal-case text-ink-faint">
                    {result.sentiment?.applied && (
                      <span className="chip">
                        <Sparkles size={10} strokeWidth={2} className="text-accent" />
                        sentiment ×{result.sentiment.volatility_multiplier.toFixed(2)}
                      </span>
                    )}
                    <span>
                      {horizonYears} yr · {formatCurrency(contribution)}/mo
                    </span>
                  </span>
                </div>
                <div className="h-[380px] px-2 py-3">
                  <div
                    className="h-full w-full"
                    role="img"
                    aria-label={`Projected portfolio growth fan chart over ${horizonYears} years with monthly contributions of ${formatCurrency(contribution)}`}
                  >
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                      <CartesianGrid stroke="var(--chart-grid)" strokeDasharray="3 3" vertical={false} />
                      <XAxis
                        dataKey="month"
                        tick={{ fill: 'var(--chart-axis)', fontSize: 11 }}
                        tickLine={false}
                        axisLine={{ stroke: 'var(--chart-grid)' }}
                        tickFormatter={(m) => (m % 12 === 0 ? `${m / 12}y` : '')}
                      />
                      <YAxis
                        tick={{ fill: 'var(--chart-axis)', fontSize: 11 }}
                        tickFormatter={(v) => `${Math.round(v / 1000)}k`}
                        tickLine={false}
                        axisLine={false}
                        width={48}
                      />
                      <Tooltip
                        content={<FanTooltip />}
                        cursor={{ stroke: 'rgba(255,255,255,0.25)', strokeDasharray: '3 3' }}
                      />
                      <Area
                        type="monotone"
                        dataKey="band"
                        stroke="none"
                        fill="var(--chart-line)"
                        fillOpacity={0.1}
                        isAnimationActive={false}
                        activeDot={false}
                      />
                      <Line
                        type="monotone"
                        dataKey="median"
                        stroke="var(--chart-line)"
                        strokeWidth={2}
                        dot={false}
                        activeDot={{ r: 3, fill: 'var(--chart-line)' }}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                  </div>
                </div>
              </div>

              <div className="panel bg-base">
                <div className="panel-title">
                  <span>Realized monthly returns</span>
                  <span className="flex items-center gap-2 font-mono text-xs normal-case text-ink-faint">
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block h-2.5 w-6" style={{ background: 'linear-gradient(90deg, var(--down), rgba(255, 255, 255, 0.05) 50%, var(--up))' }} />
                      loss → gain
                    </span>
                  </span>
                </div>

                <div className="overflow-x-auto p-4">
                  {monthlyReturnsError ? (
                    <p className="text-xs text-neg">Error: {monthlyReturnsError}</p>
                  ) : !monthlyReturns ? (
                    <p className="text-xs text-ink-faint">Loading monthly returns…</p>
                  ) : (
                    <>
                      <div className="min-w-[560px]">
                        <div className="flex items-center gap-1 pb-1 pl-10 pr-1">
                          <span className="w-24 shrink-0 font-mono text-xs text-ink-faint">Year</span>
                          {Array.from({ length: 12 }, (_, m) => (
                            <span key={m} className="flex-1 text-center font-mono text-11px text-ink-dim">
                              {['J', 'F', 'M', 'A', 'M', 'J', 'J', 'A', 'S', 'O', 'N', 'D'][m]}
                            </span>
                          ))}
                        </div>
                        {heatYears.map((year) => (
                          <div key={year} className="flex items-center gap-1 py-0.5">
                            <span className="w-24 shrink-0 font-mono text-xs text-ink-faint">{year}</span>
                            {heatmapYears[year].map((value, month) => (
                              <span
                                key={month}
                                title={`${year}-${String(month + 1).padStart(2, '0')} · ${value === null ? 'no data' : formatReturn(value)}`}
                                className={`flex-1 rounded-none border ${value === null ? 'border-base bg-base' : 'border-transparent'} px-0 py-1 text-right font-mono text-xs tabular-nums ${value === null ? '' : heatCellText(value)}`}
                                style={heatCellStyle(value)}
                              >
                                {value === null ? '·' : formatReturn(value)}
                              </span>
                            ))}
                          </div>
                        ))}
                        {heatYears.length === 0 && (
                          <p className="text-xs text-ink-faint">No monthly return history yet.</p>
                        )}
                      </div>
                    </>
                  )}
                </div>
              </div>

              {result.cached && (
                <p className="text-xs text-ink-dim">
                  Loaded from cached simulation results.
                </p>
              )}

              <div className="panel">
                <div className="panel-title">
                  <span>Replay a crisis</span>
                  {crisisLoading && (
                    <span className="flex items-center gap-1 font-mono text-xs normal-case text-accent">
                      <span className="h-1.5 w-1.5 bg-accent" />
                      running
                    </span>
                  )}
                </div>

                <div className="space-y-3 p-4">
                  <div className="flex flex-wrap items-end gap-2">
                    <div className="min-w-[220px] flex-1">
                      <span className="field-label">Scenario</span>
                      <select
                        className="select"
                        value={crisis}
                        onChange={(e) => setCrisis(e.target.value)}
                      >
                        {CRISIS_OPTIONS.map((c) => (
                          <option key={c.value} value={c.value}>
                            {c.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={replayCrisis}
                      disabled={crisisLoading}
                    >
                      <History size={14} strokeWidth={2} />
                      Replay crisis
                    </button>
                  </div>

                  {crisisError && <p className="text-xs text-neg">Error: {crisisError}</p>}

                  {crisisData && (
                    <div className="border border-edge p-3">
                      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                        <span className="text-xs font-semibold uppercase tracking-widest text-ink-soft">
                          {crisisLabel(crisisData.crisis)} · {crisisData.window.start} →
                          {' '}{crisisData.window.end}
                        </span>
                        <span className="flex items-center gap-3 font-mono text-xs text-ink-faint">
                          <span className="flex items-center gap-1.5">
                            <span className="h-0.5 w-4 bg-accent" /> simulated
                            median
                          </span>
                          <span className="flex items-center gap-1.5">
                            <span className="h-0.5 w-4 bg-pos" /> real trajectory
                          </span>
                          <span className="flex items-center gap-1.5">
                            <span className="h-2 w-4 bg-accent opacity-20" />{' '}
                            10–90th
                          </span>
                        </span>
                      </div>
                      <div className="h-[260px]">
                        <div
                          className="h-full w-full"
                          role="img"
                          aria-label={`Crisis scenario replay chart comparing median portfolio value against a baseline buy-and-hold during ${crisisLabel(crisisData.crisis)}`}
                        >
                        <ResponsiveContainer width="100%" height="100%">
                          <ComposedChart
                            data={crisisChart}
                            margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
                          >
                            <CartesianGrid
                              stroke="var(--chart-grid)"
                              strokeDasharray="3 3"
                              vertical={false}
                            />
                            <XAxis
                              dataKey="month"
                              tick={{ fill: 'var(--chart-axis)', fontSize: 11 }}
                              tickLine={false}
                              axisLine={{ stroke: 'var(--chart-grid)' }}
                              tickFormatter={(m) => `${m}m`}
                            />
                            <YAxis
                              tick={{ fill: 'var(--chart-axis)', fontSize: 11 }}
                              tickFormatter={(v) => `${Math.round(v / 1000)}k`}
                              tickLine={false}
                              axisLine={false}
                              width={48}
                            />
                            <Tooltip
                              content={<CrisisFanTooltip />}
                              cursor={{
                                stroke: 'rgba(255,255,255,0.25)',
                                strokeDasharray: '3 3',
                              }}
                            />
                            <Area
                              type="monotone"
                              dataKey="band"
                              stroke="none"
                              fill="var(--chart-line)"
                              fillOpacity={0.1}
                              isAnimationActive={false}
                              activeDot={false}
                            />
                            <Line
                              type="monotone"
                              dataKey="median"
                              stroke="var(--chart-line)"
                              strokeWidth={2}
                              dot={false}
                              activeDot={{ r: 3 }}
                            />
                            <Line
                              type="monotone"
                              dataKey="actual"
                              stroke="var(--up)"
                              strokeWidth={2}
                              strokeDasharray="4 2"
                              dot={false}
                              activeDot={{ r: 3, fill: 'var(--up)' }}
                            />
                          </ComposedChart>
                        </ResponsiveContainer>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  )
}