# Grok Handoff: Polymarket "1-cent side" backtest, PHASE A2 (fix + validate, still NOT the full run)

Written by Claude for the owner after reviewing your Phase A Review Packet. Follow EXACTLY. Where something is
ambiguous, do NOT guess: list the question in the Review Packet and stop. Claude reviews every output.
Accuracy beats speed. Do not draw conclusions about whether the strategy "works": report numbers only.

## Hard rules (same as Phase A)
- Grok app on SuperGrok only. NEVER use the xAI API or any API key.
- Create a NEW branch `grok-pmxt-a2` from `main` of qanicuq/btc-bot. Do NOT merge to main. Add new files only;
  do not edit or delete existing files or workflows. Follow CLAUDE.md. Start from your own files on branch
  `grok-pmxt-backtest` (`scripts/pmxt_backtest.py`, `.github/workflows/pmxt-backtest.yml`): copy them to new
  names (`scripts/pmxt_backtest2.py`, `.github/workflows/pmxt-backtest2.yml`, request file
  `.github/pmxt-backtest2-request`). Outputs go in `pmxt_backtest/a2/`.
- Never commit raw parquet or anything over 1 MB. Everything runs in GitHub Actions (cloud). No email, ever.
- ONE ntfy push when the run finishes, topic from the `NTFY_TOPIC` repo secret.
- Stop after Phase A2. Do NOT start Phase B.
- Your Review Packet comes back as ONE copy-ready code block (details at the bottom). Only the packet must be
  copy-ready; the rest of your reply can be as long as you like.

## What Claude verified from your Phase A (facts, not assumptions)
Evidence files on `main`: `pmxt_probe/summary_*.json`, `pmxt_probe/coverage.csv`; code: `scripts/pmxt_probe.py`
(functions `rebuild_eval`, `snap_consistency`, and the batch reader in `diagnose` that keeps each row's file position).
1. COVERAGE: files exist on many days, but the BTC 5-minute windows are only INSIDE the file on some of them.
   Your two empty hours (2026-06-15T15, 2026-07-15T15) were real: zero rows for those 24 tokens AND zero rows for
   their condition ids. See `pmxt_probe/coverage.csv` (`windows_with_data`, 0-12). Usable ranges seen so far:
   Apr 14 - Jun 10 (all 12 windows), gap Jun 13 - Jul 1 (0 windows), Jul 4/7 and Jul 16 - Aug 9 (12), no files
   after Aug 9 in the sample. Only ever test hours that `coverage.csv` says have 12.
2. UPDATE MEANINGS (tested by replaying deltas between consecutive `book` snapshots and comparing to the next one):
   your assumptions were right: `price_change.size` = NEW total size at that price (0 = removed), `side` BUY = bids,
   SELL = asks. The alternatives (size = delta, sides flipped) scored far worse. Applying `last_trade_price` as
   consumption did NOT help (price_change rows already follow trades), so do not apply trades to the book.
3. ORDERING: `timestamp` (ms, exchange time) is the right clock. File order is NOT time order (about 1 in 3
   adjacent rows go backwards). `timestamp_received` is a coarse batch time (~70 rows share one value): never use it.
   Use a STABLE sort on (timestamp, file position). Your `sort_values` default is not stable.
4. THE REBUILT BOOK IS ONLY APPROXIMATE EVEN WHEN DONE RIGHT: level-by-level agreement with the next snapshot was
   68.8% for 2026-05-22T20 and 92.5% for 2026-04-17T12 (best interpretation). Your Phase A book had impossible
   states (best bid = best ask = 0.88 in the sample), i.e. stale levels that the exchange had already removed.
   So the book must NOT be trusted blindly near the top. Fix below.
5. FEES ARE UNRESOLVED: `fee_rate_bps` on the trade rows was 1000 on 2026-04-17T12 and 0 on 2026-05-22T20 for the
   same kind of market, while docs.polymarket.com/trading/fees now says Crypto taker rate 0.07 with
   fee = shares x 0.07 x p x (1-p). Do not decide which is right. Report three views: gross; "docs" fee; and
   the per-hour distribution of `fee_rate_bps` values seen on that hour's trade rows.
6. YOUR PHASE A SCRIPT HAD THESE BUGS (fix all):
   a. It filtered rows to the window BEFORE rebuilding the book, so any token whose last snapshot came before the
      window (we saw -189 s) had NO book for the first ~190 s. Fix: rebuild from ALL rows of the token in the file in
      stable time order, and only look for triggers inside [T, T+300).
   b. Fill timing: you used the first event at/after trigger+L. Use the book AS OF trigger+L (the last event with
      timestamp <= trigger+L); if nothing happened since the trigger, that is the trigger-time book.
   c. Trigger on the exchange's own number: the first `price_change` row inside the window whose reported
      `best_ask` <= P. (Not on your rebuilt best ask.) Then fill from the repaired rebuilt book (below).
   d. Memory/time: do not copy full books for every event. Keep only ask levels <= 0.05 plus the best prices.
      Target <= 60 s and <= 3 GB per hour. Avoid iterrows over millions of rows.
   e. Fees per fill: sum over consumed levels of round(shares_i x 0.07 x p_i x (1-p_i), 5), per docs.

## Required fix: anchor the book to the exchange's own top-of-book numbers
After applying each `price_change` row, use that row's `best_bid` / `best_ask` (exchange-reported, Decimal):
- Delete every rebuilt ask level priced BELOW `best_ask` and every bid level priced ABOVE `best_bid` (stale).
- If `best_ask` is not a level in your book, add it with size `None` (= unknown). Same for `best_bid`.
- Unknown-size levels can NOT be bought from in the simulation (conservative). Count how often the best ask level
  has unknown size when a trigger fires.
- Count and report: % of price_change events where a repair changed anything.

## Tasks, in this order
T1. COVERAGE-SAFE HOURS. Use exactly these 8 hours (all have 12 windows in `coverage.csv`; chosen in advance,
    do not swap): 2026-04-14T14, 2026-04-26T14, 2026-05-08T14, 2026-05-29T14, 2026-06-07T14, 2026-07-19T14,
    2026-07-31T14, 2026-08-09T14.
T2. VALIDATION (report BEFORE any strategy result), per hour and pooled:
    (a) snapshot-to-snapshot level agreement, unrepaired vs repaired (reuse `snap_consistency` logic; for the
        repaired version apply the anchor rule while replaying);
    (b) % of price_change events with top-of-book (best bid AND best ask) equal to the row's numbers after repair,
        and the % of events that needed a repair;
    (c) per-hour distribution of `fee_rate_bps` on `last_trade_price` rows.
T3. BOOK-FREE TAPE TEST (this needs no rebuilt book): take EVERY `last_trade_price` row inside a window with
    price <= P (P = 0.01 and 0.02). A buyer paid that price whichever side was the aggressor. Per (window, token):
    cost = sum(size x price), payout = sum(size) if that token won else 0 (winner from Gamma `outcomePrices`).
    Report pooled over the 8 hours and per hour: number of trades, number of (window, token) pairs with at least
    one such trade (THIS is the real sample size), wins among those pairs, win rate with a 95% Wilson interval,
    ROI = payout/cost - 1 (gross) and with the docs fee. Break-even win rate for reference: 1.0% at 1c, 2.0% at
    2c gross; about 1.07% and 2.14% with the docs fee.
T4. STRATEGY SIMULATION with the fixes, full grid P in {0.01, 0.02}, S in {25, 100} dollars, L in {0, 1, 3} s.
    Report every cell, pooled over the 8 hours: entries, filled, unfilled because size unknown, shares, cost,
    payout, gross P&L, P&L with docs fee, wins, win rate. Also split entries into "supported" (a price_change or
    book row set the size of every consumed level within the previous 10 s) and "other".
    Cap each fill by what the book shows; no extra assumptions.
T5. COST (hard budget). The owner's Actions allowance is about 2,500 minutes/month shared by ALL his private repos
    (his other bots already use some), so budget this whole project at <= 800 minutes per month. Report MEASURED
    minutes per hour (setup + download + processing, from the Action's own timing), then the total for 300 hours
    and for 600 hours. If 600 hours would exceed 800 minutes, say what you would cut (fewer hours, narrower grid)
    and what that lean version costs. Make processing lean: read only the columns you need (`asset_id`, `timestamp`,
    `event_type`, `price`, `size`, `side`, `best_bid`, `best_ask`, `bids`, `asks`), filter to the 24 tokens in Arrow
    BEFORE converting to pandas, and skip any full-file diagnostic pass. For reference, Claude's own coverage scan
    (download + one column read) took about 15 s per hour. Also say whether a separate PUBLIC repo containing no
    secrets (unlimited free minutes) is worth proposing; do NOT create it.
T6. Write `pmxt_backtest/a2/README.md`: assumptions you could not verify, and every deviation from this prompt.

## Review Packet (what you give back)
A SINGLE copy-ready code block, plain text, no tables, at most 45 lines, containing: branch and last commit;
T2 numbers; T3 numbers (pooled P=0.01 and P=0.02: trades, pairs, wins, win rate + interval, ROI gross, ROI with
docs fee); T4 grid in compact lines (one per cell, pooled); T5 estimate; every error; every open question.
The owner pastes only this block into a new Claude chat.
