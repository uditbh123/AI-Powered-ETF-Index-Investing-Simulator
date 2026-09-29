/**
 * Hardcoded strategy library and the URL contract that carries a strategy's
 * allocation into the Simulator's portfolio form.
 *
 * Both halves live here on purpose: the Strategies page builds the query string
 * and the Simulator parses it, so a format change has exactly one home. This
 * mirrors why `holdingsToFractions` lives in `api.js` rather than being open
 * coded at each call site.
 *
 * URL shape: `/simulator?holdings=VTI:54,VXUS:36,BND:10`
 *   - comma-separated pairs of `SYMBOL:WEIGHT`
 *   - weights are PERCENTS, matching the portfolio form, which edits percents
 *     and only converts to fractions at submit time (`holdingsToFractions`)
 *   - `:` and `,` are legal in a query component, so the raw form is readable
 *     and `URLSearchParams` decodes it unchanged
 *
 * The legacy `?ticker=SPY` form is still parsed, because Etfs.jsx and Home.jsx
 * link to it; it means one symbol at 100%.
 */

/**
 * Each strategy is a plain description of a well-known published allocation.
 *
 * `caveat` is rendered on the card when present. It is not decoration: these
 * portfolios are named after real investors, and where the local dataset cannot
 * express the real recommendation the card has to say so rather than quietly
 * simulate something else.
 */
export const STRATEGIES = [
  {
    id: 'boglehead-three-fund',
    name: 'Boglehead Three-Fund',
    tagline: 'Global equity, tilted to the home market.',
    rationale:
      'The canonical "three-fund" portfolio: 54% US total market, 36% ' +
      'international, 10% US bonds. Low-cost, globally diversified, and ' +
      'simple enough to rebalance once a year.',
    holdings: [
      { symbol: 'VTI', weight: 54 },
      { symbol: 'VXUS', weight: 36 },
      { symbol: 'BND', weight: 10 },
    ],
  },
  {
    id: 'all-weather',
    name: 'Ray Dalio All-Weather',
    tagline: 'Balanced across four economic environments.',
    rationale:
      'A risk-parity shape rather than a growth one: equal-ish weight to ' +
      'equities, long bonds, intermediate bonds and gold, so no single ' +
      'macro environment dominates the outcome.',
    caveat:
      'The intermediate-bond sleeve is proxied by BND. The dataset has no ' +
      'dedicated intermediate or short-duration Treasury ETF (IEF, TIP), so ' +
      'this is an approximation of the published 30/30/20/20 split rather ' +
      'than a faithful one.',
    holdings: [
      { symbol: 'VTI', weight: 30 },
      { symbol: 'TLT', weight: 30 },
      { symbol: 'BND', weight: 20 },
      { symbol: 'GLD', weight: 20 },
    ],
  },
  {
    id: 'buffett-90-10',
    name: 'Warren Buffett 90/10',
    tagline: 'S&P 500, with a small defensive sleeve.',
    rationale:
      "Buffett's 2013 shareholder letter: 90% in a low-cost S&P 500 index " +
      'fund, 10% in short-term government bonds. Deliberately simple, and ' +
      'concentrated in one equity market rather than the whole world.',
    caveat:
      'The 10% defensive sleeve is proxied by BND, not a short-term Treasury ' +
      'fund. The dataset has no SGOV or BIL, and BND carries roughly 6 years ' +
      'of duration against near zero, so the sleeve lost 13.3% in 2022 - the ' +
      'rate-rise year it was meant to protect against. Treat this card as ' +
      'more volatile than the letter describes.',
    holdings: [
      { symbol: 'VOO', weight: 90 },
      { symbol: 'BND', weight: 10 },
    ],
  },
]

/** Serialize holdings into the `holdings` query value. */
function holdingsToQuery(holdings) {
  return holdings.map((h) => `${h.symbol}:${h.weight}`).join(',')
}

/** Link to the Simulator with a strategy's allocation pre-filled. */
export function strategyHref(strategy) {
  return `/simulator?holdings=${holdingsToQuery(strategy.holdings)}`
}

/**
 * Parse a Simulator query string into form holdings, or null when it carries
 * no pre-fill.
 *
 * Malformed pairs are skipped rather than throwing: a hand-edited or truncated
 * URL should degrade to a partially-filled form, not a blank page. The whole
 * `holdings` value is rejected if nothing in it parses, so a bad strategy link
 * cannot silently wipe the form's defaults.
 */
export function queryToHoldings(search) {
  const params = new URLSearchParams(search)

  const raw = params.get('holdings')
  if (raw) {
    const rows = []
    for (const pair of raw.split(',')) {
      const [symbol, weight] = pair.split(':')
      const parsed = Number(weight)
      if (!symbol || !Number.isFinite(parsed) || parsed < 0) continue
      rows.push({ symbol: symbol.trim().toUpperCase(), weight: parsed })
    }
    if (rows.length) return rows
  }

  const single = params.get('ticker')
  if (single && single.trim()) {
    return [{ symbol: single.trim().toUpperCase(), weight: 100 }]
  }

  return null
}
