import { ChartColumn } from 'lucide-react'
import { Link } from 'react-router-dom'
import { usePageTitle } from '../hooks/usePageTitle'

export default function NotFound() {
  usePageTitle('Page not found — ETF Simulator')

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold tracking-tight text-ink">
        Page not found
      </h1>
      <div className="panel flex flex-col items-start gap-3 px-6 py-14">
        <span className="flex h-12 w-12 items-center justify-center border border-edge bg-base-elevated text-ink-dim">
          <ChartColumn size={20} strokeWidth={1.6} />
        </span>
        <p className="max-w-prose text-sm text-ink-soft">
          That page does not exist on this terminal.
        </p>
        <Link to="/" className="btn">
          Back to the dashboard
        </Link>
      </div>
    </div>
  )
}