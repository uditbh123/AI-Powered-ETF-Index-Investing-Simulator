import { Lightbulb } from 'lucide-react'
import { usePageTitle } from '../hooks/usePageTitle'

export default function InvestingStrategies() {
  usePageTitle('Investing Strategies — ETF Simulator')

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Investing Strategies
        </h1>
        <p className="mt-1 max-w-prose text-sm text-ink-soft">
          Curated long-term ETF and index allocation strategies to simulate.
        </p>
      </div>

      <div className="panel flex flex-col gap-3 px-6 py-14">
        <span className="flex h-12 w-12 items-center justify-center border border-edge bg-base-elevated text-ink-dim">
          <Lightbulb size={20} strokeWidth={1.6} />
        </span>
        <p className="max-w-prose text-sm text-ink-soft">
          Strategy library coming soon.
        </p>
      </div>
    </div>
  )
}