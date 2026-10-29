#!/usr/bin/env python3
"""
Bring the clean BTC/ETH data up to date from data.binance.vision.

- Finds the newest 1-minute candle already in clean/<SYM>/1m/
- Downloads every missing *finished* UTC day (Binance daily zips, checksum-verified)
- Writes each new day as its own small file: clean/<SYM>/1m/<SYM>_1m_YYYY-MM-DD.csv.gz
  (small daily files keep the git history small - big yearly files are never rewritten)
- Appends the matching 1-hour candles to clean/<SYM>/<SYM>_1h.csv

Run from the repo root:  python scripts/update_data.py
Needs: pandas. Runs daily on GitHub Actions (.github/workflows/update-data.yml).
"""
import datetime as dt
import glob
import hashlib
import io
import os
import sys
import time
import urllib.error
import urllib.request
import zipfile

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(ROOT, "clean")
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
BASE = "https://data.binance.vision/data/spot/daily/klines"
RAW_COLS = ["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume",
            "trades", "taker_buy_base_volume", "taker_buy_quote_volume", "ignore"]
FLOATS = ["open", "high", "low", "close", "volume", "quote_volume",
          "taker_buy_base_volume", "taker_buy_quote_volume"]
OUT_COLS = ["open_time", "open_time_utc", "open", "high", "low", "close", "volume", "close_time",
            "quote_volume", "trades", "taker_buy_base_volume", "taker_buy_quote_volume"]


def fetch(url, tries=4):
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if i == tries - 1:
                raise
        except urllib.error.URLError:
            if i == tries - 1:
                raise
        time.sleep(5 * (i + 1))


def download_day(sym, day):
    """Return a raw DataFrame for one UTC day, or None if Binance hasn't published it yet."""
    url = f"{BASE}/{sym}/1m/{sym}-1m-{day.isoformat()}.zip"
    data = fetch(url)
    if data is None:
        return None
    chk = fetch(url + ".CHECKSUM")
    if chk and hashlib.sha256(data).hexdigest() != chk.decode().split()[0]:
        raise RuntimeError(f"Checksum mismatch: {url}")
    parts = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            parts.append(pd.read_csv(z.open(n), header=None, names=RAW_COLS, dtype={0: str}))
    return pd.concat(parts, ignore_index=True)


def clean(df):
    """Same rules as clean/scripts/clean1m.py."""
    df = df[df.open_time.astype(str).str.fullmatch(r"\d+", na=False)].copy()
    t = df.open_time.astype("int64")
    t = t.where(t < 10**14, t // 1000)          # Binance switched to microseconds in 2025
    df["open_time"] = t // 60000 * 60000
    df["close_time"] = df.open_time + 59999
    df = df.drop(columns="ignore")
    for c in FLOATS:
        df[c] = df[c].astype("float64")
    df["trades"] = df.trades.astype("int64")
    df = df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    df.insert(1, "open_time_utc",
              pd.to_datetime(df.open_time, unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M"))
    bad = ((df.high < df[["open", "close"]].max(axis=1)) |
           (df.low > df[["open", "close"]].min(axis=1)) | (df.low <= 0)).sum()
    if bad:
        raise RuntimeError(f"{bad} candles failed high/low sanity checks")
    return df[OUT_COLS]


def last_open_time(sym):
    """Newest 1m open_time on disk (checks the newest-named files only)."""
    files = sorted(glob.glob(os.path.join(CLEAN, sym, "1m", f"{sym}_1m_*.csv.gz")),
                   key=lambda p: os.path.basename(p).replace(".csv.gz", ""))
    best = 0
    for f in files[-3:]:
        best = max(best, int(pd.read_csv(f, usecols=["open_time"]).open_time.max()))
    return best


def to_hours(m):
    m = m.assign(hr=m.open_time // 3600000 * 3600000)
    h = m.groupby("hr").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
        volume=("volume", "sum"), quote_volume=("quote_volume", "sum"), trades=("trades", "sum"),
        taker_buy_base_volume=("taker_buy_base_volume", "sum"),
        taker_buy_quote_volume=("taker_buy_quote_volume", "sum")).reset_index()
    h = h.rename(columns={"hr": "open_time"})
    h["open_time_utc"] = pd.to_datetime(h.open_time, unit="ms", utc=True).dt.strftime("%Y-%m-%d %H:%M")
    h["close_time"] = h.open_time + 3599999
    return h[OUT_COLS]


def update(sym, today=None, downloader=download_day):
    today = today or dt.datetime.now(dt.timezone.utc).date()
    last = last_open_time(sym)
    day = (dt.datetime.fromtimestamp(last / 1000, dt.timezone.utc) + dt.timedelta(minutes=1)).date()
    new = []
    while day < today:                          # only finished UTC days
        raw = downloader(sym, day)
        if raw is None:
            print(f"  {sym} {day}: not published yet - stopping here")
            break
        df = clean(raw)
        df = df[df.open_time > last]
        if len(df):
            p = os.path.join(CLEAN, sym, "1m", f"{sym}_1m_{day.isoformat()}.csv.gz")
            df.to_csv(p, index=False, compression={"method": "gzip", "compresslevel": 6, "mtime": 0})
            new.append(df)
            print(f"  {sym} {day}: {len(df)} candles")
        day += dt.timedelta(days=1)
    n = sum(len(d) for d in new)
    print(f"  {sym}: +{n} new 1m candles" if n else f"  {sym}: 1m already up to date")
    sync_1h(sym)
    return n


def sync_1h(sym):
    """Append any hours the 1h file is missing, built from the daily 1m files (self-healing)."""
    hp = os.path.join(CLEAN, sym, f"{sym}_1h.csv")
    h_old = pd.read_csv(hp)
    start = int(h_old.open_time.max()) + 3600000
    start_day = dt.datetime.fromtimestamp(start / 1000, dt.timezone.utc).date().isoformat()
    daily = [f for f in glob.glob(os.path.join(CLEAN, sym, "1m", f"{sym}_1m_????-??-??.csv.gz"))
             if os.path.basename(f)[len(sym) + 4:len(sym) + 14] >= start_day]
    if not daily:
        return
    m = pd.concat([pd.read_csv(f) for f in daily], ignore_index=True)
    m = m[m.open_time >= start]
    if not len(m):
        return
    h = pd.concat([h_old, to_hours(m)], ignore_index=True)
    h.to_csv(hp, index=False)
    print(f"  {sym}: 1h now ends {h.open_time_utc.iloc[-1]}")


def write_status(status):
    import json
    p = os.path.join(ROOT, ".github", "update-status.json")
    with open(p, "w") as f:
        json.dump(status, f, indent=2)
        f.write("\n")


def main():
    status = {"run_utc": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M"),
              "ok": False, "new_1m_candles": 0, "data_through": {}, "error": None}
    try:
        # connectivity check even when nothing is missing
        probe = (dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=3)).isoformat()
        if fetch(f"{BASE}/BTCUSDT/1m/BTCUSDT-1m-{probe}.zip.CHECKSUM") is None:
            raise RuntimeError("Binance probe file missing")
        for sym in SYMBOLS:
            print(f"== {sym}")
            status["new_1m_candles"] += update(sym)
            last = last_open_time(sym)
            status["data_through"][sym] = dt.datetime.fromtimestamp(
                last / 1000, dt.timezone.utc).strftime("%Y-%m-%d %H:%M")
        status["ok"] = True
    except Exception as e:  # recorded in the status file so Claude can see it
        status["error"] = f"{type(e).__name__}: {e}"
        print("ERROR", status["error"])
    write_status(status)
    print(f"Done: {status}")
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
