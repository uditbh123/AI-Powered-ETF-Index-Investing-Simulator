# Data Methodology

How the simulator builds its inputs and why. Each section is written against
the actual implementation in `backend/` (files cited inline), so the text
matches what the code does, not what it aims to do.

## Price data

_Per the project's ingest implementation (`app/services/market_data.py`,
`app/scripts/ingest.py`, `app/dao/prices.py`)._

- **Source.** Daily OHLCV bars for the fixed catalog in
  `app/data/ticker_catalog.py` (13 ETFs/indices, e.g. SPY, QQQ, `^GSPC`) are
  pulled from Yahoo Finance through `yfinance` (`yf.download(..., interval="1d",
  auto_adjust=True, progress=False, threads=False)`).
- **Adjusted-close basis.** `auto_adjust=True` asks Yahoo for adjusted series,
  which internally re-scale the full history at each dividend and split so that
  percentage moves between bars are clean, dividend-adjusted changes. Only the
  **Close** (adjusted) and **Volume** columns are persisted into the
  `prices(ticker_id, date, close, volume)` table.
- **Full-history refresh.** With no start/end bound the downloader passes
  `period="max"` (Yahoo defaults to ~1 month when both `period` and `start` are
  omitted). When an `end` bound is given but no `start`, `period` is never
  passed — Yahoo gives `period` precedence and would silently drop `end` — so a
  sentinel `start="1900-01-01"` is used instead. Rows with a non-finite close
  are dropped; a missing volume is stored as `NULL`.
- **Rewriting on every refresh.** Upserts (`INSERT ... ON CONFLICT(ticker_id,
  date) DO UPDATE`) overwrite existing rows, not just add new dates. This is
  deliberate: because `auto_adjust=True` re-scales the entire series whenever
  Yahoo re-bases it, a refresh that merely appended new dates would leave older
  rows on the previous basis and fabricate phantom jumps at the boundary. The
  scheduled daily refresh (`app/scheduler.py`) therefore always pulls **full**
  history (never a `start` window) so the whole stored series is rewritten on
  the current basis. The count returned is of genuinely *new* dates; rewritten
  rows are not counted.
- **Idempotence.** Re-running a pull never duplicates rows thanks to the
  `UNIQUE(ticker_id, date)` constraint.

## Screener metrics

_Source: `compute_screener_stats` in `app/services/screener.py`, exposed as
`GET /screener` (`app/routers/screener.py`)._

Per tracked ticker with at least one stored price row, computed from the local
`prices` table with pandas (no network):

| Metric | Definition |
|--------|-----------|
| Latest / Prev close | Last two stored daily closes. |
| 1D change | `(latest / prev − 1) · 100`, `null` without two closes. |
| 1Y return | Close 252 trading days ago vs latest: `(latest / base − 1) · 100`; `null` with fewer than 253 rows. |
| Annualized volatility | Std. dev. (`ddof=1`) of daily log returns over the last 252 closes, × `√252` × 100; `null` with fewer than 30 points in the window. |
| Max drawdown (1Y) | Largest peak-to-trough decline over the last year (negative %; 0 when the series never declined). |

### KNOWN LIMITATION — adjustment basis

All metrics derive from the stored `Close` column, which Yahoo serves on the
adjustment basis of the most recent download (see Price data above). The exact
basis used for each series is **under review**. Because the close is a pure
price, income metrics such as the 1-year return exclude dividend
reinvestment and may **understate a dividend payer's true (total-return)
performance** until the basis issue is resolved.

## Monthly return construction

_Source: `portfolio_monthly_returns` in `app/services/simulation.py`._

1. Every holding's daily closes are read from `prices` and resampled to
   month-end with `.resample("ME").last()` — the last available close in each
   calendar month, forward-filled (`.ffill()`) from the previous month when a
   month has no bar.
2. The per-holding month-end series are aligned into one frame; months where
   **any** holding lacks data (the ragged early period before a fund's IPO) are
   dropped (`dropna(how="any")`).
3. Each holding's simple monthly return is `pct_change()` on that frame.
4. The portfolio's monthly return is the **linear combination**
   `(returns * weights).sum(axis=1)` where `weights` are the user's holding
   weights normalized to sum to 1.

The engine then needs at least two overlapping monthly returns to run.

## Rebalancing assumption

Because the portfolio return in every month is the same fixed linear combination
of holding returns (monthly linear combination `Σ wᵢ·rᵢₜ`), the model implicitly
assumes the portfolio is **rebalanced back to the target weights at the start of
every month**. Drift between months is not tracked: a holding that grew faster
than the portfolio is not assumed to have a larger weight the next month. This
is the standard constant-weight / monthly-rebalanced approximation and keeps the
return series stationary and simple to bootstrap. Nothing else rebalances —
there is no intra-month trading or cash-flow reallocation logic.

## Bootstrap design

_Source: `_draw_returns` / `simulate_paths` in `app/simulation/monte_carlo.py`._

The simulator resamples the historical monthly return series, never assuming a
parametric law of motion.

- **IID bootstrap (default, `blocks=None`).** Each of the `n_simulations`
  synthetic timelines draws `horizon_months` returns independently with
  replacement from the historical series (`rng.choice(... , replace=True)`).
- **Block bootstrap (`blocks=n`).** To preserve short-run autocorrelation, the
  horizon is split into `ceil(horizon / n)` contiguous blocks; each block starts
  at a uniformly random historical index and reads `n` consecutive returns,
  wrapping around the end of the series (`np.take(idx % n_history)`) — typical
  for horizons longer than the available history.
- **Compounding.** Along each path the engine compounds with
  `growth = cumprod(1 + r)`. Contributions are deposited at the **start** of
  each month and earn that month's return (annuity-due timing; verified by the
  closed-form test `test_constant_return_matches_closed_form`).
- **Volatility scaling.** When sentiment requests a multiplier `m`, the return
  series is pre-scaled about its mean — `r' = μ + m·(r − μ)` — which scales the
  sample std. dev. by exactly `m` while preserving the drift, before resampling
  (`scale_returns_volatility`); scaled draws are floored at −0.99.

## Percentile method

_Source: `path_percentiles` in `app/simulation/monte_carlo.py`._

At each time step the engine takes `np.percentile(paths, levels, axis=0)`
across all simulated paths, with NumPy's default **linear interpolation**
between ranked paths. Levels are hard-coded at **10 / 50 / 90** (the 10th
"worst case", 50th median, 90th "best case") matching the fan chart and the
`DEFAULT_PERCENTILES` constant. The reported summary values
(`worst/median/best_case_final_value`) are the finals of those same three bands.

## Sentiment band rationale

_Source: constants + `volatility_multiplier_from_sentiment` in
`app/simulation/monte_carlo.py`, evidence in `docs/sentiment_validation.md`._

FinBERT scores are collapsed from per-headline probabilities into a portfolio
score in [−1, 1] (`portfolio_sentiment_score` in `app/services/sentiment_signal.py`)
and mapped to a volatility multiplier applied to the bootstrap dispersion:

| Score       | Multiplier |
|-------------|-----------:|
| −1.0        | 1.10x (wider fan) |
| 0.0         | 1.00x (no adjustment) |
| +1.0        | 0.95x (narrower fan) |

The band is deliberately **narrow** because the project's own validation
(`docs/sentiment_validation.md`, ~33–50 matched days per series) found the
sentiment-to-realized-volatility correlation to be weak — none of the forward
signals survived the 0.05 bar — so the model only moves lightly on sentiment
rather than pretending it is a strong variance predictor. Two design choices
remain:

- **Asymmetry.** Negative news widens more than positive news narrows
  (sensitivities 0.10 vs 0.05). This follows the leverage effect (Black 1976):
  bad news / uncertainty moves markets harder than good news calms them.
- **Safety clip.** Multipliers are clamped to [0.9, 1.1] and scores clamped to
  [−1, 1] before mapping, so one noisy headline batch can never produce a
  degenerate (near-zero variance) or explosive distribution. Non-finite inputs
  and the no-news case map to 1.0 (no adjustment).

Because the multiplier is part of the simulation cache key, a fresh news batch
that changes the score produces a new run instead of a stale cached fan chart.

## Crisis replay

_Source: `app/services/crisis.py`, `POST /portfolios/{id}/crisis-replay`
(`app/routers/crisis.py`)._

A "crisis replay" re-runs a portfolio through one of three fixed historical
windows, month-end inclusive:

| Name | Window |
|------|--------|
| `dot_com_2000` | 2000-03 → 2002-09 (31 months) |
| `gfc_2008` | 2007-10 → 2009-03 (18 months) |
| `covid_2020` | 2020-02 → 2020-04 (3 months) |

- **Real trajectory.** The portfolio's own realized monthly returns (from
  `portfolio_monthly_returns_with_dates`, the same construction as any
  simulation) are sliced to the window and compounded with contributions at the
  **start** of the month — the same annuity-due convention as the main engine
  (`compound_actual` mirrors `simulate_paths` for a single path and is verified
  against the same closed form as `test_constant_return_matches_closed_form`).
- **Simulated bands.** Alongside the actual path, the response returns 10th /
  50th / 90th percentile bands resampled from the **full** history by the
  bootstrap engine with a fixed seed (`seed=42`, the same default percentile
  levels), so the chart shows what the window actually did vs. what a fan chart
  would have predicted.
- **Coverage requirement.** The whole window must be present in the portfolio's
  overlapping monthly history, otherwise the endpoint returns 400 naming the
  crisis and the reason (e.g. "instruments launched after the crisis window
  ended").

## Distribution statistics

_Source: `compute_distribution_stats` in `app/simulation/monte_carlo.py`,
computed at run time and persisted on `simulation_runs.stats_json` (added as a
forward-compatible `ALTER TABLE` migration via `ensure_column` in
`app/database.py`; legacy runs have `stats_json = NULL` and the API's `stats`
field is `null` for them)._

Every simulation response now carries a `stats` object summarizing the full
`n_simulations` final-value distribution (not just the three percentile bands):

| Statistic | Definition |
|-----------|-----------|
| `total_contributed` | Book value: `initial_balance + monthly_contribution · horizon_months`. |
| `probability_of_profit` | Fraction of paths ending **above** `total_contributed`. |
| `final_percentiles` | `p10 / p25 / p50 / p75 / p90` of the final values (`np.percentile`, linear). |
| `median_max_drawdown` | Median over paths of each path's peak-to-end drawdown `value/cummax − 1`. |
| `upside_downside_ratio` | `(p90 − total_contributed) / (total_contributed − p10)`; `null` when `p10 ≥ total_contributed` (all risk is downside-free). |
| `histogram` | 20 equal-width bins of final values: `bin_edges` (21) + `counts` (20). |

**Drawdown caveat.** `median_max_drawdown` is measured on the *portfolio*
trajectory, which includes contributions. Each deposit raises the running peak
that later drawdowns are measured from, so ongoing contributions
proportionally **dampen** the reported magnitudes — it is *not* the drawdown a
buy-and-hold investor in the underlying index would have seen. Months before
any money is in the portfolio (zero initial balance) contribute a drawdown of
exactly 0, never NaN.