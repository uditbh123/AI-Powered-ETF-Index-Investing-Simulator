# S3-frontend.md — Phase 3 read-only frontend audit (no edits/commits/deletions)

**Role:** read-only auditor. Frontend design is **FROZEN**; this report describes
what the code does, it does not propose a redesign. No source was modified; no
commits made.

**Scope:** `frontend/src` (plus read-only cross-checks against
`backend/app/data/ticker_catalog.py`, `backend/app/simulation/monte_carlo.py`,
`backend/app/services/simulation.py`, `backend/app/scripts/seed_demo.py`, the
seed DBs, and `docs/ai_usage_log.md`). Tool outputs written to
`C:\Users\uditb\AppData\Local\Temp\opencode\`.

---

## 0. Baseline

| Item | Value |
|---|---|
| Branch | `main` |
| HEAD | `ea03de802e37a6c315308bd06e34f02d5f98b7ec` ("docs: add S2 backend audit") |
| git status | Dirty only with known noise: ` D tree.txt`, `?? project-files.txt`, `?? project-tree.txt` (AGENTS.md "Git hygiene"). No `frontend/` file dirty. |
| `cd frontend; npm run lint` (oxlint) | **exit 0, no diagnostics** |
| `cd frontend; npx --yes knip` | **knip 6.41.0, exit 0, no issues** (see §5) |
| Frontend vs S1 audit | **Unchanged.** `git diff --stat e342a5c..HEAD -- frontend` is **empty**; last commit touching `Simulator.jsx` is `7cd30ea` (pre-S1-audit HEAD `e342a5c`). S3 therefore *re-derives* S1's frontend findings from the same bytes. |

Every claim below carries `file:line`. The current Simulator page is 1,256 lines.

---

## 1. SIMULATOR CHARTS — histogram presence, trajectory duplication

**What was checked:** every chart the Simulator page renders *from code*, the
existence and rendering of the Stage J final-value histogram, and whether any
trajectory chart is rendered more than once.

**Chart library in play.** `Simulator.jsx` imports only recharts
`Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis,
YAxis` (`Simulator.jsx:3-12`). `ComposedChart` is the only plotting component
used; no `BarChart`/`Bar`/`LineChart`/`PieChart` is imported. `grep` for
`histogram|Histogram|BarChart|Bar\b` across `frontend/src` returns **2 hits, both
the lucide icon `BarChart3` in the ETF screener** (`Etfs.jsx:2`, `Etfs.jsx:140`)
— **0 hits in `Simulator.jsx`**.

**Charts rendered by the Simulator (in code):**

| # | Chart | Component + line | Series | Condition |
|---|---|---|---|---|
| 1 | **Value trajectory** | `<ComposedChart data={trajectoryData}>` `Simulator.jsx:864-951` (panel title `:836`) | p90 `:904`, p10 `:915`, p50 `:926`, contributed `:941` | inside `stats ?` branch (`:785`) |
| 2 | **Growth fan chart · 10th–90th percentile** | `<ComposedChart data={chartData}>` `Simulator.jsx:1011-1048` (panel title `:969`) | band Area `:1031`, median Line `:1040` | always when `result` |
| 3 | **Crisis replay** | `<ComposedChart data={crisisChart}>` `Simulator.jsx:1186-1242` | band Area `:1216`, simulated median `:1225`, real trajectory `:1233` | inside `crisisData &&` (`:1158`) |
| 4 | **Realized monthly returns** | HTML table, **not** a chart component `Simulator.jsx:1072-1109` | per-month return cells | inside `result` branch |

(For completeness, the only other recharts chart in the app is `Home.jsx`
`<AreaChart>` at `Home.jsx:360`, not on the Simulator page.)

### 1a. Stage J final-value histogram — present? rendered?

**Verdict: NOT present and NOT rendered (CONFIRMED as a fact).**

- `grep histogram frontend/src` → **0 matches**; `grep BarChart` → only the
  lucide screener icon. There is no histogram data builder, no `BarChart`, no
  `Bar` element anywhere in `frontend/src`.
- It *was* built. Stage J J2 added a `BarChart`, 20 bins, accent bars, custom
  tooltip and p50/contributed marker lines (`docs/ai_usage_log.md:304-308`), and
  verification explicitly confirmed "20-bin histogram with both marker lines"
  (`ai_usage_log.md:326`).
- It was *deliberately removed* by Stage S1d, which replaced the
  "Final value distribution" `BarChart` with the "Value trajectory"
  `ComposedChart` and deleted `Bar`, `BarChart`, `HistogramTooltip`,
  `histogramData`, `histogramBucketFor` (`docs/ai_usage_log.md:743-749`; commit
  `9b68415`, whose subject is "replace final-value histogram with a trajectory
  chart").
- The **backend still computes and persists** the histogram — 20 equal-width
  bins (`backend/app/simulation/monte_carlo.py:478-490`), rounded and stored on
  the run as `stats.histogram` (`backend/app/services/simulation.py:200-205`),
  shipped on every response. **No UI reads it** → it is an orphaned payload, not
  a regression.

So: not a Stage J regression in the frontend (removal was an intentional,
logged S1 decision), but the Stage J histogram feature no longer exists in the
shipped UI.

### 1b. A trajectory chart rendered twice? — YES

**Verdict: CONFIRMED — the p10/p50/p90 percentile trajectories are drawn in two
panels simultaneously.**

- Chart 1 and Chart 2 both read the **same source**: `result.percentiles` →
  `bandPath(10|50|90)` (`Simulator.jsx:404-413`). `trajectoryData` is literally
  `chartData.map(...)` plus the contributed column (`Simulator.jsx:523-532`).
- Chart 1 plots `high` (p90), `low` (p10) and `median` (p50)
  (`Simulator.jsx:904,915,926`); Chart 2 plots a filled band of the same
  `[low,high]` and the same `median` (`Simulator.jsx:1031,1040`). The identical
  three trajectories therefore appear in both panels in a single results view;
  Chart 1 additionally overlays the book-value line.
- This is **known and deliberate**, not accidental: S1e recorded "the already
  existing Growth fan chart … plotting the same p10/p50/p90 data as a filled
  band", kept the new panel deliberately compact, and left consolidation to the
  user ("Known trade-off, flagged not hidden", `docs/ai_usage_log.md:783-790`).
  Needs human eyes to decide; not re-reported here as a new defect.

---

## 2. SENTIMENT TOGGLE INSTANCES

**What was checked:** every sentiment on/off control in `frontend/src`.

**Count: exactly ONE sentiment toggle.**

| # | What | Where | Bound state |
|---|---|---|---|
| 1 | `ToggleSwitch` — "AI Sentiment Adjustment (Includes Geopolitical Risk)" / "Scales historical volatility by recent FinBERT news sentiment." | `frontend/src/pages/Simulator.jsx:709-714` | `checked={useSentiment}` `onChange={setUseSentiment}` |

Supporting facts:

- The toggle's state is declared once, `const [useSentiment, setUseSentiment] =
  useState(false)` (`Simulator.jsx:242`), and is sent to the server as
  `use_sentiment: useSentiment` (`Simulator.jsx:371`).
- `ToggleSwitch` is a component defined at `Simulator.jsx:175-212`
  (`role="switch"` at `:179`). It is instantiated **3 times** on the Simulator
  page: sentiment `:709`, inflation `:720`, capital-gains tax `:727`. Only the
  first is sentiment-bound.
- The two sentiment **chips are read-only badges, not toggles**:
  score + volatility multiplier `Simulator.jsx:983-989`, and "sentiment n/a ·
  no recent news" `Simulator.jsx:990-998`.
- `FinancialNews.jsx` contains the only other `sentiment` strings
  (`:116,128,176,178`) — static labels/scores on the News page, no toggle.
- No other `role="switch"` / checkbox bound to sentiment exists in
  `frontend/src`.

**Verdict: NOT CONFIRMED** (if the suspicion was a duplicate/extra sentiment
toggle — there is exactly one). Unchanged from S1 §6.

---

## 3. STRATEGY PRESETS vs THE 13-ETF CATALOG

**What was checked:** tickers + weights per preset card, diffed against the
13-entry catalog and against both seed/deploy DBs.

**Preset cards** — `frontend/src/strategyHoldings.js:29-83`, rendered by
`frontend/src/pages/InvestingStrategies.jsx:12-67`:

| Card | Tickers + weights (as authored) | Sum | Source lines | Caveat? |
|---|---|---|---|---|
| Boglehead Three-Fund | VTI 54 · VXUS 36 · BND 10 | 100% | `strategyHoldings.js:38-42` | no |
| Ray Dalio All-Weather | VTI 30 · TLT 30 · BND 20 · GLD 20 | 100% | `strategyHoldings.js:57-62` | yes (`:52-56`, BND proxy for IEF/TIP) |
| Warren Buffett 90/10 | VOO 90 · BND 10 | 100% | `strategyHoldings.js:78-81` | yes (`:72-77`, BND proxy for SGOV/BIL) |

Weights are percents (matching the Simulator form), converted to fractions at
submit time by `holdingsToFractions` (`frontend/src/api.js:40-45`); all three
cards sum to exactly 100 (`InvestingStrategies.jsx:13`).

**Full ETF catalog — 13 entries.** `backend/app/data/ticker_catalog.py:17-31`:

```
SPY  VOO  VTI  QQQ  IWM  VXUS  EEM  BND  TLT  GLD  ^GSPC  ^IXIC  ^DJI
```

**DB dump (both `backend/deploy.db` and `backend/simulator.db`, read-only):**
`tickers` = **13 rows each**, 106,251 price rows each. Price-row counts exactly
match S1 §7: BND 4894 · EEM 5897 · GLD 5493 · IWM 6618 · QQQ 6926 · SPY 8468 ·
TLT 6075 · VOO 4032 · VTI 6353 · VXUS 3934 · ^DJI 8741 · ^GSPC 24797 · ^IXIC
14023. (`deploy.db`: 0 portfolios; `simulator.db`: 6 ad-hoc portfolios, all
holding only SPY / VTI / BND.)

**Missing-preset-ticker check:** union of preset tickers =
`{VTI, VXUS, BND, TLT, GLD, VOO}`.

- All 6 are present in `ticker_catalog.py:17-31`. **Missing: none.**
- All 6 have `price_rows > 0` in both DBs, so they also survive the Simulator's
  holding-dropdown filter (`Simulator.jsx:672`, `t.price_rows > 0`) and the
  Portfolios builder filter (`Portfolios.jsx:73`).
- `seed_demo.py` demo portfolios use `{VXUS, VTI, BND, QQQ}` (`seed_demo.py:100,
  106, 112`) — all also in the catalog. Nothing missing there either.

**Verdict: NOT CONFIRMED** (no preset ticker is missing from the catalog or from
either DB). Unchanged from S1 §7. *Non-defect note:* 7 catalog tickers go
unused by any preset — `SPY, QQQ, IWM, EEM, ^GSPC, ^IXIC, ^DJI` (the three
indices are additionally hidden from the ETF screener, `Etfs.jsx:66-70`).

---

## 4. INFLATION / TAX — where applied, and every client-side figure

**What was checked:** whether inflation/tax are computed in the frontend or the
backend, and an exhaustive inventory of values the frontend alters client-side.

### 4.1 The math is backend-only

The Simulator sends the two booleans to the server and re-runs there; it does
not post-process the chart (`request body` `Simulator.jsx:371-373`; the
comment stating exactly this at `Simulator.jsx:716-719`). The actual
computation is the service layer:

- `apply_real_world_adjustments` — deflation `monte_carlo.py:331-334`,
  tax on final profit `:339-343`, breakdown `:347-357`.
- call site `backend/app/services/simulation.py:372-379` (after the Monte Carlo
  draw, before stats/percentiles), with the breakdown folded into `stats`
  (`simulation.py:386-388`) and persisted rounded (`simulation.py:209-212`).

### 4.2 Every value the frontend modifies client-side

| # | Value | Kind | Where | What it does |
|---|---|---|---|---|
| 1 | `trajectoryData.contributed` | **display series** (book-value line) | `Simulator.jsx:522-532` | Deflates the contributed line by `Math.pow(1 + adjustments.inflation_rate, month/12)`, using the **run's own** `result.params` and the persisted `stats.adjustments.inflation_rate` (defaults block `Simulator.jsx:512-520`). Mirrors the backend's deflation of `total_contributed`; no-op when the toggle is off / legacy runs (rate 0). |
| 2 | `chartData.low/median/high` | cosmetic | `Simulator.jsx:409-413` | `Math.round` of the p10/p50/p90 path values for display. |
| 3 | `crisisChart.low/median/high/actual` | cosmetic | `Simulator.jsx:420-431` | `Math.round` of crisis percentile paths + real path. |
| 4 | TextView of summary stats | formatting only | `Simulator.jsx:433-439` | `statCards` read `result.summary.best_case_final_value / median_final_value / worst_case_final_value` **verbatim**; only `formatCurrency` applied. |
| 5 | TextView of insight stats | formatting only | `Simulator.jsx:442-491` | `insightCards` read `stats.probability_of_profit`, `stats.final_percentiles.p50/p10`, `stats.upside_downside_ratio`, `stats.median_max_drawdown` **verbatim**; only `*100`, `toFixed`, `formatCurrency` applied. |
| 6 | Basis-disclosure text | formatting only | `Simulator.jsx:797-818` | Prints `adjustments.inflation_rate`, `adjustments.capital_gains_tax_rate`, `adjustments.median_capital_gains_tax`, `adjustments.taxable_fraction_of_paths` — read from the server, only `*100`/`formatCurrency`. |

**No simulation statistic is recomputed client-side.** The only value whose
*magnitude* is altered in the browser is row 1, the contributed book-value line,
and it is a *drawn series*, not a stat card — done so the book-value line and the
deflated paths share units (backend does the identical units fix at
`monte_carlo.py:334`).

Other derived client-side figures exist elsewhere in the app but are **not
simulation stats** and are unaffected by inflation/tax: `Home.jsx` `summarize()`
derives latest price / 1-day change / % change from raw closes
(`Home.jsx:59-67`, `:106-108`); `FinancialNews.jsx` prints the backend's
`feed.aggregate_score` verbatim (`FinancialNews.jsx:125`); `Portfolios.jsx`
computes `totalWeight` purely as a save affordance vs 100% (`Portfolios.jsx:
93-102`); `InvestingStrategies.jsx:13` sums preset percents for the card header.

### 4.3 Cross-check against Session 1 (S1 §2, `docs/audits/S1-premilege.md:110-169`)

**AGREEMENT — fully.** S1 concluded: "No stat is recomputed client-side … The
only other client-side modified figure is the contributed book-value line"
(`S1-premilege.md:137-139`, `:160-162`), citing exactly
`Simulator.jsx:522-532`. The S3 re-read of the current source finds the same
lines and the same behaviour, with the same `adjustments` fallback block
(`Simulator.jsx:512-520`) and the same request-body toggles
(`Simulator.jsx:371-373`) that S1 cited. This is expected rather than
coincidental: no `frontend/` file has changed since S1's HEAD `e342a5c`
(§0, empty diff).

**Verdict: NOT CONFIRMED** (as a suspected frontend-only implementation). Math is
backend; frontend alters one drawn series and formats the rest. Unchanged from
S1 §2.

---

## 5. `npx knip` — every hit verified

**Command:** `npx --yes knip` from `frontend/` (knip not in `package.json`, so
npx fetched it). **Result: knip 6.41.0, `EXIT=0`, no output — zero reported
issues.** `--include files,dependencies,exports,types,duplicates` and a `--debug`
run were used to confirm the run is real, not a no-op.

**Verification that knip actually scanned the app** (`knip_debug.txt`, captured
to temp):

- No `knip.json`/`knip.jsonc`/`knip.ts` exists → log line 1
  `[*] Unresolved configuration`; knip fell back to default entry patterns plus
  auto-enabled plugins.
- Workspaces analysed: `[ 'frontend' ]` (`knip_debug.txt:120-121`).
- Enabled plugins: `Node.js, Oxlint, PostCSS, Tailwind, Vite`
  (`knip_debug.txt:158-159`).
- Entry paths resolved include `src/main.jsx` (from both `package.json` and
  `vite.config.js`), `vite.config.js`, `tailwind.config.js`, `postcss.config.js`,
  `.oxlintrc.json` (`knip_debug.txt:219-227`, `:315-321`).
- **Project files resolved = all 18 files under `frontend/src`** — the full app
  including every page, component, hook, `api.js`, `strategyHoldings.js`, and
  `index.css` (`knip_debug.txt:338-358`). knip compiled `src/index.css`
  (`:361`).

**Hits to verify: none.** There are 0 unused files, 0 unused dependencies, 0
unlisted dependencies, 0 unused exports, 0 unused types, 0 duplicates. (Manually
spotted the exports that could plausibly be dead — `holdingsToFractions` and
`fractionToPercentInput` in `api.js`, `STRATEGIES`/`strategyHref`/
`queryToHoldings` in `strategyHoldings.js`, `usePageTitle` in `hooks/` — and each
is imported by live code, so knip's clean result is consistent with the source.)

**Caveats (reported for honesty):**
- No knip config file exists, so this is knip's *default* view (default entry
  globs + plugin detection); a project config could change the entry set. It is
  nonetheless a genuine full-`src` scan.
- The Vite plugin contributes a default `server.js` pattern
  (`knip_debug.txt:305,327`); no such file exists, which is harmless and not a
  finding.

**Verdict: CONFIRMED CLEAN** — `npx knip` reports no issues, and the run's debug
log proves the entry points and all 18 `src` files were actually analysed.

---

## Summary

| # | Question | Answer / Classification |
|---|---|---|
| 1a | Stage J final-value histogram present **and** rendered? | **NOT present, NOT rendered (CONFIRMED fact).** Introduced in Stage J (`ai_usage_log.md:304-308`), deliberately removed by Stage S1 (`ai_usage_log.md:743-749`, commit `9b68415`). `grep histogram\|BarChart` in `frontend/src` = 0 real hits (only the lucide `BarChart3` icon in `Etfs.jsx:2,140`). Backend still ships an unread `stats.histogram` (`monte_carlo.py:478-490`; `services/simulation.py:200-205`). |
| 1b | Any trajectory chart rendered twice? | **CONFIRMED — yes.** The same p10/p50/p90 series renders in both the Value-trajectory chart (`Simulator.jsx:864`) and the Growth fan chart (`Simulator.jsx:1011`); `trajectoryData = chartData.map(...)` (`:523-532`). Known/intentional per `ai_usage_log.md:783-790`; needs human eyes. |
| 2 | Sentiment toggle instances | **1.** `Simulator.jsx:709-714` (state `:242`, sent `:371`). Other `ToggleSwitch` uses are inflation `:720` and tax `:727`; sentiment chips `:983-989`,`:990-998` are read-only. **NOT CONFIRMED** (no duplicate). |
| 3 | Preset tickers vs 13-ETF catalog | **Missing: none.** Presets = {VTI 54/VXUS 36/BND 10}, {VTI 30/TLT 30/BND 20/GLD 20}, {VOO 90/BND 10} (`strategyHoldings.js:38-42,57-62,78-81`); all 6 in `ticker_catalog.py:17-31` and in `deploy.db`/`simulator.db` with `price_rows > 0`. **NOT CONFIRMED.** |
| 4 | Inflation/tax frontend or backend? Every client-side stat? | **Backend.** Toggles re-run server-side (`Simulator.jsx:371-373,716-719`); math at `monte_carlo.py:331-343` via `services/simulation.py:372-379`. **No stat recomputed client-side**; the only magnitude altered in-browser is the drawn `contributed` book-value line (`Simulator.jsx:522-532`); the rest is rounding/formatting (`:409-431`, `:433-491`, `:797-818`). **AGREES with Session 1 §2** (`S1-premilege.md:137-139,160-162`) — and the `frontend/src` tree is byte-identical to S1's HEAD (`git diff e342a5c..HEAD -- frontend` empty). |
| 5 | `npx knip` hits | **None — CONFIRMED CLEAN.** knip 6.41.0, exit 0; debug log proves entries (`src/main.jsx` etc.) and all 18 `src` files were analysed (`knip_debug.txt:120-159,219-227,338-358`). No unused files/deps/exports/types. |

**Overall:** The frontend is knip-clean and oxlint-clean, and the three questions
the brief anticipated as possible defects (missing preset tickers, duplicate
sentiment toggle, frontend-side inflation/tax math) are all **NOT CONFIRMED**.
The two **CONFIRMED** items are factual, not defects: the Stage J histogram is
gone by design (with a now-orphaned backend payload), and the p10/p50/p90
trajectory is intentionally drawn in two panels — both already logged, and both
flagged as design decisions for human eyes rather than bugs.
