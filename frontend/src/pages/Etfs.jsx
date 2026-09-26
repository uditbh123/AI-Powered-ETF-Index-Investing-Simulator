import { useEffect, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, ArrowUpDown, BarChart3 } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { fetchJSON } from '../api'
import { usePageTitle } from '../hooks/usePageTitle'

const COLUMNS = [
  { key: 'symbol', label: 'Symbol', align: 'left', kind: 'symbol' },
  { key: 'name', label: 'Name', align: 'left', kind: 'text' },
  { key: 'sector', label: 'Sector', align: 'left', kind: 'text' },
  { key: 'one_year_total_return_pct', label: '1Y', align: 'right', kind: 'pct', tone: 'signed' },
  { key: 'one_day_change_pct', label: '1D', align: 'right', kind: 'pct', tone: 'signed' },
  { key: 'annualized_volatility_pct', label: 'Vol (ann.)', align: 'right', kind: 'pct' },
  { key: 'max_drawdown_pct', label: 'Max DD (1Y)', align: 'right', kind: 'pct', tone: 'drawdown' },
  { key: 'latest_close', label: 'Latest', align: 'right', kind: 'price' },
]

function fmtPrice(value) {
  return value == null
    ? '—'
    : value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(value) {
  return value == null ? '—' : `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

function cellTone(row, column) {
  if (!column.tone) return ''
  const value = row[column.key]
  if (value == null) return 'text-ink-faint'
  if (column.tone === 'drawdown') return value < 0 ? 'text-neg' : 'text-ink-faint'
  return value >= 0 ? 'text-pos' : 'text-neg'
}

function cellContent(row, column) {
  if (column.kind === 'text' || column.kind === 'symbol') return row[column.key]
  if (column.kind === 'price') return fmtPrice(row[column.key])
  return fmtPct(row[column.key])
}

function cellClass(column) {
  const columns = ['px-4 py-2', 'text-sm']
  columns.push(column.align === 'right' ? 'text-right' : 'text-left')
  if (column.kind === 'symbol') columns.push('font-mono font-semibold text-accent')
  if (column.kind === 'pct' || column.kind === 'price') columns.push('num')
  return columns.join(' ')
}

function fetchScreener() {
  return fetchJSON('/screener')
}

function SortIcon({ column, sortKey, sortDir }) {
  if (sortKey !== column.key) {
    return <ArrowUpDown size={11} strokeWidth={1.8} className="text-ink-dim" />
  }
  return sortDir === 'asc' ? (
    <ArrowUp size={11} strokeWidth={2} className="text-accent" />
  ) : (
    <ArrowDown size={11} strokeWidth={2} className="text-accent" />
  )
}

export default function Etfs() {
  usePageTitle('ETF Screener — ETF Simulator')

  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sortKey, setSortKey] = useState('symbol')
  const [sortDir, setSortDir] = useState('asc')
  const navigate = useNavigate()

  useEffect(() => {
    fetchScreener()
      .then(setRows)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  function refresh() {
    setLoading(true)
    setError(null)
    fetchScreener()
      .then(setRows)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }

  const sortedRows = useMemo(() => {
    const direction = sortDir === 'asc' ? 1 : -1
    return [...rows].sort((a, b) => {
      const left = a[sortKey]
      const right = b[sortKey]
      if (left == null && right == null) return 0
      if (left == null) return 1
      if (right == null) return -1
      if (typeof left === 'string' || typeof right === 'string') {
        return String(left).localeCompare(String(right)) * direction
      }
      return (left - right) * direction
    })
  }, [rows, sortKey, sortDir])

  function toggleSort(key) {
    if (key === sortKey) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            ETF screener
          </h1>
          <p className="mt-1 max-w-prose text-sm text-ink-soft">
            Screening stats computed from stored price history. Click a row to
            open it in the simulator.
          </p>
        </div>
        {!loading && !error && (
          <span className="chip shrink-0">
            <BarChart3 size={11} strokeWidth={2} className="text-accent" />
            {rows.length.toString().padStart(2, '0')} tracked
          </span>
        )}
      </div>

      {loading && (
        <div className="panel space-y-2 p-4">
          <div className="h-4 w-1/3 bg-base-hover" />
          <div className="h-9 bg-base-hover" />
          <div className="h-9 bg-base-hover" />
        </div>
      )}

      {error && (
        <div className="panel px-4 py-3 text-sm text-neg">
          Error loading screener: {error}
        </div>
      )}

      {!loading && !error && sortedRows.length === 0 && (
        <div className="panel px-4 py-8">
          <p className="text-sm text-ink-soft">
            No ETF pricing data yet — screener metrics are computed from
            stored daily closes.
          </p>
          <p className="mt-2 text-xs text-ink-faint">
            Ingest historical prices, then refresh:
          </p>
          <div className="mt-3 flex items-center gap-3">
            <button type="button" className="btn" onClick={refresh}>
              Refresh
            </button>
            <span className="font-mono text-xs text-ink-soft">
              python -m app.scripts.ingest
            </span>
          </div>
        </div>
      )}

      {!loading && !error && sortedRows.length > 0 && (
        <div className="panel overflow-hidden">
          <div className="max-h-[calc(100vh-220px)] overflow-auto">
            <table className="w-full border-collapse">
              <thead className="sticky top-0 z-10 bg-white text-left">
                <tr className="border-b border-edge">
                  {COLUMNS.map((column) => (
                    <th key={column.key} className="px-4 py-2">
                      <button
                        type="button"
                        onClick={() => toggleSort(column.key)}
                        className={`flex items-center gap-1.5 text-xs font-semibold uppercase tracking-widest text-ink-faint transition-colors hover:text-ink-soft ${
                          column.align === 'right' ? 'ml-auto' : ''
                        }`}
                      >
                        {column.label}
                        <SortIcon column={column} sortKey={sortKey} sortDir={sortDir} />
                      </button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sortedRows.map((row) => (
                  <tr
                    key={row.symbol}
                    onClick={() => navigate(`/simulator?ticker=${row.symbol}`)}
                    title={`Run a simulation with ${row.symbol}`}
                    className="cursor-pointer border-b border-edge-subtle transition-colors last:border-0 hover:bg-base-hover"
                  >
                    {COLUMNS.map((column) => (
                      <td key={column.key} className={`${cellClass(column)} ${cellTone(row, column)}`}>
                        {cellContent(row, column)}
                      </td>
                    ))}
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