# Grok Handoff: Polymarket "1-cent side" backtest (PHASE A = test only)

Written by Claude for the owner. Follow EXACTLY. Where anything is ambiguous, do NOT guess: list the
question in the Review Packet and stop. Claude reviews every output. Accuracy beats speed.

## Hard rules
- Use the Grok app on SuperGrok only. NEVER use the xAI API or any API key.
- Work on a new branch `grok-pmxt-backtest` of qanicuq/btc-bot. Do NOT merge to main. Do NOT edit
  or delete existing files or workflows (add new files only). Follow CLAUDE.md in the repo root.
- Never commit raw parquet files, secrets, or anything over 1 MB. Everything runs in GitHub Actions
  (cloud). Nothing runs on the owner's PC. No email notifications, ever.
- Send ONE ntfy push when a run finishes (success or failure) to the topic in the `NTFY_TOPIC` repo secret.
- Report bad or boring results plainly. No cherry-picking. Do not tune settings on the test hours.
- Stop after PHASE A. Do not start PHASE B until Claude approves.

## The question
Some Polymarket "Bitcoin Up or Down" 5-minute markets briefly trade one side at about 1 cent
(pays $1 if it wins). A viral post claims a wallet profits by buying those. Using archived order-book
data, measure whether "buy the ~1 cent side" earns money after realistic fills.

## Data (free, public, no key)
- Hour files: `https://r2v2.pmxt.dev/polymarket_orderbook_YYYY-MM-DDTHH.parquet` (UTC hour, 100-400 MB).
  Download in the Action only; delete after use. Files exist for most days Apr 14 - Jul 31, 2026;
  Aug-Oct is patchy; Feb-Mar absent. Start from `scripts/pmxt_probe.py` in the repo (it already does
  download, Gamma lookups, and filtering and has worked in Actions).
- Columns seen: timestamp_received, timestamp (ms UTC), market, event_type, asset_id (token id string),
  bids, asks (JSON strings of [price,size] pairs, on `book` rows only; list order is NOT sorted
  best-first, so compute min/max yourself), price, size, side (BUY/SELL), best_bid, best_ask,
  fee_rate_bps, transaction_hash.
- event_type values: `book` (full snapshot), `price_change` (level update; size is believed to be the
  NEW total size at that price, 0 = level removed), `last_trade_price` (an actual trade).
  THESE MEANINGS ARE ASSUMPTIONS. Verify them against the data in Phase A and report what you find.
- Known oddity: `timestamp_received` can lag `timestamp` by seconds to minutes on `book` rows.
  Phase A must test both orderings (by `timestamp`, by `timestamp_received`) and report which one
  rebuilds the book consistently.
- Windows: slug `btc-updown-5m-{T}`, T = unix start time, a multiple of 300; the window is [T, T+300).
  Look up with `https://gamma-api.polymarket.com/events?slug=SLUG`: `markets[0].clobTokenIds` (JSON string,
  order matches `outcomes`, e.g. ["Up","Down"]) and `outcomePrices` (JSON string; winner = "1", e.g.
  ["1","0"] means Up won). Use only closed markets.

## Strategy to simulate (fixed; do not change)
For each window and each of its two tokens, in the window [T, T+300) only:
1. Rebuild that token's order book from `book` snapshots plus `price_change` updates.
2. Entry trigger: the first moment the best ask is <= P and at least 1 share is available at <= P.
3. Fill: after a delay L, buy from the book as it stands at (trigger time + L). Spend up to a budget S,
   taking asks at prices <= P only, level by level. Partial fills are allowed. Unfilled = no trade.
   One entry per token per window.
4. Payout: shares x $1 if that token won, else $0. P&L = payout - cost - fees.
5. Fees: look up Polymarket's current documented fee rule for these markets (docs.polymarket.com),
   implement it as documented, and cite the page in the packet. Also report P&L with zero fees.
   Do not invent a formula. If you cannot find it, report gross only and say so.
Settings grid (all combinations, report ALL of them): P in {0.01, 0.02}; S in {$25, $100};
L in {0 s, 1 s, 3 s}.

## PHASE A (test only): what to build and run
Add: `scripts/pmxt_backtest.py`, `.github/workflows/pmxt-backtest.yml` (manual trigger via a request
file `.github/pmxt-backtest-request`, same pattern as `.github/workflows/pmxt-probe.yml`), outputs in
`pmxt_backtest/phaseA/` (`summary.json`, `entries.csv`, `checks.md`). Run on exactly these 3 hours:
`2026-05-22T20`, `2026-06-15T15`, `2026-07-15T15`.

Checks that MUST appear in the results:
1. Each hour: windows found (expect 12), all closed with a winner, errors = none.
2. Book check: for `price_change` rows, how often does YOUR rebuilt best bid/ask match the row's
   `best_bid`/`best_ask` columns (exact, and within 0.01)? Do this for both orderings.
3. Trade check: count `last_trade_price` rows at <= P, and compare with how many of your simulated
   entries had a real trade at about that price within +/-5 s (sanity check on fillability).
4. Per setting (P, S, L): entries, fills, shares, cost, payout, P&L, win rate, with and without fees.
5. One fully worked example entry: timestamps, book levels consumed, cost, shares, winner, P&L.
6. Runtime and peak memory per hour, plus an estimate of total Actions minutes for 400 hours.
   Also state whether the repo is public or private, because private repos have a monthly free-minutes cap.
7. A plain list of everything you assumed and could not verify.

## Review Packet (what you give back)
A SINGLE copy-ready code block, at most 40 lines, plain text, no tables, containing: branch name and
last commit; the 7 items above in short form (numbers, not prose); every error; every open question.
The owner pastes only this block into a new Claude chat. Everything outside the block may be as long as
you like, but only the block needs to be copy-ready.
