import { Route, Routes } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import DisclaimerBanner from './components/DisclaimerBanner'
import AmbientDataGrid from './components/AmbientDataGrid'
import Home from './pages/Home'
import Simulator from './pages/Simulator'
import Tickers from './pages/Tickers'

function App() {
  return (
    <div className="relative flex h-screen overflow-hidden">
      <AmbientDataGrid />
      <Sidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="shrink-0 border-b border-white/10 bg-black">
          <DisclaimerBanner />
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-7xl px-6 py-5">
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/tickers" element={<Tickers />} />
              <Route path="/simulator" element={<Simulator />} />
              <Route path="*" element={<Home />} />
            </Routes>
          </div>
        </main>
      </div>
    </div>
  )
}

export default App