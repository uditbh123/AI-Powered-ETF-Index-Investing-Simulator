import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ChartCandlestick,
  ChartLine,
  Sparkles,
  ArrowUpRight,
  Database,
} from 'lucide-react'
import { fetchJSON } from '../api'

const CARDS = [
  {
    to: '/tickers',
    icon: ChartCandlestick,
    title: 'Ticker catalog',
    body: 'Browse the 13 ETFs and indices tracked by the simulator, with price history coverage per instrument.',
    cta: 'View tickers',
  },
  {
    to: '/simulator',
    icon: ChartLine,
    title: 'Monte Carlo simulator',
    body: 'Define holdings, contributions and horizon, then run a simulation to see the median growth trajectory.',
    cta: 'Run a simulation',
  },
]

function StatTile({ icon: Icon, label, value }) {
  return (
    <div className="panel px-4 py-3">
      <div className="flex items-center gap-1.5 text-ink-faint">
        <Icon size={13} strokeWidth={1.8} />
        <span className="text-[11px] font-medium uppercase tracking-[0.08em]">
          {label}
        </span>
      </div>
      <div className="mt-1.5 font-mono text-2xl text-ink">{value}</div>
    </div>
  )
}

export default function Home() {
  const [stats, setStats] = useState({ instruments: '—', pricePoints: '—' })

  useEffect(() => {
    fetchJSON('/tickers')
      .then((tickers) => {
        setStats({
          instruments: tickers.length.toLocaleString(),
          pricePoints: tickers
            .reduce((n, t) => n + (t.price_rows || 0), 0)
            .toLocaleString(),
        })
      })
      .catch(() => {})
  }, [])

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Overview
          </h1>
          <p className="mt-1 text-sm text-ink-soft">
            Study long-term ETF and index investing with historical data,
            Monte Carlo simulations and news sentiment analysis.
          </p>
        </div>
        <span className="chip shrink-0">
          <Sparkles size={11} strokeWidth={2} className="text-accent" />
          Data up to date
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {CARDS.map(({ to, icon: Icon, title, body, cta }) => (
          <Link
            key={to}
            to={to}
            className="panel group flex flex-col gap-2 bg-base-panel px-4 py-4 transition-colors hover:border-edge-strong hover:bg-base-hover"
          >
            <span className="flex items-center justify-between">
              <span className="flex h-8 w-8 items-center justify-center rounded-md border border-edge-subtle bg-base-elevated text-accent">
                <Icon size={15} strokeWidth={1.8} />
              </span>
              <ArrowUpRight
                size={15}
                strokeWidth={1.8}
                className="text-ink-dim transition-colors group-hover:text-accent"
              />
            </span>
            <span className="mt-1 text-lg font-semibold tracking-wide text-ink">
              {title}
            </span>
            <span className="text-sm leading-relaxed text-ink-soft">{body}</span>
            <span className="mt-1 text-sm font-medium text-accent">{cta} →</span>
          </Link>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <StatTile icon={Database} label="Instruments" value={stats.instruments} />
        <StatTile
          icon={ChartCandlestick}
          label="Price points"
          value={stats.pricePoints}
        />
      </div>
    </div>
  )
}