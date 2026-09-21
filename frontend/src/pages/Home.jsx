import { useEffect, useMemo, useState } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Search } from 'lucide-react'
import { fetchJSON } from '../api'

const RECENT_POINTS = 30

const RANGE_POINTS = {
  '1M': 21,
  '3M': 63,
  '6M': 126,
  '1Y': 252,
  '5Y': 1260,
  MAX: Infinity,
}

function formatPrice(value) {
  if (value == null) return '—'
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatAxisPrice(value) {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}k`
  return `${Math.round(value)}`
}

function formatAxisDate(date) {
  const parsed = new Date(date)
  if (Number.isNaN(parsed.getTime())) return date
  return parsed.toLocaleDateString(undefined, { month: 'short', year: '2-digit' })
}

function orderInstruments(list) {
  return list
    .filter((t) => t.price_rows > 0)
    .sort((a, b) => {
      const aIndex = a.symbol.startsWith('^') ? 1 : 0
      const bIndex = b.symbol.startsWith('^') ? 1 : 0
      if (aIndex !== bIndex) return aIndex - bIndex
      return (
        (b.price_rows || 0) - (a.price_rows || 0) ||
        a.symbol.localeCompare(b.symbol)
      )
    })
}

function summarize(prices) {
  if (!prices || prices.length === 0) return null
  const latest = prices[prices.length - 1].close
  if (prices.length === 1) return { latest, change: 0, changePct: 0 }
  const prev = prices[prices.length - 2].close
  const change = latest - prev
  const changePct = prev ? (change / prev) * 100 : 0
  return { latest, change, changePct }
}

function Sparkline({ values, positive }) {
  if (!values || values.length < 2) {
    return <span className="h-6 w-14 shrink-0" aria-hidden="true" />
  }
  const width = 56
  const height = 24
  const min = Math.min(...values)
  const max = Math.max(...values)
  const span = max - min || 1
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * width
      const y = height - ((value - min) / span) * height
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      className={`shrink-0 ${positive ? 'text-pos' : 'text-neg'}`}
    >
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth={1.25}
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

function WatchRow({ ticker, prices, active, onSelect }) {
  const stats = summarize(prices)
  const positive = stats ? stats.changePct >= 0 : true

  return (
    <button
      type="button"
      onClick={onSelect}
      className={[
        'flex w-full items-center gap-2 border-l-2 px-3 py-2 text-left transition-colors',
        active
          ? 'border-accent bg-white/[0.04]'
          : 'border-transparent hover:border-white/20 hover:bg-white/[0.03]',
      ].join(' ')}
    >
      <span className="min-w-0 flex-1">
        <span className="block font-mono text-sm font-semibold text-ink">
          {ticker.symbol}
        </span>
        <span className="block truncate text-[11px] text-ink-faint">
          {ticker.name}
        </span>
      </span>
      <Sparkline values={prices?.map((p) => p.close)} positive={positive} />
      <span className="w-[76px] shrink-0 text-right">
        <span className="block font-mono text-[12px] text-ink tabular-nums">
          {stats ? formatPrice(stats.latest) : '—'}
        </span>
        <span
          className={[
            'block font-mono text-[11px] tabular-nums',
            positive ? 'tick-up' : 'tick-down',
          ].join(' ')}
        >
          {stats ? `${positive ? '+' : ''}${stats.changePct.toFixed(2)}%` : ''}
        </span>
      </span>
    </button>
  )
}

function PriceTooltip({ active, payload, label, symbol }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rounded-md border border-white/10 bg-black px-3 py-2">
      <div className="text-[11px] text-ink-faint">
        {symbol} · {label}
      </div>
      <div className="mt-0.5 font-mono text-sm text-accent tabular-nums">
        {formatPrice(payload[0].value)}
      </div>
    </div>
  )
}

export default function Home() {
  const [tickers, setTickers] = useState([])
  const [seriesBySymbol, setSeriesBySymbol] = useState({})
  const [activeSymbol, setActiveSymbol] = useState(null)
  const [history, setHistory] = useState([])
  const [historySymbol, setHistorySymbol] = useState(null)
  const [range, setRange] = useState('MAX')
  const [query, setQuery] = useState('')
  const [loadingList, setLoadingList] = useState(true)
  const [listError, setListError] = useState(null)
  const [chartError, setChartError] = useState(null)

  // Load the catalog, then pull a short recent series for every instrument so
  // the watchlist can show latest price + sparkline.
  useEffect(() => {
    let cancelled = false

    async function load() {
      try {
        const list = await fetchJSON('/tickers')
        if (cancelled) return
        setTickers(list)

        const tradable = orderInstruments(list)

        const preferred = tradable.find((t) => t.symbol === 'SPY') || tradable[0]
        if (preferred) setActiveSymbol(preferred.symbol)

        const results = await Promise.allSettled(
          tradable.map((t) =>
            fetchJSON(
              `/tickers/${encodeURIComponent(t.symbol)}/prices?limit=${RECENT_POINTS}`,
            ),
          ),
        )
        if (cancelled) return
        const map = {}
        results.forEach((result, index) => {
          if (result.status === 'fulfilled') {
            map[tradable[index].symbol] = result.value.prices
          }
        })
        setSeriesBySymbol(map)
      } catch (e) {
        if (!cancelled) setListError(e.message)
      } finally {
        if (!cancelled) setLoadingList(false)
      }
    }

    load()
    return () => {
      cancelled = true
    }
  }, [])

  // Full history for the active instrument.
  useEffect(() => {
    if (!activeSymbol) return
    let cancelled = false
    fetchJSON(`/tickers/${encodeURIComponent(activeSymbol)}/prices`)
      .then((res) => {
        if (!cancelled) {
          setHistory(res.prices)
          setHistorySymbol(activeSymbol)
          setChartError(null)
        }
      })
      .catch((e) => {
        if (!cancelled) setChartError(e.message)
      })
    return () => {
      cancelled = true
    }
  }, [activeSymbol])

  const ordered = useMemo(() => orderInstruments(tickers), [tickers])

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase()
    if (!needle) return ordered
    return ordered.filter(
      (t) =>
        t.symbol.toLowerCase().includes(needle) ||
        (t.name || '').toLowerCase().includes(needle),
    )
  }, [ordered, query])

  const activeTicker = tickers.find((t) => t.symbol === activeSymbol)
  const historyReady = activeSymbol != null && historySymbol === activeSymbol
  const loadingChart = activeSymbol != null && !historyReady
  const activeStats = historyReady ? summarize(history) : null

  const chartData = useMemo(() => {
    if (!historyReady) return []
    const count = RANGE_POINTS[range]
    const sliced = count === Infinity ? history : history.slice(-count)
    return sliced.map((point) => ({ date: point.date, close: point.close }))
  }, [history, historyReady, range])

  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto lg:flex-row lg:overflow-hidden">
      {/* ---- Primary chart pane ---- */}
      <section className="flex min-h-[460px] min-w-0 flex-1 flex-col border-b border-white/10 lg:min-h-0 lg:border-b-0 lg:border-r">
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-b border-white/5 px-4 py-2.5">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="font-mono text-lg font-semibold leading-none text-ink">
                {activeSymbol || '—'}
              </span>
              {activeTicker?.sector && (
                <span className="chip">{activeTicker.sector}</span>
              )}
            </div>
            <div className="mt-1 truncate text-[11px] text-ink-faint">
              {activeTicker?.name || ''}
            </div>
          </div>

          {activeStats && (
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-xl text-ink tabular-nums">
                {formatPrice(activeStats.latest)}
              </span>
              <span
                className={[
                  'font-mono text-[12px] tabular-nums',
                  activeStats.changePct >= 0 ? 'tick-up' : 'tick-down',
                ].join(' ')}
              >
                {activeStats.changePct >= 0 ? '+' : ''}
                {activeStats.change.toFixed(2)} (
                {activeStats.changePct.toFixed(2)}%)
              </span>
            </div>
          )}

          <div className="ml-auto flex items-center gap-2">
            <select
              className="select h-7 w-[160px] py-0 text-[12px]"
              value={activeSymbol || ''}
              onChange={(event) => setActiveSymbol(event.target.value)}
              aria-label="Select instrument"
            >
              {ordered.map((t) => (
                <option key={t.symbol} value={t.symbol}>
                  {t.symbol} — {t.name}
                </option>
              ))}
            </select>
            <div className="flex items-center rounded-md border border-white/10 p-0.5">
              {Object.keys(RANGE_POINTS).map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setRange(key)}
                  className={[
                    'rounded px-1.5 py-0.5 font-mono text-[10px] transition-colors',
                    range === key
                      ? 'bg-white text-black'
                      : 'text-ink-faint hover:text-white',
                  ].join(' ')}
                >
                  {key}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="relative min-h-0 flex-1 p-2">
          {loadingChart ? (
            <div className="flex h-full items-center justify-center text-sm text-ink-faint">
              Loading price history…
            </div>
          ) : chartError ? (
            <div className="flex h-full items-center justify-center text-sm text-neg">
              {chartError}
            </div>
          ) : chartData.length ? (
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={chartData}
                margin={{ top: 8, right: 12, bottom: 4, left: 0 }}
              >
                <defs>
                  <linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1">
                    <stop
                      offset="0%"
                      stopColor="var(--chart-line)"
                      stopOpacity={0.28}
                    />
                    <stop
                      offset="100%"
                      stopColor="var(--chart-line)"
                      stopOpacity={0}
                    />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  stroke="var(--chart-grid)"
                  strokeDasharray="3 3"
                  vertical={false}
                />
                <XAxis
                  dataKey="date"
                  tick={{ fill: 'var(--chart-axis)', fontSize: 11 }}
                  tickLine={false}
                  axisLine={{ stroke: 'var(--chart-grid)' }}
                  minTickGap={56}
                  tickFormatter={formatAxisDate}
                />
                <YAxis
                  domain={['auto', 'auto']}
                  tick={{ fill: 'var(--chart-axis)', fontSize: 11 }}
                  tickLine={false}
                  axisLine={false}
                  width={56}
                  tickFormatter={formatAxisPrice}
                />
                <Tooltip
                  content={<PriceTooltip symbol={activeSymbol} />}
                  cursor={{
                    stroke: 'rgba(255,255,255,0.25)',
                    strokeDasharray: '3 3',
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="close"
                  stroke="var(--chart-line)"
                  strokeWidth={1.75}
                  fill="url(#priceFill)"
                  dot={false}
                  activeDot={{
                    r: 3,
                    fill: 'var(--chart-line)',
                    stroke: 'var(--chart-glow)',
                  }}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-ink-faint">
              No price history for this instrument.
            </div>
          )}
        </div>
      </section>

      {/* ---- Watchlist pane ---- */}
      <aside className="flex w-full shrink-0 flex-col lg:w-[320px]">
        <div className="flex items-center justify-between gap-2 border-b border-white/5 px-4 py-2.5">
          <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-ink-soft">
            Top ETFs
          </span>
          <span className="font-mono text-[10px] text-ink-faint">
            {filtered.length.toString().padStart(2, '0')}
          </span>
        </div>

        <div className="border-b border-white/5 px-3 py-2">
          <div className="relative">
            <Search
              size={13}
              strokeWidth={1.8}
              className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-dim"
            />
            <input
              type="text"
              className="input h-7 py-0 pl-7 text-[12px]"
              placeholder="Search symbol or name"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Filter watchlist"
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {loadingList ? (
            <div className="space-y-1 p-3">
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <div
                  key={i}
                  className="h-11 animate-pulse rounded bg-white/[0.03]"
                />
              ))}
            </div>
          ) : listError ? (
            <p className="px-4 py-3 text-xs text-neg">{listError}</p>
          ) : filtered.length === 0 ? (
            <p className="px-4 py-3 text-xs text-ink-faint">
              No instruments match “{query}”.
            </p>
          ) : (
            filtered.map((ticker) => (
              <WatchRow
                key={ticker.symbol}
                ticker={ticker}
                prices={seriesBySymbol[ticker.symbol]}
                active={ticker.symbol === activeSymbol}
                onSelect={() => setActiveSymbol(ticker.symbol)}
              />
            ))
          )}
        </div>
      </aside>
    </div>
  )
}
