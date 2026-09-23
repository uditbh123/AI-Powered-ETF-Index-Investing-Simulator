import { useEffect, useState } from 'react'
import { Newspaper, Clock, TrendingDown, TrendingUp } from 'lucide-react'
import { fetchJSON } from '../api'

const CATEGORIES = [
  { value: 'sector', label: 'Sector' },
  { value: 'geopolitical', label: 'Geopolitical' },
]

const DAY_OPTIONS = [7, 30, 90]

function formatScore(score) {
  if (score === null || score === undefined) return '—'
  return `${score >= 0 ? '+' : ''}${score.toFixed(2)}`
}

function scoreTone(score) {
  if (score === null || score === undefined) return 'text-ink-faint'
  return score >= 0 ? 'text-pos' : 'text-neg'
}

export default function FinancialNews() {
  const [category, setCategory] = useState('sector')
  const [days, setDays] = useState(30)
  const [feed, setFeed] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchJSON(`/news?category=${category}&days=${days}`)
      .then(setFeed)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [category, days])

  function selectCategory(value) {
    setCategory(value)
    setLoading(true)
    setError(null)
  }

  function selectDays(value) {
    setDays(value)
    setLoading(true)
    setError(null)
  }

  const scoreIcon =
    feed && feed.aggregate_score !== null ? (
      feed.aggregate_score >= 0 ? (
        <TrendingUp size={15} strokeWidth={1.8} className="text-pos" />
      ) : (
        <TrendingDown size={15} strokeWidth={1.8} className="text-neg" />
      )
    ) : null

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Financial News
          </h1>
          <p className="mt-1 text-sm text-ink-soft">
            Sector and geopolitical headlines scored by the FinBERT sentiment
            pipeline.
          </p>
        </div>
        {!loading && !error && feed && (
          <span className="chip shrink-0">
            <Clock size={11} strokeWidth={2} className="text-accent" />
            {feed.n_headlines} headlines · {days}d window
          </span>
        )}
      </div>

      <div className="flex items-center justify-between gap-4">
        <div className="flex gap-1 rounded-md border border-white/10 bg-white/[0.03] p-1">
          {CATEGORIES.map((c) => (
            <button
              key={c.value}
              type="button"
              onClick={() => selectCategory(c.value)}
              className={[
                'rounded px-2.5 py-1 text-[11px] font-medium uppercase tracking-[0.06em] transition-colors',
                category === c.value
                  ? 'bg-white text-black'
                  : 'text-ink-soft hover:text-white',
              ].join(' ')}
            >
              {c.label}
            </button>
          ))}
        </div>
        <div className="flex gap-1">
          {DAY_OPTIONS.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => selectDays(option)}
              className={[
                'rounded border border-white/10 px-2 py-1 font-mono text-[11px] transition-colors',
                days === option
                  ? 'border-white/50 bg-white/10 text-white'
                  : 'text-ink-soft hover:text-white',
              ].join(' ')}
            >
              {option}d
            </button>
          ))}
        </div>
      </div>

      {!loading && !error && feed && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
          <div className="panel flex flex-col items-center justify-center gap-2 px-4 py-8 text-center">
            {scoreIcon || (
              <span className="flex h-9 w-9 items-center justify-center rounded-full border border-edge bg-base-elevated text-ink-dim">
                <Newspaper size={16} strokeWidth={1.6} />
              </span>
            )}
            <span className="text-[11px] font-medium uppercase tracking-[0.06em] text-ink-faint">
              Aggregate sentiment
            </span>
            <span
              className={`font-mono text-4xl tabular-nums ${
                feed.aggregate_score === null ? 'text-ink-dim' : scoreTone(feed.aggregate_score)
              }`}
            >
              {formatScore(feed.aggregate_score)}
            </span>
            <span className="text-[11px] leading-snug text-ink-dim">
              Mean of non-null sentiment scores · −1 (bearish) to +1 (bullish)
            </span>
          </div>

          <div className="panel overflow-hidden">
            {feed.headlines.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-3 px-6 py-16 text-center">
                <span className="flex h-12 w-12 items-center justify-center rounded-full border border-edge bg-base-elevated text-ink-dim">
                  <Newspaper size={20} strokeWidth={1.6} />
                </span>
                <p className="text-sm text-ink-soft">
                  No scored headlines in this window yet.
                </p>
              </div>
            ) : (
              <div className="max-h-[calc(100vh-340px)] divide-y divide-edge-subtle overflow-auto">
                {feed.headlines.map((h, index) => (
                  <div
                    key={`${h.published_at}-${index}`}
                    className="flex items-start justify-between gap-4 px-4 py-3"
                  >
                    <span className="min-w-0">
                      <span className="block text-sm leading-snug text-ink">{h.headline}</span>
                      <span className="mt-1 block font-mono text-[11px] text-ink-dim">
                        {h.source || 'Unknown source'} · {h.published_at || 'no date'}
                      </span>
                    </span>
                    <span
                      className={`shrink-0 font-mono text-sm tabular-nums ${scoreTone(h.sentiment_score)}`}
                    >
                      {formatScore(h.sentiment_score)}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {loading && (
        <div className="panel space-y-2 p-4">
          <div className="h-4 w-1/3 animate-pulse rounded bg-base-hover" />
          <div className="h-9 animate-pulse rounded bg-base-hover" />
          <div className="h-9 animate-pulse rounded bg-base-hover" />
        </div>
      )}

      {error && (
        <div className="panel px-4 py-3 text-sm text-neg">Error loading news: {error}</div>
      )}
    </div>
  )
}