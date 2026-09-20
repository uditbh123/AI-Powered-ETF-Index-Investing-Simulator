import { useEffect, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { fetchJSON } from '../api'
import './Simulator.css'

const DEFAULT_HOLDINGS = [{ symbol: 'SPY', weight: 100 }]

function formatCurrency(value) {
  return value.toLocaleString(undefined, {
    style: 'currency',
    currency: 'USD',
    maximumFractionDigits: 0,
  })
}

export default function Simulator() {
  const [tickers, setTickers] = useState([])
  const [name, setName] = useState('My Portfolio')
  const [contribution, setContribution] = useState(200)
  const [initialBalance, setInitialBalance] = useState(10000)
  const [horizonYears, setHorizonYears] = useState(10)
  const [holdings, setHoldings] = useState(DEFAULT_HOLDINGS)

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
        }),
      })
      setResult(sim)
      setPhase('done')
    } catch (e) {
      setError(e.message)
      setPhase('idle')
    }
  }

  const medianBand = result?.percentiles.find((p) => p.level === 50)
  const chartData = medianBand?.path.map((value, month) => ({
    month,
    value: Math.round(value),
  }))

  return (
    <section>
      <h1>Simulator</h1>
      <p>
        Configure a hypothetical portfolio, then run a Monte Carlo simulation
        to see its median growth trajectory.
      </p>

      <form className="sim-form" onSubmit={runSimulation}>
        <div className="sim-grid">
          <label className="field">
            <span>Portfolio name</span>
            <input type="text" value={name} onChange={updateSetting(setName)} />
          </label>

          <label className="field">
            <span>Monthly contribution ($)</span>
            <input
              type="number"
              min="0"
              step="50"
              value={contribution}
              onChange={updateSetting(setContribution)}
            />
          </label>

          <label className="field">
            <span>Current balance ($)</span>
            <input
              type="number"
              min="0"
              step="500"
              value={initialBalance}
              onChange={updateSetting(setInitialBalance)}
            />
          </label>

          <label className="field">
            <span>Investment horizon (years)</span>
            <input
              type="number"
              min="1"
              max="50"
              value={horizonYears}
              onChange={updateSetting(setHorizonYears)}
            />
          </label>
        </div>

        <fieldset className="holdings-fieldset">
          <legend>Holdings</legend>
          {holdings.map((holding, index) => (
            <div className="holding-row" key={index}>
              <label className="field inline">
                <span>Ticker</span>
                <select
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
              </label>
              <label className="field inline">
                <span>Weight (%)</span>
                <input
                  type="number"
                  min="0"
                  step="1"
                  value={holding.weight}
                  onChange={(e) => updateHolding(index, 'weight', e.target.value)}
                />
              </label>
              <button
                type="button"
                className="icon-btn"
                onClick={() => removeHolding(index)}
                disabled={holdings.length <= 1}
                aria-label="Remove holding"
              >
                ✕
              </button>
            </div>
          ))}
          <button type="button" className="add-btn" onClick={addHolding}>
            + Add holding
          </button>
        </fieldset>

        {error && <p className="form-error">Error: {error}</p>}

        <button type="submit" className="sim-btn" disabled={phase === 'running'}>
          {phase === 'running' ? 'Simulating…' : 'Run simulation'}
        </button>
      </form>

      {result && (
        <div className="results">
          <div className="summary-card">
            <div className="stat best">
              <span className="stat-label">Best case (95th)</span>
              <span className="stat-value">
                {formatCurrency(result.summary.best_case_final_value)}
              </span>
            </div>
            <div className="stat">
              <span className="stat-label">Median outcome</span>
              <span className="stat-value">
                {formatCurrency(result.summary.median_final_value)}
              </span>
            </div>
            <div className="stat worst">
              <span className="stat-label">Worst case (5th)</span>
              <span className="stat-value">
                {formatCurrency(result.summary.worst_case_final_value)}
              </span>
            </div>
          </div>

          <div className="chart-card">
            <h2>Median growth trajectory</h2>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis
                  dataKey="month"
                  label={{ value: 'Months', position: 'insideBottomRight', offset: -4 }}
                  tickFormatter={(m) => (m % 12 === 0 ? m / 12 : '')}
                />
                <YAxis
                  tickFormatter={(v) => `${Math.round(v / 1000)}k`}
                  width={56}
                />
                <Tooltip
                  formatter={(value) => [formatCurrency(value), 'Portfolio value']}
                  labelFormatter={(month) =>
                    `Year ${Math.floor(month / 12)} · month ${month % 12}`
                  }
                />
                <Line
                  type="monotone"
                  dataKey="value"
                  stroke="var(--accent)"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>

          {result.cached && (
            <p className="cache-note">Loaded from cached simulation results.</p>
          )}
        </div>
      )}
    </section>
  )
}