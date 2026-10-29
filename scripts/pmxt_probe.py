"""Probe one hour of the PMXT Polymarket order-book archive for BTC 5-minute up/down markets.

Usage: python scripts/pmxt_probe.py 2026-10-10T15
Downloads the hour file (not kept in git), finds that hour's btc-updown-5m markets via
Polymarket's public Gamma API, filters the file to those markets, and writes a SMALL summary to
pmxt_probe/summary.json. Every step is wrapped so one run reports as much as possible.
"""
import datetime as dt
import json
import os
import sys
import time
import traceback
import urllib.request

import pyarrow.dataset as ds
import pyarrow.parquet as pq

HOUR = sys.argv[1].strip()
HOSTS = ["r2v2.pmxt.dev", "r2.pmxt.dev"]
TMP = os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "pmxt_hour.parquet")
OUT_DIR = "pmxt_probe"
UA = {"User-Agent": "btc-bot-probe/1.0"}

summary = {"hour": HOUR, "run_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "errors": []}


def step(name, fn):
    try:
        fn()
    except Exception:  # noqa: BLE001 - report everything, keep going
        summary["errors"].append({"step": name, "trace": traceback.format_exc()[-1500:]})


def availability():
    """Which hours exist? One 1-byte ranged GET per day at 15:00 UTC, Feb 21 -> yesterday, plus a few host checks."""
    from concurrent.futures import ThreadPoolExecutor

    def status(host, hour):
        req = urllib.request.Request(f"https://{host}/polymarket_orderbook_{hour}.parquet", headers={**UA, "Range": "bytes=0-0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                total = (r.headers.get("Content-Range") or "").split("/")[-1]
                return r.status, total
        except urllib.error.HTTPError as e:
            return e.code, ""
        except Exception as e:  # noqa: BLE001
            return str(e)[:60], ""

    day = dt.date(2026, 2, 21)
    end = dt.datetime.now(dt.timezone.utc).date() - dt.timedelta(days=1)
    days = []
    while day <= end:
        days.append(day.isoformat())
        day += dt.timedelta(days=1)
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(lambda d: (d, status("r2v2.pmxt.dev", f"{d}T15")), days))
    ok = [d for d, (s, _) in res if s in (200, 206)]
    by_month = {}
    for d, (s, _) in res:
        by_month.setdefault(d[:7], [0, 0])[0 if s in (200, 206) else 1] += 1
    summary["availability_r2v2_15utc"] = {
        "days_checked": len(days), "days_found": len(ok),
        "first_found": ok[0] if ok else None, "last_found": ok[-1] if ok else None,
        "found_vs_missing_by_month": by_month,
        "status_codes": sorted({str(s) for _, (s, _) in res}),
        "sample_sizes_bytes": {d: t for d, (s, t) in res[-3:]},
    }
    summary["requested_hour_status"] = {h: status(h, HOUR) for h in HOSTS}
    summary["doc_example_hour_2026-04-17T12"] = {h: status(h, "2026-04-17T12") for h in HOSTS}
    summary["_good_hour"] = f"{ok[-1]}T15" if ok else None


def download():
    errs = []
    for host in HOSTS:
        url = f"https://{host}/polymarket_orderbook_{HOUR}.parquet"
        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=120) as r, open(TMP, "wb") as f:
                while chunk := r.read(1 << 20):
                    f.write(chunk)
            summary["download"] = {"url": url, "mb": round(os.path.getsize(TMP) / 1e6, 1), "seconds": round(time.time() - t0, 1)}
            return
        except Exception as e:  # noqa: BLE001
            errs.append(f"{url}: {e}")
    raise RuntimeError("download failed: " + " | ".join(errs))


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


markets = []  # one dict per btc-updown-5m window in the hour


def find_markets():
    start = int(dt.datetime.strptime(HOUR, "%Y-%m-%dT%H").replace(tzinfo=dt.timezone.utc).timestamp())
    for k in range(12):
        ts = start + k * 300
        slug = f"btc-updown-5m-{ts}"
        try:
            ev = get_json(f"https://gamma-api.polymarket.com/events?slug={slug}")
            m = ev[0]["markets"][0]
            markets.append({
                "slug": slug,
                "condition_id": m.get("conditionId"),
                "tokens": json.loads(m["clobTokenIds"]),
                "outcomes": json.loads(m["outcomes"]),
                "outcome_prices": json.loads(m.get("outcomePrices") or "[]"),
                "closed": m.get("closed"),
            })
        except Exception as e:  # noqa: BLE001
            markets.append({"slug": slug, "error": str(e)[:200]})
    summary["markets_found"] = sum(1 for m in markets if "tokens" in m)
    summary["markets"] = markets


def inspect_and_filter():
    pf = pq.ParquetFile(TMP)
    summary["schema"] = [f"{f.name}: {f.type}" for f in pf.schema_arrow]
    summary["rows_total"] = pf.metadata.num_rows
    names = pf.schema_arrow.names
    tokens = [t for m in markets for t in m.get("tokens", [])]
    cids = [m["condition_id"] for m in markets if m.get("condition_id")]
    dset = ds.dataset(TMP)
    if "asset_id" in names:
        table = dset.to_table(filter=ds.field("asset_id").isin(tokens))
    elif "market_id" in names:
        table = dset.to_table(filter=ds.field("market_id").isin(cids))
    else:
        raise RuntimeError("no asset_id/market_id column; see schema")
    df = table.to_pandas()
    summary["rows_matched"] = len(df)
    summary["columns"] = list(df.columns)
    kind = "event_type" if "event_type" in df.columns else ("update_type" if "update_type" in df.columns else None)
    if kind:
        summary["event_type_counts"] = df[kind].astype(str).value_counts().to_dict()
    summary["sample_rows"] = [{k: str(v)[:300] for k, v in row.items()} for row in df.head(3).to_dict("records")]
    if "price" in df.columns and "asset_id" in df.columns:
        import pandas as pd
        df["price_n"] = pd.to_numeric(df["price"], errors="coerce")
        df["size_n"] = pd.to_numeric(df["size"], errors="coerce") if "size" in df.columns else float("nan")
        per = []
        for m in markets:
            for tok, outc in zip(m.get("tokens", []), m.get("outcomes", [])):
                d = df[(df["asset_id"] == tok) & df["price_n"].notna()]
                low = d[d["price_n"] <= 0.02]
                per.append({
                    "slug": m["slug"], "outcome": outc, "events_with_price": len(d),
                    "min_price": None if d.empty else float(d["price_n"].min()),
                    "events_price_le_2c": len(low),
                    "size_at_le_2c": None if low.empty else float(low["size_n"].sum()),
                    "sides_le_2c": low["side"].astype(str).value_counts().to_dict() if "side" in low.columns else None,
                })
        summary["per_token_price_le_2c"] = per


def _f(x):
    if x is None:
        return None
    try:
        v = float(x)
    except Exception:  # noqa: BLE001
        return None
    return None if v != v else v


def rebuild_eval(rows, key, only_last=False, want_samples=False):
    """Rebuild one token's book from `rows` (already in the order to test) and compare to best_bid/best_ask."""
    bids, asks, seen = {}, {}, False
    tot = ok_b = ok_a = ok_both = 0
    samples, started, left = [], False, 14
    for i, r in enumerate(rows):
        et = r["event_type"]
        if et == "book":
            try:
                bids = {float(p): float(s) for p, s in json.loads(r["bids"]) if float(s) > 0}
                asks = {float(p): float(s) for p, s in json.loads(r["asks"]) if float(s) > 0}
                seen = True
            except Exception:  # noqa: BLE001
                pass
            continue
        if et != "price_change" or not seen:
            continue
        p, sz = _f(r["price"]), _f(r["size"])
        if p is None or sz is None:
            continue
        book = bids if str(r["side"]).upper() == "BUY" else asks
        if sz <= 0:
            book.pop(p, None)
        else:
            book[p] = sz
        if only_last and i + 1 < len(rows) and rows[i + 1][key] == r[key]:
            continue
        rb = max(bids) if bids else None
        ra = min(asks) if asks else None
        tb, ta = _f(r["best_bid"]), _f(r["best_ask"])
        okb = rb is not None and tb is not None and abs(rb - tb) < 1e-9
        oka = ra is not None and ta is not None and abs(ra - ta) < 1e-9
        tot += 1
        ok_b += okb
        ok_a += oka
        ok_both += okb and oka
        if want_samples:
            if not (okb and oka):
                started = True
            if started and left > 0:
                samples.append({"idx": r["idx"], "ts": r["ts"], "side": str(r["side"]), "price": p, "size": sz,
                                "row_bb": tb, "row_ba": ta, "mine_bb": rb, "mine_ba": ra})
                left -= 1
    pct = lambda n: round(100 * n / tot, 1) if tot else None  # noqa: E731
    out = {"checked": tot, "both_pct": pct(ok_both), "bid_pct": pct(ok_b), "ask_pct": pct(ok_a)}
    if want_samples:
        out["samples"] = samples
    return out


def snap_consistency(rows, sem="total", trades="ignore", flip=False):
    """Replay deltas from one `book` snapshot to the next and compare with the next snapshot's levels."""
    bids = asks = None
    since = 0
    pairs = lev = exact = phantom = missing = sizediff = 0
    for r in rows:
        et = r["event_type"]
        if et == "book":
            try:
                nb = {float(p): float(s) for p, s in json.loads(r["bids"]) if float(s) > 0}
                na = {float(p): float(s) for p, s in json.loads(r["asks"]) if float(s) > 0}
            except Exception:  # noqa: BLE001
                continue
            if bids is not None and since > 0:
                pairs += 1
                for mine, snap in ((bids, nb), (asks, na)):
                    for p, s in snap.items():
                        lev += 1
                        m = mine.get(p)
                        if m is None:
                            missing += 1
                        elif abs(m - s) < 1e-6:
                            exact += 1
                        else:
                            sizediff += 1
                    phantom += sum(1 for p in mine if p not in snap)
            bids, asks, since = nb, na, 0
            continue
        if bids is None:
            continue
        p, sz = _f(r["price"]), _f(r["size"])
        if p is None or sz is None:
            continue
        if et == "price_change":
            since += 1
            book = bids if (str(r["side"]).upper() == "BUY") != flip else asks
            if sem == "total":
                if sz <= 0:
                    book.pop(p, None)
                else:
                    book[p] = sz
            else:
                v = book.get(p, 0.0) + sz
                if v <= 1e-9:
                    book.pop(p, None)
                else:
                    book[p] = v
        elif et == "last_trade_price" and trades == "consume":
            book = asks if str(r["side"]).upper() == "BUY" else bids
            if p in book:
                v = book[p] - sz
                if v <= 1e-9:
                    book.pop(p)
                else:
                    book[p] = v
    return {"pairs": pairs, "levels": lev, "exact": exact, "missing": missing, "phantom": phantom, "sizediff": sizediff}


def diagnose():
    """File-level facts (are our markets in this file? under which key?) + book-rebuild variants on 4 tokens."""
    import pyarrow as pa
    import pyarrow.compute as pc
    from collections import Counter

    pf = pq.ParquetFile(TMP)
    names = pf.schema_arrow.names
    tokens = [t for m in markets for t in m.get("tokens", [])]
    cids = [m["condition_id"] for m in markets if m.get("condition_id")]
    tok_set = pa.array(tokens, type=pa.string())
    cid_set = None
    if "market" in names:
        try:
            cid_set = pa.array([c.encode() for c in cids], type=pa.binary(66))
        except Exception:  # noqa: BLE001
            cid_set = None
    # the 4 tokens of the first two windows get a full rebuild test
    focus = []
    for m in markets[:6]:
        for tok, outc in zip(m.get("tokens", []), m.get("outcomes", [])):
            focus.append((tok, f"{m['slug'][-10:]}_{outc}", int(m["slug"].rsplit("-", 1)[1])))
    focus_set = pa.array([t for t, _, _ in focus], type=pa.string())
    want = [c for c in ("timestamp_received", "timestamp", "market", "event_type", "asset_id", "bids", "asks",
                        "price", "size", "side", "best_bid", "best_ask", "fee_rate_bps") if c in names]
    diag = {"columns_read": want}
    ets, assets, fee_counts, top_assets = Counter(), set(), Counter(), Counter()
    n = offset = tok_rows = cid_rows = 0
    tmin = tmax = None
    collected = {c: [] for c in want}
    collected["idx"] = []
    collected["ts"] = []
    collected["ts_recv"] = []
    for b in pf.iter_batches(batch_size=2_000_000, columns=want):
        n += b.num_rows
        if "event_type" in want:
            for d in pc.value_counts(b["event_type"]).to_pylist():
                ets[str(d["values"])] += d["counts"]
        if "asset_id" in want:
            assets.update(pc.unique(b["asset_id"]).to_pylist())
            tok_rows += pc.sum(pc.is_in(b["asset_id"], value_set=tok_set)).as_py() or 0
            for d in pc.value_counts(b["asset_id"]).to_pylist():
                top_assets[d["values"]] += d["counts"]
        if cid_set is not None:
            try:
                cid_rows += pc.sum(pc.is_in(b["market"], value_set=cid_set)).as_py() or 0
            except Exception as e:  # noqa: BLE001
                cid_set = None
                diag["cid_check_error"] = str(e)[:200]
        try:
            mm = pc.min_max(pc.cast(b["timestamp"], pa.int64())).as_py()
            if mm["min"] is not None:
                tmin = mm["min"] if tmin is None else min(tmin, mm["min"])
                tmax = mm["max"] if tmax is None else max(tmax, mm["max"])
        except Exception as e:  # noqa: BLE001
            diag["minmax_error"] = str(e)[:200]
        mask = pc.is_in(b["asset_id"], value_set=focus_set)
        fb = b.filter(mask)
        if fb.num_rows:
            dct = fb.to_pydict()
            for c in want:
                collected[c].extend(dct[c])
            collected["ts"].extend(pc.cast(fb["timestamp"], pa.int64()).to_pylist())
            collected["ts_recv"].extend(pc.cast(fb["timestamp_received"], pa.int64()).to_pylist())
            collected["idx"].extend((pc.indices_nonzero(mask).to_numpy() + offset).tolist())
        offset += b.num_rows
    diag.update({
        "file_rows": n, "file_event_types": dict(ets), "file_distinct_assets": len(assets),
        "ts_min": None if tmin is None else dt.datetime.fromtimestamp(tmin / 1000, dt.timezone.utc).isoformat(),
        "ts_max": None if tmax is None else dt.datetime.fromtimestamp(tmax / 1000, dt.timezone.utc).isoformat(),
        "rows_for_expected_token_ids": tok_rows,
        "rows_for_expected_condition_ids": cid_rows if cid_set is not None else "n/a",
    })
    # what are the busiest markets in this file? (to see if BTC 5m windows of this hour are in it at all)
    busy = []
    for tok, cnt in top_assets.most_common(3):
        try:
            mk = get_json(f"https://gamma-api.polymarket.com/markets?clob_token_ids={tok}")
            busy.append({"rows": cnt, "slug": mk[0].get("slug") if mk else None})
        except Exception as e:  # noqa: BLE001
            busy.append({"rows": cnt, "error": str(e)[:100]})
    diag["busiest_assets"] = busy
    # per-token rebuild tests
    total = len(collected["idx"])
    recs = [{c: collected[c][i] for c in collected} for i in range(total)]
    rebuild, book_info, fee_counts, snap_agg = {}, {}, Counter(), {}
    for r in recs:
        if r["event_type"] == "last_trade_price" and "fee_rate_bps" in r:
            fee_counts[str(r["fee_rate_bps"])] += 1
    diag["fee_rate_bps_on_trades"] = dict(fee_counts)
    for ti, (tok, label, T) in enumerate(focus):
        tr = [r for r in recs if r["asset_id"] == tok]  # file order
        if not tr:
            continue
        dec = sum(1 for a, b2 in zip(tr, tr[1:]) if b2["ts"] < a["ts"])
        books = [r for r in tr if r["event_type"] == "book"]
        book_info[label] = {
            "rows": len(tr), "book_events": len(books),
            "first_books_sec_from_window_start": [round((r["ts"] - T * 1000) / 1000, 1) for r in books[:4]],
            "books_inside_window": sum(1 for r in books if T * 1000 <= r["ts"] < (T + 300) * 1000),
            "file_order_ts_decreases": dec,
        }
        variants = {
            "file_all": (tr, "ts", False),
            "file_lastinms": (tr, "ts", True),
            "ts_stable_all": (sorted(tr, key=lambda r: (r["ts"], r["idx"])), "ts", False),
            "ts_stable_lastinms": (sorted(tr, key=lambda r: (r["ts"], r["idx"])), "ts", True),
            "recv_stable_lastinms": (sorted(tr, key=lambda r: (r["ts_recv"], r["idx"])), "ts_recv", True),
        }
        if ti < 4:
            rebuild[label] = {}
            for vname, (rows, key, last) in variants.items():
                rebuild[label][vname] = rebuild_eval(rows, key, last, want_samples=(ti == 0 and vname == "file_all"))
        ordered = {"ts_stable": variants["ts_stable_all"][0], "file": tr}
        for oname, rows in ordered.items():
            for sem in ("total", "delta"):
                for trd in ("ignore", "consume"):
                    for flip in (False, True):
                        agg = snap_agg.setdefault(f"{oname}|{sem}|trades_{trd}|flip_{flip}", Counter())
                        for k, v in snap_consistency(rows, sem, trd, flip).items():
                            agg[k] += v
        if ti == 0:
            hits = [i for i, r in enumerate(tr) if r["event_type"] == "last_trade_price" and 0.05 < (_f(r["price"]) or 0) < 0.95]
            if hits:
                i0 = hits[0]
                diag["trade_context_file_order"] = [
                    {k: str(r[k]) for k in ("idx", "ts", "event_type", "side", "price", "size", "best_bid", "best_ask")}
                    for r in tr[max(0, i0 - 6): i0 + 7]]
    diag["snap_consistency"] = {
        k: {**dict(v), "exact_pct": round(100 * v["exact"] / v["levels"], 1) if v["levels"] else None}
        for k, v in snap_agg.items()}
    diag["book_info"] = book_info
    diag["rebuild"] = rebuild
    summary["diag"] = diag


if os.environ.get("PROBE_AVAIL"):
    step("availability", availability)
for name, fn in [("download", download), ("find_markets", find_markets), ("inspect_and_filter", inspect_and_filter),
                 ("diagnose", diagnose)]:
    step(name, fn)
    if name == "download" and "download" not in summary:
        break

os.makedirs(OUT_DIR, exist_ok=True)
with open(os.path.join(OUT_DIR, f"summary_{HOUR}.json"), "w") as f:
    json.dump(summary, f, indent=2, default=str)
print(json.dumps(summary.get("diag", summary), indent=2, default=str)[:6000])
if os.path.exists(TMP):
    os.remove(TMP)
