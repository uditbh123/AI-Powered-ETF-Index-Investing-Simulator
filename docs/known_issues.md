# Known Issues

Accepted limitations — things that are **known, understood, and deliberately
shipped as they are**. They are not open bugs and should not be "fixed"
opportunistically; each one records the reasoning, what still bounds it, and
what would have to change to close it.

Anything found after the current freeze goes under
[## Open items](#open-items) at the bottom.

---

## 1. No authentication or authorization

**Status:** accepted limitation. Single-user by design.

**What it is.** There is no authentication, no authorization, and no user
scoping anywhere in the API. Every portfolio route is open to any client that
can reach the port.

**Evidence.**

| Fact | Where |
|---|---|
| The only shared FastAPI dependency is `get_db`; there is no auth dependency to hang off | `backend/app/deps.py` |
| `get_or_create_user` — *"MVP has no auth; a single default user is auto-created on demand."* | `backend/app/dao/portfolios.py:7` |
| `list_portfolios` selects every portfolio with no owner filter | `backend/app/dao/portfolios.py:49` |
| Routers are registered with no auth dependency | `backend/app/main.py:46` |
| No CORS middleware; `add_middleware` / `CORSMiddleware` appear nowhere | `backend/app/main.py` |
| `users` holds one hard-coded row (`Demo User` from the seeder, or `default` on demand) | `backend/app/scripts/seed_demo.py`, `app/dao/portfolios.py` |

The `*_api_key` settings in `app/config.py` are third-party service keys
(`market_data_api_key`, `news_api_key`), not user credentials.

**Impact.** Anyone who can reach `:8000` can read every portfolio, create new
ones, and `PATCH` / `DELETE` any existing one by id. Market data and
statistics are read-only and derived from the bundled snapshot.

**What is still enforced — bounding, not authorization.** The Stage L4 audit
made every input expensive-but-finite rather than open, and that still holds:
`MAX_PATH_STEPS`, `MAX_BLOCK_MONTHS`, `MAX_HOLDINGS`, `MAX_HOLDING_WEIGHT`,
`MAX_SYMBOL_LENGTH`, `MAX_INITIAL_BALANCE`, `MAX_MONTHLY_CONTRIBUTION`, a SQL-level
news row limit, and the fraction weight-sum rule. None of these decide *who* may
act — they decide *how much* they may ask for.

**Why it is acceptable here.** This is a single-user educational simulator. The
only user-visible data is their own portfolio configuration, and the same
process serves the SPA in production, so the browser origin is same-origin. A
cross-origin web page cannot *read* API responses without CORS headers (none are
sent), but CORS is a browser control only — it does nothing to stop a direct
non-browser client.

**What would close it.** A real user model plus an auth dependency applied at
the router layer, and an owner column on `portfolios` so reads are filtered. That
is a product decision, not a bug fix, and is out of scope until multi-user is
actually wanted.

---

## 2. The runtime/ingest import split is a convention, not a build constraint

**Status:** accepted limitation, now regression-tested.

**What it is.** The deployed image installs `backend/requirements.txt` only
(FastAPI, uvicorn, pydantic, numpy, pandas). Six further packages —
`yfinance`, `APScheduler`, `feedparser`, `scipy`, `torch`, `transformers` —
live in `backend/requirements-ingest.txt` and are absent from the image. The
only thing keeping them off the boot path is that the modules that need them
import them **inside the function that uses them**.

Nothing structural stops that from regressing. A single top-level
`import torch` in a module the app imports would crash the container at import
time with `ModuleNotFoundError` — in production only, because the dev venv has
all three requirement files installed and the bug is invisible until deploy.

**How it is enforced now.** `backend/tests/test_import_hygiene.py` parses every
`.py` under `backend/app/` (excluding `app/scripts/` and `__pycache__`) and
fails on any module-level import of a package from
`{yfinance, torch, transformers, apscheduler, feedparser, sentencepiece,
huggingface_hub}`. Function-local imports are the intended pattern and are
allowed by construction.

**Residual blind spots — accepted, worth knowing:**

1. Only direct children of the AST module body are inspected. An import nested
   in a top-level `if TYPE_CHECKING:` or `try:`/`except ImportError` is not
   detected. Neither executes unconditionally so neither can crash the
   container, but a bare `try: import torch` would pass the test.
2. The banned set is a literal list of package names. A newly added
   ingest-only dependency is not caught until it is added to `INGEST_ONLY`.
3. The scan is name-based, so it cannot tell a genuinely new runtime dependency
   from an ingest one that is missing from the list.

**Caught during Stage M (regression, now fixed).** `app/services/news_fetch.py`
had a module-level `import feedparser` (and a module-level `import httpx`, which
is dev-only and equally absent from the image). This was latent rather than
active: the only importer was `app/scripts/sentiment_ingest.py`, an
operator-invoked CLI. Both imports were moved into their single call sites
(`parse_feed_xml` and `fetch_feed_xml`). The module's own docstring anticipated
being "wired into the scheduler", which would have converted the latent
violation into a boot-time crash in the container.

`app/scripts/` is excluded from the scan because those CLIs are never imported
by the app and may use the ingest stack directly. That exclusion is itself
tested: `scripts/validate_sentiment.py` imports `scipy` at module level, so the
exclusion is load-bearing rather than a blanket pass.

---

## 3. `prices.close` has no positive-value constraint at the storage layer

**Status:** accepted limitation, mitigated in code, regression-tested.

**What it is.** `prices.close` is `REAL NOT NULL` with no `CHECK (close > 0)`,
unlike `weight`, which does have one. A close of `0.0` is *finite*, so it passes
every `isfinite` filter on the ingest path and can be written to the table. Once
stored, `pct_change` turns it into `inf` (`x / 0`) and `diff` into `nan`
(`0 / 0`), and either value resamples straight into every simulated path:
`cumprod(1 + nan)` makes the growth factor `nan`, the `1 / growth` discount in
`_compound_annuity_due` produces `inf`, and the whole fan chart is NaN. The
request then died with numpy's own message ΓÇö `"autodetected range of [nan, nan]
is not finite"` ΓÇö as a 400 detail, which named neither the ticker nor the cause.

**How it is contained now ΓÇö three layers, outermost first.**

1. *Ingest* (`app/services/market_data.py::history_to_rows`): the filter is
   `np.isfinite(closes) & (closes > 0)`, so a non-positive close is no longer
   written to the table in the first place.
2. *Service* (`app/services/simulation.py::_portfolio_monthly_returns_core`): a
   stored close is passed through `closes.where(closes > 0)`, which masks a
   non-positive value as missing. The following `.resample("ME").last()` skips
   the NaN and takes the last *valid* close in that month, so a bad day degrades
   to an earlier price in the same month rather than dropping the month or
   failing the simulation. This layer exists specifically so an existing DB ΓÇö
   including the frozen `backend/deploy.db` snapshot, which was ingested before
   the ingest guard existed ΓÇö degrades instead of failing.
3. *Engine* (`app/simulation/monte_carlo.py::simulate_paths`): rejects any
   non-finite historical return with `ValueError("returns must all be finite")`,
   which the router surfaces as a 400 naming the actual problem. This is the
   backstop for write paths that bypass both layers above ΓÇö a migration, a
   script, or a hand-edited DB.

Separately, the engine now applies **two** floors, because they bound different
things.

1. A per-draw floor of `-0.99` on the **drawn** matrix. This was a real gap:
   `scale_returns_volatility` documents a `-0.99` floor but returns early when
   `multiplier == 1.0`, and `simulate_paths` only calls it when
   `volatility_multiplier != 1.0`, so the **default** path never floored
   anything. A `-1.0` draw (reachable from a delisted instrument's history)
   would otherwise imply a loss of more than the entire position.
2. A floor of `MIN_GROWTH = 1e-12` on the **cumulative growth factor** itself.
   The per-draw floor is necessary but not sufficient: it bounds each draw, not
   the product, and a long enough run of floored draws still underflows
   `cumprod` to exactly `0.0` (`0.01 ** 161 == 0.0` in float64). The discount
   `1 / growth` in `_compound_annuity_due` would then be `inf` and the product
   `growth * inf` would be `nan`. Flooring the product is what actually bounds
   the discount at `1e12` and keeps a path finite at any horizon.

Verified at the API's maximum horizon (600 months) with an all-wipeout history
and both zero and non-zero contributions: zero non-finite cells.

**Why the constraint is not simply added to the schema.** `CHECK (close > 0)`
is the correct fix, but SQLite cannot add a constraint to an existing table
without a full table rebuild ΓÇö `ensure_column` in `app/database.py` rebuilds
*columns* only. That is a migration with real blast radius against a frozen
deployment snapshot, so it is deliberately not bundled into a bug fix. It should
ride with the next schema-version bump.

**Residual blind spots ΓÇö accepted, worth knowing:**

1. A ticker whose *entire* price history is non-positive yields an empty frame
   and the honest 400 `"not enough overlapping monthly history to simulate"`,
   rather than a simulated result. That is the intended outcome, not a masking
   of one.
2. Negative returns below `-1.0` (impossible from real prices, possible from a
   hand-edited row) are rejected by `simulate_paths` only via the `-0.99` floor
   on the drawn matrix, not at the source. `returns_from_prices` already
   rejects non-positive prices outright.

---

## Open items

<!-- Intentionally empty. Add post-freeze findings here, most recent last. -->
