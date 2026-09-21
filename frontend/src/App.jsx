import { Navigate, Route, Routes, useLocation } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import DisclaimerBanner from './components/DisclaimerBanner'
import AmbientDataGrid from './components/AmbientDataGrid'
import Home from './pages/Home'
import Simulator from './pages/Simulator'
import Etfs from './pages/Etfs'
import FinancialNews from './pages/FinancialNews'
import InvestingStrategies from './pages/InvestingStrategies'

function App() {
  const { pathname } = useLocation()
  const isDashboard = pathname === '/'

  return (
    <div className="relative flex h-screen overflow-hidden">
      <AmbientDataGrid />
      <Sidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="shrink-0 bg-black">
          <DisclaimerBanner />
        </header>

        <main
          className={isDashboard ? 'flex-1 overflow-hidden' : 'flex-1 overflow-y-auto'}
        >
          <div className={isDashboard ? 'h-full' : 'mx-auto max-w-7xl px-6 py-5'}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/etfs" element={<Etfs />} />
              <Route path="/simulator" element={<Simulator />} />
              <Route path="/news" element={<FinancialNews />} />
              <Route path="/strategies" element={<InvestingStrategies />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  )
}

export default App