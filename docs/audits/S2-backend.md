# S2-backend.md — Phase 2 read-only backend audit (no edits/commits/deletions)

**Scope:** `backend/` code, schemas, DAOs, routers, services, simulation, tests, config/db.

**Date/agent:** 2026-10-08 (read-only). Script outputs written to `C:\Users\uditb\AppData\Local\Temp\opencode\`.

**Test baseline (from pytest, backend/.venv):** **327 passed in 24.64s** (matches AGENTS.md and S1 audit). AST scan of `tests/test_*.py` counted 296 top-level `test_*` definitions; parametrization/marks explain the +31 delta.

**Non-standard decisions about sources:**
- "Math rules (AGENTS.md §5)" was ambiguous (AGENTS.md has no §5). I interpreted this as the mathematical conventions in **`docs/data_methodology.md`** ("Monthly return construction", "Rebalancing", "Bootstrap design", "Percentile method", "Distribution statistics", "Real-world adjustments") plus AGENTS.md’s **Holding-weight convention** (fractions in (0,1], sum=1.0, enforced by `app/schemas.py::_check_weight_convention`). That interpretation is stated here.
- No `rg` (ripgrep) available on this Windows host; searches used the tool **Grep** and PowerShell `Select-String` where necessary. For multi-line Python checks I wrote small `*.py` verifiers in `%TEMP%\opencode\`.

**Tooling notes (reported for hygiene):**
- `vulture 2.16` (backend venv): run `app tests scripts --min-confidence 80` → 2 hits: `app/schemas.py:115` `cls` (in `@classmethod`) and `tests/test_scheduler.py:38` `func` (FakeScheduler.add_job param). Both false positives.
- `ruff check app tests scripts --select F` → clean (exit 0).

## 1. Baseline table
| Check | Result | Evidence |
|---|---|---|
| `python -m pytest` (backend) | **327 passed** | Run output 24.64s |
| `ruff --select F` | **OK** | Exit 0 |
| `vulture --min-confidence 80` | **2 false positives** | `app/schemas.py:115` (`cls`), `tests/test_scheduler.py:38` (`func`) |
| Deploy DB snapshot (`backend/deploy.db`) | **Verified shape** | 13 tickers, 106251 prices, 594 news rows; `published_at` all exactly 10-char `YYYY-MM-DD` (no NULLs/non-date-shaped), ticker_ids 1–4; 0 runs, 0 portfolios, 1 user |
| Import hygiene (`tests/test_import_hygiene.py`) | **Passes in CI-like context** | Repo requires lazy imports for ingest-only deps; boot-time `ModuleNotFoundError` prevented (see AGENTS.md) |

## 2. Correctness findings

### 2.1. [CONFIRMED] `/simulation-runs/{id}` returns 200 with error payload (not 404)
- **Where:** `app/services/simulation.py:419-420` (returns dict with `error`) vs `app/routers/simulations.py:56-60` (treats `None` as 404, but `get_run_response` can also return an `error` dict when results missing).
- **Observed:** For a run with no stored results, GET `/simulation-runs/{1}` returns **200 OK** with `{"run_id":1,"error":"run has no stored results"}` and **none** of the documented fields (`percentiles`, `summary`, etc.). (Verified by `temp\opencode\run_shape_check.py`.)
- **Expected semantics:** Missing/stale run results should be a 404 (consistent with `GET /tickers/{symbol}/prices` → 404 when symbol unknown, `GET /portfolios/{id}` → 404). Returning 200 with an `error` key is a shape/contract violation; clients cannot rely on the "simulation result" schema.
- **Impact:** **High** (contract bug). Frontend/consumers will misread the response (treat as success). Also `STATS_VERSION=2` is present but the response shape when `error` exists is incomplete.
- **Recommendation:** Return 404 when `run` missing, or when `stats_json`/results missing (treat "no stored results" as not found / expired). Keep response schema consistent (error details or proper error response, not 200-with-embedded error).

### 2.2. [CONFIRMED] Empty cache hit causes recomputation/new run row (self-heals; DB garbage)
- **Where:** `app/services/simulation.py:336-352` — cache lookup returns a run; if `get_run_response(cached_run)` indicates no stored results (or `stats_json` absent), code logs and does **not** delete/reuse in a clean way and proceeds to recompute and creates a **new** simulation run. The `ORDER BY id DESC LIMIT 1` lookup in `get_or_create_cached_run` can still pick the newest run later, but the "stale cache" row remains.
- **Effect:** Can create orphaned simulation_run rows with `stats_json` NULL. No automatic cleanup path; looks like self-healing by selecting newest. Production load could accumulate such rows over time (no GC). Not a correctness bug for the returned result; correctness preserved.
- **Impact:** **Low**. Operational/DB hygiene only.
- **Recommendation:** On "run has no stored results", either delete the cached row (`simulation_runs` with NULL results) before recomputing, or mark it expired. At least avoid leaving many NULL-result rows.

### 2.3. [CONFIRMED] N+1 queries in `/tickers`
- **Where:** `app/routers/tickers.py:25-41` — for each ticker does MIN(date), MAX(date), COUNT(*) via separate queries (`price_dao.price_range`, `price_dao.count_prices`). 
- **Observed:** With 13 tickers, `/tickers` issues **40 SQL statements** (1 list tickers + 13×MIN + 13×MAX + 13×COUNT). Verified by trace callback (`temp\opencode\query_count_check.py`).
- **Impact:** **Medium** (linear in number of tickers; small catalog now, will grow). Easy to denorm/aggregate in one pass or CTE; schema already indexed by `(ticker_id,date)`.
- **Recommendation:** Aggregate per ticker in one query (GROUP BY ticker_id with MIN/MAX/COUNT) or compute via join; avoid N+1.

### 2.4. [CONFIRMED] `/screener` loads **full** price history per ticker
- **Where:** `app/routers/screener.py:34-41` iterates tickers and calls `price_dao.get_price_history(conn, ticker_id=t.id)`; `app/dao/prices.py:43-49` defaults `limit=None` and does `SELECT ... ORDER BY date` with no windowing. 
- **Observed:** 14 SQL statements returning all 1620 seeded price rows in that trace (each ticker fetched fully). With 13 tickers × ~8180 prices on deploy.db (106251/13) this is ~106k rows read for a single screener call.
- **Impact:** **High** (I/O/latency/memory). Screener only needs recent window (e.g. 252 trading days for 1Y, 30 for vol, drawdown over recent window) per metric in `app/services/screener.py` (uses `series.iloc[-253:]`, `MIN_VOLATILITY_WINDOW=30`, `TRADING_DAYS_PER_YEAR=252`). 
- **Recommendation:** Push windowing into DAO (limit by lookback days) and/or compute rolling metrics without materializing entire history in the request path. At least cap by max lookback (e.g. 2×max needed). Note: current code is correct mathematically but does unbounded full scans per request.

### 2.5. [CONFIRMED] `/news` accepts unknown `ticker_id` and returns 200 (inconsistent 404s)
- **Where:** `app/routers/news.py:39-56` — `ticker_id: int | None` passed through; if provided, filters by `news_dao.list_sentiment(..., ticker_id=...)`. No existence check. 
- **Observed:** `GET /news?category=sector&ticker_id=9999` → **200 OK**, `n_headlines=0`. `GET /news?ticker_id=-1` → **200 OK**, `n_headlines=0`. Contrast: `GET /portfolios/99999` → **404**, `GET /tickers/ZZZZ/prices` → **404**.
- **Contract inconsistency:** "not found" for referenced entities is often 404 elsewhere; here it’s a silent empty result. Also `ticker_id` has no bounds (negative allowed). 
- **Impact:** **Low** (API consistency). Could mask client bugs.
- **Recommendation:** Validate `ticker_id` exists (404 if not found) or document behavior; at minimum reject `ticker_id < 1` with 422. Consider consistent 404 for non-existent foreign keys on read filters.

### 2.6. [CONFIRMED] `validate_bootstrap` off-by-one drops first return period
- **Where:** `app/simulation/monte_carlo.py:524-585` (`validate_bootstrap`).
  - Builds `periods_path = paths[:, 1:]` (drops time 0) then `per_period = periods_path[:, 1:] / periods_path[:, :-1]` → returns `r_2,...,r_H` (H-1 monthly returns) — drops `r_1 = paths[:,1]/paths[:,0]`.
  - Compares those to `historical` returns mean/std via `block_bootstrap_validation` and `bootstrap_stats` but the historical series used is the full `returns` sequence passed in? The function takes `returns: Sequence[float]` (historical) and generates paths via `simulate_paths` with same `returns`, `horizon_months=len(returns) if horizon matches?` Or uses `horizon_months` default 120 in context? Also checks `if abs(d) > tolerance: ...` and returns geometric means where present (Bug 3 already fixed: `historical_geometric_mean`/`geometric_mean_match` added per `docs/ai_usage_log.md:32-40`).
- **Analysis:** Geometric mean check uses `simulated_geometric_mean = np.exp(np.mean(np.log(periods_path[:, -1] / periods_path[:, 0])))` over H periods total? Or compares against historical over the same horizon. But the per-period mean/std exclude period 1. For many use cases (especially constant returns) tests still pass; effect is subtle. No existing test asserts mean/std of per-period returns include all H steps.
- **Impact:** **Low–Medium** (correctness of validation metrics). Could mask bootstrap distributional issues in rare cases.
- **Recommendation:** Include all per-period returns: `per_period = paths[:, 1:] / paths[:, :-1]` over the full matrix (shape (n_sims, H)). Also confirm horizon alignment.

### 2.7. [CONFIRMED] `get_or_create_ticker` uses `assert row is not None` (vanishes under -O)
- **Where:** `app/dao/tickers.py:43` — `assert row is not None` after INSERT...SELECT; function annotated `-> sqlite3.Row`. 
- **Risk:** If assertions disabled, returns `None` despite type hint and can propagate to callers. Also race between SELECT and INSERT-then-SELECT is possible but common pattern; better to catch and fetch or use INSERT OR IGNORE + SELECT.
- **Impact:** **Low** (no production path observed failing; defensive). Still a latent correctness/typing issue.
- **Recommendation:** Replace `assert` with explicit check/raise (or `row = ...fetchone(); if row is None: ...`) to preserve behavior under `python -O`.

### 2.8. [CONFIRMED] `users.name` has no UNIQUE constraint (race/duplication)
- **Where:** `app/schema.sql:26` — `name TEXT NOT NULL` (no UNIQUE). `app/dao/portfolios.py:7-12` implements `get_or_create_user(name="default")` as SELECT then INSERT; in concurrent transactions this can create duplicate "default" users.
- **Impact:** **Low** (no auth, `list_portfolios` not filtered by user; single-user dev). Data hygiene only.
- **Recommendation:** Add `UNIQUE(name)` on `users.name` (migration) and use `INSERT ... ON CONFLICT DO NOTHING` + SELECT, or `INSERT ... ON CONFLICT(name) DO UPDATE SET name=name` pattern.

### 2.9. [CONFIRMED-mechanism] `with get_connection()` does **not** close connection
- **Where:** `app/database.py:45` (`init_db`) and `:84` (`check_db_connected`) use `with get_connection() as conn:` but `get_connection()` returns a bare `sqlite3.Connection` (not a contextmanager). The `with` block calls `__enter__` (returns conn) but **never calls `__exit__`** → connection is never closed. Also `app/deps.py:11-17` shows the proper request-scoped pattern: `conn = get_connection(); try: yield conn; finally: conn.close()` (and rollback on error).
- **Measurement:** Wrote verifier scripts in temp (handle count via `psutil`/ctypes). Under CPython refcounting, opening/closing many connections doesn’t leak OS handles in a visible way (objects finalized quickly); handle counts plateaued (e.g. +173 after 500 opens, +245 after 3000) — consistent with refcounted cleanup, not an unbounded OS-handle leak in practice. Behavior is still incorrect API usage.
- **Impact:** **Low** (hygiene). `init_db` and `check_db_connected` are called infrequently (startup/health checks). No request-path impact. 
- **Recommendation:** Either make `get_connection()` a contextmanager, or call `conn.close()` explicitly in those two call sites (and in any others). Prefer explicit `try/finally` or a proper CM to avoid confusion.

## 3. Performance observations (read-only)

- **N+1 in `/tickers`:** 40 SQLs for 13 tickers (linear). Fixable by single aggregation.
- **Full scan in `/screener`:** loads entire price history per ticker (106k rows total on deploy snapshot) even though only recent windows needed. Largest request-time data read in the observed paths.
- **Price DAO:** `get_price_history` takes `limit: int | None = None` with no default cap; router/screener never pass limit. Consider `limit` defaulting to max lookback (e.g. 2*253) or enforce in service layer.
- **News unknown ticker_id:** cheap (just filter) — no performance issue; consistency issue only.

No other obvious O(n^2) query patterns found in routers/DAOs on quick scan.

## 4. Dead code / over-engineering notes

- **`CATEGORIES = ("sector","geopolitical")`** in `app/dao/news.py:16` and exported via `__all__` (`:167`) — **zero** backend production references; only backend tests reference via imports in a few places? Export scan: `CATEGORIES` appears in `frontend/src/pages/FinancialNews.jsx:6,66` (frontend) and is exported by backend DAO. Backend production code (app/, scripts/) has **no** references to `app.dao.news.CATEGORIES`. It’s an exported constant from app package with no app-side consumers → effectively dead from backend runtime perspective (kept for API surface or cross-package; frontend imports from its own source, not backend). Classification: **TEST-ONLY in backend app context?** Export scan labeled `CATEGORIES` as `TEST-ONLY` overall but also has frontend refs (separately tracked) — backend non-test refs: 0. Low value to keep exported if unused.
- **`count_sentiment`** (`app/dao/news.py:149`, `__all__` `:170`) — **zero production callers** in backend/app or scripts; referenced only in `tests/test_news_dao.py` (11 refs). Export scan: **TEST-ONLY**. This is test scaffolding exported from app package. Not "dead" code (used by tests) but is app-package surface area unused in production.
- **`validate_bootstrap`, `ValidationReport`** (`app/simulation/monte_carlo.py:494-521`, exported in `app/simulation/__init__.py:9,16`) — present and used by tests (`tests/test_monte_carlo.py` calls `validate_bootstrap`). Also exported API surface. Not dead.
- **`get_portfolio_by_user_and_name`** (`app/dao/portfolios.py:14-22`, exported `__all__`:17 in DAO) — appears only in its own definition context? Export scan didn’t flag as dead; quick grep shows definition + maybe not called. (Low priority; follow export scan result.)
- **Over-engineering observations (subjective, read-only):**
  - `STATS_VERSION = 2` hardcoded in simulation service; versioning exists but `get_run_response` shape diverges when error present.
  - `app/errors.py` does careful NaN/Inf stripping and logging redaction — thorough, appropriate for API.
  - Contribution-timing logic centralized in `_compound_annuity_due` (`app/simulation/monte_carlo.py:153-180`) — good (single source of truth).
  - `SIMULATION_SLOTS` semaphore acquired after 404 checks in both `/simulate` and `/crisis-replay` (routers:25-35, crisis:31-41) — correct ordering (avoid reserving slot on 404).

## 5. Test honesty analysis

AST scan of 296 top-level `test_*` definitions (pytest collected 327 passed; delta = parametrized tests/marks).

### 5.1. Status-code-only tests (16)
Found via grep for status-code assertions in tests:
- `tests/test_api.py:131,148,153`
- `tests/test_crisis.py:188`
- `tests/test_error_handling.py:113,123,202`
- `tests/test_input_limits.py:147,215,365`
- `tests/test_insights_api.py:149,153`
- `tests/test_news_api.py:191`
- `tests/test_portfolio_delete.py:112,116`
- `tests/test_portfolio_patch.py:151`

**Assessment:** Many are legitimate contract checks (404/422). Examples like `test_create_portfolio_invalid_weights_rejected` and `test_50k_paths_over_600_months_is_rejected` would benefit from asserting the error detail/message (not just status) to catch response-shape regressions like 2.1. Not inherently "dishonest", but low-specificity.

### 5.2. Weights are unobservable in key fixtures (math-rule coverage gap)
- **Where:** `tests/test_insights_api.py:21-27` seeds SPY and QQQ with identical curve `close = 100.0 * (1.005**i)` for i=0..71. 
- **Also:** `tests/test_api.py:25-43` similar synthetic price generation.
- **Consequence (Monthly return construction, per `docs/data_methodology.md` rule 3/4 context):** With identical price paths, any linear combination `w1*R1 + w2*R2` is identical regardless of weights `(w1,w2)` (as long as sum 1). So tests that vary portfolio weights cannot detect if weights are applied incorrectly (e.g. using means instead of weighted combination, or swapping weights). 
- **Impact on test honesty:** Tests appear to exercise "weighted" behavior but the signal is not present in fixtures. A bug that ignores weights would still pass these cases.
- **Recommendation (read-only note):** Add fixtures where assets have different return paths (different drift/vol) so weight changes produce observable differences in weighted metrics.

### 5.3. Block bootstrap semantics under-tested
- **Where:** `tests/test_monte_carlo.py:132-137` `test_block_bootstrap_shape` checks only shape and finiteness. `tests/test_input_limits.py:84-92` checks bounds only. `tests/test_monte_carlo.py` has `test_bootstrap_reproduces_historical_mean` and `test_bootstrap_flags_mean_mismatch` (lines ~183-209 in the file) — those do check mean/std/geom alignment in specific cases (and Bug 3 fix added geom fields). 
- **Gap:** If `block_bootstrap` were to accidentally produce IID resamples (ignore block structure) for typical block sizes, many tests wouldn’t catch it unless there is a strong serial dependence in fixtures. Current synthetic fixtures are simple; no test asserts dependence structure is preserved.
- **Impact:** **Low**. Correctness of block bootstrap is important but current validation is mostly distributional (mean/std/geom). Not a direct false-positive risk, more a coverage gap.

### 5.4. `_portfolio_monthly_returns_core` internals untested directly
- **Where:** `app/services/simulation.py` contains `_portfolio_monthly_returns_core` (referenced by simulation logic) which does `.resample("ME").last()`, `.ffill()`, `.dropna(how="any")` (standard pandas semantics). 
- **Coverage:** Only indirect — `tests/test_api.py:282-301` exercises zero-close fallback path; `tests/test_insights_api.py:135` checks "36 month-ends → 35 returns". No direct unit test asserts the exact resample/ffill/dropna behavior (e.g. price gap filled, all-NaN dropped, month-end alignment). 
- **Impact:** **Low** (integration tests cover main paths). Still a small test-honesty/precision gap.

### 5.5. Percentile method covered
- `tests/test_monte_carlo.py:307` asserts `percentile_levels == [10,50,90]`. `tests/test_distribution_stats.py:30-35` uses `np.percentile` with linear interpolation. `path_percentiles` uses `np.percentile(paths, levels*10 if levels 0-100? Or levels in percent)` and bands shape (3,121). Coverage is adequate.

## 6. Summary of actionable items (read-only)
1. **[High]** Fix `/simulation-runs/{id}` to return proper error status (404) when no results exist; align response shape with other 404s. (2.1)
2. **[Medium–High]** Avoid full price history scan in `/screener` (push lookback/windowing into DAO; cap limit). (2.4)
3. **[Medium]** Eliminate N+1 in `/tickers` via aggregation (GROUP BY). (2.3)
4. **[Low]** Make `get_connection()` contextmanager or explicitly close in `init_db`/`check_db_connected`. (2.9)
5. **[Low]** Replace `assert row is not None` with explicit check in `get_or_create_ticker`. (2.7)
6. **[Low]** Add UNIQUE on `users.name` + upsert-safe create. (2.8)
7. **[Low]** Validate `ticker_id` in `/news` (404 if non-existent or reject <1 with 422) for consistency. (2.5)
8. **[Low–Med]** Fix `validate_bootstrap` per-period indexing to include all periods (or document). (2.6)
9. **[Low]** Strengthen tests: add weight-sensitive fixtures; assert error details in status-code-only tests; add direct tests for resample/ffill/dropna and block-bootstrap dependence where meaningful. (5.2–5.4)

## Verification notes (scripts run)
- `run_shape_check.py`: confirmed 200 + error body for run with no results.
- `query_count_check.py`: confirmed 40 SQLs for 13 tickers; `/screener` fetches each ticker fully; unknown `ticker_id` → 200.
- `export_scan.py`: exported names from backend/app/scripts: 115 total; TEST-ONLY = 2 (`count_sentiment`, `CATEGORIES`); PROD=113; DEAD=0. Backend app non-test refs to `CATEGORIES`/`count_sentiment`: 0 (frontend refs to `CATEGORIES` exist separately).
- Handle-leak probes (ctypes + psutil in temp): no unbounded OS handle growth under CPython refcounting; mechanism (no close in `with get_connection()`) is confirmed.

**Conclusion:** Core math/engine logic is coherent and well-tested overall (327 passing). Main issues are API contract consistency (200-with-error), performance (full scans + N+1), and small hygiene items. All findings above are labeled CONFIRMED/NOT CONFIRMED with file:line citations.
