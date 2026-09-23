import { lazy, Suspense } from 'react'
import { Route, Routes, useLocation } from 'react-router-dom'
import TopNav from './components/TopNav'
import DisclaimerBanner from './components/DisclaimerBanner'
import AmbientDataGrid from './components/AmbientDataGrid'

const Home = lazy(() => import('./pages/Home'))
const Etfs = lazy(() => import('./pages/Etfs'))
const FinancialNews = lazy(() => import('./pages/FinancialNews'))
const Simulator = lazy(() => import('./pages/Simulator'))
const InvestingStrategies = lazy(() => import('./pages/InvestingStrategies'))
const NotFound = lazy(() => import('./pages/NotFound'))

function PageLoader() {
  return (
    <div className="panel px-4 py-14">
      <p className="text-sm text-ink-soft">Loading…</p>
    </div>
  )
}

function App() {
  const { pathname } = useLocation()
  const isDashboard = pathname === '/'

  return (
    <div className="relative flex h-screen flex-col overflow-hidden">
      <AmbientDataGrid />
      <TopNav />

      <header className="shrink-0 bg-base">
        <DisclaimerBanner />
      </header>

      <main
        className={
          isDashboard ? 'min-h-0 flex-1 overflow-hidden' : 'min-h-0 flex-1 overflow-y-auto'
        }
      >
        <div className={isDashboard ? 'h-full' : 'mx-auto max-w-7xl px-6 py-5'}>
          <Suspense fallback={<PageLoader />}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/etfs" element={<Etfs />} />
              <Route path="/simulator" element={<Simulator />} />
              <Route path="/news" element={<FinancialNews />} />
              <Route path="/strategies" element={<InvestingStrategies />} />
              <Route path="*" element={<NotFound />} />
            </Routes>
          </Suspense>
        </div>
      </main>
    </div>
  )
}

export default App