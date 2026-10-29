"""Weekly 200-week SMA buy-limit alert -> ntfy. Runs on GitHub Actions. No Claude, no orders:
it only sends the owner the numbers to type into Webull.

  python scripts/sma_alert.py [--dry-run]

Matches Webull's weekly bars: Webull weeks end Saturday 00:00 New York time, priced in USD.
Each week's close = the last hourly USD close before that Saturday midnight (Coinbase BTC-USD /
ETH-USD; Binance USDT as a fallback). Webull's own data can't be read from GitHub, so expect the
result to be within a few dollars of Webull's chart, not identical.

Runs at 00:15 Saturday New York time. If the new week isn't in the data yet (SMA unchanged from
last week), it waits 15 minutes and tries again, up to 2 hours.
"""
import argparse
import json
import os
import pathlib
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

COINS = ("BTC", "ETH")
WEEKS = 200
DISCOUNT = 0.02          # limit 2% under the SMA to cover Webull's buy spread/markup (no commission)
TOPIC = os.environ.get("NTFY_TOPIC")
UA = {"User-Agent": "sma-alert/2.0"}
NY = ZoneInfo("America/New_York")
STATE = pathlib.Path(__file__).with_name("sma_state.json")
RETRY_MIN, MAX_TRIES = 15, 9


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
        return json.load(r)


def week_ends(now):
    """The last WEEKS Saturday-00:00-New-York boundaries (as UTC), newest first."""
    ny = now.astimezone(NY)
    sat = (ny - timedelta(days=(ny.weekday() - 5) % 7)).replace(hour=0, minute=0, second=0, microsecond=0)
    ends = []
    while len(ends) < WEEKS:
        ends.append(sat.astimezone(timezone.utc))
        sat = (sat.replace(tzinfo=None) - timedelta(days=7)).replace(tzinfo=NY)  # stays midnight across DST
    return ends


def coinbase_hourly(coin, start, end):
    out, s = {}, start
    while s < end:
        e = min(s + timedelta(hours=300), end)
        for t, lo, hi, op, cl, v in _get(f"https://api.exchange.coinbase.com/products/{coin}-USD/candles?granularity=3600"
                                         f"&start={s:%Y-%m-%dT%H:%M:%SZ}&end={e:%Y-%m-%dT%H:%M:%SZ}"):
            out[int(t)] = float(cl)
        s = e
        time.sleep(0.15)
    return out


def binance_hourly(coin, start, end):
    out, s = {}, int(start.timestamp() * 1000)
    while s < end.timestamp() * 1000:
        rows = _get(f"https://data-api.binance.vision/api/v3/klines?symbol={coin}USDT&interval=1h&startTime={s}&limit=1000")
        if not rows:
            break
        for r in rows:
            out[r[0] // 1000] = float(r[4])
        s = rows[-1][0] + 3600_000
    return out


def sma_for(coin, now):
    ends = week_ends(now)
    errs = []
    for name, fn in (("Coinbase USD", coinbase_hourly), ("Binance USDT", binance_hourly)):
        try:
            hours = fn(coin, ends[-1] - timedelta(hours=2), ends[0])
            closes = []
            for e in ends:  # close of the hourly candle that ends at the week boundary
                c = hours.get(int((e - timedelta(hours=1)).timestamp()))
                if c is None:
                    raise RuntimeError(f"missing hour before {e:%Y-%m-%d %H:%M} UTC")
                closes.append(c)
            return sum(closes) / WEEKS, name, ends[0]
        except Exception as ex:
            errs.append(f"{name}: {ex}")
    raise RuntimeError(f"{coin}: {'; '.join(errs)}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    try:
        last = json.loads(STATE.read_text())
    except Exception:
        last = {}

    for attempt in range(1, MAX_TRIES + 1):
        now = datetime.now(timezone.utc)
        results, errors = {}, []
        for coin in COINS:
            try:
                results[coin] = sma_for(coin, now)
            except Exception as ex:
                errors.append(f"{coin}: FAILED - {ex}")
        week = max((r[2] for r in results.values()), default=None)
        if week is not None and last.get("week_end") == week.isoformat():
            print("This week's alert was already sent.")
            return
        unchanged = bool(results) and all(round(r[0], 2) == last.get(c) for c, r in results.items())
        if (unchanged or errors) and attempt < MAX_TRIES:
            print(f"Try {attempt}: {'unchanged' if unchanged else errors}; waiting {RETRY_MIN} min")
            time.sleep(RETRY_MIN * 60)
            continue
        break

    ok = not errors
    lines = [f"{c}: buy limit ${r[0] * (1 - DISCOUNT):,.2f}  (200W SMA ${r[0]:,.2f}, {r[1]})" for c, r in results.items()]
    lines += errors
    if week:
        lines.append(f"Weeks ending {week.astimezone(NY):%a %b %d} 12:00 AM ET, like Webull's weekly chart.")
    lines.append("Cancel last week's unfilled buys in Webull before placing the new ones.")
    title = "200W SMA buy limits (2% under)" if ok else "200W SMA alert: problem"
    body = "\n".join(lines)
    print(title, body, sep="\n")
    if a.dry_run:
        return
    if not TOPIC:
        raise SystemExit("NTFY_TOPIC secret is not set")
    urllib.request.urlopen(urllib.request.Request(
        f"https://ntfy.sh/{TOPIC}", data=body.encode(),
        headers={"Title": title, "Tags": "moneybag" if ok else "warning", **UA}), timeout=15).read()
    if not ok:
        raise SystemExit(1)
    STATE.write_text(json.dumps({"week_end": week.isoformat(), **{c: round(r[0], 2) for c, r in results.items()}}))


if __name__ == "__main__":
    main()
