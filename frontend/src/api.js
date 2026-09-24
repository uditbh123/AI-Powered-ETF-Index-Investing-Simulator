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