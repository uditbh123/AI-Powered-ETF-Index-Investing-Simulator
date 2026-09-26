import { useEffect, useState } from 'react'
import { Newspaper, Clock, TrendingDown, TrendingUp } from 'lucide-react'
import { fetchJSON } from '../api'
import { usePageTitle } from '../hooks/usePageTitle'

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
  usePageTitle('Financial News — ETF Simulator')

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

  const otherCategory = category === 'sector' ? 'geopolitical' : 'sector'

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">
            Financial News
          </h1>
          <p className="mt-1 max-w-prose text-sm text-ink-soft">
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

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 border border-edge-subtle bg-base-hover p-1">
          {CATEGORIES.map((c) => (
            <button
              key={c.value}
              type="button"
              onClick={() => selectCategory(c.value)}
              className={[
                'px-2.5 py-1 text-xs font-medium uppercase tracking-widest transition-colors',
                category === c.value
                  ? 'bg-ink text-white'
                  : 'text-ink-soft hover:text-ink',
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
                'border border-edge px-2 py-1 font-mono text-xs transition-colors',
                days === option
                  ? 'border-accent bg-accent/10 text-accent'
                  : 'text-ink-soft hover:text-ink',
              ].join(' ')}
            >
              {option}d
            </button>
          ))}
        </div>
      </div>

      {!loading && !error && feed && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
          <div className="panel p-4">
            {scoreIcon || (
              <span className="mb-3 flex h-9 w-9 items-center justify-center border border-edge bg-base-elevated text-ink-dim">
                <Newspaper size={16} strokeWidth={1.6} />
              </span>
            )}
            <span className="block text-xs font-medium uppercase tracking-widest text-ink-faint">
              Aggregate sentiment
            </span>
            <span
              className={`mt-1 num block text-2xl ${
                feed.aggregate_score === null
                  ? 'text-ink-dim'
                  : scoreTone(feed.aggregate_score)
              }`}
            >
              {formatScore(feed.aggregate_score)}
            </span>
            <span className="mt-2 block text-xs leading-snug text-ink-dim">
              Mean of non-null sentiment scores · −1 (bearish) to +1 (bullish)
            </span>
          </div>

          <div className="panel">
            {feed.headlines.length === 0 ? (
              <div className="p-4">
                <p className="text-sm text-ink-soft">
                  No scored headlines in the last {days} days for{' '}
                  {category} news.
                </p>
                <p className="mt-2 text-xs text-ink-faint">
                  Widen the time window or switch category:
                </p>
                <div className="mt-3 flex flex-wrap gap-2">
                  <button
                    type="button"
                    className="btn"
                    onClick={() => selectDays(90)}
                  >
                    Widen to 90 days
                  </button>
                  <button
                    type="button"
                    className="btn"
                    onClick={() => selectCategory(otherCategory)}
                  >
                    Switch to {otherCategory} news
                  </button>
                </div>
              </div>
            ) : (
              <div className="max-h-[calc(100vh-340px)] space-y-3 p-4">
                {feed.headlines.map((h, index) => (
                  <div
                    key={`${h.published_at}-${index}`}
                    className="flex items-start justify-between gap-4"
                  >
                    <span className="max-w-prose min-w-0">
                      <span className="block text-sm leading-snug text-ink">
                        {h.headline}
                      </span>
                      <span className="mt-0.5 block font-mono text-xs text-ink-dim">
                        {h.source || 'Unknown source'} ·{' '}
                        {h.published_at || 'no date'}
                      </span>
                    </span>
                    <span
                      className={`shrink-0 num text-sm ${scoreTone(h.sentiment_score)}`}
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
          <div className="h-4 w-1/3 bg-base-hover" />
          <div className="h-9 bg-base-hover" />
          <div className="h-9 bg-base-hover" />
        </div>
      )}

      {error && (
        <div className="panel px-4 py-3 text-sm text-neg">
          Error loading news: {error}
        </div>
      )}
    </div>
  )
}