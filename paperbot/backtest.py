"""Backtest the live strategy (trend.py) on this repo's Binance BTC/ETH history.

  python -m paperbot.backtest            # 2018-03-01 to the latest data
Needs pandas (only for loading the price files). Prints the summary as JSON.
"""
import json
import math
import os
import sys

from . import trend

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

START = "2018-03-01"
DATA = {"BTCUSD": "BTCUSDT", "ETHUSD": "ETHUSDT"}


def load_daily():
    from load import load_1h, resample
    out = {}
    for coin, sym in DATA.items():
        d = resample(load_1h(sym, start="2016-01-01"), "1D")["close"]
        out[coin] = [(t.to_pydatetime(), float(v)) for t, v in d.items()]
    return out


def run(series, start=START, end=None, size=trend.SIZE):
    eq_by_day, trades = {}, 0
    for coin, rows in series.items():
        sleeve = {"cash": 1000 * trend.SLEEVE, "units": 0.0, "target": 0.0}
        closes = []
        for t, px in rows:
            closes.append(px)
            day = t.strftime("%Y-%m-%d")
            if day < start or (end and day > end):
                continue
            if t.weekday() == trend.REBALANCE_WEEKDAY:
                v = trend.votes(closes)
                if v is not None and abs(v * size - sleeve["target"]) > 1e-9:   # trade only when the votes change
                    trend.rebalance(sleeve, px, v * size)
                    sleeve["target"] = v * size
                    trades += 1
            eq_by_day[day] = eq_by_day.get(day, 0.0) + sleeve["cash"] + sleeve["units"] * px
    days = sorted(eq_by_day)
    eq = [eq_by_day[d] for d in days]
    peak, mdd = eq[0], 0.0
    for e in eq:
        peak = max(peak, e)
        mdd = min(mdd, e / peak - 1)
    yrs = (len(days) - 1) / 365.25
    years = {}
    for d, e in zip(days, eq):
        years.setdefault(d[:4], [None, None])
        years[d[:4]][1] = e
    prev = 1000.0
    by_year = {}
    for y in sorted(years):
        by_year[y] = round((years[y][1] / prev - 1) * 100, 1)
        prev = years[y][1]
    return {"from": days[0], "to": days[-1], "end_equity": round(eq[-1], 2),
            "total_return_pct": round((eq[-1] / 1000 - 1) * 100, 1),
            "per_year_pct": round(((eq[-1] / 1000) ** (1 / yrs) - 1) * 100, 1),
            "worst_drop_pct": round(mdd * 100, 1), "trades": trades,
            "trades_per_year": round(trades / yrs, 1), "by_year_pct": by_year}


if __name__ == "__main__":
    s = load_daily()
    print(json.dumps({"full": run(s), "2018-2022": run(s, end="2022-12-31"),
                      "2023-now": run(s, start="2023-01-01")}, indent=1))
