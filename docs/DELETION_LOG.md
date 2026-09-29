# Code Deletion Log

Record of every removal made by a dead-code/refactor pass, with the evidence that
justified it. Add a new section at the top for each session; do not edit older
sections.

---

## [2026-09-29] Dead code pass (frontend + backend)

Scope: static-analysis sweep of the whole repo. **No business logic was changed.**
Every deletion below was a name, import, local binding, or CSS/Tailwind token with
zero references anywhere in the repo (source, tests, scripts, and docs).

### Tools used

| Tool | Invocation | Result before |
|---|---|---|
| knip | `npx --yes knip --no-progress` (in `frontend/`) | 2 unused exports |
| ruff | `python -m ruff check backend/app backend/tests backend/scripts --select F` | 11 errors (9 F401, 2 F841) |
| vulture | `vulture backend/app backend/scripts --min-confidence 60/80` | route handlers only (60% is noise) |
| custom AST scan | repo-wide `ast` + word-boundary reference index | 2 dead definitions |

Note: a word-boundary index must **not** exclude dotted references (`dao.func()`),
or every DAO method reads as dead. The first version of this scan did exclude
them and produced 43 false positives.

### Unused Dependencies Removed

None. `package.json` and the three `requirements*.txt` sets are all fully
consumed. Removing anything here would break the documented runtime/ingest/dev
dependency split in `AGENTS.md`.

### Unused Files Deleted

None.

**Note on the "Smoke 10y mock data files"**: these do not exist. The Smoke 10y
rows are *rows in the SQLite DB*, created by curl/manual smoke runs — see
`docs/ai_usage_log.md` (32 rows, 2× "Smoke 10y"). They are data, not files, and
are handled by `backend/scripts/cleanup_portfolios.py` (a separate concern). No
file was deleted for this.

### Dead Definitions Removed (backend, 2)

Both were `__all__`-declared with **zero** real callers — the only other
occurrence of either name in the entire repo was its own entry in its own
`__all__` list.

- `backend/app/dao/simulations.py::list_runs` — 6-line DAO read, never called.
  No route, script, or test references it. Removed with its `__all__` entry.
- `backend/app/data/news_sources.py::all_sources` — `sector_sources() +
  macro_sources()`. `sentiment_ingest.py` imports the four *windowed*
  variants directly, so the non-windowed convenience wrapper had no consumer.
  Removed with its `__all__` entry.

### Unused Imports Removed (backend, 4)

- `backend/app/services/news_fetch.py:20` — `from urllib.parse import urlparse`
  (the module does its own ISO-date normalisation, not URL parsing).
- `backend/app/scripts/ingest.py:13` — `from app.config import settings`
- `backend/app/scripts/sentiment_ingest.py:19` — `from app.config import settings`
  (the only other `settings` hit is the word inside an `--limit` help string).
- `backend/app/services/market_data.py:17` — `from ..config import settings`

### Unused Local Bindings Removed (backend, 1)

- `backend/app/simulation/monte_carlo.py::validate_bootstrap` —
  `periods = np.arange(1, horizon_months + 1)`, assigned and never read. The
  adjacent `periods_path` is a different variable and is still used. This line
  predates the in-flight real-world-adjustments work; it was not part of it.

### Unused Exports Removed (frontend, 2)

- `frontend/src/api.js:31` — `export const API_BASE_URL = API_BASE`. Nothing
  imported it; every call site goes through `fetchJSON`, which closes over the
  module-local `API_BASE`. Removed the re-export, kept `API_BASE`.
- `frontend/src/strategyHoldings.js:86` — dropped the `export` keyword from
  `holdingsToQuery`. The function **is** live (`strategyHref` calls it on the
  next line); only the export was unused. Do not delete the function.

### Orphaned CSS / Design Tokens Removed (frontend, 8)

- `frontend/src/index.css` — `.select-native` removed from the shared
  `.input, .select, .select-native` rule. Zero uses repo-wide.
- `frontend/tailwind.config.js` — 7 tokens with zero generated-class usage
  (verified by substring grep *and* by confirming no `className={`…`}` builder
  could construct them dynamically):
  `base.deep`, `edge.strong`, `accent.dim`, `pos.dim`, `neg.dim`, `warn.dim`,
  `boxShadow.accent-glow`.
  Tokens **kept** because they are referenced: `ink.dim` (21), `base.elevated`
  (5), `text.11px` (16), `boxShadow.panel` (1), `borderRadius.none` (1).

### Write-Only React State Removed (frontend, 1)

- `frontend/src/pages/Portfolios.jsx` — `const dialogRef = useRef(null)` plus
  `ref={dialogRef}` on the delete-confirm dialog. React wrote the ref; nothing
  ever read it. (`deleteCancelRef` on the line above *is* read, for `.focus()`,
  and was kept.)

### Test-File Hygiene (5)

- `backend/tests/test_dao.py` — `import pytest`, `from app.database import get_connection`
- `backend/tests/test_database.py` — `import pytest`
- `backend/tests/test_simulation_cache.py` — `import pytest`
- `backend/tests/test_validate_sentiment.py` — `daily_returns` imported but
  never called; the test computes its returns inline via `pct_change`.
- `backend/tests/test_seed_demo.py` — dropped a redundant
  `user_id = portfolio_dao.get_or_create_user(db, DEMO_USER_NAME)`. `seed_demo()`
  is called two lines above and already creates that user (`seed_demo.py:175`),
  so the call and the binding were both dead. The two *other*
  `get_or_create_user` bindings in that file are used and were left alone.

### Deliberately NOT Removed (findings kept for a follow-up pass)

- **`formatCurrency` is duplicated** in `Simulator.jsx:45` and
  `Portfolios.jsx:16`, but they are not equivalent: the first uses
  `Intl.NumberFormat` currency style, the second `Number()`-coerces and prefixes
  `"$"`. Merging them would change rendered output, so this is a behaviour
  change, not a cleanup.
- **Skeleton loader triplicated** — the same 3-div pulse markup appears in
  `Etfs.jsx`, `FinancialNews.jsx`, and `Portfolios.jsx`. Worth a shared
  component, but it is a structural refactor across 3 pages.
- **`FanTooltip` / `CrisisFanTooltip`** in `Simulator.jsx` are near-identical
  (~25 lines, same file). Consolidating is low-risk but touches WIP.
- **Stale comment**: `frontend/src/strategyHoldings.js` says `Home.jsx` links
  `?ticker=SPY`; only `Etfs.jsx:206` does. Comment only, no code impact.

### Impact

- Files changed: 17 (11 backend, 6 frontend)
- Lines removed: 44 · lines rewritten: 4 · net **-40**
- Dead definitions: 2 · unused exports: 2 · unused imports: 4 · unused locals: 1
- Orphaned CSS/tokens: 8 · write-only refs: 1
- Runtime dependencies removed: 0
- Bundle-size change: none measurable (CSS tokens are not emitted when unused;
  JS removals were a re-export and an `export` keyword)

### Testing

- `python -m pytest` (from `backend/`) → **282 passed, 0 failed, 0 errors,
  0 skipped** (count read from `--junit-xml`; PowerShell was swallowing the
  terminal summary line, not a test problem). Matches the documented baseline.
- `python -m ruff check backend/app backend/tests backend/scripts --select F`
  → **All checks passed** (was 11 errors).
- `npx --yes knip` (in `frontend/`) → **0 findings** (was 2).
- `npm run lint` (oxlint) → clean, exit 0.
- `npm run build` → succeeded, exit 0, `built in 15.95s`.

### Not committed

The working tree also contains unrelated in-flight work
(real-world adjustments, the `strategyHoldings` feature, the cleanup script).
**These removals are not committed.** When committing, stage only the files
listed in this log — `backend/app/simulation/monte_carlo.py`,
`frontend/src/pages/Portfolios.jsx`, and
`frontend/src/strategyHoldings.js` are WIP files that now carry both this
cleanup and unrelated changes. Per `AGENTS.md`, never commit `tree.txt`,
`project-files.txt`, or `project-tree.txt`.
