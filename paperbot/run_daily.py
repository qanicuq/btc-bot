"""Daily paper run on GitHub Actions. No Claude involved. PAPER ONLY: nothing here can place a real order.

  python -m paperbot.run_daily [--no-notify]

Every day: fetch completed daily candles (Kraken, Coinbase as fallback), value the paper account,
update DASHBOARD.md. Once a week (Sunday's close) it re-checks the trend votes and trades only if they changed.
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

from . import trend

HERE = os.path.dirname(os.path.abspath(__file__))
STATE = os.path.join(HERE, "state.json")
CONTROL = os.path.join(HERE, "control.json")
OUT = os.path.join(HERE, "out")
UA = {"User-Agent": "paperbot/2.0"}
ALERT_DRAWDOWN = -0.25        # phone alert when the account is 25% below its high
AUTO_STOP_DRAWDOWN = -0.50    # beyond the backtest's worst (-42%): something is wrong, go to cash and stop


def _get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
        return json.load(r)


def kraken_daily(coin):
    base = coin[:-3]
    pair = ("XBT" if base == "BTC" else base) + "USD"
    d = _get(f"https://api.kraken.com/0/public/OHLC?pair={pair}&interval=1440")
    if d.get("error"):
        raise RuntimeError(f"Kraken: {d['error']}")
    key = next(k for k in d["result"] if k != "last")
    return [(int(r[0]), float(r[4])) for r in d["result"][key]]     # (day open unix s, close)


def coinbase_daily(coin):
    prod = coin[:-3] + "-USD"
    end = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    rows = {}
    for k in range(3):          # 3 x 300 days
        e = end - timedelta(days=300 * k)
        s = e - timedelta(days=300)
        for t, lo, hi, op, cl, v in _get(f"https://api.exchange.coinbase.com/products/{prod}/candles?granularity=86400"
                                         f"&start={s:%Y-%m-%dT%H:%M:%SZ}&end={e:%Y-%m-%dT%H:%M:%SZ}"):
            rows[int(t)] = float(cl)
    return sorted(rows.items())


def completed_closes(coin, now):
    errs = []
    for name, fn in (("Kraken", kraken_daily), ("Coinbase", coinbase_daily)):
        try:
            rows = [(datetime.fromtimestamp(t, timezone.utc), c) for t, c in fn(coin)]
            rows = [r for r in rows if r[0] + timedelta(days=1) <= now]        # drop today's unfinished candle
            if len(rows) >= trend.MIN_HISTORY:
                return rows, name
            errs.append(f"{name}: only {len(rows)} days")
        except Exception as ex:
            errs.append(f"{name}: {ex}")
    raise RuntimeError(f"no daily prices for {coin} ({'; '.join(errs)})")


def notify(topic, title, body, tags="chart_with_upwards_trend"):
    if not topic:
        return
    try:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=body.encode(), headers={"Title": title, "Tags": tags, **UA})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as ex:
        print("notify failed:", ex, file=sys.stderr)


def money(x):
    return f"${x:,.2f}"


def new_state(now):
    return {"version": 2, "started": now.strftime("%Y-%m-%d"), "starting_equity": 1000.0,
            "sleeves": {c: {"cash": 1000.0 * trend.SLEEVE, "units": 0.0, "target": 0.0} for c in trend.COINS},
            "last_rebalance_day": None, "equity_curve": [], "trades": [], "peak": 1000.0,
            "stopped": {"on": False, "reason": "", "at": None}, "alerted_drawdown": False}


def equity(state, prices):
    return sum(s["cash"] + s["units"] * prices[c] for c, s in state["sleeves"].items())


def go_to_cash(state, prices, day, reason):
    for c, s in state["sleeves"].items():
        if s["units"] > 0:
            usd = trend.rebalance(s, prices[c], 0.0)
            state["trades"].append({"day": day, "coin": c, "usd": round(usd, 2), "price": prices[c], "why": reason})
        s["target"] = 0.0


def svg(curve, path):
    vals = [e for _, e in curve][-730:] or [1000.0]
    if len(vals) == 1:
        vals = vals * 2
    w, h, p = 640, 160, 8
    lo, hi = min(vals + [1000.0]), max(vals + [1000.0])
    if hi - lo < 1:
        lo, hi = lo - 5, hi + 5
    X = lambda i: p + i * (w - 2 * p) / (len(vals) - 1)
    Y = lambda v: h - p - (v - lo) * (h - 2 * p) / (hi - lo)
    pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vals))
    with open(path, "w") as f:
        f.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}">'
                f'<rect width="{w}" height="{h}" fill="#fff"/>'
                f'<line x1="{p}" x2="{w-p}" y1="{Y(1000):.1f}" y2="{Y(1000):.1f}" stroke="#bbb" stroke-dasharray="4 4"/>'
                f'<polyline points="{pts}" fill="none" stroke="#1f6feb" stroke-width="2"/>'
                f'<text x="{p}" y="14" font-family="sans-serif" font-size="11" fill="#555">high {money(hi)}</text>'
                f'<text x="{p}" y="{h-2}" font-family="sans-serif" font-size="11" fill="#555">low {money(lo)}</text></svg>')


def track_cost(state, s, units_before, usd):
    """Average-cost bookkeeping so each sell has a realized profit/loss (fees included)."""
    fee = abs(usd) * trend.COST_PER_SIDE
    if usd > 0:
        s["cost"] = s.get("cost", 0.0) + usd + fee
    elif usd < 0 and units_before > 0:
        sold_share = (units_before - s["units"]) / units_before
        cost_sold = s.get("cost", 0.0) * sold_share
        s["cost"] = s.get("cost", 0.0) - cost_sold
        state.setdefault("closed_pl", []).append(round(-usd - fee - cost_sold, 2))


def max_drawdown(curve):
    """Worst drop from a high to a later low in the daily equity curve, as a negative fraction."""
    peak, worst = 0.0, 0.0
    for _, v in curve:
        peak = max(peak, v)
        worst = min(worst, v / peak - 1)
    return worst


def dashboard(state, prices, detail, day, src, path):
    e = equity(state, prices)
    dd = e / state["peak"] - 1
    invested = sum(s["units"] * prices[c] for c, s in state["sleeves"].items())
    L = ["# Crypto paper bot (weekly trend)", "",
         f"Paper money only. Prices through **{day}** (daily close, UTC). Checks daily, trades only on Sunday's close if the trend votes changed. Runs free on GitHub Actions.", "",
         "![equity](out/equity.svg)", "",
         "| Paper account | Since start | From its high | Worst drawdown | In coins | Status |", "|---|---|---|---|---|---|",
         f"| {money(e)} | {(e/state['starting_equity']-1)*100:+.2f}% | {dd*100:.1f}% | {max_drawdown(state['equity_curve'])*100:.1f}% | {money(invested)} ({invested/e*100:.0f}%) | "
         f"{'STOPPED: ' + state['stopped']['reason'] if state['stopped']['on'] else 'running'} |", "",
         "## Trend votes (5 per coin)", "", "| Coin | Price | 100d | 150d | 200d | 250d | 12-month | Target in coin |", "|---|---|---|---|---|---|---|---|"]
    for c in trend.COINS:
        d = detail[c]
        yn = lambda k: "yes" if d[k] else "no"
        L.append(f"| {c} | {money(prices[c])} | {yn('above_100d_avg')} | {yn('above_150d_avg')} | {yn('above_200d_avg')} | "
                 f"{yn('above_250d_avg')} | {yn('up_over_12_months')} | {state['sleeves'][c]['target']*100:.0f}% of its half |")
    pls = state.get("closed_pl", [])
    L += ["", f"Expectancy (average profit/loss per sell, fees included): "
          + (f"{money(sum(pls) / len(pls))} over {len(pls)} sells" if pls else "n/a (no sells yet)")]
    L += ["", "## Last 10 trades", ""]
    if state["trades"]:
        L += ["| Day | Coin | Bought (+) / sold (−) | Price | Why |", "|---|---|---|---|---|"]
        for t in reversed(state["trades"][-10:]):
            L.append(f"| {t['day']} | {t['coin']} | {money(t['usd'])} | {money(t['price'])} | {t['why']} |")
    else:
        L.append("None yet.")
    L += ["", f"Prices from {src}. Costs modelled at Webull's ~1.1% per buy or sell.",
          "Stop it: set `\"kill\": true` in `paperbot/control.json` and commit. Backtest: `python -m paperbot.backtest`."]
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-notify", action="store_true")
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    control = json.load(open(CONTROL))
    topic = None if a.no_notify else os.environ.get("NTFY_TOPIC")
    state = json.load(open(STATE)) if os.path.exists(STATE) else new_state(now)
    os.makedirs(OUT, exist_ok=True)

    try:
        data, srcs = {}, {}
        for c in trend.COINS:
            data[c], srcs[c] = completed_closes(c, now)
    except Exception as ex:
        notify(topic, "Paper bot: skipped today", f"Couldn't get prices, nothing changed. {ex}"[:400], "warning")
        print("FETCH FAILED:", ex, file=sys.stderr)
        return 1

    last_day = min(rows[-1][0] for rows in data.values())          # latest day both coins have
    for c in data:
        data[c] = [r for r in data[c] if r[0] <= last_day]
    day = last_day.strftime("%Y-%m-%d")
    prices = {c: rows[-1][1] for c, rows in data.items()}
    closes = {c: [x for _, x in rows] for c, rows in data.items()}
    detail = {c: trend.vote_detail(closes[c]) for c in trend.COINS}
    events = []

    # manual stop / restart
    if control.get("kill") and not state["stopped"]["on"]:
        go_to_cash(state, prices, day, "stopped by you")
        state["stopped"] = {"on": True, "reason": "stopped by you (control.json)", "at": day}
        events.append("Stopped by you: everything moved to cash.")
    elif not control.get("kill") and state["stopped"]["on"] and state["stopped"]["reason"].startswith("stopped by you"):
        state["stopped"] = {"on": False, "reason": "", "at": None}
        state["last_rebalance_day"] = None            # re-check votes right away
        events.append("Restarted by you.")

    # weekly decision: the most recent Sunday on or before the latest close, if not done yet
    back = (last_day.weekday() - trend.REBALANCE_WEEKDAY) % 7
    sunday = (last_day - timedelta(days=back)).strftime("%Y-%m-%d")
    if not state["stopped"]["on"] and (state["last_rebalance_day"] or "") < sunday:
        for c in trend.COINS:
            v = trend.votes(closes[c])
            s = state["sleeves"][c]
            tgt = v * trend.SIZE
            if abs(tgt - s["target"]) > 1e-9:
                units_before = s["units"]
                usd = trend.rebalance(s, prices[c], tgt)
                track_cost(state, s, units_before, usd)
                yes = int(round(v * 5))
                why = f"{yes}/5 trend votes"
                state["trades"].append({"day": day, "coin": c, "usd": round(usd, 2), "price": prices[c], "why": why})
                events.append(f"{'Bought' if usd > 0 else 'Sold'} {money(abs(usd))} of {c[:-3]} at {money(prices[c])} ({why})")
                s["target"] = tgt
        state["last_rebalance_day"] = sunday
        weekly = True
    else:
        weekly = False

    e = equity(state, prices)
    state["peak"] = max(state["peak"], e)
    dd = e / state["peak"] - 1
    if dd <= AUTO_STOP_DRAWDOWN and not state["stopped"]["on"]:
        go_to_cash(state, prices, day, "auto-stop")
        state["stopped"] = {"on": True, "reason": f"auto-stop at {dd:.0%} from the high", "at": day}
        events.append(f"AUTO-STOP: account {dd:.0%} below its high (worse than any backtest). Moved to cash. "
                      "Set kill true then false in control.json to restart.")
        e = equity(state, prices)
    if dd <= ALERT_DRAWDOWN and not state["alerted_drawdown"]:
        state["alerted_drawdown"] = True
        events.append(f"Heads up: the account is {dd:.0%} below its high. The backtest's worst was -42%.")
    if dd > ALERT_DRAWDOWN / 2:
        state["alerted_drawdown"] = False

    if not state["equity_curve"] or state["equity_curve"][-1][0] != day:
        state["equity_curve"].append([day, round(e, 2)])
    else:
        state["equity_curve"][-1][1] = round(e, 2)
    state["trades"] = state["trades"][-500:]

    # last line of defence: never save a ledger that borrows (negative cash) or is short (negative coins)
    bad = [c for c, s in state["sleeves"].items() if s["cash"] < -1e-6 or s["units"] < 0]
    if bad:
        notify(topic, "Paper bot: safety stop", "A safety check failed (borrowing or shorting). "
               "Nothing was saved; yesterday's ledger stands.", "warning")
        print("SAFETY CHECK FAILED", bad, file=sys.stderr)
        return 1

    with open(STATE, "w") as f:
        json.dump(state, f, indent=1)
    svg(state["equity_curve"], os.path.join(OUT, "equity.svg"))
    src = ", ".join(sorted(set(srcs.values())))
    dashboard(state, prices, detail, day, src, os.path.join(HERE, "DASHBOARD.md"))
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump({"day": day, "equity": round(e, 2), "drawdown": round(dd, 4), "prices": prices,
                   "targets": {c: s["target"] for c, s in state["sleeves"].items()}, "votes": detail,
                   "stopped": state["stopped"], "source": src}, f, indent=1)

    if events:
        notify(topic, "Paper bot", "\n".join(events))
    if weekly:
        inv = sum(s["units"] * prices[c] for c, s in state["sleeves"].items())
        notify(topic, "Paper bot weekly note",
               f"Paper account {money(e)} ({(e/state['starting_equity']-1)*100:+.1f}% since {state['started']}), "
               f"{inv/e*100:.0f}% in coins.\n"
               + "\n".join(f"{c[:-3]}: {sum(detail[c].values())}/5 trend votes" for c in trend.COINS), "calendar")
    print(json.dumps({"day": day, "equity": round(e, 2), "events": events, "source": src}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
