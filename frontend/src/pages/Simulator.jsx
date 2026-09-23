import { useEffect, useState } from 'react'
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
  Calculator,
  Gauge,
  Play,
  Plus,
  Sparkles,
  Trash,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import { fetchJSON } from '../api'

const DEFAULT_HOLDINGS = [{ symbol: 'SPY', weight: 100 }]

function formatCurrency(value) {
  return value.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  })
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
    <div className="rounded-md border border-white/10 bg-black px-3 py-2">
      <div className="text-[11px] text-ink-faint">
        Year {Math.floor(point.month / 12)} · month {point.month % 12}
      </div>
      <div className="mt-1 space-y-0.5 font-mono text-[12px] tabular-nums">
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

function ToggleSwitch({ checked, onChange, title, subtitle }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="flex w-full items-center justify-between gap-3 rounded-md border border-white/10 bg-white/[0.02] px-2.5 py-2 text-left transition-colors hover:border-white/30"
    >
      <span className="min-w-0">
        <span className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-soft">
          <Sparkles
            size={11}
            strokeWidth={1.8}
            className={checked ? 'text-accent' : 'text-ink-dim'}
          />
          {title}
        </span>
        <span className="mt-0.5 block text-[11px] leading-snug text-ink-dim">
          {subtitle}
        </span>
      </span>
      <span
        className={[
          'relative h-4 w-8 shrink-0 rounded-full border transition-colors',
          checked ? 'border-accent bg-accent/25' : 'border-white/20 bg-white/5',
        ].join(' ')}
      >
        <span
          className={[
            'absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full transition-all',
            checked ? 'left-[15px] bg-accent' : 'left-0.5 bg-ink-faint',
          ].join(' ')}
        />
      </span>
    </button>
  )
}

export default function Simulator() {
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

  useEffect(() => {
    fetchJSON('/tickers')
      .then(setTickers)
      .catch(() => {})
  }, [])

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
    try {
      const portfolio = await fetchJSON('/portfolios', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim() || 'My Portfolio',
          monthly_contribution: Number(contribution),
          holdings,
        }),
      })
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

  const statCards = result
    ? [
        { icon: TrendingUp, label: 'Best case (90th)', value: result.summary.best_case_final_value, tone: 'tick-up' },
        { icon: Gauge, label: 'Median outcome', value: result.summary.median_final_value, tone: 'text-accent' },
        { icon: TrendingDown, label: 'Worst case (10th)', value: result.summary.worst_case_final_value, tone: 'tick-down' },
      ]
    : []

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">Simulator</h1>
        <p className="mt-1 text-sm text-ink-soft">
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
              <span className="flex items-center gap-1 font-mono text-[10px] normal-case text-accent">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent" />
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
              <span className="mb-1.5 block text-[11px] font-medium uppercase tracking-[0.06em] text-ink-faint">
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
                    <div className="flex h-8 w-16 items-center gap-0.5 rounded-md border border-edge bg-base-elevated px-1.5 focus-within:border-accent-dim">
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="1"
                        className="w-full bg-transparent text-right font-mono text-sm text-ink outline-none"
                        value={holding.weight}
                        onChange={(e) => updateHolding(index, 'weight', e.target.value)}
                      />
                      <span className="text-[11px] text-ink-faint">%</span>
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
            <div className="panel flex flex-col items-center justify-center gap-3 bg-base-panel px-6 py-20 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-full border border-edge bg-base-elevated text-ink-dim">
                <Calculator size={20} strokeWidth={1.6} />
              </span>
              <p className="text-sm text-ink-soft">
                Adjust the controls and press{' '}
                <span className="font-medium text-accent">Run simulation</span> to
                chart the 10th–90th percentile growth fan.
              </p>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                {statCards.map(({ icon: Icon, label, value, tone }) => (
                  <div key={label} className="panel flex items-center gap-3 px-4 py-3">
                    <span
                      className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-edge bg-base-elevated ${tone}`}
                    >
                      <Icon size={15} strokeWidth={1.8} />
                    </span>
                    <span className="min-w-0">
                      <span className="block text-[11px] font-medium uppercase tracking-[0.06em] text-ink-faint">
                        {label}
                      </span>
                      <span className="block truncate font-mono text-xl text-ink tabular-nums">
                        {formatCurrency(value)}
                      </span>
                    </span>
                  </div>
                ))}
              </div>

              <div className="panel bg-base-panel">
                <div className="panel-title">
                  <span>Growth fan chart · 10th–90th percentile</span>
                  <span className="flex items-center gap-2 font-mono text-[10px] normal-case text-ink-faint">
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
                        activeDot={{ r: 3, fill: 'var(--chart-line)', stroke: 'var(--chart-glow)' }}
                      />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {result.cached && (
                <p className="text-center text-[11px] text-ink-dim">
                  Loaded from cached simulation results.
                </p>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  )
}