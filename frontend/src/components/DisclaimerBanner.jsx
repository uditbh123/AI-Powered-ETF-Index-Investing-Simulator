import { TriangleAlert } from 'lucide-react'

const SEGMENTS = [
  'Educational simulator only — not financial advice. Simulated results are hypothetical, based on historical data, and do not guarantee future performance.',
  'Market data may be delayed, incomplete, or inaccurate.',
  'No brokerage or account linking. Portfolios are hypothetical.',
]

export default function DisclaimerBanner() {
  return (
    <div
      className="flex items-start gap-2 border-b border-edge-subtle bg-base px-4 py-2"
      role="note"
    >
      <TriangleAlert size={13} strokeWidth={2} className="mt-0.5 shrink-0 text-warn" />
      <p className="text-xs leading-snug text-ink-soft">{SEGMENTS.join('  ·  ')}</p>
    </div>
  )
}