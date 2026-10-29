=====================================================================
  BTC / ETH BACKTEST DATA  -  READ ME FIRST
  GitHub repo: qanicuq/btc-bot
  Updated with Claude on 2026-10-10
=====================================================================

WHAT THIS IS
------------
Complete Binance price history for Bitcoin (BTCUSDT) and Ethereum
(ETHUSDT), from August 2017 onward, at 1-minute detail. It's for
backtesting the crypto paper-trading bot.

Prices are Binance USDT prices. Webull uses USD, so expect small
differences from Webull, but they're fine for testing a strategy.

Everything lives on GitHub, so it works from any Claude chat - phone,
web or desktop - even when your computer is off.


HOW TO USE IT IN A NEW CHAT
---------------------------
Start any Claude chat and say:

   Use my btc-bot repo and backtest this strategy: <describe it>

Claude will attach the repo, make sure the data is up to date
(through yesterday), and run the backtest.


THE DATA UPDATES ITSELF
-----------------------
A small job on GitHub downloads the newest Binance data every day
(about 11pm Eastern) and saves it to the repo. You don't need to
run anything on your PC.

- Saying "use my btc-bot repo" also triggers an update if the
  data is behind.
- To run it by hand: open the repo on github.com -> "Actions" tab
  -> "Update BTC/ETH data" -> "Run workflow".
- Binance publishes each day's file a few hours after midnight UTC,
  so the newest data is always through YESTERDAY.


WHAT'S IN THE REPO
------------------
clean\                <- THE DATA. Don't edit these files.
  README.md             Technical details: columns, data quirks
  BTCUSDT\1m\           1-minute candles: one file per year up to
                        Oct 9 2026, then one small file per day
  BTCUSDT\BTCUSDT_1h.csv  1-hour candles
  ETHUSDT\ ...          Same layout for Ethereum
  scripts\              Original cleaning/checking scripts
scripts\
  update_data.py        The daily updater (runs on GitHub)
  load.py               How Claude loads the data for backtests
CLAUDE.md               Instructions Claude reads automatically
update_data.ps1         Old PC download script (no longer needed)


THINGS TO REMEMBER
------------------
- Start backtests in March 2018 or later. Binance's earliest data
  has timing quirks and outages.
- Any candle size from 1 minute up (5m, 15m, 1h, 4h, daily, weekly,
  monthly) can be built from the 1-minute files. Just ask Claude.
- Smaller than 1 minute (1-second or tick data) isn't included.
- Your PC's Desktop\BTC folder is now just an old copy. The raw
  Binance zips there aren't in the repo; keep or delete them as
  you like.
