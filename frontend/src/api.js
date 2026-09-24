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
  return response.json()
}

export const API_BASE_URL = API_BASE