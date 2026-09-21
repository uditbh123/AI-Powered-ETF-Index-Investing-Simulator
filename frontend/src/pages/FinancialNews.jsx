import { Newspaper } from 'lucide-react'

export default function FinancialNews() {
  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-ink">
          Financial News
        </h1>
        <p className="mt-1 text-sm text-ink-soft">
          Sector and geopolitical headlines scored by the FinBERT sentiment
          pipeline.
        </p>
      </div>

      <div className="panel flex flex-col items-center justify-center gap-3 bg-base-panel px-6 py-20 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-full border border-edge bg-base-elevated text-ink-dim">
          <Newspaper size={20} strokeWidth={1.6} />
        </span>
        <p className="text-sm text-ink-soft">
          News sentiment feed coming in a later phase.
        </p>
      </div>
    </div>
  )
}
