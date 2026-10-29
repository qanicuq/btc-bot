#!/usr/bin/env python3
"""
Download Binance spot kline (OHLCV) history for BTCUSDT and ETHUSDT
and merge it into one clean CSV per pair.

Usage:
    python get_binance_data.py            # 1h candles (default)
    python get_binance_data.py 15m        # any interval: 1m 5m 15m 30m 1h 4h 1d ...

Output (in the folder you run it from):
    BTCUSDT_1h.csv
    ETHUSDT_1h.csv

No extra packages needed - standard Python 3 only.
"""
import csv
import datetime as dt
import hashlib
import io
import sys
import urllib.error
import urllib.request
import zipfile

SYMBOLS = ["BTCUSDT", "ETHUSDT"]
INTERVAL = sys.argv[1] if len(sys.argv) > 1 else "1h"
START = dt.date(2017, 8, 1)  # both pairs list from Aug 2017
BASE = "https://data.binance.vision/data/spot"

HEADER = [
    "open_time_ms", "open_time_utc", "open", "high", "low", "close", "volume",
    "close_time_ms", "quote_volume", "trades",
    "taker_buy_base_volume", "taker_buy_quote_volume",
]


def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def to_ms(ts):
    """Binance switched spot timestamps to microseconds on 2025-01-01."""
    ts = int(ts)
    return ts // 1000 if ts > 10**14 else ts


def download_zip(url):
    data = fetch(url)
    if data is None:
        return None
    checksum = fetch(url + ".CHECKSUM")
    if checksum:
        expected = checksum.decode().split()[0]
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError(f"Checksum mismatch: {url}")
    rows = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            with z.open(name) as f:
                for row in csv.reader(io.TextIOWrapper(f, "utf-8")):
                    if row and row[0].isdigit():  # skip any header row
                        rows.append(row)
    return rows


def months(start, end):
    y, m = start.year, start.month
    while (y, m) < (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def main():
    today = dt.datetime.now(dt.timezone.utc).date()
    first_of_month = today.replace(day=1)

    for sym in SYMBOLS:
        print(f"\n== {sym} {INTERVAL} ==")
        candles = {}

        # Finished months: monthly files
        for y, m in months(START, first_of_month):
            url = f"{BASE}/monthly/klines/{sym}/{INTERVAL}/{sym}-{INTERVAL}-{y}-{m:02d}.zip"
            rows = download_zip(url)
            status = "missing" if rows is None else f"{len(rows)} rows"
            print(f"  {y}-{m:02d}: {status}")
            for r in rows or []:
                candles[to_ms(r[0])] = r

        # Current month so far: daily files (yesterday is the latest published)
        d = first_of_month
        while d < today:
            url = f"{BASE}/daily/klines/{sym}/{INTERVAL}/{sym}-{INTERVAL}-{d.isoformat()}.zip"
            rows = download_zip(url)
            if rows:
                print(f"  {d}: {len(rows)} rows")
                for r in rows:
                    candles[to_ms(r[0])] = r
            d += dt.timedelta(days=1)

        out = f"{sym}_{INTERVAL}.csv"
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(HEADER)
            for t in sorted(candles):
                r = candles[t]
                utc = dt.datetime.fromtimestamp(t / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
                w.writerow([t, utc, r[1], r[2], r[3], r[4], r[5],
                            to_ms(r[6]), r[7], r[8], r[9], r[10]])
        print(f"  -> wrote {out} ({len(candles):,} candles)")

    print("\nDone. Attach the CSV files in the Claude chat.")


if __name__ == "__main__":
    main()
