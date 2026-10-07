# Stage V1 — Pre-milestone change audit (read-only)

Auditor: opencode (big-pickle). Scope: read-only verification of 8 suspected
issues. No code was modified; no commits made. Every claim carries file:line.

---

## 0. Baseline

| Item | Value |
|---|---|
| Branch | `main` |
| HEAD | `e342a5c76f7e60961e69f42607064623ec2f253c` ("docs: document the real-world basis switches…") |
| git status | Dirty working tree: 15 modified files (incl. `backend/app/simulation/monte_carlo.py`, `backend/app/services/simulation.py`, `backend/app/routers/simulations.py`, `frontend` untouched — see full list below), 1 deleted (`tree.txt`, known noise), 2 untracked (`project-files.txt`, `project-tree.txt`, known noise per AGENTS.md "Git hygiene") |
| pytest | **327 passed, 2 warnings in 33.11s** (`backend/`, `.venv\Scripts\python.exe -m pytest`) |

Modified files: `AGENTS.md`, `Dockerfile`, `backend/app/config.py`,
`backend/app/deps.py`, `backend/app/main.py`, `backend/app/routers/crisis.py`,
`backend/app/routers/simulations.py`, `backend/app/services/market_data.py`,
`backend/app/services/simulation.py`, `backend/app/simulation/monte_carlo.py`,
`backend/tests/test_api.py`, `backend/tests/test_market_data.py`,
`backend/tests/test_monte_carlo.py`, `backend/tests/test_static_serving.py`,
`docs/deployment.md`, `docs/known_issues.md`.

**Expectation mismatch:** the task said "expect 261 passing"; the actual result
is **327**, which matches AGENTS.md's stated "Expected: 327 passing". The 261
figure is stale. The audit ran against the working tree (uncommitted changes
included), not against HEAD.

---

## 1. CACHE KEY

**What was checked:** key construction for the simulation run cache, whether
the inflation/tax flags and rates are in it, and where defaults are injected
relative to key construction.

**Key construction** — `backend/app/services/simulation.py:161-175`
(`canonical_params`), serialized and looked up at
`backend/app/services/simulation.py:307-333`:

```python
    return {
        "initial_balance": float(initial_balance),
        "monthly_contribution": float(monthly_contribution),
        "horizon_months": int(horizon_months),
        "n_simulations": int(n_simulations),
        "blocks": blocks,
        "seed": seed,
        "use_sentiment": bool(use_sentiment),
        "volatility_multiplier": round(float(volatility_multiplier), 6),
        "sentiment_score": (
            None if sentiment_score is None else round(float(sentiment_score), 6)
        ),
        "adjust_for_inflation": bool(adjust_for_inflation),      # line 173
        "apply_capital_gains_tax": bool(apply_capital_gains_tax),# line 174
    }
```

plus `params["data_fingerprint"]` (line 328) and `params["stats_version"]`
(line 332), then `params_json = json.dumps(params, sort_keys=True)` (line 333),
matched exactly by `find_cached_run`
(`backend/app/dao/simulations.py:32-43`: `WHERE portfolio_id = ? AND params_json = ?`).

**Answers:**

- **Inflation flag — IN the key** (`services/simulation.py:173`).
- **Tax flag — IN the key** (`services/simulation.py:174`).
- **Inflation rate — NOT in the key.** It is also **not client-parameterizable**:
  `SimulationRequest` exposes only the two booleans
  (`backend/app/schemas.py:225-226`), with the comment at
  `schemas.py:221-224`: "Rates live in app.simulation.monte_carlo as module
  constants rather than being client-supplied". `run_portfolio_simulation`
  never passes `inflation_rate`/`tax_rate` to
  `monte_carlo.apply_real_world_adjustments`
  (`services/simulation.py:372-379` — only the two toggles), so the defaults
  `INFLATION_ANNUAL_RATE` / `CAPITAL_GAINS_TAX_RATE`
  (`simulation/monte_carlo.py:276-277`) always apply.
- **Tax rate — NOT in the key**, same rationale as above.

**Default injection point (the suspected collision):** defaults are applied
**BEFORE** the key is built, at three successive layers, all upstream of
`canonical_params`:

1. Pydantic request validation: `adjust_for_inflation: bool = False`,
   `apply_capital_gains_tax: bool = False` (`schemas.py:225-226`) are resolved
   when FastAPI parses the body, before the handler body runs
   (`routers/simulations.py:37-48` passes `request.adjust_for_inflation` etc.
   explicitly — lines 46-47).
2. Service signature defaults (`services/simulation.py:271-272`) — same values.
3. `canonical_params` signature defaults (`services/simulation.py:145-146`) —
   same values.

There is **no default application after `params_json` is built** (lines
333-335 go straight to `find_cached_run`). A request omitting the toggle and a
request sending `false` therefore produce the **identical** key from the
**identical** resolved value — which is correct, not a collision. A request
sending `true` produces a different key.

**Verdict: NOT CONFIRMED.** No post-key default injection exists; omitted and
explicit-default requests intentionally share one cache entry.

*Residual concern (not a bug today):* if `inflation_rate`/`tax_rate` ever
become client-supplied, they must be added to `canonical_params` at the same
time or cached runs will cross-contaminate. The guarding comment lives at
`schemas.py:221-224` and `services/simulation.py:154-159`.

---

## 2. PLACEMENT — backend math vs frontend display filter

**What was checked:** where the inflation/tax math is applied, and every
stat/series the frontend modifies client-side.

**Backend (the actual math):** `routers/simulations.py:46-47` →
`services/simulation.py:372-379`:

```python
    paths, adjustments = monte_carlo.apply_real_world_adjustments(
        paths,
        initial_balance=initial_balance,
        monthly_contribution=monthly_contribution,
        horizon_months=horizon_months,
        adjust_for_inflation=adjust_for_inflation,
        apply_capital_gains_tax=apply_capital_gains_tax,
    )
```

Called **after** the Monte Carlo draw (`simulation.py:358-367`) and **before**
`compute_distribution_stats` (`simulation.py:381-387`) and before percentile
trajectories are recomputed (`simulation.py:392-395`), so chart, summary and
stats all come from the adjusted paths (docstring `simulation.py:281-287`).

**Frontend:** the toggles are sent to the server, not applied locally
(`frontend/src/pages/Simulator.jsx:371-373` request body; comment at
`Simulator.jsx:716-719`: "Both re-run the simulation on the server rather than
post-processing the chart locally"). The **only** client-side modified figure
is the **"contributed" book-value line of the compact Value-trajectory chart**,
`Simulator.jsx:522-532`:

```js
  const inflationRate = Number(adjustments.inflation_rate ?? 0)
  const trajectoryData = result?.params
    ? chartData.map((row) => ({
        ...row,
        contributed: Math.round(
          (Number(result.params.initial_balance ?? 0) +
            Number(result.params.monthly_contribution ?? 0) * row.month) /
            Math.pow(1 + inflationRate, row.month / 12),
        ),
      }))
    : []
```

That is a display-only deflation of one series, using the run's own persisted
`stats.adjustments.inflation_rate` (defaults block `Simulator.jsx:512-520`),
mirroring the backend's deflation of `total_contributed`
(`monte_carlo.py:334`). Rationale documented at `Simulator.jsx:500-511`.

**No stat is recomputed client-side:** stat cards read
`result.summary.*` (`Simulator.jsx:433-439`), insight cards read
`result.stats.*` verbatim (`Simulator.jsx:441-491`), the fan chart reads
`result.percentiles` verbatim (`Simulator.jsx:404-413`). The only other
frontend use of `adjustments` is the basis-disclosure badges
(`Simulator.jsx:797-818`).

**Verdict: NOT CONFIRMED** (as a suspected frontend-only implementation).
Math is backend/service-layer; frontend changes exactly one displayed series
(the contributed line), for a documented units-consistency reason.

---

## 3. TAX FORMULA

**What was checked:** the reduction computation, the rate constant, every
user-visible label, and LTCG / "long-term" wording.

**Formula** — `backend/app/simulation/monte_carlo.py:339-343`:

```python
    final_profit = adjusted[:, -1] - total_contributed   # line 339
    taxable = final_profit > 0.0                         # line 340
    if apply_capital_gains_tax:
        tax = np.where(taxable, final_profit * tax_rate, 0.0)  # line 342
        adjusted[:, -1] -= tax                                   # line 343
```

It is **rate × (final − total contributions)** — i.e. on *profit*, not on the
final value. `total_contributed` is the deflated book value when inflation is
on (`monte_carlo.py:334`), nominal otherwise (`:337`). Tax is levied once, on
the final column only, and only when profit > 0 (no loss credit, `:340`).

**Rate constant:** `CAPITAL_GAINS_TAX_RATE = 0.15`
(`backend/app/simulation/monte_carlo.py:46`), paired with
`INFLATION_ANNUAL_RATE = 0.03` (`:38`).

**Every user-visible label for the rate:**

| Location | String |
|---|---|
| `frontend/src/pages/Simulator.jsx:724` | `"Adjust for 3% Inflation"` (toggle title — the inflation rate's only UI literal) |
| `frontend/src/pages/Simulator.jsx:731` | `title="Apply Capital Gains Tax"` (toggle title) |
| `frontend/src/pages/Simulator.jsx:732` | subtitle `"15% on the final profit of each path, charged once at liquidation."` (the only UI literal for the tax rate) |
| `frontend/src/pages/Simulator.jsx:806` | `"{(adjustments.inflation_rate * 100).toFixed(0)}% inflation"` (basis badge, dynamic) |
| `frontend/src/pages/Simulator.jsx:811-812` | `"{(adjustments.capital_gains_tax_rate * 100).toFixed(0)}% capital gains tax"` (basis badge, dynamic) |

Backend user-visible surface: no string labels — the API only returns the
numeric keys `capital_gains_tax_rate` / `inflation_rate`
(`monte_carlo.py:349,351`) and the UI formats them.

**"LTCG" / "long-term" wording:** matches found only in **code comments and
docs**, never in a user-visible string:

- `backend/app/simulation/monte_carlo.py:40-46` — comment: `"Standard
  long-term capital gains tax"` … "US federal *top marginal* rate" …
  "qualified dividends/LTCGs are taxed at preferential 0/15/20% rates".
- `docs/data_methodology.md:281-284` — "**Not modelled.** Dividends and their
  taxation, short-term vs long-term holding periods per path, the 0%/15%/20%
  bracket…".
- `docs/ai_usage_log.md:818-823` — records that "Standard long-term capital
  gains tax" is ambiguous and **the user chose 15%**.

**Finnish-context observation (code-level fact):** the model uses a flat 15%
US-LTCG-flavoured rate with **no holding-period or LTCG/short-term
distinction anywhere** — neither in the formula (single end-of-horizon
liquidation, `monte_carlo.py:294-300`) nor in the UI copy. It does **not**
implement the Finnish 30%/34% capital-income-tax model. The UI label is
jurisdiction-neutral ("Apply Capital Gains Tax"), so no incorrect Finnish
claim is made; but the underlying rate is a deliberate, user-approved
US-style choice (ai_usage_log T1a), not an accident.

**Verdicts:**
- Formula = rate × profit, not rate × final: **NOT CONFIRMED** (as a suspected bug — the correct variant is implemented).
- Rate constant 0.15 with the label inventory above: **CONFIRMED** (fact).
- User-visible "LTCG"/"long-term" wording: **NOT CONFIRMED** (comments/docs only).
- Finnish 30%/34% mismatch: **CONFIRMED as a code-level fact**, flagged for a product decision (needs human eyes — changing it contradicts the logged T1a user decision).

---

## 4. INFLATION METHOD

**What was checked:** deflator-on-outputs vs modification-of-returns, ordering
vs tax, and whether `docs/data_methodology.md` documents either.

**Method: deflator on outputs, applied after the Monte Carlo draw — returns are
never modified.** `monte_carlo.py:251-266`:

```python
def inflation_deflator(horizon_months, inflation_rate=INFLATION_ANNUAL_RATE):
    ...
    steps = np.arange(horizon_months + 1, dtype=float) / 12.0
    return np.power(1.0 + float(inflation_rate), steps)
```

`monte_carlo.py:331-337`:

```python
    if adjust_for_inflation:
        deflator = inflation_deflator(horizon_months, inflation_rate)
        adjusted = paths / deflator[None, :]
        total_contributed = nominal_contributed / float(deflator[-1])
    else:
        adjusted = paths.copy()
        total_contributed = nominal_contributed
```

**Ordering vs tax: inflation first, then tax.** Deflation at `:331-334`;
`final_profit` computed from the deflated path and book value at `:339`; tax
subtracted at `:342-343`. So with both toggles on, the nominal 15% rate is
applied to a real (deflated) profit — documented as a deliberate simplification
in `monte_carlo.py:302-306` and `docs/data_methodology.md:275-279`.

Call-site ordering confirms adjustments run before any derivation:
`services/simulation.py:372` (adjust) → `:381` (stats) → `:392` (percentiles).

**Docs:** `docs/data_methodology.md` **does document both**, in a dedicated
section `## Real-world adjustments (tax & inflation)` at
`docs/data_methodology.md:235-289` — covering the deflator formula (`:247-249`),
book-value deflation (`:251-259`), tax charging rules and ordering (`:261-265`),
the nominal-vs-real rate caveat (`:275-279`), what is not modelled (`:281-284`),
and the drawdown caveat (`:286-289`). Source/rate constants cited at `:237-241`;
cache-key interaction at `:243-245`.

**Verdict: NOT CONFIRMED** on all counts — method is a post-hoc deflator of
outputs (with tax ordered after), and the methodology doc covers inflation and
tax extensively.

---

## 5. SIMULATOR CHARTS

**What was checked:** every chart the Simulator page renders (from code), the
existence/rendering of a final-value distribution histogram, and whether any
trajectory chart is rendered more than once.

**Charts rendered by `frontend/src/pages/Simulator.jsx` (recharts
`ComposedChart`, the only chart component imported — lines 3-12):**

1. **Value trajectory chart** — `ComposedChart data={trajectoryData}` at
   `Simulator.jsx:864-951`, inside the "Value trajectory" header
   (`:833-856`); series: p90 (`:904`), p10 (`:915`), p50 (`:926`),
   contributed (`:941`).
2. **Growth fan chart** — `ComposedChart data={chartData}` at
   `Simulator.jsx:1011-1048`, panel "Growth fan chart · 10th–90th percentile"
   (`:969`); series: band Area (`:1031`) + median Line (`:1040`).
3. **Crisis replay chart** — `ComposedChart data={crisisChart}` at
   `Simulator.jsx:1186-1242`, conditional on `crisisData` (`:1158`);
   series: band (`:1216`), simulated median (`:1225`), real trajectory (`:1233`).
4. **Realized monthly returns heatmap** — an HTML table, not a chart component
   (`Simulator.jsx:1072-1109`).

(Other charts in the app — `Home.jsx` AreaChart at `Home.jsx:360` and
`Sparkline` at `Home.jsx:69` — are not on the Simulator page.)

**Histogram:** `grep histogram frontend/src` → **0 matches**. A final-value
distribution histogram **does not exist** in `frontend/src` and is therefore
not rendered. This is deliberate: commit `9b68415` (2026-09-26) is titled
"feat(S1): replace final-value histogram with a trajectory chart, fix the
undefined upside/downside ratio". The backend still computes and persists the
histogram (`monte_carlo.py:418-419` "histogram buckets … 20 equal-width bins";
persisted at `services/simulation.py:200-205`) — it ships in `stats.histogram`
on every run but no UI reads it.

**Trajectory rendered more than once:** **Yes.** Charts 1 and 2 both plot the
same three percentile series from the same source (`result.percentiles` →
`bandPath`/`chartData` at `Simulator.jsx:404-413`); chart 1 is chart 2's data
plus the contributed line (`trajectoryData = chartData.map(...)` at
`:523-532`). In a single results view the p10/p50/p90 trajectories are
therefore drawn twice, in two panels.

**Verdicts:**
- Histogram absent from frontend: **CONFIRMED** (as a fact; deliberate removal per `9b68415`, so "regression" framing = NOT CONFIRMED; the orphaned backend `stats.histogram` payload is worth noting).
- Trajectory chart rendered more than once: **CONFIRMED** (two panels, same series; whether the duplication is wanted is a design question — needs human eyes).

---

## 6. SENTIMENT TOGGLES

**What was checked:** every sentiment on/off toggle rendered in the Simulator
page.

**Count: exactly ONE toggle.**

- `frontend/src/pages/Simulator.jsx:709-714`:
  ```jsx
  <ToggleSwitch
    checked={useSentiment}
    onChange={setUseSentiment}
    title="AI Sentiment Adjustment (Includes Geopolitical Risk)"
    subtitle="Scales historical volatility by recent FinBERT news sentiment."
  />
  ```
  (state declared at `:242`; sent as `use_sentiment: useSentiment` at `:371`.)

Not toggles (status chips only, read-only):
- `Simulator.jsx:983-989` — sentiment score + multiplier badge.
- `Simulator.jsx:990-998` — "sentiment n/a · no recent news" badge.

No other `ToggleSwitch`/checkbox bound to sentiment exists anywhere in
`frontend/src` (grep `[Ss]entiment` returns only `FinancialNews.jsx`
display strings at `:116,:128,:176,:178`, which are not toggles and not on the
Simulator page).

**Verdict: NOT CONFIRMED** (if the suspicion was a duplicate/extra toggle —
there is exactly one).

---

## 7. STRATEGY PRESETS vs ETF CATALOG

**Preset cards** — `frontend/src/strategyHoldings.js:29-83`, rendered by
`frontend/src/pages/InvestingStrategies.jsx:12-67`:

| Card | Tickers + weights | Source lines |
|---|---|---|
| Boglehead Three-Fund | VTI 54%, VXUS 36%, BND 10% | `strategyHoldings.js:38-42` |
| Ray Dalio All-Weather | VTI 30%, TLT 30%, BND 20%, GLD 20% | `strategyHoldings.js:57-62` |
| Warren Buffett 90/10 | VOO 90%, BND 10% | `strategyHoldings.js:78-81` |

(Both All-Weather and 90/10 carry explicit `caveat` strings about the BND
proxy at `strategyHoldings.js:52-56` and `:72-77`, rendered at
`InvestingStrategies.jsx:48-52`.)

**Full ETF catalog** — `backend/app/data/ticker_catalog.py:17-31`
(`DEFAULT_TICKERS`, the ingest source of truth), 13 entries:

```
SPY    SPDR S&P 500 ETF Trust                  US Large-Cap Equity
VOO    Vanguard S&P 500 ETF                    US Large-Cap Equity
VTI    Vanguard Total Stock Market ETF         US Total Market
QQQ    Invesco QQQ Trust                       US Large-Cap Growth
IWM    iShares Russell 2000 ETF                US Small-Cap Equity
VXUS   Vanguard Total International Stock ETF  International Equity
EEM    iShares MSCI Emerging Markets ETF       Emerging Markets Equity
BND    Vanguard Total Bond Market ETF          US Bonds
TLT    iShares 20+ Year Treasury Bond ETF      US Long-Term Treasuries
GLD    SPDR Gold Shares                        Commodities
^GSPC  S&P 500 Index                           Index - US Large-Cap
^IXIC  NASDAQ Composite Index                  Index - US Broad Tech
^DJI   Dow Jones Industrial Average            Index - US Large-Cap
```

**Deploy DB cross-check** (`backend/deploy.db`, read-only query, price row
counts): BND 4894 · EEM 5897 · GLD 5493 · IWM 6618 · QQQ 6926 · SPY 8468 ·
TLT 6075 · VOO 4032 · VTI 6353 · VXUS 3934 · ^DJI 8741 · ^GSPC 24797 ·
^IXIC 14023.

**Missing-preset-ticker check:** union of preset tickers = {VTI, VXUS, BND,
TLT, GLD, VOO} — **all present in the catalog and all have price rows in the
deploy snapshot** (the Simulator's holding dropdown additionally filters on
`price_rows > 0`, `Simulator.jsx:672`, which every preset ticker passes).

**Verdict: NOT CONFIRMED** — no preset ticker is missing from the catalog.

---

## 8. GIT PROCESS

Last 10 commits (all authored by `uditbh123`, all on `main`), with parent
counts from `git log --pretty=format:"%h parents:%p"`:

| # | sha | date | subject | parents | via PR merge? |
|---|---|---|---|---|---|
| 1 | `e342a5c` | 2026-09-29 | docs: document the real-world basis switches, and fix the lint the CI never ran | 1 | no — direct |
| 2 | `78f60d0` | 2026-09-29 | perf(ingest,simulation): vectorize history conversion, batch news dedupe, share the annuity-due helper | 1 | no — direct |
| 3 | `7cd30ea` | 2026-09-29 | feat(ui): hand a strategy's allocation to the Simulator, and add the real-world basis switches | 1 | no — direct |
| 4 | `c74d7f2` | 2026-09-29 | feat(adjustments): inflation and capital-gains-tax basis switches | 1 | no — direct |
| 5 | `d526aa4` | 2026-09-29 | fix(ui): hide market indices from the ETF screener, drop dead page headers | 1 | no — direct |
| 6 | `9b68415` | 2026-09-26 | feat(S1): replace final-value histogram with a trajectory chart, fix the undefined upside/downside ratio | 1 | no — direct |
| 7 | `e8224f8` | 2026-09-26 | refactor(UI): brutally minimal institutional aesthetic - hairline borders, monochrome, Archivo/IBM Plex Mono | 1 | no — direct |
| 8 | `466dbf0` | 2026-09-26 | test(hygiene): guard the runtime/ingest import split, drop stale openapi.json | 1 | no — direct |
| 9 | `e8fa9e6` | 2026-09-26 | docs(arch): add Archify runtime architecture diagram | 1 | no — direct |
| 10 | `bc4860e` | 2026-09-26 | fix(weights): unify holding weights on fractions in (0,1] summing to 1.0 | 1 | no — direct |

`git log --merges -10` returns **zero merge commits** — the entire recent
history is linear, single-parent, committed directly to `main`. No PR merges.

Also relevant to process: the working tree currently carries 15 uncommitted
modified files and 2 untracked artifacts (`project-files.txt`,
`project-tree.txt` — listed in AGENTS.md as never-commit noise, alongside the
deleted `tree.txt`).

---

## Summary — classification of each suspected issue

| # | Suspected issue | Classification |
|---|---|---|
| 1 | Cache-key collision because defaults are injected after the key is built (omitted toggle vs explicit-default toggle) | **NOT CONFIRMED** — defaults resolve at Pydantic validation (`schemas.py:225-226`) before `canonical_params` (`services/simulation.py:307-319`); rates are not in the key but are also not client-supplied, so no collision path exists |
| 2 | Inflation/tax applied as a frontend display filter rather than in the backend | **NOT CONFIRMED** — applied in the service layer (`services/simulation.py:372-379` → `monte_carlo.py:269-358`); the frontend modifies exactly one displayed series (the contributed line, `Simulator.jsx:522-532`), no stats |
| 3a | Tax computed as rate × final instead of rate × (final − contributions) | **NOT CONFIRMED** — it is `tax_rate × (final − total_contributed)` (`monte_carlo.py:339-342`) |
| 3b | Rate constant / label inventory | **CONFIRMED (fact)** — 0.15 at `monte_carlo.py:46`; UI literals at `Simulator.jsx:724,731,732,806,811-812` |
| 3c | User-visible "LTCG"/"long-term" wording implying a holding-period distinction | **NOT CONFIRMED** — wording appears only in comments (`monte_carlo.py:40-46`) and docs (`data_methodology.md:281`); UI says neutral "capital gains tax" |
| 3d | Rate does not match the Finnish 30%/34% capital-income-tax context | **CONFIRMED as a code-level fact (needs human eyes)** — flat 15% US-style rate, no LTCG/holding-period concept anywhere; changing it contradicts the logged user decision (ai_usage_log T1a, `docs/ai_usage_log.md:818-823`) |
| 4 | Inflation applied by modifying returns; and/or docs silent on inflation/tax | **NOT CONFIRMED** — deflator applied to outputs post-simulation (`monte_carlo.py:331-334`), tax applied after deflation (`:339-343`); `docs/data_methodology.md:235-289` documents both in detail |
| 5a | Final-value distribution histogram missing from frontend | **CONFIRMED as a fact** (0 matches in `frontend/src`; deliberately replaced by commit `9b68415`) — the backend still ships an unread `stats.histogram` payload (`monte_carlo.py:418`, `services/simulation.py:200-205`) |
| 5b | A trajectory chart rendered more than once | **CONFIRMED** — the same p10/p50/p90 series renders in both the Value-trajectory chart (`Simulator.jsx:864`) and the Growth fan chart (`Simulator.jsx:1011`); design intent needs human eyes |
| 6 | Duplicate/extra sentiment on/off toggles on the Simulator page | **NOT CONFIRMED** — exactly one toggle (`Simulator.jsx:709-714`); the two sentiment chips (`:983-989`, `:990-998`) are read-only badges |
| 7 | A preset ticker missing from the ETF catalog | **NOT CONFIRMED** — {VTI, VXUS, BND, TLT, GLD, VOO} all in `ticker_catalog.py:17-31` and all have price rows in `deploy.db` |
| 8 | PR/merge-based history | **CONFIRMED fact: none** — all of the last 10 commits are single-parent direct commits to `main`; `git log --merges` is empty; working tree is dirty with 15 modified files |

**Baseline note:** expected "261 passing" was not met because it is stale —
actual is **327 passed**, matching AGENTS.md.
