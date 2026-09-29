# AI Usage Log

Log of AI-assisted changes found through human code review. One entry per bug;
evidence from the test suite is included.

## Bug 1 â€” Contribution timing in the Monte Carlo engine
- **Found by:** human review (docstring vs. code mismatch).
- **Verification:** the `simulate_paths` contribution timing was already fixed
  in an earlier commit (`a0de804`, "fixed the contribution timing bug"): the
  engine already implements start-of-period (annuity-due) deposits matching the
  docstring, i.e. `inv_shifted` shifted one column right. The bug-as-described
  (ordinary annuity) was **not present** in the code.
- **What changed:** the pre-existing closed-form test
  `test_constant_return_matches_closed_form` still encoded the OLD
  ordinary-annuity formula and was the one red test in the baseline suite.
  Its expectation was aligned to the documented annuity-due closed form, and
  the review's `test_volatility_drag_lowers_median` was added.
- **Test evidence:** baseline `test_constant_return_matches_closed_form`
  FAILED (`1111.` vs expected `1110.` at month 1). After alignment:
  `102 passed`. Commit `96b360f`.

## Bug 2 â€” Percentile levels documented three ways
- **Found by:** human review.
- **Verification:** confirmed both stale texts present:
  - `monte_carlo.py` `path_percentiles` docstring: "best-case (95th), median
    (50th) and worst-case (5th)".
  - `schema.sql` `simulation_results.percentile` comment: "-- e.g. 5, 50, 95".
- **What changed:** both updated to the true 10 / 50 / 90 levels.
- **Test evidence:** suite green after change (`100 passed`).
  Commit `99c20f2`.

## Bug 3 â€” Trivially-true geometric-mean match in `validate_bootstrap`
- **Found by:** human review.
- **Verification:** confirmed. `hist_geom = hist_geom_mean if hist_geom_mean is
  not None else sim_geom` made `geometric_mean_match` always `True` (and
  reported the simulated g. mean as the "historical" one) whenever any
  historical return was `<= -1`.
- **What changed:** when the historical geometric mean is undefined it is now
  reported as `None` (`ValidationReport.historical_geometric_mean: float | None`,
  `geometric_mean_match: bool | None`, propagated through `as_dict()`), and no
  match is ever computed in that case. Added
  `test_geometric_mean_undefined_yields_none_match`. Only touched test:
  `tests/test_monte_carlo.py` (new test added; existing `assert
  report.geometric_mean_match` in `test_bootstrap_matches_empirical_distribution`
  still valid for all-positive returns and unchanged).
- **Test evidence:** `101 passed`. Commit `ea7e740`.

## Bug 4 â€” Fragile summary indexing in `_assemble_response`
- **Found by:** human review.
- **Verification:** confirmed `finals[len(finals) // 2]` assumed ascending,
  odd-count levels. Frontend checked first: `frontend/src/pages/Simulator.jsx`
  reads `summary.best/median/worst_case_final_value`, `sentiment.applied`, and
  `sentiment.volatility_multiplier` â€” all keys preserved; the raw
  `sentiment.score` was already present, so the change is additive only.
- **What changed:** summary finals now indexed by percentile level value
  (`dict(zip(levels, finals))` with `min/max/get(50.0, ...)` fallback).
  The `"applied": bool(use_sentiment) and multiplier != 1.0` logic was kept.
- **Test evidence:** suite green. Commit `e186b91`.

## Bug 5 â€” Stray character at end of schema.sql
- **Found by:** human review.
- **Verification:** the stray `a` is **not present** â€” raw byte inspection
  shows the file ends with `...published_at);` and the final non-whitespace
  character is `;`. Nothing was removed.
- **What changed:** created `tests/test_schema.py` asserting schema.sql runs
  via `executescript()` without error. With the BUG 7 index added,
  `test_news_category_published_index_exists` was extended so the file asserts
  both news indexes (the review's requested coverage).
- **Test evidence:** `test_schema.py` green. Commit `65fb139`.

## Bug 6 â€” Foreign keys not enforced per connection
- **Found by:** human review.
- **Verification:** confirmed. `get_connection()` set only
  `PRAGMA foreign_keys = ON`; `journal_mode`/`busy_timeout` were never set on
  new connections, so the schema.sql PRAGMAs did not persist.
- **What changed:** every new connection from `get_connection()` now executes
  `PRAGMA journal_mode = WAL`, `PRAGMA busy_timeout = 5000`, and
  `PRAGMA foreign_keys = ON`. Added `tests/test_database.py` asserting
  `PRAGMA foreign_keys == 1`, WAL mode, and busy_timeout 5000.
- **Test evidence:** `101 passed`. Commit `db31b85`.

## Bug 7 â€” Schema never applied to non-empty databases
- **Found by:** human review.
- **Verification:** the premise was **already false** â€” `init_db()` runs
  `executescript` unconditionally (idempotent, all statements `IF NOT EXISTS`),
  so new schema reaches existing databases at startup. `ANALYZE` is not run at
  startup. Nothing to fix in `database.py`.
- **What changed:** added the missing `idx_news_category_published
  (category, published_at)` index to schema.sql and extended
  `tests/test_schema.py` to assert both news indexes.
- **Note:** `ANALYZE` should still be run once manually after the next bulk
  ingest (none of the new indexes have runtime statistics yet).
- **Test evidence:** `102 passed`. Commit `ddabf88`.

## Bug 8 â€” Sentiment-to-volatility band too wide (deliberate parameter change)
- **Found by:** human review (uses docs/sentiment_validation.md findings).
- **Verification:** confirmed existing constants
  (`NEGATIVE_SENTIMENT_SENSITIVITY = 0.75`, `POSITIVE_SENTIMENT_SENSITIVITY =
  0.25`, `MIN_VOLATILITY_MULTIPLIER = 0.5`, `MAX_VOLATILITY_MULTIPLIER = 2.0`).
- **What changed:** constants narrowed to 0.10 / 0.05 / 0.9 / 1.1 (score -1 ->
  1.10x vol, score +1 -> 0.95x vol); module comment updated to document the
  deliberate narrow band (weak sentiment signal) and the retained asymmetry
  (leverage effect, Black 1976); `volatility_multiplier_from_sentiment`
  docstring clip range updated to [0.9, 1.1].
- **Tests updated (and why):**
  - `test_monte_carlo.py::test_sentiment_multiplier_is_asymmetric_around_neutral`
    â€” asserted old magnitudes 1.75 / 0.75.
  - `test_monte_carlo.py::test_sentiment_multiplier_is_clipped_and_handles_nan`
    â€” asserted old clipped bounds 1.75 / 0.75 (clips are now 1.10 / 0.95).
  - `test_api.py::test_positive_sentiment_narrows_volatility` â€” asserted old
    multiplier 0.75 for score +1.0.
  - `test_api.py::test_negative_sentiment_widens_the_fan_chart` â€” the old wide
    band made the 10/90 spread gap visible at 2-dp rounding; with the narrow
    band the max-signal setup (score -1.0, horizon 60) keeps the strict
    direction check meaningful. Multiplier assertion tightened to `1.10`.
  - Tests passing explicit multipliers to `simulate_paths` (1.75 / 0.75) were
    NOT changed â€” that path is not clipped.
- **Test evidence:** `102 passed`. Commit `ead678c`.

## Stage A â€” News sentiment feed API + Financial News page
- **What changed:** new `GET /news?category=sector|geopolitical&ticker_id=&days=30`
  endpoint (`app/routers/news.py`, response models `HeadlineOut`/`NewsFeedOut`
  in `app/schemas.py`). Newest-first, headlined capped at 100, `days` clamped to
  1..90, aggregate score = mean of non-null sentiment in the window (null when
  none). `ticker_id` filters sector rows only and is ignored for geopolitical
  news. `list_sentiment` gained an additive `desc` ordering flag
  (`app/dao/news.py`). Financial News page (`frontend/src/pages/FinancialNews.jsx`)
  wired to the endpoint with sector/geopolitical tabs, 7/30/90-day windows,
  aggregate-score card, and empty/error/loading states.
- **Test evidence:** `tests/test_news_api.py` (10 tests: category, window,
  clamping, ticker filter incl. geopolitical-ignore, mean-of-non-null,
  all-null, newest-first, 100 cap, 422s, empty feed). `109 -> 119 passed`.
  Commit `0878342`.

## Stage B â€” ETF screener endpoint + sortable screener table
- **What changed:** new `GET /screener` (`app/routers/screener.py`,
  `app/services/screener.py`) computing per-ticker screening stats from the
  stored daily closes with pandas (no network): 1D change, 1Y total return
  (null <253 rows), annualized volatility (std of daily log returns over the
  last 252 closes Ã—âˆš252, null <30 points), and max drawdown over the last year
  (negative %). Only tickers with price history appear, sorted by symbol. The
  known adjustment-basis limitation is documented in the endpoint docstring and
  `docs/data_methodology.md`. ETF catalog page now renders the screener with
  click-to-sort columns and row click deep-linking to the Simulator with the
  ticker pre-selected via `?ticker=` (`frontend/src/pages/Etfs.jsx`,
  `Simulator.jsx`).
- **Test evidence:** `tests/test_screener.py` (12 tests: 1Y null/known-value,
  1D, vol null/known/zero, drawdown, API shape + exclusion of history-less
  tickers). `119 -> 131 passed`. Commit `48f7eb1`.

## Stage C â€” FK-safe DELETE /portfolios/{id}
- **What changed:** `delete_portfolio` in `app/dao/portfolios.py` removes child
  rows in dependency order (simulation_results â†’ simulation_runs â†’
  portfolio_holdings â†’ portfolios) with foreign keys enforced per connection;
  returns 404 when the portfolio does not exist. No frontend change.
- **Test evidence:** `tests/test_portfolio_delete.py` (4 tests) asserts row
  counts in all four tables drop to zero after delete, 404 for missing, 404 on
  double-delete, and that other portfolios are untouched. `131 -> 135 passed`.
  Commit `75363d8`.

## Stage D â€” Crisis replay endpoint + Simulator overlay
- **What changed:** new `POST /portfolios/{id}/crisis-replay`
  (`app/routers/crisis.py`, `app/services/crisis.py`) replays a portfolio
  through fixed windows (`dot_com_2000` 2000-03â†’2002-09, `gfc_2008`
  2007-10â†’2009-03, `covid_2020` 2020-02â†’2020-04). The real trajectory compounds
  the portfolio's realized monthly returns with start-of-month contributions,
  mirroring the engine (`compound_actual` matches the same closed form as
  `test_constant_return_matches_closed_form`); a history that does not fully
  cover the window returns 400 naming the crisis and reason. 10/50/90 percentile
  bands are resampled from the full history with `seed=42`.
  `portfolio_monthly_returns_with_dates` added (additive) in
  `app/services/simulation.py`. Simulator page gained a minimal "Replay a
  crisis" control overlaying the real trajectory on the simulated fan chart
  (`frontend/src/pages/Simulator.jsx`); methodology documented in
  `docs/data_methodology.md`.
- **Test evidence:** `tests/test_crisis.py` (15 tests: window slicing for all
  three crises, coverage-error reasons, annuity-due closed form, plain-growth
  compounding, plus API wiring/422s/400s and seed determinism).
  `135 -> 150 passed`. Commit `a869e9c`.

## Stage F â€” Frontend design pass (quant-terminal aesthetic; presentational only)
- **What changed:** styling-only pass; no API calls, data wiring, prop
  contracts, routing, or backend files were touched. Design decisions:
  accent `#4cc2ff` for all interactive elements (accent), semantic up/down
  colors `pos #16c98e` / `neg #ff5c6c` (exempt from the one-accent rule), a
  single corner radius of `0px` (terminal square look), a fixed type scale of
  12/14/16/20/24/32px (body 1.5, headings 1.2), and a font pair of Inter
  (prose) + JetBrains Mono (tickers, numbers, tables) with tabular numerals.
  All hex lives once in `tailwind.config.js`; chart/runtime colors in
  `index.css` are derived from it via `theme()`.
  Removed: gradient area-chart fills, all `border-white/5` micro-dividers
  (replaced with spacing), decorative hover/scale/glow effects, `animate-pulse`
  skeletons, the disclaimer marquee, and the `AmbientDataGrid`
  requestAnimationFrame loop (now a static one-shot grid with event-driven
  resize redraw only). DisclaimerBanner is now a static, always-visible,
  high-contrast strip. Tables/prose are left-aligned; prose blocks capped at
  `max-w-prose` (65ch). Every page got a designed empty/loading state. Fonts
  loaded via Google Fonts `<link>` in `index.html`.
- **Files changed:** `tailwind.config.js`, `index.css`, `index.html`,
  `src/App.jsx`, `src/components/Sidebar.jsx`,
  `src/components/DisclaimerBanner.jsx`, `src/components/AmbientDataGrid.jsx`,
  `src/pages/Home.jsx`, `src/pages/Etfs.jsx`, `src/pages/Simulator.jsx`,
  `src/pages/FinancialNews.jsx`, `src/pages/InvestingStrategies.jsx`,
  `README.md` (Screenshots section), `docs/screenshots/before/` and
  `docs/screenshots/after/` (5 pages Ã— desktop 1440Ã—900 + mobile 390Ã—844,
  captured with Edge headless).
- **Evidence:** `npm run lint` (oxlint) clean; `npm run build` clean; DOM
  verification after the pass shows the same real data rendering on all pages
  (SPY watchlist rows, screener table + "tracked" chip, headlines + aggregate
  sentiment, simulator controls). Frontend has no test suite; the backend
  suite is unaffected (150 passed).

## Stage H  —  Branded frontend shell (top nav, 404, page meta, a11y, code splitting)
- **What changed:** presentational/frontend-only; no backend files touched.
  - H3: `Sidebar.jsx` removed; new `components/TopNav.jsx` replaces it inside
    `App.jsx`  —  sticky top row with "ETF Simulator" wordmark (accent
    candlestick mark), nav links Home / ETFs / News / Simulator / Strategies,
    active tab = accent text + 2px accent bottom border, mobile = horizontally
    scrollable link row.
  - H6: custom `pages/NotFound.jsx` (the old `*` route's `Navigate` to "/" was
    replaced by a real 404 page).
  - H5: new `hooks/usePageTitle.js` applied to all six routes (per-page
    `<title>`; verified headless: "Home  —  ETF Simulator", "Page not found  — 
    ETF Simulator"); `index.html` gained meta description, `theme-color
    #0a0a0a`, Open Graph tags, and `public/og-image.png` (a real desktop Home
    screenshot); `public/favicon.svg` restyled to the accent candlestick.
  - H7: Edge `--enable-logging=stderr` on all six routes  —  zero page console
    errors (only Edge-internal sync/oneauth noise). No app-level warnings.
  - H8: `vite.config.js` sets `build.sourcemap: false`; all route components
    are `React.lazy` + one `Suspense`. Bundle before (Stage F build): single
    670.87 kB JS (gzip 199.90 kB) + 18.57 kB CSS with a >500 kB chunk warning.
    After: entry `index` 267.41 kB (gzip 85.62) + split Recharts chunk 353.19 kB
    (loaded only with chart pages) + small lazy route chunks (Home 9.45, Etfs
    5.52, News 5.23, Simulator 29.73, Strategies 1.13, NotFound 0.83); chunk
    warning gone.
  - H9: Home gained an `sr-only` h1 (one h1 per page now across all routes,
    verified by DOM count); charts wrapped in `role="img"` + aria-label
    (Home price chart, Simulator growth fan + crisis replay). Landmarks:
    single `<main>`, `nav aria-label="Primary"`.
  - H2/H4 (verify-then-fix): no Sidebar "Phase 4.7" footer remains after H3;
    the "stray annotation at 2002-09-17 (56.68)" on the Home chart does NOT
    reproduce as a persistent element  —  full DOM render shows only the hidden
    Recharts tooltip wrapper (`visibility: hidden`) at rest; the text appears
    only transiently while hovering the first data point (correct tooltip
    behavior), so no structural change was made.
- **Files changed:** `src/App.jsx`, `src/pages/Home.jsx`, `src/pages/Etfs.jsx`,
  `src/pages/Simulator.jsx`, `src/pages/FinancialNews.jsx`,
  `src/pages/InvestingStrategies.jsx` (reworded "later phase"  —  "coming
  soon"), new `src/components/TopNav.jsx`, `src/hooks/usePageTitle.js`,
  `src/pages/NotFound.jsx`, deleted `src/components/Sidebar.jsx`, `index.html`,
  `public/favicon.svg`, `public/og-image.png`, `vite.config.js`,
  `docs/screenshots/round3/` (5 pages + 404 at 1440A-900 and 5 at 390A-844).
- **Evidence:** `npm run lint` (oxlint) clean; `npm run build` clean;
  headless DOM checks confirm wordmark + five nav links + active-tab classes,
  one h1 and one `<main>` per page, dynamic `<title>` on Home and 404, and no
  console errors. Backend suite unaffected (150 passed).

## Stage I  —  Insights statistics backend (distribution stats + monthly returns)
- **What changed:** backend-only; no frontend files touched.
  - I1: `compute_distribution_stats(paths, initial_balance, monthly_contribution,
    horizon_months)` added to `app/simulation/monte_carlo.py`  —  a pure,
    vectorized summary over the full final-value distribution:
    `total_contributed`, `probability_of_profit`, `final_percentiles`
    (p10/p25/p50/p75/p90), `median_max_drawdown` (median peak-to-end drawdown;
    zero months with a zero running peak never emit NaN; docstring notes that
    contributions proportionally dampen the reported magnitude), and
    `upside_downside_ratio` = (p90 - contributed) / (contributed - p10), `null`
    when p10 >= contributed, plus a 20-bin histogram. Exported via
    `app/simulation/__init__.py`.
  - I2: `simulation_runs.stats_json TEXT` added to `schema.sql` and
    forward-migrated onto existing databases by a new `ensure_column()`
    helper in `app/database.py` (SQLite has no `ADD COLUMN IF NOT EXISTS`;
    checked against `PRAGMA table_info`, idempotent, called from `init_db`).
    Stats are computed in `run_portfolio_simulation` from the full simulated
    paths, rounded for compact JSON, stored on the run, and served as an
    additive `stats` field in every simulation response (fresh, cached, and
    `GET /simulation-runs/{id}`). Legacy rows and pre-stats caches have
    `stats_json = NULL`  —  the API returns `stats: null` for them.
  - I3: new `GET /portfolios/{id}/monthly-returns`
    (`app/routers/portfolios.py`, backed by the existing
    `portfolio_monthly_returns_with_dates` service)  —  `[{year, month, return}]`
    of the weighted portfolio monthly returns, 404 for a missing portfolio, 400
    for no holdings / insufficient overlapping history.
- **Files changed:** `schema.sql`, `app/database.py`, `app/dao/simulations.py`,
  `app/services/simulation.py`, `app/routers/portfolios.py`,
  `app/simulation/monte_carlo.py`, `app/simulation/__init__.py`,
  `tests/test_distribution_stats.py` (new, 10 tests incl. hand-computed
  p10/p25/p50/p75/p90, 0.75 probability, ratio numbers/null cases, NaN-free zero
  initial balance), `tests/test_insights_api.py` (new, 5 tests: stats shape +
  consistency, cached-stats equality, legacy-null served, monthly-returns shape
  + 404 + 400), `tests/test_database.py` (2 migration tests), and the new
  "Distribution statistics" section in `docs/data_methodology.md`.
- **Test evidence:** `150 -> 168 passed`. Commit `bf5a7df`.

## Stage J  —  Insights frontend (stat cards, distribution histogram, monthly-returns heatmap)
- **What changed:** frontend-only, additive in `frontend/src/pages/Simulator.jsx`
  plus one new 11px type token in `frontend/tailwind.config.js`.
  - J1: "Outcome insights" panel above the fan chart  —  five stat cards fed by
    the Stage I `stats` payload: Probability of profit (%, pos/neg-toned by
    >=/ < 50%), Median final value (p50), Worst case (p10), Upside / downside
    (`stats.upside_downside_ratio`, `—` when null, pos/neg-toned), Median max
    drawdown. Cards use the 11px uppercase micro-label + 24px mono value format
    (new `text-11px` scale token; no arbitrary value classes).
  - J2: final-value distribution histogram (`BarChart`, 20 bins, accent bars,
    `isAnimationActive={false}`) in the same panel with a custom tooltip
    (range + path count) and two marker lines: p50 (solid accent) and total
    contributed (dashed dim). Marker buckets are matched by category label;
    markers are skipped when p50 / contributed fall outside the binned range.
  - J3: "Realized monthly returns" heatmap panel fed by
    `GET /portfolios/{id}/monthly-returns`  —  one row per year, 12 month
    columns, cell intensity scaled from `returns / 5%` via
    `color-mix(in srgb, var(--up|--down) <alpha>%, transparent)` (integer
    alpha, no gradients), strong cells flip to black text for contrast, native
    `title` tooltips (`YYYY-MM · ±x.xx%`), a compact `loss → gain` legend, and
    standalone loading / error / no-history states. The fetch fires only once a
    portfolio exists and a run completes (deduped by effect deps, cancelled on
    unmount).
  - J4: when a run's `stats` is `null` (legacy pre-Stage-I run), the insights
    panel collapses to a "Re-run to see insights" empty state; the heatmap still
    renders because it does not depend on `stats`.
- **Verification:** `npm run lint` (oxlint) clean; `npm run build` clean
  (Simulator chunk 29.73  →  61.50 kB raw, 17.62 kB gzip, from the new
  panels; entry chunk unchanged). Headless Edge DOM checks with a temporary,
  `?autorun=1`-gated auto-run (removed before commit) confirmed real data
  rendering: all five card values (98%, $72,725, $45,857, "—", -19.0%),
  20-bin histogram with both marker lines, J/F/M/… month headers, per-year
  rows with correct `color-mix` alphas (e.g. +2.24% → up 45%), and the J4
  empty state when `stats` is forced null (heatmap still rendered). Backend
  suite unaffected: 168 passed. Screenshots: `docs/screenshots/round4/`.
- **Note:** legacy cached runs cannot be re-served (their `params_json` lacks
  the `data_fingerprint` key used in modern cache lookups), so the J4 empty
  state is defensive for legacy runs and any future stats-null responses.
- **Files changed:** `frontend/src/pages/Simulator.jsx`, `frontend/tailwind.config.js`,
  `docs/screenshots/round4/` (desktop + mobile, incl. tall result-area shots).
- **Test evidence:** frontend lint+build clean; backend suite `168 passed`.
  Commit `e2cdb75`.

## Stage K -- Demo seeding + deployable single container
- **Found by:** implementation task (Stage K of `docs/PROJECT.md`).
- **What changed (K1, commit `cd86d2e`):** a Demo User seeding CLI. New DAO
  `get_portfolio_by_user_and_name`; `backend/app/scripts/seed_demo.py` creates
  three portfolios on first run (idempotent, keyed by user+name): "All-World
  Growth" (VXUS 100%, $200/mo), "Balanced 60/40" (VTI 60 / BND 40, $100/mo,
  with a lowest-volatility catalog fallback when a bond-like ticker is
  unavailable, `exclude={VTI}`), and "Tech Tilt" (QQQ 70 / VXUS 30, $200/mo).
  Run with `python -m app.scripts.seed_demo`.
- **What changed (K2):**
  - Split requirements: `requirements.txt` is now runtime-only (fastapi,
    uvicorn[standard], pydantic, pydantic-settings, python-dotenv, numpy,
    pandas); `requirements-ingest.txt` adds yfinance/APScheduler/feedparser/
    scipy/torch/transformers; `requirements-dev.txt` adds pytest/httpx.
    Verified the API boots and the whole suite runs in a fresh venv with only
    `requirements.txt` + `requirements-dev.txt`.
  - Skip-guards: tests that import ingest-only deps now `pytest.importorskip`
    (`test_sentiment` torch; `test_market_data` yfinance x3;
    `test_news_fetch` + `test_sentiment_ingest` feedparser;
    `test_validate_sentiment` scipy; `test_scheduler` apscheduler x1). Runtime
    venv: 149 passed / 8 skipped; full venv: 181 passed.
  - Scheduler gating (verify-then-fix: `ENABLE_SCHEDULER` + lifespan gate
    already existed in `app/main.py`) validated with
    `tests/test_scheduler_gating.py` covering both states via monkeypatched
    `app.main.create_scheduler` / `shutdown_scheduler`.
  - Static SPA serving (`app/main.py::_frontend_dist` + `spa_fallback`): when
    `frontend/dist` (or `FRONTEND_DIST`) exists, `/` returns `index.html`,
    hashed assets are served from disk, unknown paths fall back to
    `index.html`, and all API routes are untouched (registered first). With no
    dist, the JSON root and FastAPI 404s are unchanged. `tests/test_static_serving.py`.
  - Frontend same-origin fix: `frontend/src/api.js` now uses
    `(VITE_API_BASE_URL ?? '/api').replace(/\/+$/, '')` so the container build
    (`VITE_API_BASE_URL=/`) yields root-path API calls without double slashes.
  - `Dockerfile` (node:20-alpine build stage -> python:3.13-slim runtime, only
    `requirements.txt` installed, `ENABLE_SCHEDULER=0`, `FRONTEND_DIST`,
    `HEALTHCHECK` on `/health`) + root `.dockerignore`
    (simulator.db\* excluded, deploy.db shipped).
  - `backend/scripts/prepare_deploy_db.py` folds the dev WAL
    (`PRAGMA wal_checkpoint(TRUNCATE)` + `ANALYZE`) and copies
    `simulator.db` -> `deploy.db` (frozen snapshot, 8.6 MB, 13 tickers /
    106,251 prices / 23 runs).
  - New `docs/deployment.md`, root `AGENTS.md`, README dependency-table +
    deployment sections.
- **Test evidence:** backend suite `181 passed` (dev venv); runtime-only venv
  `149 passed, 8 skipped`; `npm run lint` + `npm run build` clean; local
  `docker build -t etf-simulator` succeeded (447 MB) and the container ran:
  `/health` ok, `/tickers` 200 JSON, `/screener` 200 JSON, `/` 200 - served
  `index.html` (title "ETF Simulator ..."), `/simulator` fell back to
  `index.html`, and a full create-portfolio + simulate (seed 42, n=100)
  returned a cached `run_id` with `p50=58,470.57` / `p90=90,021.52` /
  `probability_of_profit=0.99`.
- **Files changed:** `backend/requirements.txt`, `requirements-ingest.txt`,
  `requirements-dev.txt`, `app/config.py`, `app/main.py`,
  `scripts/prepare_deploy_db.py`, tests (6 guarded modules + 2 new files),
  `frontend/src/api.js`, `Dockerfile`, `.dockerignore`, `AGENTS.md`, `README.md`,
  `docs/deployment.md`.
- **Commits:** `cd86d2e` (K1); `5b5fa81` (K2).

## Stage L3 -- Institutional light retheme
- **Found by:** implementation task (Stage L3 of `docs/PROJECT.md`).
- **What changed:** dark quant-terminal -> institutional light, token-only (no
  layout/spacing/structure/component-logic changes):
  - Full palette swap in `frontend/tailwind.config.js` (exact values: background
    #F6F7F9, surface #FFFFFF, hover #EEF0F3, border #E2E5EA, ink #16181D,
    secondary #5A6270, muted #8A919E, accent #0B5FFF, pos #0E7C3A, neg #C62828;
    warn reuses neg red). Derived values (`.dim*`, `edge.strong`) are written
    as rgba() of the exact palette hex; `warn` gains a named `#C62828` alias.
    Single elevation token `boxShadow.panel = 0 1px 2px rgba(22,24,29,0.06)`.
  - `index.css`: chart vars (`--chart-grid` #E2E5EA, `--chart-axis` #5A6270,
    `--chart-line` #0B5FFF, `--up`/`--down` from pos/neg), `color-scheme: light`,
    `.panel`/`.btn`/`.btn-primary`/`.chip`/`.input`/`.select` restyled on
    tokens, plus full L1 slider CSS (16px accent thumb, 4px edge track, accent
    focus ring) and global `:focus-visible` outlines.
  - `index.html` theme-color #F6F7F9 + inline no-dark-flash style and
    `color-scheme: light`; `public/favicon.svg` and `public/og-image.png`
    regenerated for the light palette (og card 1200x630, candlestick motif).
  - AmbientDataGrid kept but recolored to a near-invisible #E2E5EA grid
    (alpha 0.35) - canvas interaction retained, decision verified by screenshot.
  - Straggler sweep in `Home.jsx` (watch-row hover/active, range pills, tooltip
    white+panel shadow, axis 12px, accent-dim cursor), `Simulator.jsx` (tooltips
    white, toggle switch, weight boxes, heatmap null-cell + strong-cell
    contrast flip to white text, histogram axis/bar/cursor, fan + crisis axes
    12px + accent cursors, ReferenceLine var fix), `Etfs.jsx` (sticky thead
    white, skeleton fills), `FinancialNews.jsx` (category/day toggle pills
    tokens), `TopNav.jsx` (hover:text-ink, brand text-ink).
  - Fresh screenshots: `docs/screenshots/light-theme/` (5 pages x desktop
    1440x900 + mobile 390x844); README embeds point there (dark history kept in
    `before|after/`).
- **Note (pre-existing, not fixed here - production route collision):** a GET
  `/news` API route shadows the SPA `/news` route on a single-origin build, so
  a hard refresh of `/news` returns the API's 422 JSON. In dev the Vite
  `/api` proxy avoids it. Left as-is for L3 (theme-only stage); tracked for a
  future stage.
- **Test evidence:** `npm run lint` clean; `npm run build` clean after fixing
  a Tailwind constrain: a color key named `hover` cannot be used as
  `hover:bg-hover` inside `@apply` (and `bg-hover` alone is not generated - the
  token lives at `base.hover` -> `bg-base-hover`). Backend untouched by L3.
  WCAG contrast on the new palette: ink 17.8:1, secondary 6.2:1, accent 5.1:1,
  white-on-accent 5.1:1, pos 5.3:1, neg 5.6:1 (all >= AA normal text).
- **Files changed:** `frontend/tailwind.config.js`, `frontend/src/index.css`,
  `frontend/index.html`, `frontend/public/favicon.svg`, `frontend/public/og-image.png`,
  `frontend/src/components/AmbientDataGrid.jsx`, `frontend/src/components/TopNav.jsx`,
  `frontend/src/pages/Home.jsx`, `frontend/src/pages/Simulator.jsx`,
  `frontend/src/pages/Etfs.jsx`, `frontend/src/pages/FinancialNews.jsx`,
  `README.md`, `docs/screenshots/light-theme/*`, `docs/ai_usage_log.md`.

## Stage L1 -- Form-control styling + keyboard-focus audit
- **Found by:** implementation task (Stage L1: consistent token-driven form
  controls with visible range thumb/track, keyboard operability, visible
  focus).
- **What changed:**
  - The control layer already shipped with the L3 retheme: `.input` /
    `.select` / `.select-native` (white surface, edge border, 2px `accent/25`
    focus ring), `.btn` / `.btn-primary` / `.btn-danger-ghost` (accent/neg
    `focus-visible` rings), `.slider` (16px accent thumb, 4px edge track on
    WebKit + Gecko, accent focus ring), and a global `button/a/[role=switch]:focus-visible`
    accent outline for bare controls. L1 verified every control adopts one of
    these, so one change covered the audit.
  - One gap fixed: the Simulator holding-weight number input's focus was only a
    1px border shift; added the same `focus-within:ring-2 ring-accent/25`
    accent ring used elsewhere.
- **Per-page checklist** (control | token-styled | keyboard OK | visible
  focus):
  - Home: instrument select (.select, arrows OK) / watchlist search (.input)
    / range pills (bare button, global focus outline) — all pass.
  - Etfs: sort header buttons (bare, global outline; Arrow/Enter activate) /
    Refresh (.btn) — pass.
  - FinancialNews: category toggle + day-toggle pills (bare, global outline) /
    empty-state buttons (.btn) — pass.
  - Simulator: portfolio name (.input) / 3 range sliders (.slider, 16px accent
    thumb, arrow keys adjust) / holding select (.select) / weight number
    input (accent border + ring) / remove/add/run (.btn/.btn-primary/
    .btn-danger-ghost) / AI-sentiment ToggleSwitch (`role=switch`, Space
    toggles, global switch focus outline) / crisis select (.select) / Replay
    (.btn-primary) — pass.
  - No `<input type=checkbox>` or radio controls exist in the app.
- **Verification:** `npm run lint` + `npm run build` clean (backend untouched).
  Focused states captured via Chrome DevTools Protocol (headless) for each
  control type: `docs/screenshots/light-theme/controls/`
  (`controls_Home_select_focus`, `controls_Home_search_focus`,
  `controls_Etfs_sort_focus`, `controls_News_daytoggle_focus`,
  `controls_Simulator_slider_focus`, `controls_Simulator_switch_focus`,
  `controls_Simulator_weight_focus`, `controls_Simulator_name_focus`); accent
  focus pixels confirmed present on the full-resolution captures. README
  Screenshots section now links the controls set.
- **Note:** the `/news` single-origin route collision (API GET /news vs SPA
  /news) was hit again while capturing the News focus shot on the built SPA;
  workaround for screenshots was client-side navigation from `/`. Still
  tracked for a future stage.
- **Files changed:** `frontend/src/pages/Simulator.jsx` (weight-input focus
  ring), `README.md`, `docs/screenshots/light-theme/controls/*`,
  `docs/ai_usage_log.md`.

## Stage L2 -- Portfolios section (create → simulate through the UI)
- **Found by:** implementation task (Stage L2: Portfolios UI + PATCH endpoint).
- **What changed:**
  - Backend: `PATCH /portfolios/{id}` (`app/routers/portfolios.py`), shared
    `_resolve_holdings` (404 naming the unknown ticker), transactional
    update+delete+insert of holdings with a single `commit()`; `PortfolioUpdate`
    mirrors create rules and enforces `abs(sum(weights) - 1.0) <= 0.01` → 422
    (`app/schemas.py`, docstring explains the deliberate strict 422 over silent
    renormalization). `created_at` added to portfolios (`schema.sql` +
    idempotent `ensure_column` + `date('now')` backfill for legacy rows in
    `app/database.py`; inserts use `date('now')`; surfaced in every read).
  - Frontend: new `frontend/src/pages/Portfolios.jsx` (list table with
    Name/Holdings/Monthly/Created/Actions, create+edit form with search-to-add
    holdings builder, per-row symbol/weight controls, live total-weight
    indicator that flips `text-neg` → `text-pos` at 100%±1, token-only delete
    confirm dialog with Escape/autofocus/`role=dialog`, empty + error states);
    lazy route `/portfolios` + "Portfolios" top-nav item; Simulator gained a
    portfolio selector, `applyPortfolio`, a `?portfolio=ID` deep link, and
    `runSimulation` now PATCHes the selected portfolio (percent → fraction
    conversion) or POSTs a new one.
  - `frontend/src/api.js`: `fetchJSON` returns null on 204 (delete) and throws
    on a non-JSON 200 (previously `.catch(() => null)` could return HTML that
    leaked through a misconfigured base URL as `null` and crash callers — e.g.
    `null.filter(...)` in Home).
- **Deviations documented (by design):** `POST /portfolios` still does NOT
  require sum-to-1.0 (only weights > 0 and positive total); the engine
  renormalizes at read. PATCH deliberately adds the strict sum rule. The
  Simulator POST path keeps sending the create payload unchanged (percentages
  as before). Single-origin producers must build with `VITE_API_BASE_URL=/`
  (as the container does); the default `/api` fetches an HTML 200 from the SPA
  fallback on FastAPI's root.
- **Bug found during verification (fixed here):** under concurrent load (Home
  mounts ~14 parallel price/tickers fetches), FastAPI's threaded
  yield-dependency teardown ran `conn.close()` on a different worker thread
  than the one that opened the connection →
  `sqlite3.ProgrammingError: SQLite objects created in a thread can only be
  used in that same thread`, flipping otherwise-successful GETs to 500s
  (`/portfolios` intermittently failed in the browser smoke). Fix:
  `sqlite3.connect(db_path, check_same_thread=False)` in `get_connection()`
  (safe: a connection is used on a single request thread; only the exit
  `close()` may cross threads). Verified via a 12-round concurrent burst of
  `/tickers/*/prices` + `/tickers` + `/portfolios`: 132 failures before, 0
  after; occurs nowhere in the visible call stack otherwise.
- **Note (pre-existing, not fixed here):** GET `/portfolios` (API) shadows the
  SPA `/portfolios` route on a single-origin build, so a hard refresh of the
  page returns JSON — same class as the tracked `/news` collision. In-app nav
  (top nav / client-side links) is unaffected.
- **Test evidence:** `tests/test_portfolio_patch.py` (6 tests: full rewrite
  visible in results via distinct SPY 0.6%/mo vs QQQ 0.3%/mo curves, 404 for
  missing portfolio / unknown ticker, 422 for missing / negative / overflow /
  off-by-sum weights, name + contribution updates preserved) — backend suite
  `181 → 187 passed`. `npm run lint` + `npm run build` clean
  (`VITE_API_BASE_URL=/`). Headless Chrome CDP smoke of the full flow
  (client-side nav to Portfolios → create with total-weight indicator → deep
  link to Simulator → run → verify stored weights are fractions → edit free →
  delete via confirm dialog): ALL PASSED; screenshots in
  `docs/screenshots/light-theme/portfolios/`.
- **Files changed:** `backend/schema.sql`, `backend/app/database.py`,
  `backend/app/schemas.py`, `backend/app/dao/portfolios.py`,
  `backend/app/routers/portfolios.py`, `backend/tests/test_portfolio_patch.py`,
  `frontend/src/api.js`, `frontend/src/App.jsx`,
  `frontend/src/components/TopNav.jsx`, `frontend/src/pages/Portfolios.jsx`,
  `frontend/src/pages/Simulator.jsx`, `docs/manual_test.md`,
  `docs/screenshots/light-theme/portfolios/*`, `docs/ai_usage_log.md`.

## Stage W -- Weight convention unified: fractions everywhere
- **Found by:** human review follow-up to the Stage L4 audit and the Stage L2
  deviation noted above.
- **What changed:** holding weights are now FRACTIONS in `(0, 1]` summing to
  `1.0` within `0.01`, on both `POST /portfolios` and `PATCH /portfolios/{id}`.
  - `backend/app/schemas.py`: `MAX_HOLDING_WEIGHT` is now `1.0` (a whole
    sleeve) instead of the interim `100.0`; new `WEIGHT_SUM_TOLERANCE = 0.01`
    and a single `_check_weight_convention()` called by **both** `PortfolioCreate`
    and `PortfolioUpdate`, so the two endpoints can no longer drift apart. Uses
    `math.fsum` so the tolerance compares against an exactly-rounded total. A
    `field_validator` on `HoldingIn.weight` names the percent-scale mistake
    ("0.6 (i.e. 60%) looks right if you meant a percentage") instead of the bare
    "Input should be less than or equal to 1" that `le=1.0` alone produces.
  - `backend/app/scripts/seed_demo.py`: seeds fractions (0.6/0.4, 1.0, 0.7/0.3)
    and now **upserts by (user, name)**, rewriting stale holdings and scalars on
    an existing row rather than skipping it. A DB seeded by an earlier revision
    holds percent-scale weights the API now rejects, and those rows are exactly
    what a re-run should repair. The summary reports `created` /
    `repaired` / `unchanged`; CLI output prints weights as percent for humans.
  - `backend/app/services/simulation.py`: the `weights / weights.sum()`
    renormalization is unchanged and documented as defense-in-depth for write
    paths that bypass the API (scripts, migrations, hand-edited DB), not as the
    mechanism.
  - `frontend/src/api.js`: one shared `holdingsToFractions()` performs the
    percent → fraction conversion on submit, plus `fractionToPercentInput()` for
    the display direction. `Simulator.jsx` and `Portfolios.jsx` both call them;
    the two inline `/ 100` copies and the duplicated `weightPercent` helper were
    removed so there is exactly one conversion site. The builder's
    "total weight" indicator still balances against `100` (UI affordance only).
- **Superseded — the interim `<= 100` cap from the Stage L4 audit:** that cap
  existed only to accommodate percent-scale demo seeds. It admitted `60/40`
  sent as percentages, which is harmless-looking and wrong: the engine
  renormalizes, so a 60/40 request silently became a uniform `50/50` portfolio
  and returned plausible but incorrect statistics. Overflow protection is not
  lost -- it is strengthened, because `le=1.0` bounds the weight sum at
  `MAX_HOLDINGS` (50), making the `inf` sum that motivated the cap (two
  holdings at `1e308` → every normalized weight 0 → a silently flat, zero-variance
  fan chart) unreachable.
- **This also removes the Stage L2 deviation** recorded above ("`POST
  /portfolios` still does NOT require sum-to-1.0 ... PATCH deliberately adds the
  strict sum rule"). That asymmetry let a portfolio be created that could never
  be re-saved with its own stored weights. Create and PATCH now share one
  validator, and a test asserts a rejected PATCH leaves the stored weights
  untouched.
- **Regression guard for the scale itself:** a mis-scaled weight does not error
  downstream, it just changes the numbers, so the tests assert behavior rather
  than just status codes --
  - `test_percent_scale_payload_is_rejected_by_create_and_patch` (422 on both
    verbs, error names the expected fraction, PATCH left the row unchanged);
  - `test_seeded_balanced_portfolio_matches_the_same_weights_posted_by_hand`
    compares the seeded 60/40 against a hand-built `0.6/0.4` under a fixed seed;
    had the seeder written `60/40` the two would renormalize differently and
    disagree on `probability_of_profit` and the percentiles;
  - `test_seeded_portfolios_simulate_to_sane_probabilities` asserts every seeded
    portfolio lands strictly inside `(0, 1)` on a price series with real
    drawdowns, so a degenerate weight cannot hide behind a plausible 0.0/1.0;
  - `test_rerunning_repairs_percent_scale_rows_from_an_older_seed` and
    `test_rerunning_does_not_duplicate_holdings` cover the upsert path;
  - `test_seeded_weights_are_fractions_in_the_unit_interval` round-trips seeded
    weights through `PortfolioCreate`, so demo data that the API would reject
    fails the suite.
- **Note (not changed here):** `openapi.json` at the repo root was a stale
  checked-in dump (9 paths; missing `/news`, `/screener`, `/crisis-replay`,
  `/monthly-returns`, PATCH, DELETE) and still showed the old `weight`
  description. Left untouched at this stage; Stage M deletes it and points the
  README at the live `/docs` endpoint instead.
- **Test evidence:** backend suite `245 → 257 passed` (0 failures, 0 skipped,
  37s) via `--junitxml`; `npm run lint` clean; `npm run build` clean
  (`VITE_API_BASE_URL=/`).
- **Files changed:** `backend/app/schemas.py`,
  `backend/app/scripts/seed_demo.py`, `backend/app/services/simulation.py`,
  `backend/tests/test_seed_demo.py`, `backend/tests/test_input_limits.py`,
  `backend/tests/test_insights_api.py`, `frontend/src/api.js`,
  `frontend/src/pages/Simulator.jsx`, `frontend/src/pages/Portfolios.jsx`,
  `README.md`, `AGENTS.md`, `docs/ai_usage_log.md`.

## Stage M -- Hygiene: import guard, stale artifact, known issues
- **Found by:** implementation task (freeze-prep hygiene pass).
- **M1 -- import hygiene test.** New `backend/tests/test_import_hygiene.py`
  parses every `.py` under `backend/app/` (excluding `app/scripts/` and
  `__pycache__`) with `ast` and fails on any *module-level* import of
  `{yfinance, torch, transformers, apscheduler, feedparser, sentencepiece,
  huggingface_hub}`. It walks only `tree.body`, so an import inside a function
  body -- the lazy pattern the whole repo already uses -- is allowed by
  construction rather than by an exemption list. Three supporting tests: a
  vacuous-pass guard (asserts the scanner found >=30 files and the expected
  modules, so a wrong path cannot make the check silently pass), a pinned
  regression test for `app/scheduler.py` alone, and a test asserting the
  `app/scripts/` exclusion is load-bearing (`scripts/validate_sentiment.py`
  imports scipy at module level, which is also ingest-only but is not on the
  banned list).
- **Caught regression (not the predicted one).** The task anticipated
  `app/scheduler.py` failing. It does not: `apscheduler` was already imported
  inside `create_scheduler()` at `scheduler.py:49`. The violation was elsewhere
  -- **`app/services/news_fetch.py` had a module-level `import feedparser`**
  (line 22) plus a module-level `import httpx` (line 23, also absent from
  `requirements.txt`, being dev-only). Both moved into their single call sites
  (`parse_feed_xml`, `fetch_feed_xml`); the file now carries a comment
  explaining why. This was *latent*, not an active crash: the only importer was
  `app/scripts/sentiment_ingest.py`, an operator CLI. It was one wiring change
  away from being live -- the module docstring explicitly anticipated being
  "wired into the scheduler", which would have made the container fail at boot
  with `ModuleNotFoundError` for a package the image never installs.
  `tests/test_news_fetch.py` (10) and `tests/test_sentiment_ingest.py` (6) still
  pass, so the refactor is behaviorally inert.
- **Negative control:** a hygiene test that has never failed proves nothing, so
  `import torch` was temporarily injected into `app/services/screener.py` and
  the suite confirmed the guard fires with
  `app/services/screener.py:1 imports 'torch' at module level`, then the
  injection was reverted (confirmed clean via `git status`).
- **M2 -- stale artifact removed.** `git rm openapi.json` (repo root, 8,214
  bytes, last touched in `a0de804`). It postdated Stages A-D/L2, listed 9 paths
  against the live app's 14, and still documented the pre-Stage-W percent-scale
  `weight`, so it was actively misleading. The live schema is served by FastAPI
  on any running instance, so the README now says exactly that instead. Nothing
  in the build or the tracked source referenced the file (only this log did, and
  the note above now points forward to Stage M).
- **M3 -- `docs/known_issues.md`.** Two accepted-limitation entries, each
  written against verified code rather than assumption: (1) no auth -- confirmed
  by `deps.py` exposing only `get_db`, `list_portfolios` having no owner filter
  (`dao/portfolios.py:49`), the `get_or_create_user` docstring
  (`dao/portfolios.py:7`), routers registered with no auth dependency
  (`main.py:46`), and no CORS middleware anywhere; (2) the runtime/ingest split
  being convention-only. Entry 1 also records what *is* enforced (the Stage L4
  resource bounds) and is explicit that bounding is not authorization, and
  notes that CORS is a browser control that does nothing to stop a direct
  client. Entry 2 records the three blind spots the AST scan deliberately
  leaves: imports nested in a top-level `if TYPE_CHECKING:` / `try:`, a
  name-literal banned set, and name-based detection. A `## Open items` section
  is present and intentionally empty for post-freeze findings.
- **Also updated:** `AGENTS.md` dependency section replaced its unfilled `:L`
  placeholders with a table of the five verified lazy-import sites, and now
  points at both the new test and `docs/known_issues.md`; README `docs/`
  layout line now mentions the architecture diagram, known issues, and usage log.
- **Test evidence:** backend suite `257 -> 261 passed` (0 failures, 0 skipped)
  via `--junitxml`; the 4 new tests are pure-`ast` and need no ingest packages,
  so they run on a runtime-only venv.
- **Files changed:** `backend/tests/test_import_hygiene.py` (new),
  `backend/app/services/news_fetch.py`, `openapi.json` (deleted),
  `docs/known_issues.md` (new), `README.md`, `AGENTS.md`,
  `docs/ai_usage_log.md`.
## Stage S1 -- Simulator trajectory chart + upside/downside fix

**Goal.** Replace the "Final value distribution" histogram on the Simulator tab
with an interactive worst/median/best trajectory chart, and fix the
`Upside / downside` insight card that rendered blank.

**Diagnosis (the blank was a real backend bug, not a display bug).** The card
already had a null branch, and the API already returned the field, so the first
step was to reproduce rather than assume. Running the real service against
`simulator.db` with the UI's own defaults ($10,000 initial, $200/mo, 10 years)
gave `total_contributed = 46,000` against `p10 = 50,562`. The old formula
`(p90 - contributed) / (contributed - p10)` therefore had a **negative**
denominator and the guard at `monte_carlo.py` returned `null`.

The root cause is that the old definition is undefined in the *common* case
rather than the degenerate one: over any horizon long enough for drift to
matter, even the 10th-percentile path finishes above the book value. It was
designed to fail only when an outcome was risk-free, but in practice it failed
for most realistic long-horizon runs.

- **S1a - metric redefined.** `upside_downside_ratio` is now the Sortino-family
  ratio on monthly simple returns with a zero threshold: mean of positive months
  divided by the root-mean-square of negative months. It only needs one losing
  month to exist. Steps opening on zero (a zero initial balance) have no defined
  return and are counted as 0 rather than NaN, matching the existing drawdown
  convention. Null now means "no month was negative", not "the denominator went
  negative". The real 10-year run above returns **1.0978** (and 1.0955 on a
  different seed) instead of null. The response key is unchanged.
- **S1b - cache invalidation bug found while verifying.** The first post-change
  run still returned `null` because `run_portfolio_simulation` returned a
  *cached* run whose stored `stats_json` predated the change; the cache key
  covers params and a `data_fingerprint` of the price data, but nothing about
  the stats schema. Shipping the formula change alone would have left every
  previously cached run replaying the old `null`, making the fix look broken.
  Added `STATS_VERSION` (currently 2) to `app/services/simulation.py`, folded
  into the cache key alongside the existing fingerprint, following the same
  rationale already documented there for price changes.
- **S1c - tests.** Replaced the three old ratio tests with six covering the
  exact value, the p10-above-contributed regression, an all-losing path
  (defined `0.0`, not null or inf), an all-gaining path (null), a zero opening
  balance (no NaN), and a single-column matrix (null). Two of my first drafts
  failed for the right reason: one asserted `None` for a path set whose every
  step return was positive (so null was correct), and one had the mean taken
  over 2 returns instead of 6. Both were test-authoring errors, not code bugs.
  One old test was also misnamed `..._is_none_when_no_downside` while asserting
  the opposite; it is now `..._none_when_no_losses` and asserts what it says.
- **S1d - frontend.** The "Final value distribution" `BarChart` is replaced by a
  "Value trajectory" `ComposedChart` plotting the p10 / p50 / p90 paths over a
  shared crosshair tooltip that reads all four values at once. The dead
  histogram code is removed (`Bar`, `BarChart`, `HistogramTooltip`,
  `histogramData`, `histogramBucketFor`); the backend still returns
  `stats.histogram`, which is left in place for the API contract and documented
  as such.
- **S1e - design decisions on the new chart.** Three points worth recording,
  since each was a deliberate choice rather than a default:
  - *Monochrome encoding.* The palette is black/white/grey, so the three
    percentile lines are distinguished by opacity and width (p90 at 0.3, p10 at
    0.6, p50 at 2px solid) rather than by hue. A legend spells out the mapping
    instead of relying on colour.
  - *Contributed line reads `result.params`, not live form state.* This was
    caught by the verification pass, not by inspection: the verification run
    reported `monthly_contribution = 300` while the UI's contribution slider
    sits at $200, because a loaded portfolio carries its own contribution. Had
    the chart used the live slider value it would have silently drawn a wrong
    book-value line for every existing portfolio. It is also applied at steps
    1..horizon and never at step 0, matching the engine.
  - *Kept as a plain derived `const`, not `useMemo`.* The neighbouring
    `chartData` / `crisisChart` are plain consts recomputed each render, so
    memoising `trajectoryData` on `[chartData, result]` would never hit its cache
    (`chartData` has a fresh identity every render) and would only imply a
    performance win that does not exist. Matching the surrounding convention was
    the honest choice.
- **S1f - ratio card copy.** The null branch now renders `n/a` instead of an
  em dash, and the card carries a `title` explaining the definition (mean of
  positive months over RMS of negative months) and what null means, so the
  previously silent "blank card" cannot recur unreadably. The `title` was wired
  through the existing `insightCards` renderer rather than special-cased.
- **Verification.** Beyond the 264-test suite, the real HTTP path was exercised
  through `TestClient` against a copy of `simulator.db` with the UI defaults,
  asserting the whole response the frontend consumes: `stats_version = 2`,
  `upside_downside_ratio = 1.0988` (a float, not null), percentile levels
  `[10, 50, 90]` with 121-point paths, and `params.initial_balance` /
  `params.monthly_contribution` present for the chart's book-value line. A
  second identical POST was asserted to return `cached = True` **and** the same
  ratio, which is the direct regression test for the S1b cache bug. Frontend
  `oxlint` and `vite build` are clean.
- **Known trade-off, flagged not hidden:** the page already had a "Growth fan
  chart - 10th-90th percentile" panel directly below this one, plotting the same
  p10/p50/p90 data as a filled band. Two identical hero charts would be a
  regression in its own right, so the new panel was kept deliberately compact
  (h-48, thinner lines, no filled area) and titled "Value trajectory" to read
  as a summary against the book-value line rather than a second feature chart.
  Consolidating the two into a single panel is the obvious follow-up and is
  left for the user to decide.
- **Test evidence:** backend suite `261 -> 264 passed` (0 failures, 0 skipped).
  Frontend `oxlint` clean and `vite build` clean.
- **Files changed:** `backend/app/simulation/monte_carlo.py`,
  `backend/app/services/simulation.py`, `backend/tests/test_distribution_stats.py`,
  `docs/data_methodology.md`, `frontend/src/pages/Simulator.jsx`,
  `docs/ai_usage_log.md`.
## Stage T1 -- real-world utility: inflation & capital gains tax

**Goal.** Two toggles on the Simulator ("Adjust for 3% Inflation", "Apply
Capital Gains Tax"), two booleans on the simulate endpoint, deflation of the
projected paths, and a tax deduction from the final simulated profit.

**The spec contained one ambiguity that would have shipped a silent lie, so it
was resolved explicitly rather than by picking a reading.** "Discount the
projected paths by 3% annually" is unambiguous about the numerator and silent
about the denominator. Deflating only the paths leaves `total_contributed` in
nominal dollars, so `probability_of_profit` compares real assets against nominal
deposits. Measured on the seeded demo data, that mistake takes the probability
from 0.947 to **0.000** - it would have reported that every single path lost to
inflation, on a portfolio that comfortably beat it. The book value is therefore
deflated by the same factor, and a test pins the invariance that follows:
`(V - C) / f` has the same sign as `V - C`, so the profit probability is exactly
unchanged by the toggle. The same trap exists in the chart, where the
"total contributed" line is drawn client-side from params; it now applies the
same deflator, sourced from the run's own `stats.adjustments.inflation_rate`, so
a nominal line never sits under a real line and implies a loss.

- **T1a - tax rate is ambiguous; the user chose 15%.** "Standard long-term
  capital gains tax" has no single value. US long-term holdings are taxed at
  **0%** federally (the entire point of the one-year threshold), so a literal
  reading makes the toggle a no-op and looks broken. Raised with the user rather
  than guessed; 15% (US federal top marginal, also India's LTCG rate) was
  selected. The constant's docstring records the 0% caveat so a future reader
  does not "correct" it to zero.
- **T1b - tax timing.** Also raised rather than assumed. Applied to each path's
  final value only (a single liquidation at the end), not compounded along the
  path, so the chart ends with a visible drop representing the final bill. The
  alternative - taxing each year's realized gain - smooths that into a gradual
  drag and is the better model for a rebalancing investor; left as a follow-up.
- **T1c - engine.** New pure functions `inflation_deflator` and
  `apply_real_world_adjustments` in `app/simulation/monte_carlo.py` (no DB or
  network deps, matching the module's contract). Adjustments are applied to the
  path matrix *after* the bootstrap and before anything is derived from it, so
  the percentile bands, the summary, the stats and the chart cannot disagree
  about which basis is in force. They deliberately do not enter the resampling:
  deflating the returns would change the simulated distribution rather than the
  units it is reported in.
- **T1d - derived stats.** `compute_distribution_stats` gained an optional
  `total_contributed` override, defaulting to the nominal book value so no
  existing caller changed. Percentile trajectories are now recomputed from the
  adjusted paths rather than reused from the nominal run.
- **T1e - caching.** Both toggles were added to `canonical_params`, so flipping
  one yields a different `params_json` and a different cached run. This has a
  useful side effect: it makes every run cached before this feature unreachable
  by string mismatch, which is why `STATS_VERSION` was deliberately **not**
  bumped despite `stats` gaining an `adjustments` block. The reasoning is
  recorded at the constant so a future change does not "fix" it into a needless
  full-cache invalidation.
- **T1f - frontend.** Reused the existing `ToggleSwitch` rather than adding a
  second control; it gained an optional `icon` prop defaulting to `Sparkles`, so
  the AI-sentiment call site is unchanged. A "Basis" disclosure strip now
  appears above the insight cards when either toggle is on, naming the rates and
  the median tax, because an after-tax run otherwise looks like a mysteriously
  worse portfolio rather than the same one restated.
- **T1g - legacy tolerance.** The `adjustments` block is defaulted field by field
  in the UI, because runs cached before this feature have no such block.

**Tests 264 -> 282.** 18 new in `tests/test_real_world_adjustments.py`:
hand-computed deflator values, both-off exact no-op, non-mutation of the input
array, per-column deflation, the book-value deflation and the
probability-invariance regression guard, tax on the final column only, tax
suppressed on non-profitable paths, the no-sign-flip property, configurable
rate, out-of-range rate rejected, horizon/width mismatch rejected, both-toggles
ordering (deflate then tax), a hand-computed combined figure ($100 -> $300 over
2 years leaves $254.50), and three cache-key tests. Verified on the real HTTP
path across all four toggle combinations: probability of profit invariant at
0.947, inflated p50 exactly nominal/1.03^10, real book 34,228.32 = 46,000/1.03^10,
median tax $5,987 = 15% of the median profit, and four distinct run ids.

Two of my own test expectations were wrong on first run and were corrected after
checking the arithmetic: I used 1.03**2 for a `horizon_months=2` case (that is two
*months*, so 1.03**(2/12)), and hand-computed the combined figure as 270.06
against the correct 254.50. Both were test-authoring errors, not code bugs.

**Not visually reviewed.** The two switches, the basis strip, and the
end-of-chart tax drop have had no browser check.
## Stage U1 -- populate the Strategies page

**Goal.** Replace the "Strategy library coming soon" placeholder with a
responsive grid of three hardcoded strategy cards, each linking to the Simulator
with its ETF tickers and weights pre-filled.

- **U1a - the dataset constrained two of the three portfolios.** The local
  `tickers` table has only 10 tradeable ETFs: SPY, VOO, VTI, VXUS, BND, TLT,
  GLD, IWM, EEM, QQQ. The canonical Boglehead 3/6/10 maps exactly (VTI 54,
  VXUS 36, BND 10). The other two do not, and silently substituting would have
  meant simulating a different portfolio than the card is named after:
  - All-Weather's published 30/30/20/20 uses an intermediate-bond sleeve. There
    is no IEF or TIP, so BND stands in. Flagged on the card as an
    approximation rather than passed off as the real split.
  - Buffett's 90/10 is 90% S&P 500 plus 10% *short-term* Treasuries. There is no
    SGOV or BIL. BND is the only remaining bond proxy, and it carries ~6 years
    of duration against SGOV's ~0.1 years - a large difference in exactly the
    risk the 10% sleeve exists to remove. Measured from the local price data,
    BND returned **-13.33% in 2022**, the rate-rise year the sleeve was meant to
    protect against, and the simulated 90/10 consequently shows a -14.0% median
    max drawdown. The card states this in those terms so nobody reads the
    backtest as validating the strategy.
  Neither is fixable in a UI change: adding tickers means an ingest run and
  re-freezing `deploy.db`. Raised as documented approximations instead.
- **U1b - URL contract in one module.** The Strategies page builds the query
  and the Simulator parses it, so `frontend/src/strategyHoldings.js` owns the
  format, the strategy data, and a defensive parser - the same reasoning that
  put `holdingsToFractions` in `api.js`. Shape is
  `/simulator?holdings=VTI:54,VXUS:36,BND:10`, with weights as PERCENTS to match
  the form, which edits percents and converts at submit. `:` and `,` are legal
  in a query component, so the readable form decodes unchanged; verified both
  raw and percent-encoded round-trip.
- **U1c - fixed a latent pre-fill bug on the way through.** The existing
  `?ticker=SPY` support was a lazy `useState` initializer, which only runs on
  mount. Changing the query within the same route - clicking a second strategy
  card, or browser back - left the previous holdings on screen while the URL
  claimed otherwise. Now the initializer handles mount and a render-time
  adjustment keyed on `search` handles in-place change. Done during render
  rather than in an effect because oxlint's `react/set-state-in-effect` is
  right that a synchronous setState in an effect is a cascading render; React's
  documented pattern for state tracking a changing input is to adjust during
  render, and nothing else on the page writes `search`, so it cannot clobber
  in-progress edits.
- **U1d - parser rejects rather than half-applies.** Malformed pairs are
  dropped, and if nothing in `holdings` parses the whole value is refused so a
  hand-edited link degrades to the default SPY portfolio instead of a
  one-symbol form the API would reject. `?portfolio=ID` deliberately returns
  null so the deep-link owns the form rather than racing it.

**Verification.** Round-tripped every strategy through the real parser: all
three sum to exactly 100, all symbols exist in the dataset, and
`strategyHref` -> `queryToHoldings` is identity. Then created and simulated all
three through the API at 10k/200mo/10y, confirming they run end-to-end and the
stored fractions sum to exactly 1.0: Boglehead p50 67,159 (maxDD -16.0%),
All-Weather p50 54,727 (**maxDD -9.0%**, the lowest of the three, which is the
risk-parity shape behaving as advertised), Buffett p50 83,484 (maxDD -14.0%,
inflated by the BND substitution above). oxlint and vite build clean. Backend
untouched: 282 passed.

**Not visually reviewed.** The three-card grid at each breakpoint, and the
pre-fill landing in the Simulator form, have had no browser check.

**Known gap, pre-existing and not introduced here.** The Simulator's holdings
form has no running total-weight indicator, so a user who edits one pre-filled
weight off 100 gets a 400 from the API's weight-sum check with no on-screen
warning. The Portfolios page does have such an indicator. Worth adding.
## Stage V1 -- wire news sentiment to the Simulator

**Goal.** Add an "Apply FinBERT Sentiment" toggle to the Simulator whose effect
on the Monte Carlo volatility is visible to the user as a small badge.

**Mostly already built, so the first task was to find out what was missing.**
The request describes a pipeline that Phase 5/6 had already delivered, so before
writing anything I traced it end to end:

| Requirement | State on arrival |
|---|---|
| Toggle in the Simulator controls | present ("AI Sentiment Adjustment") |
| Score fetched from `news_sentiment` | present (`sentiment_signal.portfolio_sentiment_score`) |
| Negative sentiment widens volatility | present (`volatility_multiplier_from_sentiment`) |
| **Badge showing the score** | **showed the multiplier only** |

Confirmed live against the real DB rather than by reading the code alone. A
120-month run of the first portfolio: score **-0.094121** -> multiplier
**1.009412**, matching the documented piecewise map (`1 + 0.10 * -score` for
negative) to within 1e-6, with the percentile path differing from the
unadjusted run and the cache correctly splitting into a distinct `run_id`. So
the backend needed nothing; rebuilding it would have been the risk, not the
fix.

- **V1a - the badge now shows the score, not just what it did to volatility.**
  The old chip read `sentiment x1.01`, which does not answer the only question
  a user actually has after toggling it: which way did sentiment lean. It now
  reads `sentiment -0.09 · vol ×1.01`, signed, because the sign is the entire
  content of the number - a bare `0.09` is ambiguous about direction.

  First attempt keyed the "no data" branch off the response's own `applied`
  flag, which is `use_sentiment AND multiplier != 1.0`. That is wrong for a
  genuinely neutral score: score `0.0` gives multiplier `1.0`, so a real,
  valid input would have been reported as "no recent news". Re-keyed both
  branches on the score being present, which is what the distinction actually
  means. `neutral -> sentiment +0.00 · vol ×1.00` now renders correctly.

- **V1b - a toggle that silently does nothing reads as broken.** When the
  toggle is on but no scored headline falls inside the 30-day lookback, the
  backend returns a null score and the run is unadjusted. Previously that was
  indistinguishable from forgetting to toggle. Now the badge reads
  `sentiment n/a · no recent news`, so the run is honestly labelled as
  unadjusted rather than implying an adjustment happened.

- **V1c - deliberate deviation from the wording of the request.** The prompt
  says to fetch "the **latest** Aggregate Sentiment score". The shipped
  implementation uses a 30-day lookback, weighted by holding weight, mixing
  each holding's sector headlines with market-wide geopolitical ones. I did
  **not** change this to the most recent headline. `docs/sentiment_validation.md`
  measured the sentiment->forward-volatility relationship at p = 0.12-0.49
  across SPY/QQQ - i.e. weak and mostly not significant - which is precisely
  why the feature is built to act lightly (0.10 negative / 0.05 positive
  sensitivity, clipped to ±10%) over an averaged window. A single latest
  headline is one document's opinion; feeding it into a 10-year distribution
  would manufacture a confident-looking adjustment out of noise, and it would
  contradict the validation that motivated the small sensitivities. The
  request's own parenthetical - "negative sentiment *slightly* increases
  volatility" - asks for exactly the mild, aggregate effect already in place.
  Flagging the deviation rather than silently following the literal wording.

**Verification.** Captured three real API payloads - toggle off, toggle on with
news, toggle on with `news_sentiment` emptied - and evaluated the two badge
conditions against them: 0 badges, 1 badge, and 1 "no recent news" badge
respectively, plus the neutral-score case. Worth noting the first fixture I
built flattened the payload to a top-level `use_sentiment` and reported a false
failure; the component reads `result.params.use_sentiment` and was correct. The
fixture was wrong, and the harness caught it rather than the reverse.

Backend untouched and unchanged: 282 passed, 0 failures (the two numpy
divide-by-zero warnings are the intentional divide-by-zero test). oxlint and
vite build clean. No frontend test runner exists in this project, so the badge
logic was checked with node against captured payloads rather than a unit test;
adding a runner for one formatter is not a trade worth making here.

**Not visually reviewed.** The badge's appearance next to the horizon label is
unconfirmed in a browser.
## Stage W1 -- pre-user-study database cleanup

**Goal.** Empty the Portfolios list so the user study starts from a clean slate,
leaving the schema intact.

- **W1a - "the test portfolios" was 32, not 2.** The request named "Smoke 10y"
  and "Phase6 check", but the table held 32 rows: 2x Smoke 10y, 1x Phase6
  check, and **29x "My Portfolio"** - the API's default name, one holding, $200/mo,
  which is what repeated curl/smoke checks leave behind. Wiping only the two
  named ones would have left 29 identical rows in front of study participants,
  so the default scope is all portfolios, with `--name` available for a
  surgical delete.

- **W1b - the deployed database was dirty too.** `simulator.db` had 32
  portfolios, but `deploy.db` - the frozen snapshot the Docker image ships -
  had 24 more. A study run against the container would never have seen the
  local cleanup at all. Both were cleaned. Worth remembering that
  `prepare_deploy_db.py` copies simulator.db -> deploy.db, so if a study DB is
  ever rebuilt from a clean source it will be clean, but an existing deploy.db
  has to be cleaned separately.

- **W1c - reused the app's own delete path instead of writing DELETE
  statements.** `simulation_runs` references `portfolios(id)` with **no ON
  DELETE CASCADE**, so deleting a portfolio with child rows fails outright
  under FK enforcement, and the correct order (simulation_results ->
  simulation_runs -> portfolio_holdings -> portfolios) lives in
  `app.dao.portfolios.delete_portfolio`. Hand-rolling the SQL would create a
  second copy of that ordering to keep in sync. The script opens its own
  connection with `PRAGMA foreign_keys = ON` to match `database.get_connection`;
  without it the dependency order is never actually checked by the FK engine,
  so a bug in it would pass silently.

- **W1d - guards, because this deletes data.** Dry run is the default and
  `--apply` is required. A timestamped backup is taken first, WAL-checkpointed
  so committed rows still sitting in `simulator.db-wal` end up in the copy - the
  dev database runs in WAL mode, and copying the main file alone would produce
  a backup that silently restores stale data. The whole delete is one
  transaction, and the script compares every table's CREATE statement before
  and after, rolling back and exiting non-zero if the schema moved. `--name`
  is escaped for LIKE wildcards, so `--name "%"` matches nothing rather than
  everything.

- **W1e - the backup filename had to be designed.** First version wrote
  `simulator.db.bak-<stamp>`, which does **not** match the `*.db` rule in
  .gitignore - the backup showed up as an untracked 8 MB file, one `git add -A`
  from being committed. Backups are now `<stem>.bak-<stamp>.db` so the existing
  rule covers them with no new pattern to forget.

**Result.** simulator.db and deploy.db both at 0 portfolios; cascade removed 37
holdings / 37 runs / 111 results and 27 / 23 / 69 respectively. Untouched, as
the study needs them: prices (106,251 rows), tickers (13), users (1),
news_sentiment (594). Schema byte-identical before and after. Verified through
the API rather than by trusting the SQL: `GET /portfolios` returns `[]`, a
create returns `id=1` (counter reset), and that portfolio deletes cleanly with
204. Backups retained as `simulator.bak-20260926-182435.db` and
`deploy.bak-20260926-182436.db`. 282 passed, 0 failures.

## Why the ETF screener lists ^DJI, ^GSPC and ^IXIC

Reported as a question, and the data is correct - the *display* was not.
`^DJI` (Dow Jones Industrial Average), `^GSPC` (S&P 500) and `^IXIC` (NASDAQ
Composite) are **market indices, not ETFs**. The `^` is Yahoo Finance's
convention for index symbols, documented in `app/ticker_catalog.py`: "yfinance
tickers (indices use the caret prefix, e.g. ^GSPC)". They are in the catalog
deliberately, with `sector = "Index - ..."`, and they are load-bearing:

- `app/services/news_sources.py` keys the geopolitical/macro Google News
  searches off those three symbols, which is where the market-wide sentiment
  rows that feed the Simulator's FinBERT adjustment come from.
- Their price history (8,741 / 24,797 / 14,023 rows) backs the benchmark
  comparisons.

`/screener` returns all 13 stored tickers by design -
`test_screener_returns_stored_tickers_only` pins that. So the backend is
correct and the bug was purely presentational: a page titled "ETF Screener" was
listing three things you cannot buy.

Fixed in the UI rather than the API, since other consumers may legitimately
want the indices. Keyed on the catalog's own `sector` classification
("Index - ...") instead of the `^` prefix, so the frontend follows the data's
stated asset type rather than encoding Yahoo's ticker convention - a future
non-Yahoo index source would classify itself in `sector` and be filtered
automatically. The screener drops from 13 rows to the 10 real ETFs; the "10
tracked" chip counts the filtered set, not the raw response, so the header
number cannot disagree with the table. Nothing was deleted. oxlint and vite
build clean; 282 backend tests unaffected.

### W2 - removed the redundant page subheadings

Reported as unwanted: "people know what an ETF screener is", and the nav
already names every page, so the `<h1>` + one-sentence description on each page
was restating the tab the user had just clicked. Removed from ETFs, News,
Portfolios, Simulator and Investing Strategies, leaving each page to open
straight onto its content.

Kept deliberately:

- `Home.jsx`'s `<h1>` is `sr-only` - invisible, and screen readers need exactly
  one top-level heading per page for orientation.
- `NotFound.jsx`'s `<h1>` *is* the content ("404 - Page not found"), not a label
  for content that follows.
- In-content prose: the "No portfolios yet" and "No portfolio yet" empty states,
  the legacy-run notice, and the strategy caveats. These describe an actual
  state or a data limitation, which is a different thing from labelling the
  page.

One real bug fixed alongside: the header chip counted `rows.length` (13) while
the table rendered 10, so "13 tracked" sat directly above ten rows. The filter
had introduced that inconsistency; the chip now counts `etfRows`.

Deleting the subheadings left their wrappers behind, which reserved a blank
1rem slot: the parent is `space-y-4`, and that margin is applied to every child
including one that renders nothing. Two pages were affected.

- `FinancialNews.jsx` always rendered its header row, so the row was empty
  while loading or on error and the filter bar below was pushed down. The
  "N headlines / Nd window" chip is now the middle child of the existing filter
  row (category tabs | chip | day options) instead of a row of its own, which
  removes the gap rather than just hiding it.
- `Portfolios.jsx` had the same shape, gated on `!editsForm`: opening the form
  emptied the row and left a gap above it. The whole row is now inside the
  condition, so it is absent rather than present-and-blank.

The Etfs chip row was already conditional, so it never reserved an empty slot
and was left as a single right-aligned row. Simulator and Investing Strategies
had no wrapper left over - the removed `<div>`'s only child - so their content
was already flush to the top.

### W3 - realized monthly returns now respect the horizon filter

Reported as a flaw: the "Realized monthly returns" heatmap ignored the year
entered in Controls. `GET /portfolios/{id}/monthly-returns` returns the entire
price history, and the client built a row per year from all of it, so the
heatmap grew every year the snapshot aged - 16 stacked rows for a 2011-start
holding, regardless of what the user set. The endpoint takes no parameters, so
nothing constrained it.

`horizonYears` (Investment horizon, 1-50, default 10) is now applied on the
client: the heatmap shows the trailing `horizonYears` calendar years. Filtering
client-side rather than adding a query parameter keeps the API contract stable
and means dragging the slider updates the heatmap with no refetch - the fetch
effect only depends on `portfolioId` and `phase`, so it does not re-run.

The window is anchored on the newest year **present in the data**, not on
today. The snapshot is frozen (it ends 2026-09), so anchoring to the current
date would render a column of empty cells whenever the data lags. Anchoring on
the data's own maximum guarantees at least one populated row and never pads
with blanks. When the horizon exceeds the available history it clamps to what
exists rather than inventing rows.

Verified against the real endpoint for a 60/30/10 VTI/VXUS/BND holding: 188
months spanning 2011-2026. Horizon 1 -> 1 row (2026), 2 -> 2, 3 -> 3, 5 -> 5,
10 -> 10 (2017-2026), and 20/50 -> all 16. Null and empty payloads yield no rows
and no crash. The applied window is now printed in the panel title ("2017-2026
· 10 yr") so the limit is visible rather than silently truncating history. The
incomplete current year keeps its empty trailing months, which is honest - the
months have not happened yet. oxlint and vite build clean.
