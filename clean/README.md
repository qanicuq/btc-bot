# BTC / ETH historical data (Binance spot, USDT pairs)

Built 2026-10-10 from data.binance.vision. Coverage: 2017-08-17 04:00 UTC to 2026-10-09 23:59 UTC.

## Files
- `BTCUSDT/1m/BTCUSDT_1m_YYYY.csv.gz` and `ETHUSDT/1m/...` - 1-minute candles, one gzip CSV per year
  (~4.78 million rows per coin). This is the master data: every larger candle size can be built from it.
- `BTCUSDT/BTCUSDT_1h.csv`, `ETHUSDT/ETHUSDT_1h.csv` - 1-hour candles (80,053 rows each).

## Columns
open_time is in milliseconds (UTC) for every row - the 2025 switch to microseconds has been fixed.
open_time, open_time_utc, open, high, low, close, volume (BTC or ETH), close_time,
quote_volume (USDT), trades, taker_buy_base_volume, taker_buy_quote_volume

Load in Python: `pd.read_csv("BTCUSDT/1m/BTCUSDT_1m_2024.csv.gz")`

## Known data quirks (real Binance outages, not errors)
- Missing minutes: concentrated in 2017-2021 (largest: 2018-02-08/09, ~33 hours). 2022, 2024, 2025, 2026 are complete.
- Dec 2017 - Feb 2018: Binance's raw 1-minute candles were offset by 15-21 seconds; they have been snapped to whole minutes.
  Because of these early quirks, 1m and 1h data disagree on some hours before March 2018. Prefer data from 2018-03 onward.
- In the 1h files, 43 candles after the Feb 2018 outage start at :28 past the hour (left as Binance published them).
- From March 2018 on, 1m candles rolled up to hours match the 1h files exactly on price; about 40 hours per coin
  differ slightly in volume (~0.08%), which comes from Binance's own files.
- No duplicate candles; every row passed high/low sanity checks.

## Updates
New days are added automatically by `scripts/update_data.py` (GitHub Actions, daily) as small files
`1m/<SYM>_1m_YYYY-MM-DD.csv.gz` after the yearly files end (2026-10-09). Load with `scripts/load.py`.
