"""Which PMXT hours actually contain Polymarket BTC 5-minute windows?

Usage: python scripts/pmxt_coverage.py START_DATE END_DATE STEP_DAYS HOUR_UTC   e.g. 2026-04-14 2026-10-14 3 14
For each sampled hour: download the PMXT file, look up that hour's 12 windows on Gamma, count how many windows
have any rows in the file. Writes pmxt_probe/coverage.csv (rewritten after every hour so partial runs survive).
"""
import csv
import datetime as dt
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

START, END, STEP, HH = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
TMP = os.path.join(os.environ.get("RUNNER_TEMP", "/tmp"), "pmxt_cov.parquet")
OUT = "pmxt_probe/coverage.csv"
UA = {"User-Agent": "btc-bot-coverage/1.0"}
FIELDS = ["hour", "file", "mb", "windows_found_on_gamma", "windows_with_data", "distinct_assets", "seconds", "note"]


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def window_tokens(start_ts):
    def one(k):
        slug = f"btc-updown-5m-{start_ts + k * 300}"
        try:
            ev = get_json(f"https://gamma-api.polymarket.com/events?slug={slug}")
            return json.loads(ev[0]["markets"][0]["clobTokenIds"]) if ev else None
        except Exception:  # noqa: BLE001
            return None
    with ThreadPoolExecutor(6) as ex:
        return list(ex.map(one, range(12)))


def download(hour):
    url = f"https://r2v2.pmxt.dev/polymarket_orderbook_{hour}.parquet"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=180) as r, open(TMP, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        return round(os.path.getsize(TMP) / 1e6, 1), ""
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code}"
    except Exception as e:  # noqa: BLE001
        return None, str(e)[:80]


rows = []
day = dt.date.fromisoformat(START)
end = dt.date.fromisoformat(END)
while day <= end:
    hour = f"{day.isoformat()}T{HH:02d}"
    t0 = time.time()
    row = {k: "" for k in FIELDS}
    row["hour"] = hour
    mb, note = download(hour)
    row["file"] = "yes" if mb else "no"
    row["mb"] = mb or ""
    row["note"] = note
    if mb:
        try:
            start_ts = int(dt.datetime.strptime(hour, "%Y-%m-%dT%H").replace(tzinfo=dt.timezone.utc).timestamp())
            wt = window_tokens(start_ts)
            row["windows_found_on_gamma"] = sum(1 for t in wt if t)
            alltok = [t for w in wt if w for t in w]
            tok_set = pa.array(alltok, type=pa.string())
            present, assets = set(), set()
            for b in pq.ParquetFile(TMP).iter_batches(batch_size=2_000_000, columns=["asset_id"]):
                col = b["asset_id"]
                assets.update(pc.unique(col).to_pylist())
                present.update(pc.unique(col.filter(pc.is_in(col, value_set=tok_set))).to_pylist())
            row["windows_with_data"] = sum(1 for w in wt if w and any(t in present for t in w))
            row["distinct_assets"] = len(assets)
        except Exception as e:  # noqa: BLE001
            row["note"] = ("ERR " + str(e))[:120]
        finally:
            if os.path.exists(TMP):
                os.remove(TMP)
    row["seconds"] = round(time.time() - t0, 1)
    rows.append(row)
    os.makedirs("pmxt_probe", exist_ok=True)
    with open(OUT, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(row, flush=True)
    day += dt.timedelta(days=STEP)
