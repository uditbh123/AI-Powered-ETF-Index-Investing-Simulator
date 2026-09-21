# AI Usage Log

Log of AI-assisted changes found through human code review. One entry per bug;
evidence from the test suite is included.

## Bug 1 — Contribution timing in the Monte Carlo engine
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

## Bug 2 — Percentile levels documented three ways
- **Found by:** human review.
- **Verification:** confirmed both stale texts present:
  - `monte_carlo.py` `path_percentiles` docstring: "best-case (95th), median
    (50th) and worst-case (5th)".
  - `schema.sql` `simulation_results.percentile` comment: "-- e.g. 5, 50, 95".
- **What changed:** both updated to the true 10 / 50 / 90 levels.
- **Test evidence:** suite green after change (`100 passed`).
  Commit `99c20f2`.

## Bug 3 — Trivially-true geometric-mean match in `validate_bootstrap`
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

## Bug 4 — Fragile summary indexing in `_assemble_response`
- **Found by:** human review.
- **Verification:** confirmed `finals[len(finals) // 2]` assumed ascending,
  odd-count levels. Frontend checked first: `frontend/src/pages/Simulator.jsx`
  reads `summary.best/median/worst_case_final_value`, `sentiment.applied`, and
  `sentiment.volatility_multiplier` — all keys preserved; the raw
  `sentiment.score` was already present, so the change is additive only.
- **What changed:** summary finals now indexed by percentile level value
  (`dict(zip(levels, finals))` with `min/max/get(50.0, ...)` fallback).
  The `"applied": bool(use_sentiment) and multiplier != 1.0` logic was kept.
- **Test evidence:** suite green. Commit `e186b91`.

## Bug 5 — Stray character at end of schema.sql
- **Found by:** human review.
- **Verification:** the stray `a` is **not present** — raw byte inspection
  shows the file ends with `...published_at);` and the final non-whitespace
  character is `;`. Nothing was removed.
- **What changed:** created `tests/test_schema.py` asserting schema.sql runs
  via `executescript()` without error. With the BUG 7 index added,
  `test_news_category_published_index_exists` was extended so the file asserts
  both news indexes (the review's requested coverage).
- **Test evidence:** `test_schema.py` green. Commit `65fb139`.

## Bug 6 — Foreign keys not enforced per connection
- **Found by:** human review.
- **Verification:** confirmed. `get_connection()` set only
  `PRAGMA foreign_keys = ON`; `journal_mode`/`busy_timeout` were never set on
  new connections, so the schema.sql PRAGMAs did not persist.
- **What changed:** every new connection from `get_connection()` now executes
  `PRAGMA journal_mode = WAL`, `PRAGMA busy_timeout = 5000`, and
  `PRAGMA foreign_keys = ON`. Added `tests/test_database.py` asserting
  `PRAGMA foreign_keys == 1`, WAL mode, and busy_timeout 5000.
- **Test evidence:** `101 passed`. Commit `db31b85`.

## Bug 7 — Schema never applied to non-empty databases
- **Found by:** human review.
- **Verification:** the premise was **already false** — `init_db()` runs
  `executescript` unconditionally (idempotent, all statements `IF NOT EXISTS`),
  so new schema reaches existing databases at startup. `ANALYZE` is not run at
  startup. Nothing to fix in `database.py`.
- **What changed:** added the missing `idx_news_category_published
  (category, published_at)` index to schema.sql and extended
  `tests/test_schema.py` to assert both news indexes.
- **Note:** `ANALYZE` should still be run once manually after the next bulk
  ingest (none of the new indexes have runtime statistics yet).
- **Test evidence:** `102 passed`. Commit `ddabf88`.

## Bug 8 — Sentiment-to-volatility band too wide (deliberate parameter change)
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
    — asserted old magnitudes 1.75 / 0.75.
  - `test_monte_carlo.py::test_sentiment_multiplier_is_clipped_and_handles_nan`
    — asserted old clipped bounds 1.75 / 0.75 (clips are now 1.10 / 0.95).
  - `test_api.py::test_positive_sentiment_narrows_volatility` — asserted old
    multiplier 0.75 for score +1.0.
  - `test_api.py::test_negative_sentiment_widens_the_fan_chart` — the old wide
    band made the 10/90 spread gap visible at 2-dp rounding; with the narrow
    band the max-signal setup (score -1.0, horizon 60) keeps the strict
    direction check meaningful. Multiplier assertion tightened to `1.10`.
  - Tests passing explicit multipliers to `simulate_paths` (1.75 / 0.75) were
    NOT changed — that path is not clipped.
- **Test evidence:** `102 passed`. Commit `ead678c`.