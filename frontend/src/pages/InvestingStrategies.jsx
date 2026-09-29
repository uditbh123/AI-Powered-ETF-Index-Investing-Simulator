import { Play } from 'lucide-react'
import { Link } from 'react-router-dom'
import { STRATEGIES, strategyHref } from '../strategyHoldings'
import { usePageTitle } from '../hooks/usePageTitle'

export default function InvestingStrategies() {
  usePageTitle('Investing Strategies — ETF Simulator')

    return (
      <div className="space-y-4">
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {STRATEGIES.map((strategy) => {
          const total = strategy.holdings.reduce((sum, h) => sum + h.weight, 0)
          return (
            <div key={strategy.id} className="panel flex flex-col">
              <div className="panel-title">
                <span>{strategy.name}</span>
                <span className="num text-ink-faint">{total}%</span>
              </div>

              <div className="flex flex-1 flex-col gap-3 p-4">
                <p className="text-xs uppercase tracking-widest text-ink-faint">
                  {strategy.tagline}
                </p>
                <p className="text-sm leading-snug text-ink-soft">
                  {strategy.rationale}
                </p>

                <dl className="mt-1 border-t border-edge-subtle pt-2">
                  {strategy.holdings.map((holding) => (
                    <div
                      key={holding.symbol}
                      className="flex items-baseline justify-between gap-3 py-0.5"
                    >
                      <dt className="font-mono text-sm text-ink">
                        {holding.symbol}
                      </dt>
                      <dd className="num text-sm text-ink-soft">
                        {holding.weight}%
                      </dd>
                    </div>
                  ))}
                </dl>

                {/* Stated wherever the dataset cannot express the real
                    recommendation, so a card never quietly simulates a
                    different portfolio than the one it is named after. */}
                {strategy.caveat && (
                  <p className="mt-auto border-t border-edge-subtle pt-2 text-xs leading-snug text-ink-dim">
                    {strategy.caveat}
                  </p>
                )}
              </div>

              <div className="border-t border-edge-subtle p-3">
                <Link
                  to={strategyHref(strategy)}
                  className="btn btn-primary w-full"
                  aria-label={`Simulate ${strategy.name}`}
                >
                  <Play size={13} strokeWidth={2} fill="currentColor" />
                  Simulate Strategy
                </Link>
              </div>
            </div>
          )
        })}
      </div>

      <p className="max-w-prose text-xs text-ink-dim">
        Simulations bootstrap from this app&apos;s own stored price history, so
        results depend on the period covered by the local dataset. Each
        portfolio is simulated on the intersection of its holdings&apos; history
        — for VXUS and VOO that starts in 2011 and 2010 respectively, which is
        still ample for a 10-year horizon but is a shorter sample than SPY or
        VTI would give.
      </p>
    </div>
  )
}
