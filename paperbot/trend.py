"""The strategy, in one place. Used by both the live bot and the backtest, so they can't drift apart.

Five slow trend "votes" per coin, from daily closes (oldest first, last = latest completed day):
  - close above its 100-, 150-, 200- and 250-day average   (4 votes)
  - close above where it was 365 days ago                    (1 vote)
Target holding = share of votes that are "yes" x SIZE of that coin's sleeve.
Decisions are made once a week, on Sunday's close. Costs are charged on every dollar traded.
"""
LOOKBACKS = (100, 150, 200, 250)
MOMENTUM_DAYS = 365
MIN_HISTORY = MOMENTUM_DAYS + 1

COINS = ("BTCUSD", "ETHUSD")      # only coins with years of history behind the backtest
SLEEVE = 0.5                      # each coin gets half of the starting money
SIZE = 0.5                        # at most half of a sleeve is ever in the coin -> max 50% of the account invested
COST_PER_SIDE = 0.011             # ~1% Webull spread + 0.1% slippage, charged on each buy and each sell
REBALANCE_WEEKDAY = 6             # Sunday (Monday=0)


def votes(closes):
    """Fraction of the five trend votes that are 'yes' (0.0, 0.2, ... 1.0). None if not enough history."""
    if len(closes) < MIN_HISTORY:
        return None
    c = closes[-1]
    v = [c > sum(closes[-n:]) / n for n in LOOKBACKS]
    v.append(c > closes[-1 - MOMENTUM_DAYS])
    return sum(v) / len(v)


def vote_detail(closes):
    c = closes[-1]
    out = {f"above_{n}d_avg": c > sum(closes[-n:]) / n for n in LOOKBACKS}
    out["up_over_12_months"] = c > closes[-1 - MOMENTUM_DAYS]
    return out


def rebalance(sleeve, price, target_weight):
    """Move a sleeve {cash, units} to target_weight of its value in the coin at `price`. Returns $ traded (signed).

    No-liquidation guarantees, enforced here for every trade:
      - never more than SIZE (50%) of a sleeve in the coin, so at least half the account is always cash
      - never borrows: a buy is shrunk so cash can't go below zero (no margin, no leverage)
      - never sells short: holdings can't go below zero
    So even if both coins went to $0, the account keeps its cash half; nothing can force-sell it.
    """
    if not (price > 0):
        raise ValueError("bad price; refusing to trade")
    target_weight = min(max(target_weight, 0.0), SIZE)
    value = sleeve["cash"] + sleeve["units"] * price
    target_units = max(value * target_weight / price, 0.0)
    delta = target_units - sleeve["units"]
    if delta > 0:   # buying: the cost of the coins plus fees must fit in the cash on hand
        max_buy = max(sleeve["cash"], 0.0) / (price * (1 + COST_PER_SIDE))
        delta = min(delta, max_buy)
        target_units = sleeve["units"] + delta
    notional = abs(delta) * price
    if notional < 1e-9:
        return 0.0
    sleeve["cash"] -= delta * price + notional * COST_PER_SIDE
    sleeve["units"] = target_units
    assert sleeve["cash"] >= -1e-6 and sleeve["units"] >= 0, "safety check failed: would borrow or go short"
    return delta * price
