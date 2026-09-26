import { useCallback, useEffect, useState } from 'react'
import { useLocation } from 'react-router-dom'
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
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
import { fetchJSON, fractionToPercentInput, holdingsToFractions } from '../api'
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
    { label: 'median', value: point.median, tone: 'text-ink' },
    { label: '10th', value: point.low, tone: 'text-neg' },
  ]
  return (
    <div className="border border-ink bg-base-panel px-2 py-1.5">
      <div className="text-11px uppercase tracking-widest text-ink-faint">
        Year {Math.floor(point.month / 12)} · month {point.month % 12}
      </div>
      <div className="mt-1 space-y-0.5">
        {rows.map(({ label, value, tone }) => (
          <div key={label} className="flex items-center justify-between gap-5">
            <span className="text-11px uppercase tracking-widest text-ink-faint">
              {label}
            </span>
            <span className={`num text-xs ${tone}`}>{formatCurrency(value)}</span>
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
    { label: 'median', value: point.median, tone: 'text-ink' },
    { label: '10th', value: point.low, tone: 'text-neg' },
    { label: 'actual', value: point.actual, tone: 'text-pos' },
  ]
  return (
    <div className="border border-ink bg-base-panel px-2 py-1.5">
      <div className="text-11px uppercase tracking-widest text-ink-faint">
        Crisis month {point.month}
      </div>
      <div className="mt-1 space-y-0.5">
        {rows.map(({ label, value, tone }) => (
          <div key={label} className="flex items-center justify-between gap-5">
            <span className="text-11px uppercase tracking-widest text-ink-faint">
              {label}
            </span>
            <span className={`num text-xs ${tone}`}>{formatCurrency(value)}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

function TrajectoryTooltip({ active, payload }) {
  if (!active || !payload?.length) return null
  const point = payload[0].payload
  const rows = [
    { label: 'best p90', value: point.high },
    { label: 'median p50', value: point.median },
    { label: 'worst p10', value: point.low },
    { label: 'contributed', value: point.contributed },
  ]
  return (
    <div className="border border-ink bg-base-panel px-2 py-1.5">
      <div className="text-11px uppercase tracking-widest text-ink-faint">
        Year {Math.floor(point.month / 12)} · month {point.month % 12}
      </div>
      <div className="mt-1 space-y-0.5">
        {rows.map(({ label, value }) => (
          <div key={label} className="flex items-center justify-between gap-5">
            <span className="text-11px uppercase tracking-widest text-ink-faint">
              {label}
            </span>
            <span className="num text-xs text-ink">{formatCurrency(value)}</span>
          </div>
        ))}
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
      className="flex w-full items-center justify-between gap-3 border border-edge bg-white px-2.5 py-2 text-left transition-colors hover:border-ink/25"
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
          checked ? 'border-accent bg-accent/15' : 'border-edge bg-base-hover',
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
  const [portfolios, setPortfolios] = useState([])
  const [selectedPortfolioId, setSelectedPortfolioId] = useState(null)
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
    fetchJSON('/portfolios')
      .then(setPortfolios)
      .catch(() => {})
  }, [])

  const applyPortfolio = useCallback((portfolio) => {
    setName(portfolio.name)
    setContribution(portfolio.monthly_contribution)
    setHoldings(
      portfolio.holdings.map((h) => ({
        symbol: h.symbol,
        weight: fractionToPercentInput(h.weight),
      })),
    )
  }, [])

  // Deep link: /simulator?portfolio=ID loads that portfolio into the controls
  // so "Open in Simulator" from the Portfolios page lands ready to run.
  useEffect(() => {
    const id = new URLSearchParams(search).get('portfolio')
    if (!id || selectedPortfolioId) return
    let cancelled = false
    fetchJSON(`/portfolios/${id}`)
      .then((portfolio) => {
        if (!cancelled) {
          setSelectedPortfolioId(portfolio.id)
          applyPortfolio(portfolio)
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [search, selectedPortfolioId, applyPortfolio])

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
      // Weights are edited as percentages; the API stores fractions that sum
      // to 1.0, so a reused portfolio converts before PATCHing. The conversion
      // is centralized in api.js so the scale can never diverge from the
      // contract by more than one call site.
      const fractionHoldings = holdingsToFractions(holdings)
      let portfolio
      if (selectedPortfolioId) {
        portfolio = await fetchJSON(`/portfolios/${selectedPortfolioId}`, {
          method: 'PATCH',
          body: JSON.stringify({
            name: name.trim() || 'My Portfolio',
            monthly_contribution: Number(contribution),
            holdings: fractionHoldings,
          }),
        })
        setPortfolios((prev) =>
          prev.map((p) => (p.id === portfolio.id ? portfolio : p)),
        )
      } else {
        portfolio = await fetchJSON('/portfolios', {
          method: 'POST',
          body: JSON.stringify({
            name: name.trim() || 'My Portfolio',
            monthly_contribution: Number(contribution),
            holdings: fractionHoldings,
          }),
        })
        setSelectedPortfolioId(portfolio.id)
        setPortfolios((prev) => [portfolio, ...prev])
      }
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
          // Sortino-style ratio on monthly returns. Null is now reserved for
          // the genuinely undefined case (no losing month at all), not for
          // "the p10 finished above the book value" as it used to be, so this
          // card should essentially always show a number.
          value:
            stats.upside_downside_ratio === null
              ? 'n/a'
              : `${stats.upside_downside_ratio.toFixed(2)}×`,
          tone:
            stats.upside_downside_ratio === null
              ? 'text-ink-dim'
              : stats.upside_downside_ratio >= 1
                ? 'text-pos'
                : 'text-neg',
          title:
            stats.upside_downside_ratio === null
              ? 'No month was negative across the simulated paths, so downside deviation is zero and the ratio is undefined.'
              : 'Mean of positive months divided by the root-mean-square of negative months, across all simulated paths.',
        },
        {
          icon: Activity,
          label: 'Median max drawdown',
          value: `${(stats.median_max_drawdown * 100).toFixed(1)}%`,
          tone: 'text-ink',
        },
      ]
    : []

  // Trajectory rows for the compact summary chart. `chartData` already carries
  // the p10/p50/p90 paths from the run's percentile series; this only adds the
  // book-value line at each month so the crossing point is readable. The
  // contribution is applied at steps 1..horizon (never at step 0), which is
  // why the run's own params are used rather than the live form state - the
  // form may have been edited since the run was made, and a loaded portfolio
  // carries its own monthly_contribution (which is not the slider's value).
  const trajectoryData = result?.params
    ? chartData.map((row) => ({
        ...row,
        contributed: Math.round(
          Number(result.params.initial_balance ?? 0) +
            Number(result.params.monthly_contribution ?? 0) * row.month,
        ),
      }))
    : []

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
    // Strong cells sit on a saturated pos/neg fill -> flip to white; weak
    // cells keep ink text on the near-transparent tint.
    return Math.abs(value) / 0.05 >= 0.55 ? 'text-white' : 'text-ink'
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
              <span className="field-label">
                <span>Portfolio</span>
                <span className="font-mono text-xs normal-case text-ink-faint">
                  {selectedPortfolioId ? 'saves to this portfolio' : 'creates a new one'}
                </span>
              </span>
              <select
                className="select"
                value={selectedPortfolioId ?? ''}
                onChange={(event) => {
                  const value = event.target.value
                  if (!value) {
                    setSelectedPortfolioId(null)
                    return
                  }
                  const id = Number(value)
                  if (id === selectedPortfolioId) return
                  setSelectedPortfolioId(id)
                  fetchJSON(`/portfolios/${id}`)
                    .then(applyPortfolio)
                    .catch(() => {})
                }}
              >
                <option value="">New portfolio…</option>
                {portfolios.map((portfolio) => (
                  <option key={portfolio.id} value={portfolio.id}>
                    {portfolio.name}
                  </option>
                ))}
              </select>
            </label>

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
                    <div className="flex h-8 w-16 items-center gap-0.5 border border-edge bg-white px-1.5 focus-within:border-ink">
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
                      <span className="block truncate num text-xl text-ink">
                        {formatCurrency(value)}
                      </span>
                    </span>
                  </div>
                ))}
              </div>

              {stats ? (
                <div className="panel">
                  <div className="panel-title">
                    <span>Outcome insights</span>
                    <span className="font-mono text-xs normal-case text-ink-faint">
                      {(result.params.n_simulations ?? 1000).toLocaleString()} simulated paths
                    </span>
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-5 p-4 sm:grid-cols-3 xl:grid-cols-5">
                    {insightCards.map(({ icon: Icon, label, value, tone, title }) => (
                      <div key={label} title={title}>
                        <span className="flex items-center gap-1.5 text-11px font-semibold uppercase tracking-widest text-ink-faint">
                          <Icon size={12} strokeWidth={1.8} />
                          {label}
                        </span>
                        <span className={`mt-1 block num text-xl ${tone}`}>
                          {value}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="border-t border-edge px-4 pb-4 pt-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-xs font-semibold uppercase tracking-widest text-ink-soft">
                        Value trajectory
                      </span>
                      <span className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-11px text-ink-faint">
                        <span className="flex items-center gap-1.5">
                          <span className="h-px w-4 bg-ink opacity-30" />
                          best p90
                        </span>
                        <span className="flex items-center gap-1.5">
                          <span className="h-0.5 w-4 bg-ink" />
                          median p50
                        </span>
                        <span className="flex items-center gap-1.5">
                          <span className="h-px w-4 bg-ink opacity-60" />
                          worst p10
                        </span>
                        <span className="flex items-center gap-1.5">
                          <span className="h-px w-4 bg-ink-faint" />
                          contributed
                        </span>
                      </span>
                    </div>
                    <div className="mt-3 h-48">
                      <div
                        className="h-full w-full"
                        role="img"
                        aria-label={`Best, median and worst case portfolio value trajectories over ${horizonYears} years, with the total contributed line for comparison`}
                      >
                        <ResponsiveContainer width="100%" height="100%">
                          <ComposedChart
                            data={trajectoryData}
                            margin={{ top: 4, right: 8, bottom: 0, left: 0 }}
                          >
                            <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
                            <XAxis
                              dataKey="month"
                              tick={{
                                fill: 'var(--chart-axis)',
                                fontSize: 11,
                                fontFamily: 'var(--font-mono)',
                              }}
                              tickLine={false}
                              axisLine={{ stroke: 'var(--chart-grid)' }}
                              minTickGap={48}
                              tickFormatter={(m) => (m % 12 === 0 ? `${m / 12}y` : '')}
                            />
                            <YAxis
                              tick={{
                                fill: 'var(--chart-axis)',
                                fontSize: 11,
                                fontFamily: 'var(--font-mono)',
                              }}
                              tickFormatter={(v) => `${Math.round(v / 1000)}k`}
                              tickLine={false}
                              axisLine={false}
                              width={44}
                            />
                            <Tooltip
                              content={<TrajectoryTooltip />}
                              isAnimationActive={false}
                              cursor={{
                                stroke: 'var(--chart-axis)',
                                strokeWidth: 1,
                                strokeOpacity: 0.6,
                              }}
                            />
                            {/* p90 / p10 frame the fan; alpha and width carry the
                                distinction so all three paths stay in the
                                monochrome palette. */}
                            <Line
                              type="monotone"
                              dataKey="high"
                              name="Best case (p90)"
                              stroke="var(--chart-line)"
                              strokeWidth={1}
                              strokeOpacity={0.3}
                              dot={false}
                              activeDot={false}
                              isAnimationActive={false}
                            />
                            <Line
                              type="monotone"
                              dataKey="low"
                              name="Worst case (p10)"
                              stroke="var(--chart-line)"
                              strokeWidth={1}
                              strokeOpacity={0.6}
                              dot={false}
                              activeDot={false}
                              isAnimationActive={false}
                            />
                            <Line
                              type="monotone"
                              dataKey="median"
                              name="Median (p50)"
                              stroke="var(--chart-line)"
                              strokeWidth={2}
                              dot={false}
                              activeDot={{
                                r: 2.5,
                                fill: 'var(--chart-line)',
                                stroke: 'var(--chart-surface)',
                                strokeWidth: 1,
                              }}
                              isAnimationActive={false}
                            />
                            <Line
                              type="monotone"
                              dataKey="contributed"
                              name="Total contributed"
                              stroke="var(--chart-axis)"
                              strokeWidth={1}
                              dot={false}
                              activeDot={false}
                              isAnimationActive={false}
                            />
                          </ComposedChart>
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
                    outcome statistics, the value trajectory, and the monthly-returns heatmap.
                  </p>
                </div>
              )}

              <div className="panel">
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
                        tick={{ fill: 'var(--chart-axis)', fontSize: 12 }}
                        tickLine={false}
                        axisLine={{ stroke: 'var(--chart-grid)' }}
                        tickFormatter={(m) => (m % 12 === 0 ? `${m / 12}y` : '')}
                      />
                      <YAxis
                        tick={{ fill: 'var(--chart-axis)', fontSize: 12 }}
                        tickFormatter={(v) => `${Math.round(v / 1000)}k`}
                        tickLine={false}
                        axisLine={false}
                        width={48}
                      />
                      <Tooltip
                        content={<FanTooltip />}
                        cursor={{ stroke: 'color-mix(in srgb, var(--chart-line) 45%, transparent)', strokeDasharray: '3 3' }}
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

              <div className="panel">
                <div className="panel-title">
                  <span>Realized monthly returns</span>
                  <span className="flex items-center gap-2 font-mono text-xs normal-case text-ink-faint">
                    <span className="flex items-center gap-1.5">
                      <span className="inline-block h-2.5 w-6" style={{ background: 'linear-gradient(90deg, var(--down), transparent 50%, var(--up))' }} />
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
                                className={`flex-1 rounded-none border ${value === null ? 'border-edge-subtle bg-white' : 'border-transparent'} px-0 py-1 num-r text-xs ${value === null ? '' : heatCellText(value)}`}
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
                              tick={{ fill: 'var(--chart-axis)', fontSize: 12 }}
                              tickLine={false}
                              axisLine={{ stroke: 'var(--chart-grid)' }}
                              tickFormatter={(m) => `${m}m`}
                            />
                            <YAxis
                              tick={{ fill: 'var(--chart-axis)', fontSize: 12 }}
                              tickFormatter={(v) => `${Math.round(v / 1000)}k`}
                              tickLine={false}
                              axisLine={false}
                              width={48}
                            />
                            <Tooltip
                              content={<CrisisFanTooltip />}
                              cursor={{
                                stroke: 'color-mix(in srgb, var(--chart-line) 45%, transparent)',
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