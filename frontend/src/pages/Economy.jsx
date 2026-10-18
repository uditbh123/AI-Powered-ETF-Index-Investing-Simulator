import { useEffect, useState } from 'react'
import { Check, Globe, Minus } from 'lucide-react'
import { fetchJSON } from '../api'
import { usePageTitle } from '../hooks/usePageTitle'

function formatValue(value, unit) {
  if (value === null || value === undefined) return '—'
  const rendered = Number.isInteger(value) ? String(value) : value.toFixed(2)
  return unit ? `${rendered}${unit}` : rendered
}

// Group flat indicator rows into { indicator, label, rows[] }, preserving the
// backend's indicator/country ordering so the page is stable between loads.
function groupByIndicator(indicators) {
  const groups = new Map()
  for (const row of indicators) {
    if (!groups.has(row.indicator)) {
      groups.set(row.indicator, {
        indicator: row.indicator,
        label: row.label || row.indicator,
        rows: [],
      })
    }
    groups.get(row.indicator).rows.push(row)
  }
  return [...groups.values()]
}

function ProviderRow({ provider }) {
  return (
    <li className="flex items-start gap-2">
      <span
        className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center border border-edge ${
          provider.configured ? 'text-pos' : 'text-ink-faint'
        }`}
      >
        {provider.configured ? (
          <Check size={12} strokeWidth={2.4} />
        ) : (
          <Minus size={12} strokeWidth={2.4} />
        )}
      </span>
      <span className="min-w-0">
        <span className="block text-sm text-ink">{provider.name}</span>
        <span className="mt-0.5 block text-xs leading-snug text-ink-dim">
          {provider.description}
        </span>
      </span>
    </li>
  )
}

export default function Economy() {
  usePageTitle('Macro Economy — ETF Simulator')

  const [economy, setEconomy] = useState(null)
  const [providers, setProviders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      fetchJSON('/economy/indicators'),
      fetchJSON('/economy/providers').catch(() => ({ providers: [] })),
    ])
      .then(([economyData, providerData]) => {
        if (cancelled) return
        setEconomy(economyData)
        setProviders(providerData.providers || [])
      })
      .catch((e) => {
        if (!cancelled) setError(e.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const groups = economy ? groupByIndicator(economy.indicators) : []

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-ink">Macro Economy</h1>
          <p className="mt-0.5 text-sm text-ink-soft">
            Macro indicators pulled offline by{' '}
            <span className="font-mono text-xs">intel_ingest</span>.
          </p>
        </div>
        {economy && (
          <span className="chip">
            {economy.count} indicators
            {economy.as_of ? ` · as of ${economy.as_of}` : ''}
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
          Error loading macro data: {error}
        </div>
      )}

      {!loading && !error && economy && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[240px_minmax(0,1fr)]">
          <div className="panel space-y-3 p-4">
            <div>
              <span className="block text-xs font-medium uppercase tracking-widest text-ink-faint">
                Data sources
              </span>
              <p className="mt-1 text-xs leading-snug text-ink-dim">
                Providers run at ingest time only; a page load never calls out.
              </p>
            </div>
            {providers.length === 0 ? (
              <p className="text-xs text-ink-faint">Provider status unavailable.</p>
            ) : (
              <ul className="space-y-2.5">
                {providers.map((p) => (
                  <ProviderRow key={p.name} provider={p} />
                ))}
              </ul>
            )}
          </div>

          {groups.length === 0 ? (
            <div className="panel p-4">
              <span className="mb-3 flex h-9 w-9 items-center justify-center border border-edge bg-base-elevated text-ink-dim">
                <Globe size={16} strokeWidth={1.6} />
              </span>
              <p className="text-sm text-ink-soft">No macro indicators stored yet.</p>
              <p className="mt-2 text-xs text-ink-faint">
                Populate this page by running the ingest CLI:
              </p>
              <code className="mt-3 block border border-edge bg-base-elevated px-3 py-2 font-mono text-xs text-ink-soft">
                python -m app.scripts.intel_ingest --providers tradingeconomics
              </code>
            </div>
          ) : (
            <div className="space-y-4">
              {groups.map((group) => (
                <div key={group.indicator} className="panel">
                  <div className="flex items-baseline justify-between gap-3 border-b border-edge-subtle px-4 py-3">
                    <span className="text-sm font-semibold text-ink">{group.label}</span>
                    <span className="font-mono text-xs text-ink-faint">
                      {group.rows[0]?.source || 'tradingeconomics'}
                    </span>
                  </div>
                  <table className="w-full">
                    <tbody>
                      {group.rows.map((row) => (
                        <tr
                          key={`${row.country}-${row.indicator}`}
                          className="border-b border-edge-subtle last:border-0"
                        >
                          <td className="px-4 py-2 text-sm text-ink">{row.country}</td>
                          <td className="px-4 py-2 text-right num text-sm text-ink">
                            {formatValue(row.value, row.unit)}
                          </td>
                          <td className="px-4 py-2 text-right font-mono text-xs text-ink-dim">
                            {row.period || '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
