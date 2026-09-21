import { useEffect, useState } from 'react'
import { ChartCandlestick } from 'lucide-react'
import { fetchJSON } from '../api'

export default function Etfs() {
  const [tickers, setTickers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchJSON('/tickers')
      .then(setTickers)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            ETF catalog
          </h1>
          <p className="mt-1 text-sm text-ink-soft">
            Instruments tracked by the simulator with local price-history
            coverage.
          </p>
        </div>
        {!loading && !error && (
          <span className="chip shrink-0">
            <ChartCandlestick size={11} strokeWidth={2} className="text-accent" />
            {tickers.length.toString().padStart(2, '0')} symbols
          </span>
        )}
      </div>

      {loading && (
        <div className="panel space-y-2 p-4">
          <div className="h-4 w-1/3 animate-pulse rounded bg-base-hover" />
          <div className="h-9 animate-pulse rounded bg-base-hover" />
          <div className="h-9 animate-pulse rounded bg-base-hover" />
        </div>
      )}

      {error && (
        <div className="panel px-4 py-3 text-sm text-neg">
          Error loading tickers: {error}
        </div>
      )}

      {!loading && !error && (
        <div className="panel overflow-hidden">
          <div className="max-h-[calc(100vh-220px)] overflow-auto">
            <table className="w-full border-collapse text-sm">
              <thead className="sticky top-0 z-10 bg-base-panel text-left">
                <tr className="border-b border-edge">
                  <th className="px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-faint">
                    Symbol
                  </th>
                  <th className="px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-faint">
                    Name
                  </th>
                  <th className="px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-faint">
                    Sector
                  </th>
                  <th className="px-4 py-2 text-right text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-faint">
                    Price points
                  </th>
                  <th className="px-4 py-2 text-right text-[11px] font-semibold uppercase tracking-[0.06em] text-ink-faint">
                    Date range
                  </th>
                </tr>
              </thead>
              <tbody>
                {tickers.map((t) => (
                  <tr
                    key={t.symbol}
                    className="border-b border-edge-subtle transition-colors last:border-0 hover:bg-base-hover"
                  >
                    <td className="px-4 py-2 font-mono text-sm font-semibold text-accent">
                      {t.symbol}
                    </td>
                    <td className="px-4 py-2 text-ink">{t.name}</td>
                    <td className="px-4 py-2 text-ink-soft">{t.sector}</td>
                    <td className="px-4 py-2 text-right font-mono text-ink tabular-nums">
                      {(t.price_rows || 0).toLocaleString()}
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-[12px] text-ink-soft tabular-nums">
                      {t.first_date ? `${t.first_date} → ${t.last_date}` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
