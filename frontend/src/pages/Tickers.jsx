import { useEffect, useState } from 'react'
import { fetchJSON } from '../api'
import './Tickers.css'

export default function Tickers() {
  const [tickers, setTickers] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    fetchJSON('/tickers')
      .then(setTickers)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <section>
      <h1>Available Tickers</h1>
      {loading && <p>Loading tickers&hellip;</p>}
      {error && <p className="form-error">Error: {error}</p>}
      {!loading && !error && (
        <table className="ticker-table">
          <thead>
            <tr>
              <th>Symbol</th>
              <th>Name</th>
              <th>Sector</th>
              <th className="num">Price Points</th>
              <th>Date Range</th>
            </tr>
          </thead>
          <tbody>
            {tickers.map((t) => (
              <tr key={t.symbol}>
                <td className="mono">{t.symbol}</td>
                <td>{t.name}</td>
                <td>{t.sector}</td>
                <td className="num">{t.price_rows.toLocaleString()}</td>
                <td>{t.first_date ? `${t.first_date} – ${t.last_date}` : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}