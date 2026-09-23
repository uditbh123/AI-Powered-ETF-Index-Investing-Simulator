import {
  ChartColumn,
  ChartLine,
  ChartCandlestick,
  Lightbulb,
  Newspaper,
  Settings,
} from 'lucide-react'
import { NavLink } from 'react-router-dom'

const NAV_ITEMS = [
  { to: '/', label: 'Home', icon: ChartColumn, end: true },
  { to: '/etfs', label: 'ETFs', icon: ChartCandlestick },
  { to: '/simulator', label: 'Simulator', icon: ChartLine },
  { to: '/news', label: 'Financial News', icon: Newspaper },
  { to: '/strategies', label: 'Investing Strategies', icon: Lightbulb },
]

function linkClass(isActive) {
  return [
    'group flex items-center gap-2.5 border-l-2 py-2 pl-2.5 pr-3 text-sm font-medium transition-colors',
    isActive
      ? 'border-white text-white'
      : 'border-transparent text-ink-soft hover:border-white/20 hover:text-white',
  ].join(' ')
}

export default function Sidebar() {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-edge bg-base">
      <div className="flex h-14 items-center gap-2.5 px-4 pb-3">
        <span className="flex h-8 w-8 items-center justify-center border border-white/20 text-white">
          <ChartCandlestick size={16} strokeWidth={2} />
        </span>
        <span>
          <span className="block text-sm font-semibold tracking-wide text-white">
            ETF Terminal
          </span>
          <span className="block text-xs uppercase tracking-widest text-ink-faint">
            Investing Simulator
          </span>
        </span>
      </div>

      <nav className="flex-1 space-y-1 p-3" aria-label="Primary">
        {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
          <NavLink key={to} to={to} end={end} className={({ isActive }) => linkClass(isActive)}>
            <Icon size={15} strokeWidth={1.8} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="flex items-center gap-2 px-4 py-3 text-xs text-ink-dim">
        <Settings size={12} strokeWidth={1.8} />
        <span>Phase 4.7 · dashboard</span>
      </div>
    </aside>
  )
}