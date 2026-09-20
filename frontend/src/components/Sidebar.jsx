import {
  ChartColumn,
  ChartLine,
  ChartCandlestick,
  Settings,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/', label: 'Home', icon: ChartColumn, end: true },
  { to: '/tickers', label: 'Tickers', icon: ChartCandlestick },
  { to: '/simulator', label: 'Simulator', icon: ChartLine },
]

function linkClass(isActive) {
  return [
    'group flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors',
    isActive
      ? 'bg-accent-dim/15 text-accent'
      : 'text-ink-soft hover:bg-base-hover hover:text-ink',
  ].join(' ')
}

export default function Sidebar() {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-edge bg-base-panel">
      <div className="flex h-14 items-center gap-2.5 border-b border-edge-subtle px-4">
        <span className="flex h-8 w-8 items-center justify-center rounded-md border border-accent-dim/40 bg-accent-dim/15 text-accent shadow-accent-glow">
          <ChartCandlestick size={16} strokeWidth={2} />
        </span>
        <span className="leading-tight">
          <span className="block text-sm font-semibold tracking-wide text-ink">
            ETF Terminal
          </span>
          <span className="block text-[10px] uppercase tracking-[0.14em] text-ink-faint">
            Investing Simulator
          </span>
        </span>
      </div>

      <nav className="flex-1 space-y-0.5 p-3" aria-label="Primary">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => linkClass(isActive)}>
            <Icon size={15} strokeWidth={1.8} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="flex items-center gap-2 border-t border-edge-subtle px-4 py-3 text-[10px] text-ink-dim">
        <Settings size={12} strokeWidth={1.8} />
        <span>Phase 4.5 · UI overhaul</span>
      </div>
    </aside>
  )
}