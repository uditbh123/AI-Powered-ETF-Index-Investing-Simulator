import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  ExternalLink,
  FolderOpen,
  Pencil,
  Plus,
  Search,
  Trash,
  Wallet,
  X,
} from 'lucide-react'
import { fetchJSON } from '../api'
import { usePageTitle } from '../hooks/usePageTitle'

function formatCurrency(value) {
  const n = Number(value) || 0
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`
}

function formatDate(value) {
  if (!value) return '—'
  const [year, month, day] = String(value).split('-').map(Number)
  if (!year || !month || !day) return value
  return new Date(Date.UTC(year, month - 1, day)).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

function weightPercent(weight) {
  return Math.round(Number(weight) * 100)
}

export default function Portfolios() {
  usePageTitle('Portfolios — ETF Simulator')

  const navigate = useNavigate()
  const [portfolios, setPortfolios] = useState([])
  const [tickers, setTickers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const [mode, setMode] = useState('list') // list | create | edit
  const [editingId, setEditingId] = useState(null)
  const [query, setQuery] = useState('')
  const [form, setForm] = useState({ name: '', contribution: '100', holdings: [] })
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState(null)

  const [deleting, setDeleting] = useState(null)
  const [deletingError, setDeletingError] = useState(null)
  const deleteCancelRef = useRef(null)
  const dialogRef = useRef(null)

  useEffect(() => {
    Promise.all([fetchJSON('/portfolios'), fetchJSON('/tickers')])
      .then(([portfoliosResult, tickersResult]) => {
        setPortfolios(portfoliosResult)
        setTickers(tickersResult)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (!deleting) return
    deleteCancelRef.current?.focus()
    function onKey(event) {
      if (event.key === 'Escape') setDeleting(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [deleting])

  const tradable = useMemo(
    () => tickers.filter((t) => t.price_rows > 0),
    [tickers],
  )

  const defaultSymbol = () =>
    tradable[0]?.symbol ?? ''

  const searchMatches = useMemo(() => {
    const needle = query.trim().toLowerCase()
    const owned = new Set(form.holdings.map((h) => h.symbol))
    const pool = needle
      ? tradable.filter(
          (t) =>
            t.symbol.toLowerCase().includes(needle) ||
            (t.name || '').toLowerCase().includes(needle),
        )
      : tradable
    return pool.filter((t) => !owned.has(t.symbol)).slice(0, 5)
  }, [query, tradable, form.holdings])

  const totalWeight = useMemo(
    () =>
      form.holdings.reduce((sum, h) => sum + (Number(h.weight) || 0), 0),
    [form.holdings],
  )
  const balanced = totalWeight >= 99 && totalWeight <= 101
  const canSave = Boolean(form.name.trim()) && balanced && !saving

  function startCreate() {
    setEditingId(null)
    setFormError(null)
    setQuery('')
    setForm({
      name: '',
      contribution: '100',
      holdings: [{ symbol: defaultSymbol(), weight: '0' }],
    })
    setMode('create')
  }

  function startEdit(portfolio) {
    setEditingId(portfolio.id)
    setFormError(null)
    setQuery('')
    setForm({
      name: portfolio.name,
      contribution: String(portfolio.monthly_contribution ?? 0),
      holdings: portfolio.holdings.map((h) => ({
        symbol: h.symbol,
        weight: String(weightPercent(h.weight)),
      })),
    })
    setMode('edit')
  }

  function cancelForm() {
    setMode('list')
    setEditingId(null)
    setFormError(null)
  }

  function addHolding(symbol) {
    setForm((f) => ({
      ...f,
      holdings: [...f.holdings, { symbol: symbol || defaultSymbol(), weight: '0' }],
    }))
  }

  function updateRow(index, field, value) {
    setForm((f) => ({
      ...f,
      holdings: f.holdings.map((row, i) =>
        i === index ? { ...row, [field]: value } : row,
      ),
    }))
  }

  function removeRow(index) {
    setForm((f) => ({
      ...f,
      holdings:
        f.holdings.length > 1 ? f.holdings.filter((_, i) => i !== index) : f.holdings,
    }))
  }

  async function saveForm(event) {
    event.preventDefault()
    if (!canSave) return
    setSaving(true)
    setFormError(null)
    const body = {
      name: form.name.trim(),
      monthly_contribution: Number(form.contribution) || 0,
      holdings: form.holdings.map((row) => ({
        symbol: row.symbol,
        weight: (Number(row.weight) || 0) / 100,
      })),
    }
    try {
      const saved =
        mode === 'edit'
          ? await fetchJSON(`/portfolios/${editingId}`, {
              method: 'PATCH',
              body: JSON.stringify(body),
            })
          : await fetchJSON('/portfolios', {
              method: 'POST',
              body: JSON.stringify(body),
            })
      setPortfolios((prev) =>
        mode === 'edit'
          ? prev.map((p) => (p.id === saved.id ? saved : p))
          : [saved, ...prev],
      )
      setMode('list')
      setEditingId(null)
    } catch (e) {
      setFormError(e.message)
    } finally {
      setSaving(false)
    }
  }

  async function confirmDelete() {
    if (!deleting) return
    setDeletingError(null)
    try {
      await fetchJSON(`/portfolios/${deleting.id}`, { method: 'DELETE' })
      setPortfolios((prev) => prev.filter((p) => p.id !== deleting.id))
      setDeleting(null)
    } catch (e) {
      setDeletingError(e.message)
    }
  }

  const editsForm = mode === 'create' || mode === 'edit'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <span className="text-xs font-semibold uppercase tracking-widest text-ink-soft">
            Portfolios
          </span>
          <h1 className="mt-0.5 text-2xl font-semibold tracking-tight text-ink">
            Your portfolios
          </h1>
          <p className="mt-1 max-w-prose text-sm text-ink-soft">
            Define an allocation once, then open any portfolio in the Simulator
            to chart its projected growth.
          </p>
        </div>
        {!editsForm && (
          <div className="flex shrink-0 items-center gap-2">
            {!loading && !error && (
              <span className="chip shrink-0">
                <Wallet size={11} strokeWidth={2} className="text-accent" />
                {portfolios.length.toString().padStart(2, '0')}
              </span>
            )}
            <button type="button" className="btn btn-primary" onClick={startCreate}>
              <Plus size={14} strokeWidth={2} />
              New portfolio
            </button>
          </div>
        )}
      </div>

      {editsForm && (
        <form className="panel" onSubmit={saveForm}>
          <div className="panel-title">
            <span>{mode === 'edit' ? 'Edit portfolio' : 'New portfolio'}</span>
            <button type="button" className="btn h-7 px-2 text-xs" onClick={cancelForm}>
              <X size={12} strokeWidth={2} />
              Cancel
            </button>
          </div>

          <div className="space-y-4 p-4">
            <label className="block">
              <span className="field-label">Name</span>
              <input
                type="text"
                className="input"
                placeholder="e.g. All-World Growth"
                value={form.name}
                onChange={(event) =>
                  setForm((f) => ({ ...f, name: event.target.value }))
                }
              />
            </label>

            <label className="block">
              <span className="field-label">
                <span>Monthly contribution</span>
                <span className="field-value">{formatCurrency(form.contribution)}/mo</span>
              </span>
              <input
                type="number"
                min="0"
                step="25"
                className="input"
                value={form.contribution}
                onChange={(event) =>
                  setForm((f) => ({ ...f, contribution: event.target.value }))
                }
              />
            </label>

            <div>
              <span className="mb-1.5 block text-xs font-medium uppercase tracking-widest text-ink-faint">
                Holdings
              </span>

              <div className="relative mb-2">
                <Search
                  size={13}
                  strokeWidth={1.8}
                  className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-dim"
                />
                <input
                  type="text"
                  className="input h-8 py-0 pl-7 text-sm"
                  placeholder="Search a ticker to add…"
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  aria-label="Search tickers to add to this portfolio"
                />
                {query.trim() && (
                  <div className="absolute left-0 right-0 top-full z-20 mt-1 border border-edge bg-base-panel shadow-panel">
                    {searchMatches.length === 0 ? (
                      <p className="px-3 py-2 text-xs text-ink-faint">
                        No matching tickers.
                      </p>
                    ) : (
                      searchMatches.map((t) => (
                        <button
                          key={t.symbol}
                          type="button"
                          onClick={() => {
                            addHolding(t.symbol)
                            setQuery('')
                          }}
                          className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left transition-colors hover:bg-base-hover"
                        >
                          <span>
                            <span className="font-mono text-sm font-semibold text-ink">
                              {t.symbol}
                            </span>
                            <span className="ml-2 text-xs text-ink-faint">
                              {t.name}
                            </span>
                          </span>
                          <span className="font-mono text-xs text-ink-dim">add +</span>
                        </button>
                      ))
                    )}
                  </div>
                )}
              </div>

              <div className="space-y-2">
                {form.holdings.map((holding, index) => (
                  <div key={index} className="flex items-center gap-1.5">
                    <select
                      className="select h-8 min-w-0 flex-1"
                      value={holding.symbol}
                      onChange={(event) => updateRow(index, 'symbol', event.target.value)}
                      aria-label={`Holding ${index + 1} symbol`}
                    >
                      {tradable.map((t) => (
                        <option key={t.symbol} value={t.symbol}>
                          {t.symbol} — {t.name}
                        </option>
                      ))}
                    </select>
                    <div className="flex h-8 w-24 items-center gap-0.5 border border-edge bg-white px-1.5 focus-within:border-accent focus-within:ring-2 focus-within:ring-accent/25">
                      <input
                        type="number"
                        min="0"
                        max="100"
                        step="1"
                        className="w-full bg-transparent text-right font-mono text-sm text-ink outline-none"
                        value={holding.weight}
                        onChange={(event) => updateRow(index, 'weight', event.target.value)}
                        aria-label={`Holding ${index + 1} weight percent`}
                      />
                      <span className="text-xs text-ink-faint">%</span>
                    </div>
                    <button
                      type="button"
                      className="btn btn-danger-ghost h-8 w-8 items-center justify-center p-0"
                      onClick={() => removeRow(index)}
                      disabled={form.holdings.length <= 1}
                      aria-label={`Remove holding ${index + 1}`}
                    >
                      <Trash size={13} strokeWidth={1.8} />
                    </button>
                  </div>
                ))}
              </div>

              <span className="mt-1.5 block text-xs text-ink-faint">
                Enter each holding's weight as a percent; they must total 100%
                (±1%) before saving.
              </span>

              <div className="mt-3 border-t border-edge pt-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium uppercase tracking-widest text-ink-faint">
                    Total weight
                  </span>
                  <span
                    className={
                      balanced ? 'font-mono text-sm text-pos' : 'font-mono text-sm text-neg'
                    }
                  >
                    {totalWeight.toFixed(1)}%
                  </span>
                </div>
                <div className="mt-1.5 h-1 bg-edge">
                  <div
                    className={balanced ? 'h-1 bg-pos' : 'h-1 bg-neg'}
                    style={{
                      width: `${Math.min(Math.max(totalWeight, 0), 100)}%`,
                      opacity: totalWeight > 0 ? 1 : 0,
                    }}
                  />
                </div>
                {!balanced && (
                  <p className="mt-1.5 text-xs text-neg">
                    Allocate to 100% ± 1% — {totalWeight.toFixed(1)}% so far.
                  </p>
                )}
              </div>
            </div>

            {formError && <p className="text-xs text-neg">Error: {formError}</p>}

            <div className="flex items-center gap-2">
              <button
                type="submit"
                className="btn btn-primary"
                disabled={!canSave}
              >
                <Plus size={14} strokeWidth={2} />
                {saving ? 'Saving…' : mode === 'edit' ? 'Save changes' : 'Create portfolio'}
              </button>
              <button type="button" className="btn" onClick={cancelForm}>
                Cancel
              </button>
            </div>
          </div>
        </form>
      )}

      {loading && (
        <div className="panel space-y-2 p-4">
          <div className="h-4 w-1/3 bg-base-hover" />
          <div className="h-9 bg-base-hover" />
          <div className="h-9 bg-base-hover" />
        </div>
      )}

      {error && (
        <div className="panel px-4 py-3 text-sm text-neg">
          Error loading portfolios: {error}
        </div>
      )}

      {!loading && !error && portfolios.length === 0 && (
        <div className="panel flex flex-col gap-3 px-6 py-14">
          <span className="flex h-12 w-12 items-center justify-center border border-edge bg-base-elevated text-ink-dim">
            <FolderOpen size={20} strokeWidth={1.6} />
          </span>
          <p className="max-w-prose text-sm text-ink-soft">
            No portfolios yet. Create your first allocation here, then open it
            in the Simulator to chart a Monte Carlo projection.
          </p>
          <div>
            <button type="button" className="btn btn-primary" onClick={startCreate}>
              <Plus size={14} strokeWidth={2} />
              Create your first portfolio
            </button>
          </div>
        </div>
      )}

      {!loading && !error && portfolios.length > 0 && (
        <div className="panel overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full border-collapse">
              <thead className="text-left">
                <tr className="border-b border-edge">
                  <th className="px-4 py-2 text-xs font-semibold uppercase tracking-widest text-ink-faint">
                    Name
                  </th>
                  <th className="px-4 py-2 text-xs font-semibold uppercase tracking-widest text-ink-faint">
                    Holdings
                  </th>
                  <th className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-widest text-ink-faint">
                    Monthly
                  </th>
                  <th className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-widest text-ink-faint">
                    Created
                  </th>
                  <th className="px-4 py-2 text-right text-xs font-semibold uppercase tracking-widest text-ink-faint">
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {portfolios.map((portfolio) => (
                  <tr
                    key={portfolio.id}
                    className="border-b border-edge-subtle transition-colors last:border-0 hover:bg-base-hover"
                  >
                    <td className="px-4 py-2 text-sm font-medium text-ink">
                      {portfolio.name}
                    </td>
                    <td className="px-4 py-2">
                      <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                        {portfolio.holdings.map((holding, index, all) => (
                          <span key={holding.symbol} className="font-mono text-xs text-ink-soft">
                            {holding.symbol} {weightPercent(holding.weight)}%
                            {index < all.length - 1 && (
                              <span className="mx-1 text-ink-dim">·</span>
                            )}
                          </span>
                        ))}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs tabular-nums text-ink-soft">
                      {formatCurrency(portfolio.monthly_contribution)}/mo
                    </td>
                    <td className="px-4 py-2 text-right font-mono text-xs text-ink-faint">
                      {formatDate(portfolio.created_at)}
                    </td>
                    <td className="px-4 py-2">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          className="btn h-8 px-2.5 text-xs"
                          onClick={() => startEdit(portfolio)}
                          aria-label={`Edit ${portfolio.name}`}
                        >
                          <Pencil size={12} strokeWidth={1.8} />
                          <span className="hidden sm:inline">Edit</span>
                        </button>
                        <button
                          type="button"
                          className="btn h-8 px-2.5 text-xs"
                          onClick={() => navigate(`/simulator?portfolio=${portfolio.id}`)}
                          aria-label={`Open ${portfolio.name} in the simulator`}
                        >
                          <ExternalLink size={12} strokeWidth={1.8} />
                          <span className="hidden xl:inline">Simulator</span>
                        </button>
                        <button
                          type="button"
                          className="btn btn-danger-ghost h-8 w-8 items-center justify-center p-0"
                          onClick={() => setDeleting(portfolio)}
                          aria-label={`Delete ${portfolio.name}`}
                        >
                          <Trash size={13} strokeWidth={1.8} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {deleting && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div
            className="absolute inset-0 bg-ink/40"
            onClick={() => setDeleting(null)}
            aria-hidden="true"
          />
          <div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="confirm-delete-title"
            className="panel relative w-full max-w-sm bg-base-panel p-5"
          >
            <h2
              id="confirm-delete-title"
              className="text-base font-semibold text-ink"
            >
              Delete “{deleting.name}”?
            </h2>
            <p className="mt-1 text-sm text-ink-soft">
              Deletes the portfolio and all of its saved simulation runs. This
              cannot be undone.
            </p>
            {deletingError && (
              <p className="mt-2 text-xs text-neg">Error: {deletingError}</p>
            )}
            <div className="mt-4 flex items-center justify-end gap-2">
              <button
                ref={deleteCancelRef}
                type="button"
                className="btn"
                onClick={() => setDeleting(null)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-danger-ghost border border-neg/30 text-neg"
                onClick={confirmDelete}
              >
                <Trash size={13} strokeWidth={1.8} />
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}