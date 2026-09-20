import { TriangleAlert } from 'lucide-react'

export default function DisclaimerBanner() {
  return (
    <div
      className="flex items-center gap-2 bg-warn-dim/10 px-4 py-1.5 text-[11px] text-warn"
      role="note"
    >
      <TriangleAlert size={12} strokeWidth={2} className="shrink-0" />
      <span>
        <strong className="font-semibold">Educational simulator only.</strong>
        <span className="text-warn/80">
          {' '}
          Not financial advice. Simulated results are hypothetical and do not
          guarantee future performance.
        </span>
      </span>
    </div>
  )
}