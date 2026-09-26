// Build-time override: the dev Vite proxy serves the API under /api; the
// container build sets VITE_API_BASE_URL=/ so the SPA and API share an origin
// (trailing slashes are trimmed so '/' + '/tickers' never double-slashes).
const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? '/api').replace(/\/+$/, '')

export async function fetchJSON(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    const detail = Array.isArray(body?.detail)
      ? body.detail.map((d) => d.msg).join(', ')
      : body?.detail
    throw new Error(detail || `${response.status} ${response.statusText}`)
  }
  if (response.status === 204) return null
  const body = await response.json().catch(() => null)
  // A 200 that is not JSON usually means an SPA-fallback page leaked through a
  // misconfigured base URL; return it as an error, never null (null can crash
  // callers who expect an array/object from an OK response).
  if (body === null) {
    throw new SyntaxError(
      `${response.url} returned non-JSON (${response.status} ${response.statusText})`,
    )
  }
  return body
}

export const API_BASE_URL = API_BASE

// --- Holding-weight convention ---------------------------------------------
// The API stores holding weights as FRACTIONS in (0, 1] summing to 1.0
// (0.6 = 60%). The holdings builders deliberately show and accept PERCENTS
// because that is how allocation is read aloud, so every percent -> fraction
// conversion goes through this one function. Adding a second inline `/ 100`
// anywhere else is the bug this comment exists to prevent: it would submit a
// 100x-too-large allocation that the API rejects with a 422 the user cannot
// act on, or (if it slipped past) that the engine silently renormalizes into a
// uniform 1/N portfolio.
export function holdingsToFractions(rows) {
  return rows.map((row) => ({
    symbol: row.symbol,
    weight: (Number(row.weight) || 0) / 100,
  }))
}

// Inverse of the above, for putting a stored fraction back into a percent
// input. Display direction only -- it never leaves the browser.
export function fractionToPercentInput(weight) {
  return String(Math.round(Number(weight) * 100))
}