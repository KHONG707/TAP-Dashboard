# TAP Desk, Support/Feedback Analysis (Writeup)

**Scope:** 1,000 Jira tickets, Jan 2025 to May 2026, for the TAP Desk support/feedback project. A major product release shipped **Oct 1, 2025**, which is the analytical spine of this writeup. Full analysis: `analysis.ipynb`; cleaning details: `DATA_CLEANING.md`; cleaned data: `data/TAP_Desk_cleaned.xlsx`.

---

## Bottom line

The Oct-1 release **permanently doubled ticket volume** (37 → 84 tickets/month, +126%) and quietly degraded quality. The focus for next quarter is **Payments**: it has by far the worst reopen rate (**25% of *all* its tickets**, vs 10.7% overall), it is the most severe component, and its failures cost real money. **Most urgent, in Payments and Checkout: the release amplified charge-correctness regressions (the product charging/refunding the wrong amount): card-declined-but-held 7→19, duplicate charge 2→7, refund-not-processed 7→17 (Payments); cart-total-wrong 8→19, tax-calc-off 6→13 (Checkout), all ~2.4-4× more often than before.** The growth in load is concentrated in **Checkout and Search**, the two components that gained the most share after the release; their fixes mostly hold, so the lever there is reducing inflow, not rework. The team also falls a little further behind each month, which is worth watching but is secondary to the Payments quality problem.

---

## What the data is (after cleaning)

1,000 tickets, **865 resolved, 135 still open (14%)**. Cleaning was conservative and fully documented (`DATA_CLEANING.md`): de-duplicated `Component` labels (11→8 from casing/whitespace), merged three identical terminal statuses (`Closed`/`Done`/`Resolved`) into one `Resolved`, neutralised 4 impossible-date rows (resolved before created), and made missing values explicit. No rows were dropped. Notable quirk: ticket `Summary` is heavily templated (77 unique strings), which we used as a recurring-issue key.

---

## Key findings

1. **The release caused a permanent step-change in volume.** Run-rate jumped **37 → 84 tickets/month (+126%)** in October and never receded, with **Reported Issues growing fastest (+132%)**. The extra load lands in **Search** (share **+3.9 pts**, 53 → 133 tickets, about 2.5×) and **Checkout** (share **+2.4 pts**, already the biggest component at 263).

2. **Payments is where fixes fail (the focus).** Without using labels at all: **Payments reopens 25% of all its tickets**, the worst component by more than 2×, vs **10.7%** overall. It is also the most severe component (**29% Critical/High**). Sharper but *label-dependent*: of the 52 Payments tickets **tagged** `regression`, **86.5% reopen** (a subset, see caveats). Overall reopen rose **8.4% → 11.8%** after the release. Note that Payments share actually *shrank* (19.6% → 17.2%), so this is a quality and risk problem, not a volume one.

3. **The release introduced new financial-correctness problems.** Charge-correctness regressions (wrong amounts, ~2.4-4×) hit **Payments** (*Card declined but money held* **7→19**, *Duplicate charge* **2→7**, *Refund not processed* **7→17**) and **Checkout** (*Cart total shows incorrect amount* **8→19**, *Tax calculation off* **6→13**). These are the highest-priority tickets because the customer is charged or refunded the wrong amount.

4. **Checkout and Search are the volume/inflow story.** Both gained the most share after the release, and in both the fixes mostly hold, so the lever is reducing inflow, not rework. **Checkout** is the biggest component (263) and its defects reopen only about **6%**; the load is release regressions (*Checkout button unresponsive on Safari*, *Cart empties on page refresh*) plus clear feature demand (*Apple Pay*, *guest checkout*, *show shipping cost earlier*). **Search** grew the most (186 tickets, up ~2.5×) and its tickets reopen about **12%**, a mix of quality (*Autocomplete slow*, *Filter by price not working*, *Misspelled query returns 0 results*) and feature requests (*in-stock-only filter*, *suggest related products*, *ranking buries new products*).

5. **Triage starves low-priority work.** Median resolution runs Critical 0.2d → High 0.7d → Medium 2.4d → **Low 5.9d**; SLA attainment (illustrative targets) falls from 100% (Critical) to 86% (Low) and dipped after the release.

6. **Operational and customer notes.** One assignee carries about **2×** the load of any peer, and **Mondays generate 2.4×** the tickets of a normal weekday (both staffing signals). There is no customer-concentration risk: the largest customer (Acme) is **16.5%** of volume and the spread is even.

**What surprised me:** among Payments tickets *tagged* a regression, a fix is *more likely to fail than hold* (86.5% reopen, a labeled subset), and the release shipped brand-new financial-correctness problems (duplicate charges, wrong tax) without anyone framing them that way.

---

## Recommendation, where engineering should focus next quarter

**Primary: Payments.** Lower and shrinking volume (180, ~17% of tickets), but this is where engineering effort is wasted and where the business cost is highest: its defects reopen **25%** (the tagged-regression slice is 86.5%), it is the most severe component (29% Critical/High), and its failures are financial (duplicate charges, card-declined-but-held, wrong tax). Fixing Payments durability and the charge-correctness bugs is the highest-leverage work.

**Then, the volume/inflow load: Checkout and Search.** These are the two components that grew the most after the release, and their fixes mostly hold (Checkout defects reopen ~6%, Search ~12%), so the goal is to *reduce what comes in*, not to chase rework. For Checkout that means the release regressions and the top feature requests; for Search it means the quality issues (slow autocomplete, broken price filter, zero-result misspellings) and the most-requested features.

**Briefly, capacity.** Tickets created exceed tickets resolved every month and the open backlog has climbed from ~9 to ~135, so throughput needs attention (including the overloaded assignee and the Monday spike). This is secondary to the Payments quality problem.

### Where to start (what the data points to, *not* an assumed fix)

The data names *where* and *which tickets*, not the code-level cause or cure:
- **Payments (primary):** the recurring and reopening tickets in two buckets, charge-correctness (money wrong → top priority): *Card declined but money held*, *Duplicate charge for order #…*, *Refund not processed*; and payment-reliability: *Stripe webhook not received*, *gateway timeout*, *3DS loops*.
- **Checkout and Search (inflow):** Checkout regressions (*Safari checkout button*, *cart empties on refresh*) and features (*Apple Pay*, *guest checkout*, *earlier shipping cost*); Search quality (*autocomplete slow*, *filter by price*, *misspelled returns 0 results*) and features (*in-stock filter*, *related products*, *ranking*).
- **Backlog (brief):** the ~8-month-old Reports/Notifications open tickets, and the Monday / single-overloaded-assignee load.

---

## Next-quarter plan (sequencing)

**Planning assumption** (post-release steady state holds, the known run-rate, not a forecast model): about **250 tickets inbound** per quarter, the open backlog drifts **135 → ~168** if nothing changes, reopens (~12%) rising. Given a finite quarter:

- **Weeks 1-2 (fix first):** the charge-correctness bugs, duplicate charges, declined-but-held, refund-not-processed (Payments), wrong cart totals / tax (Checkout).
- **Across the quarter:** get Payments fixes to stick, then reduce Checkout and Search inflow (clear the regressions and ship one or two top features in each).
- **Continuous and brief:** drain the oldest Reports/Notifications backlog and rebalance the Monday / assignee load.

**Why next quarter:** the regressions and financial bugs are fresh and concentrated right after the release, and the reopen, backlog, and SLA trends are worsening but still bendable now.

---

## Assumptions & caveats

- **No status-history** in the export, so this is a set of current snapshots, we can't analyze *flow* (where tickets get stuck) or build a credible time-series forecast (17 monthly points, a structural break at the release, a flat post-release trend).
- **Productivity** figures aren't adjusted for the difficulty/priority mix each person is assigned; **SLA targets and the pain score are illustrative/relative**, not company SLAs.
- Status labels are not given operational meaning beyond what the data shows (e.g. `Open` is *not* "untouched", 47/48 Open tickets have an assignee).
- **Label cuts cover only the labeled ~60%** of tickets (398 unlabeled); a missing label does not mean the property is absent, and voluntary tagging can bias rates (the 86.5% regression-reopen is *among tickets tagged regression*, possibly inflated). Robust findings are label-independent (component reopen, resolution, recurring `Summary`).
- The dataset is templated/synthetic, trust the **patterns** over the absolute magnitudes.
