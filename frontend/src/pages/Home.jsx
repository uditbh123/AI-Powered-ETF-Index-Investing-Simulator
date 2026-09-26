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
import { usePageTitle } from '../hooks/usePageTitle'

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
    return <span className="h-[18px] w-12 shrink-0" aria-hidden="true" />
  }
  const width = 48
  const height = 18
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
        strokeWidth={1}
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
        'flex w-full items-center gap-2 border-l-2 px-2.5 py-[5px] text-left transition-colors',
        active
          ? 'border-ink bg-base-hover'
          : 'border-transparent hover:border-ink/20 hover:bg-base-hover',
      ].join(' ')}
    >
      <span className="min-w-0 flex-1">
        <span className="num block text-sm font-semibold text-ink">
          {ticker.symbol}
        </span>
        <span className="block text-11px leading-tight text-ink-faint">
          {ticker.name}
        </span>
      </span>
      <Sparkline values={prices?.map((p) => p.close)} positive={positive} />
      {/* Fixed-width figure column: every price and pct is monospaced, so the
          decimal points line up down the whole list. Do not reorder these two
          rows independently. 76px fits a 10-glyph figure such as "123,456.78"
          at 12px Plex Mono (0.6em advance); do not narrow it without checking
          the widest plausible price. */}
      <span className="w-[76px] shrink-0">
        <span className="num-r block text-xs text-ink">
          {stats ? formatPrice(stats.latest) : '—'}
        </span>
        <span
          className={[
            'num-r block text-11px leading-tight',
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
    <div className="border border-ink bg-base-panel px-2 py-1.5">
      <div className="text-11px uppercase tracking-widest text-ink-faint">
        {symbol} · {label}
      </div>
      <div className="num mt-0.5 text-sm text-ink">
        {formatPrice(payload[0].value)}
      </div>
    </div>
  )
}

export default function Home() {
  usePageTitle('Home — ETF Simulator')

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
      <h1 className="sr-only">Market dashboard</h1>
      {/* ---- Primary chart pane ---- */}
      <section className="flex min-h-[460px] min-w-0 flex-1 flex-col border-b border-edge lg:min-h-0 lg:border-b-0 lg:border-r">
        <div className="flex flex-wrap items-end justify-between gap-x-10 gap-y-4 border-b border-edge px-6 pb-5 pt-6 lg:px-8">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2.5">
              <span className="num text-2xl font-semibold tracking-tight text-ink">
                {activeSymbol || '—'}
              </span>
              {activeTicker?.sector && (
                <span className="chip">{activeTicker.sector}</span>
              )}
            </div>
            <div className="mt-1.5 truncate text-xs text-ink-faint">
              {activeTicker?.name || ''}
            </div>
          </div>

          {/* Price is the anchor of this header, so it gets the largest type in
              the app and sits on the shared baseline with its own delta. */}
          {activeStats && (
            <div className="flex shrink-0 items-baseline gap-3">
              <span className="num text-2xl font-semibold tracking-tight text-ink">
                {formatPrice(activeStats.latest)}
              </span>
              <span
                className={[
                  'num text-xs',
                  activeStats.changePct >= 0 ? 'tick-up' : 'tick-down',
                ].join(' ')}
              >
                {activeStats.changePct >= 0 ? '+' : ''}
                {activeStats.change.toFixed(2)} (
                {activeStats.changePct.toFixed(2)}%)
              </span>
            </div>
          )}

          <div className="flex shrink-0 items-center gap-2">
            <select
              className="select h-7 w-[150px] py-0 text-xs"
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
            <div className="flex items-center border border-edge-subtle divide-x divide-edge-subtle">
              {Object.keys(RANGE_POINTS).map((key) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => setRange(key)}
                  aria-pressed={range === key}
                  className={[
                    'num px-1.5 py-1 text-11px transition-colors',
                    range === key
                      ? 'bg-ink text-white'
                      : 'text-ink-faint hover:bg-base-hover hover:text-ink',
                  ].join(' ')}
                >
                  {key}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Generous negative space: the plot is inset far from the header rule
            and the pane edges so the series reads as the only focal object. */}
        <div className="relative min-h-0 flex-1 px-6 pb-10 pt-12 lg:px-12 lg:pb-14 lg:pt-16">
          {loadingChart ? (
            <div className="flex h-full items-center justify-center text-sm text-ink-faint">
              Loading price history…
            </div>
          ) : chartError ? (
            <div className="flex h-full items-center justify-center text-sm text-neg">
              {chartError}
            </div>
          ) : chartData.length ? (
            <div
              className="h-full w-full"
              role="img"
              aria-label={`Price history chart for ${activeSymbol ?? 'the selected instrument'}`}
            >
              <ResponsiveContainer width="100%" height="100%">
              <AreaChart
                data={chartData}
                margin={{ top: 8, right: 8, bottom: 4, left: 0 }}
              >
                {/* Solid hairlines only - no dashes anywhere in the plot. */}
                <CartesianGrid
                  stroke="var(--chart-grid)"
                  vertical={false}
                />
                <XAxis
                  dataKey="date"
                  tick={{
                    fill: 'var(--chart-axis)',
                    fontSize: 11,
                    fontFamily: 'var(--font-mono)',
                  }}
                  tickLine={false}
                  axisLine={{ stroke: 'var(--chart-grid)' }}
                  minTickGap={72}
                  height={20}
                  tickFormatter={formatAxisDate}
                />
                <YAxis
                  domain={['auto', 'auto']}
                  tick={{
                    fill: 'var(--chart-axis)',
                    fontSize: 11,
                    fontFamily: 'var(--font-mono)',
                  }}
                  tickLine={false}
                  axisLine={false}
                  width={52}
                  tickFormatter={formatAxisPrice}
                />
                <Tooltip
                  content={<PriceTooltip symbol={activeSymbol} />}
                  isAnimationActive={false}
                  cursor={{
                    stroke: 'var(--chart-axis)',
                    strokeWidth: 1,
                    strokeOpacity: 0.6,
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="close"
                  stroke="var(--chart-line)"
                  strokeWidth={1.5}
                  fill="var(--chart-line)"
                  fillOpacity={0.04}
                  dot={false}
                  activeDot={{
                    r: 2.5,
                    fill: 'var(--chart-line)',
                    stroke: 'var(--chart-surface)',
                    strokeWidth: 1,
                  }}
                  isAnimationActive={false}
                />
              </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="flex h-full items-center justify-center text-sm text-ink-faint">
              No price history for this instrument.
            </div>
          )}
        </div>
      </section>

      {/* ---- Watchlist pane ---- */}
      <aside className="flex w-full shrink-0 flex-col lg:w-[288px]">
        <div className="flex items-center justify-between gap-2 px-3.5 pb-1.5 pt-3">
          <span className="text-11px font-semibold uppercase tracking-widest text-ink-soft">
            Top ETFs
          </span>
          <span className="num text-11px text-ink-faint">
            {filtered.length.toString().padStart(2, '0')}
          </span>
        </div>

        <div className="px-3 pb-2">
          <div className="relative">
            <Search
              size={12}
              strokeWidth={2}
              className="pointer-events-none absolute left-2 top-1/2 -translate-y-1/2 text-ink-faint"
            />
            <input
              type="text"
              className="input h-7 py-0 pl-7 text-xs"
              placeholder="Search symbol or name"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              aria-label="Filter watchlist"
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto border-t border-edge">
          {loadingList ? (
            <div className="space-y-px p-3">
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-9 bg-base-hover" />
              ))}
            </div>
          ) : listError ? (
            <p className="px-3.5 py-3 text-xs text-neg">{listError}</p>
          ) : filtered.length === 0 ? (
            query.trim() ? (
              <p className="px-3.5 py-3 text-xs text-ink-faint">
                No instruments match “{query}”.
              </p>
            ) : (
              <div className="px-3.5 py-4">
                <p className="text-xs text-ink-soft">
                  No price data yet, so the watchlist is empty.
                </p>
                <p className="mt-2 text-xs text-ink-faint">
                  Ingest historical closes to populate it:
                </p>
                <p className="num mt-1 text-xs text-ink-soft">
                  python -m app.scripts.ingest
                </p>
              </div>
            )
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
