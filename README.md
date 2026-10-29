# btc-bot

Backtest data and tooling for the crypto paper-trading bot (BTC & ETH).

## What's here
- `clean/` - **the data to use.** Binance spot BTCUSDT / ETHUSDT history, Aug 2017 to Oct 9 2026.
  - `clean/<SYM>/1m/<SYM>_1m_<YEAR>.csv.gz` - 1-minute candles, one file per year (master data)
  - `clean/<SYM>/<SYM>_1h.csv` - 1-hour candles
  - `clean/README.md` - columns and known data quirks (read this first)
  - `clean/scripts/` - cleaning / verification scripts
- `scripts/update_data.py` - cloud updater; runs daily via GitHub Actions (`.github/workflows/update-data.yml`)
  and adds one small 1m file per new day plus new 1h rows.
- `scripts/load.py` - `load_1m`, `load_1h`, `resample` - use these to read the data.
- `README.txt` - plain-English guide. `CLAUDE.md` - instructions Claude reads automatically.
- `update_data.ps1` - old PC-side download script (no longer needed).

Not in the repo (kept on the PC only): the raw monthly Binance zips in `BTCUSDT-1m/` and `ETHUSDT-1m/`.
They're inputs to `clean/scripts/clean1m.py`, which currently reads them from `~/mnt/BTC/`.

## Notes
- Start backtests in **March 2018 or later** (earlier Binance data has timing quirks/outages).
- Prices are USDT; Webull trades in USD, so expect small differences.
- No API keys belong in this repo. Put secrets in environment variables / scheduled-task settings.
