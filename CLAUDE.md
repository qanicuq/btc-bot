# btc-bot - instructions for Claude

The owner's BTC/ETH backtest data + tooling for his crypto paper-trading bot. Everything runs in the cloud.

## When the owner says "use my btc-bot repo" - ALWAYS refresh the data first
1. Check freshness: newest file in `clean/BTCUSDT/1m/` and its last `open_time_utc`.
   Current = data through the end of **yesterday (UTC)**.
2. If not current, trigger the GitHub Action (`.github/workflows/update-data.yml`):
   write the current UTC timestamp to `.github/refresh-request`, commit
   ("Request data refresh"), `git fetch origin main && git rebase origin/main`, push.
3. Poll `git ls-remote origin refs/heads/main` every ~30s for up to ~10 min until a new
   "Data update ..." commit appears, then fetch/pull and read `.github/update-status.json`
   (`run_utc`, `ok`, `data_through`, `error`) - that's how you see the Action's result.
4. Tell the owner in one line what range the data now covers. If no update landed, say so, and that
   Binance may not have published yesterday's file yet (it usually does within a few hours after
   00:00 UTC) or the Action failed - he can check the repo's Actions tab.
   Never fall back to running anything on his PC unless he asks (his bots stay cloud-based).

Binance (data.binance.vision) is NOT reachable from Claude's cloud workspace - only from GitHub Actions.
`gh` CLI is not authenticated here; plain git push/pull works.

## Using the data
- Load with `scripts/load.py` (`load_1m`, `load_1h`, `resample`) - don't glob files yourself:
  `clean/<SYM>/1m/` holds yearly files (2017-2026) plus small daily files the updater adds.
- Read `clean/README.md` for columns and data quirks. Start backtests in 2018-03 or later.
- Prices are Binance USDT; Webull trades in USD (small differences).

## Rules
- Never commit API keys/secrets (`.gitignore` blocks `.env` etc.).
- Don't rewrite the big yearly `.csv.gz` files (bloats git history); new data goes in daily files.
- `clean/scripts/clean1m.py` / `clean1h.py` are the original PC-side rebuild scripts (they read
  raw zips from `~/mnt/BTC/` on the owner's PC); the cloud updater is `scripts/update_data.py`.

## Weekly 200W SMA alert (`scripts/sma_alert.py`)
Every Saturday 00:15 New York time (15 min after Webull's weekly bar closes) GitHub Actions sends the owner an ntfy push
(topic from the NTFY_TOPIC secret) with BTC/ETH Stop Limit buys: stop = 200-week SMA minus 2% (Webull buy markup), limit = stop + 1% rounded down (Webull's max). Weeks match Webull's
chart: Saturday 00:00 ET boundaries, USD closes from Coinbase hourly candles (Binance USDT fallback). Retries every 15 min
(up to 2 h) until the new week appears; last sent numbers in `scripts/sma_state.json`. Request a run by committing a
timestamp to `.github/sma-request`. Alert only - he places the Webull stop-limit orders by hand.

## Crypto paper bot (`paperbot/`)
Weekly trend strategy on BTC/ETH; runs itself daily on GitHub Actions - no Claude needed. Read `paperbot/README.md`.
Never edit `trend.py` rules/sizing or `state.json` by hand; changes are proposals the owner approves, backtested first
with `python -m paperbot.backtest`.


---

# Coding guidelines

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

---

## The owner's Working Rules (added 2026-10-24)

The owner is not a programmer. Keep explanations plain and solutions simple.

- **Verify before calling it done.** Run it (test, dry run, backtest, or compare output before vs. after) and say exactly how it was checked. Unverified = not done.
- **If a fix feels hacky, scrap it** and write the simple, clean solution instead.
- **If things go sideways, stop and re-plan.** Don't keep pushing a broken approach.
- **Secrets stay secret.** The ntfy topic lives only in a GitHub secret — never in files, commits, or logs.
- **Notifications are ntfy push only.** Never email.
- **Everything runs in the cloud,** never on the owner's computer.
- **Save GitHub Actions minutes** (2,000/month limit): no unneeded runs; put `[skip ci]` in docs-only commit messages.
- **Keep this file short.** Delete rules that no longer matter.

## Lessons Learned

After any correction from the owner, add one line here so the mistake isn't repeated.
Format: `- YYYY-MM-DD: what went wrong → the rule now`

- (none yet)
