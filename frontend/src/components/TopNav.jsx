import { ChartCandlestick } from 'lucide-react'
import { NavLink } from 'react-router-dom'

const NAV_LINKS = [
  { to: '/', label: 'Home', end: true },
  { to: '/etfs', label: 'ETFs' },
  { to: '/news', label: 'News' },
  { to: '/portfolios', label: 'Portfolios' },
  { to: '/simulator', label: 'Simulator' },
  { to: '/strategies', label: 'Strategies' },
]

function linkClass(isActive) {
  return [
    'flex h-full shrink-0 items-center border-b-2 px-3 text-sm transition-colors',
    isActive
      ? 'border-ink font-semibold text-ink'
      : 'border-transparent text-ink-faint hover:text-ink',
  ].join(' ')
}

export default function TopNav() {
  return (
    <nav className="shrink-0 border-b border-edge bg-base" aria-label="Primary">
      {/* Three tracks: 1fr / minmax(0,auto) / 1fr. The two flexible tracks
          share the leftover width equally, so the middle auto track holding
          the links sits at the exact centre of the full header width -- the
          brand owns the left track (pinned left) and never participates in
          the centering math. An [auto 1fr] or flex-1 row would center the
          links only within the space LEFT OVER after the brand. minmax(0,auto)
          lets the track shrink below its content so the link row scrolls
          horizontally instead of blowing the header out at narrow widths. */}
      <div className="grid h-14 grid-cols-[1fr_minmax(0,auto)_1fr] items-center gap-4 px-4">
        <div className="flex min-w-0">
          <NavLink
            to="/"
            end
            className="flex shrink-0 items-center gap-2.5"
            aria-label="ETF Simulator home"
          >
            <span className="flex h-7 w-7 items-center justify-center border border-ink bg-ink text-white">
              <ChartCandlestick size={15} strokeWidth={2} />
            </span>
            <span className="flex flex-col">
              <span className="text-sm font-semibold tracking-wide text-ink">
                ETF Simulator
              </span>
              <span className="mt-0.5 hidden text-xs text-ink-faint sm:block">
                AI-Powered ETF &amp; Index Investing Simulator
              </span>
            </span>
          </NavLink>
        </div>

        <div className="flex h-full min-w-0 items-center justify-center overflow-x-auto">
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

        {/* Right 1fr track, intentionally empty: it balances the left track so
            the link column is centered rather than shoved right by the gap. */}
        <div className="min-w-0" />
      </div>
    </nav>
  )
}