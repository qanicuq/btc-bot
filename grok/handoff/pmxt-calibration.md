# Grok Handoff: Polymarket ALL-MARKETS price calibration ("favorite-longshot") - write the code, do NOT run conclusions

Written by Claude for the owner. Follow EXACTLY. Where something is ambiguous, do NOT guess: list the question in the
Review Packet and stop. Claude reviews every output and runs the job itself. Accuracy beats speed.
Report numbers and code only. Do NOT say whether anything "works" or is "profitable".

## What this is
The owner already tested one narrow idea (buying the ~1c side of Bitcoin 5-minute markets). It only "worked" in one odd
two-week stretch (Apr 21 - May 4, 2026) and lost money every other month. Lesson: a pooled number can hide that the
whole result came from a few weeks. This new test asks a broader question over ALL Polymarket markets:

  When a contract trades at price p, does it win more or less often than p? Is there a price/time zone where buying
  it has positive expected value after fees, AND is that true in every month, not just on average?

## Hard rules
- Grok app on SuperGrok only. NEVER use the xAI API or any API key.
- Work in the PUBLIC repo qanicuq/polymarket-btc-backtest. Create a NEW branch `grok-calibration` from `main`.
  Do NOT merge to main. Add new files only; do not edit or delete existing files or workflows.
  READ that repo's `CLAUDE.md` and `scripts/pmxt_fetch.py`, `scripts/backtest.py`, `scripts/coverage.py` first and
  follow them. Key rules from it: never commit secrets; the ntfy topic is NEVER written anywhere (only read from
  `${{ secrets.NTFY_TOPIC }}` into an env var, never echoed); workflows trigger ONLY on `push` to main with a
  `paths:` filter on a request file, `workflow_dispatch`, or `workflow_run` of this repo's own workflows (NEVER
  `pull_request` / `pull_request_target`); at most 6 parallel archive downloads across all workflows; ALWAYS download
  with `pmxt_fetch.fetch()`; never commit parquet or any file over ~5 MB; no email, ever; ONE ntfy push at the end.
- You cannot trigger workflows from a branch; that is expected. Write the code and the workflow; Claude merges and runs it.
- Everything runs in GitHub Actions in the cloud, nothing on the owner's computer.
- Stop after writing the code. Do NOT start any later phase.
- Put your plan, unverified assumptions and deviations in `calibration/README.md`.
- Your Review Packet comes back as ONE copy-ready code block (details at the bottom). Only the packet must be
  copy-ready; the rest of your reply can be as long as you like.

## Verified data facts (from Claude's earlier work; reuse, do not re-derive)
- Archive files: `https://r2v2.pmxt.dev/polymarket_orderbook_YYYY-MM-DDTHH.parquet`, 100-590 MB each, one per hour,
  holding ~85,000 different tokens (outcomes) per hour. Files exist from 2026-04-13T19 to about 2026-09-09 with gaps
  (see `coverage/coverage_*.csv`, column `file` = yes/no). Use only hours where `file` is yes.
- Columns include: timestamp_received, timestamp (exchange ms; the only valid clock), market (condition id),
  event_type (`book`, `price_change`, `last_trade_price`, `tick_size_change`), asset_id (token id), price, size,
  side, best_bid, best_ask, fee_rate_bps. Never use `timestamp_received`. File order is not time order.
- For this task only `event_type == 'last_trade_price'` rows are needed (price = trade price in dollars 0-1,
  size = shares, asset_id = token that was bought). Do NOT rebuild order books. Read only the needed columns and
  filter to `last_trade_price` in Arrow BEFORE converting to pandas. Keep memory under 3 GB per hour.
- Winner of a market comes from the Gamma API (`https://gamma-api.polymarket.com`): `outcomePrices` equal to `"1"` for
  the winner and `"0"` for losers (JSON strings). Token ids are in `clobTokenIds` (a JSON-encoded list, same order
  as `outcomes`). Claude has NOT verified Gamma field names for older, non-crypto markets: write defensively, list
  every field you rely on under UNVERIFIED in the README, and make the script fail loudly (not silently) when a
  field is missing.
- Fees: unresolved for these markets. `fee_rate_bps` on trade rows was 1000 in April and 0 afterward for crypto
  5-minute markets. Read https://docs.polymarket.com/trading/fees and put the per-category taker rates you find in
  `calibration/fees.json` with the URL and date read. Fee per trade = shares x rate x p x (1-p), rounded to 5
  decimals. If a category has no rate in the docs, use gross only for it and say so. ALWAYS report gross and with-fee.

## Design (pre-registered: do not change after seeing data)
1. SAMPLE. Hours 02:00 and 14:00 UTC of every day from 2026-04-14 to 2026-09-09 where the coverage CSVs say the
   file exists (about 280 files). Do not swap or add hours.
2. MARKET TABLE. Build once, resumable: pull every RESOLVED market from Gamma whose `endDate` falls between
   2026-04-14 and 2026-10-15 (page with limit/offset, polite rate limit, retry with backoff), keep: condition id,
   token ids, outcomes, outcomePrices, endDate, category/tags (whatever the API provides), slug, volume.
   Winner = the token whose outcomePrice is exactly `"1"`. Exclude (and COUNT, per month) markets with no clear
   single winner (voided, 50/50, unresolved). Save as `calibration/markets_*.csv(.gz)` if each file < 5 MB,
   otherwise shard or keep it as a workflow artifact and say so.
3. TAPE. For each sampled hour, take EVERY `last_trade_price` row. Join its `asset_id` to the market table. Drop (and
   COUNT) rows whose token is not in the table. Per row compute: price p, shares, cost = shares x p,
   payout = shares if that token won else 0, hours_to_end = (endDate - trade timestamp) in hours (drop and count rows
   where trade time is after endDate).
4. BUCKETS. Price (cents): <=1, 1-2, 2-5, 5-10, 10-20, 20-40, 40-60, 60-80, 80-90, 90-95, 95-98, 98-99, >99.
   Time to end: <1h, 1-6h, 6-24h, 1-7d, 7-30d, >30d. Category: crypto 5-min/15-min "up or down" (slug contains
   `-updown-`) reported SEPARATELY (already studied), plus every other category the API gives. Report the price
   x time-to-end table for ALL non-updown markets together, then per category.
5. PER CELL report: trades, shares, cost, payout, win rate by shares (payout/shares), average price, gross ROI
   (payout/cost - 1), ROI with fee, and the NUMBER OF DISTINCT MARKETS (condition ids) and distinct tokens.
   The real sample size is distinct markets, NOT trades (the two tokens of one market are perfectly opposed, and
   one market produces thousands of trades). Confidence intervals: bootstrap by resampling MARKETS (2,000 draws,
   fixed seed) for ROI; Wilson only for plain win rates by distinct token.
6. STABILITY (this is the point; do not skip). For every cell with at least 200 distinct markets, also report ROI
   with fee by month (Apr, May, Jun, Jul, Aug, Sep) and by pre-registered halves: DISCOVERY = Apr 14 - Jun 30,
   CONFIRM = Jul 1 - Sep 9. Also report the ROI with the single best 2 weeks removed (find the best consecutive
   14 days by P&L, remove them, recompute). A cell only counts as "consistent" if ROI with fee is > 0 in both
   halves and in at least 4 of 6 months; print that flag, but do not interpret it.
7. MULTIPLE TESTING. The grid has ~78 price x time cells. Print the total number of cells tested and, next to each
   cell, its bootstrap p-value that ROI <= 0, and a Bonferroni-adjusted one (x number of cells with >= 200 markets).
8. OUTPUTS: `calibration/RESULTS.md` (human-readable tables), `calibration/results.json` (all numbers), per-month and
   per-half files, all < 5 MB. A summarize step and a final ntfy push (one line: hours processed, markets, trades,
   number of consistent cells) via the NTFY_TOPIC secret.

## Code you must write (new files only)
- `scripts/calib_markets.py` (Gamma market table, resumable, polite).
- `scripts/calib_hour.py HOUR OUTDIR` (one hour -> additive sums by bucket/category/market, so results can be pooled
  later; save per-market sums so the market bootstrap is possible without re-reading parquet; keep files small).
- `scripts/calib_summarize.py OUTDIR` (pool, buckets, bootstrap, stability, writes RESULTS.md / results.json).
- `.github/workflows/calib.yml` (triggers: push to main with `paths: ["requests/calibration"]` and
  `workflow_dispatch`; matrix of weekly chunks, `max-parallel: 4`, `timeout-minutes: 355`; markets job first, then hour
  jobs that commit results to `calibration/hours/` with push/rebase retries like `scripts/run_batch.py`; summarize
  job with `if: always()`; ntfy step).
- Offline unit tests with SYNTHETIC data in `calibration/tests/` for the bucketing, the fee formula, the
  winner join, the hours_to_end calculation and the market bootstrap. Run them if you can and report the result;
  if you cannot run code, say so. Do NOT invent test output.
- Pure Python / pyarrow / numpy only; keep it simple (no framework). Match the style of `scripts/backtest.py`.

## Review Packet (what you give back)
A SINGLE copy-ready code block, plain text, no tables, at most 45 lines, containing: branch and last commit; list of
files written with line counts; whether tests ran and the exact result; the Gamma fields you rely on that are
UNVERIFIED; the fee rates you found per category (with the docs URL); the estimated time and Actions minutes per
hour and for ~280 hours (say how you estimated it); every deviation from this prompt; every open question.
The owner pastes only this block into a new Claude chat.
