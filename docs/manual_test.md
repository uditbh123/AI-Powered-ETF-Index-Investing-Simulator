# Manual test — Stage L2 (Portfolios section)

End-to-end browser check for creating and running a portfolio from the UI.
Budget: ~3 minutes.

## Setup

1. Run the backend serving the built SPA on `http://127.0.0.1:8000`
   (or open the deployed container). Start on the **Home** page and navigate
   with the top nav — do not hard-refresh `/portfolios` (the API route shadows
   the SPA route on a single-origin build, same as `/news`).

## Steps

1. **Open Portfolios** — click **Portfolios** in the top nav.
   - The page shows the eyebrow heading "Investing Portfolios", an empty state
     ("No portfolios yet…") with a **New portfolio** button (or the list if
     portfolios already exist; each row shows Name, Holdings count, Monthly
     contribution, Created date).
   - Expected: no console errors.

2. **Create a portfolio** — click **New portfolio**.
   - Name: type e.g. `Manual P` (1–120 chars).
   - Monthly contribution: enter a value, e.g. `100`. The `$100/mo` hint
     updates next to the label.
   - Holdings: type `SPY` in "Search a ticker to add…"; an `add +` result
     appears — click it to add a second holding row.
   - Total weight indicator: with both rows at 0% it reads red `0.0%` and the
     bar is hidden with "Allocate to 100% ± 1%".
   - Set row weights via the number inputs so they total 100 (e.g. `50` / `50`).
   - Expected: the indicator turns green (`text-pos`) and the hint disappears.

3. **Save** — click **Create portfolio** (disabled until valid).
   - Expected: the form closes and the new portfolio row appears with a Created
     date; toast-free, no console errors.

4. **Run it in the Simulator** — click the **Open `<name>` in the simulator**
   button on that row.
   - Expected: you land on `/simulator?portfolio=<id>`, the portfolio selector
     is set to the portfolio, and its name / monthly contribution / holdings
     (weights in %) are loaded into the form.

5. **Run a simulation** — click **Run simulation**.
   - Expected: Outcome insights cards (probability of profit, median/worst
     case), the Growth fan chart, the monthly-returns heatmap, and a Replay-a-
     Crisis control all render.

6. **Edit the portfolio** — back on **Portfolios** (top nav), click **Edit**
   (`aria-label="Edit <name>"`).
   - Change a weight (e.g. `100` on a single holding or rebalance two rows),
     then **Save changes**.
   - Expected: the row's Holdings count / Monthly total update.

7. **Delete the portfolio** — click **Delete** (`aria-label="Delete <name>"`).
   - Expected: a confirm dialog ("Delete “<name>”?") with **Cancel** (focused by
     default; **Escape** closes) and a **Delete** button. Press **Delete**.
   - Expected: the row is removed and, on a shared database, its simulation
     runs are removed too.

8. **Keyboard spot-check** — the create form's name/weight inputs, the holdings
   select, the delete dialog (Escape, Tab between Cancel/Delete), and the
   total-weight bar are reachable and operable by keyboard; visible focus on
   every control.

## Expected result

All steps pass with the built frontend and no console or network errors. If
step 2's form lets you save with weights totaling outside 100% ± 1, that is a
bug (the API rejects it with 422).