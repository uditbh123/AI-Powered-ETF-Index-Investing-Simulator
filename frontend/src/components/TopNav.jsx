import { ChartCandlestick } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const NAV_LINKS = [
  { to: '/', label: 'Home', end: true },
  { to: '/etfs', label: 'ETFs' },
  { to: '/news', label: 'News' },
  { to: '/simulator', label: 'Simulator' },
  { to: '/strategies', label: 'Strategies' },
]

function linkClass(isActive) {
  return [
    'flex h-full shrink-0 items-center border-b-2 px-3 text-sm font-medium transition-colors',
    isActive
      ? 'border-accent text-accent'
      : 'border-transparent text-ink-soft hover:text-white',
  ].join(' ')
}

export default function TopNav() {
  return (
    <nav className="shrink-0 border-b border-edge bg-base" aria-label="Primary">
      <div className="flex h-14 min-w-0 items-center gap-4 px-4">
        <NavLink
          to="/"
          end
          className="flex shrink-0 items-center gap-2.5"
          aria-label="ETF Simulator home"
        >
          <span className="flex h-7 w-7 items-center justify-center border border-accent/40 bg-accent/10 text-accent">
            <ChartCandlestick size={15} strokeWidth={2} />
          </span>
          <span className="flex flex-col">
            <span className="text-sm font-semibold tracking-wide text-white">
              ETF Simulator
            </span>
            <span className="mt-0.5 hidden text-xs text-ink-faint sm:block">
              AI-Powered ETF &amp; Index Investing Simulator
            </span>
          </span>
        </NavLink>

        <div className="flex h-full min-w-0 flex-1 items-center overflow-x-auto">
          {NAV_LINKS.map(({ to, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) => linkClass(isActive)}
            >
              {label}
            </NavLink>
          ))}
        </div>
      </div>
    </nav>
  )
}