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

## Open items

<!-- Intentionally empty. Add post-freeze findings here, most recent last. -->
