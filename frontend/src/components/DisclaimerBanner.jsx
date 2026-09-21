import { TriangleAlert } from 'lucide-react'

const DISCLAIMER =
  'Educational simulator only — not financial advice. Simulated results are hypothetical, based on historical data, and do not guarantee future performance.'

const SEGMENTS = [
  DISCLAIMER,
  'Market data may be delayed, incomplete, or inaccurate.',
  'No brokerage or account linking. Portfolios are hypothetical.',
]

function MarqueeTrack() {
  return (
    <span className="flex shrink-0 items-center">
      {SEGMENTS.map((text) => (
        <span key={text} className="flex items-center gap-1.5 px-6">
          <TriangleAlert size={11} strokeWidth={2} className="shrink-0" />
          <span>{text}</span>
        </span>
      ))}
    </span>
  )
}

export default function DisclaimerBanner() {
  return (
    <div
      className="disclaimer relative overflow-hidden border-b border-white/5 bg-black"
      role="note"
    >
      <span className="sr-only">{DISCLAIMER}</span>
      <div
        aria-hidden="true"
        className="disclaimer-track flex w-max items-center py-[3px] text-[11px] leading-none text-[#A3A3A3]"
      >
        <MarqueeTrack />
        <MarqueeTrack />
      </div>
    </div>
  )
}
