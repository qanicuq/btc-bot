"""
Load the clean data. Use this instead of globbing files yourself - the 1m folder holds
yearly files plus small daily files added by the updater, and this stitches them together.

    import sys; sys.path.insert(0, "scripts")
    from load import load_1m, load_1h, resample
    m = load_1m("BTCUSDT", start="2018-03-01")
    h4 = resample(m, "4h")
"""
import glob
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(ROOT, "clean")


def _ms(x):
    return int(pd.Timestamp(x, tz="UTC").value // 10**6)


def load_1m(sym, start=None, end=None):
    """1-minute candles for sym ('BTCUSDT' / 'ETHUSDT'), optional UTC start/end (end exclusive)."""
    files = glob.glob(os.path.join(CLEAN, sym, "1m", f"{sym}_1m_*.csv.gz"))
    if start or end:   # skip files entirely outside the range (names carry the year/day)
        y0 = pd.Timestamp(start).year if start else 0
        y1 = pd.Timestamp(end).year if end else 9999
        files = [f for f in files if y0 <= int(os.path.basename(f).split("_")[2][:4]) <= y1]
    df = pd.concat([pd.read_csv(f) for f in files], ignore_index=True)
    df = df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    if start:
        df = df[df.open_time >= _ms(start)]
    if end:
        df = df[df.open_time < _ms(end)]
    return df.reset_index(drop=True)


def load_1h(sym, start=None, end=None):
    df = pd.read_csv(os.path.join(CLEAN, sym, f"{sym}_1h.csv"))
    if start:
        df = df[df.open_time >= _ms(start)]
    if end:
        df = df[df.open_time < _ms(end)]
    return df.reset_index(drop=True)


def resample(df, rule):
    """Roll 1m (or 1h) candles up to any larger size, e.g. '5min', '15min', '4h', '1D', '1W'."""
    x = df.set_index(pd.to_datetime(df.open_time, unit="ms", utc=True))
    out = x.resample(rule, label="left", closed="left").agg({
        "open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum",
        "quote_volume": "sum", "trades": "sum",
        "taker_buy_base_volume": "sum", "taker_buy_quote_volume": "sum"}).dropna(subset=["open"])
    return out
