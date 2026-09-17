import { NavLink, Route, Routes } from 'react-router-dom'
import DisclaimerBanner from './components/DisclaimerBanner'
import Home from './pages/Home'
import Simulator from './pages/Simulator'
import Tickers from './pages/Tickers'
import './App.css'

function App() {
  return (
    <div className="app">
      <DisclaimerBanner />
      <header className="app-header">
        <span className="app-title">ETF Investing Simulator</span>
        <nav className="app-nav">
          <NavLink to="/">Home</NavLink>
          <NavLink to="/tickers">Tickers</NavLink>
          <NavLink to="/simulator">Simulator</NavLink>
        </nav>
      </header>

      <main className="app-main">
        <Routes>
          <Route path="/" element={<Home />} />
          <Route path="/tickers" element={<Tickers />} />
          <Route path="/simulator" element={<Simulator />} />
          <Route path="*" element={<Home />} />
        </Routes>
      </main>

      <footer className="app-footer">
        Educational simulator for studying long-term ETF and index investing.
      </footer>
    </div>
  )
}

export default App