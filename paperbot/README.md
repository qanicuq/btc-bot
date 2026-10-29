# Crypto paper bot (weekly trend)

Paper money only ($1,000 fake). Runs free on GitHub Actions once a day; no Claude.

## The strategy (`trend.py`)
- Coins: **Bitcoin and Ethereum** only (the coins with 8+ years of data behind the backtest). Each gets half the money.
- Five trend votes per coin from daily closes: price above its 100-, 150-, 200- and 250-day average, and price higher than 12 months ago.
- Amount held = (yes votes ÷ 5) × half of that coin's money. So 0%, 10%, 20% … up to 50% of the whole account is ever in coins; the rest sits in cash.
- Decided once a week on Sunday's close, and it only trades when the vote count changes (about 20–25 small trades a year in total).
- Costs charged on every trade: 1.1% per buy or sell (Webull's ~2% round trip).

## Safety
- `control.json`: set `"kill": true` and commit to move everything to cash and stop. Set it back to `false` to restart.
- Phone alert if the account falls 25% below its high. Automatic stop at 50% below its high (worse than anything in the backtest).
- Phone notifications: install the free **ntfy** app and subscribe to the topic stored in the `NTFY_TOPIC` repo secret.

## Backtest (`python -m paperbot.backtest`, uses this repo's Binance data)
Aug 2018 (first date with a full year of history) to Oct 2026, $1,000 start, with costs:

| | End | Return | Per year | Worst drop |
|---|---|---|---|---|
| This strategy | $5,860 | +486% | +24% | −42% |
| Hold $500 of BTC/ETH + $500 cash | $5,849 | +485% | | −72% |
| Hold $1,000 of BTC/ETH | $10,697 | +970% | | −77% |

Same return as keeping half your money in coins, with a much smaller worst drop. It does **not** beat holding coins outright in a bull market.
By year: 2018 −2%, 2019 +16%, 2020 +96%, 2021 +108%, 2022 −16%, 2023 +21%, 2024 +24%, 2025 −1%, 2026 +1% (to Oct).

## Files
- `DASHBOARD.md` — live view. `state.json` — the paper ledger (don't edit). `out/` — chart and summary.
- Replaced the 4-hour bot on 2026-10-10 after its backtest lost 80% since 2018 (too many trades for a 2% cost).
