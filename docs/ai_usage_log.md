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