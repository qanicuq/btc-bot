import sys, os, zipfile, glob, io, json
import pandas as pd, numpy as np
sym, years = sys.argv[1], [int(y) for y in sys.argv[2].split(",")]
src = os.path.expanduser(f"~/mnt/BTC/{sym}-1m")
out = os.path.expanduser(f"~/mnt/BTC/clean/{sym}/1m"); os.makedirs(out, exist_ok=True)
cols=["open_time","open","high","low","close","volume","close_time","quote_volume","trades","taker_buy_base_volume","taker_buy_quote_volume","ignore"]
def ms(s): s=s.astype("int64"); return s.where(s<10**14, s//1000)
for y in years:
    files=sorted(f for f in glob.glob(f"{src}/{sym}-1m-{y}-*.zip"))
    parts=[]
    for f in files:
        with zipfile.ZipFile(f) as z:
            bad=z.testzip()
            if bad: raise SystemExit(f"CORRUPT {f}")
            for n in z.namelist():
                d=pd.read_csv(z.open(n),header=None,names=cols,dtype={0:str})
                d=d[d.open_time.str.fullmatch(r"\d+",na=False)]
                parts.append(d)
    df=pd.concat(parts,ignore_index=True)
    df["open_time"]=ms(df.open_time)//60000*60000; df["close_time"]=df.open_time+59999  # snap Dec2017-Feb2018 offset candles to the minute
    df=df.drop(columns="ignore")
    for c in ["open","high","low","close","volume","quote_volume","taker_buy_base_volume","taker_buy_quote_volume"]: df[c]=df[c].astype("float64")
    df["trades"]=df.trades.astype("int64")
    dup=int(df.duplicated("open_time").sum())
    df=df.drop_duplicates("open_time").sort_values("open_time").reset_index(drop=True)
    t=pd.to_datetime(df.open_time,unit="ms",utc=True)
    df.insert(1,"open_time_utc",t.dt.strftime("%Y-%m-%d %H:%M"))
    badohlc=int(((df.high<df[["open","close"]].max(axis=1))|(df.low>df[["open","close"]].min(axis=1))|(df.low<=0)).sum())
    gaps=t.diff().dt.total_seconds().div(60).fillna(1)
    missing=int((gaps[gaps>1]-1).sum())
    p=f"{out}/{sym}_1m_{y}.csv.gz"
    df.to_csv(p,index=False,compression={"method":"gzip","compresslevel":6})
    print(json.dumps({"sym":sym,"year":y,"files":len(files),"rows":len(df),"first":str(t.iloc[0]),"last":str(t.iloc[-1]),"dups":dup,"bad_ohlc":badohlc,"missing_min":missing,"MB":round(os.path.getsize(p)/1e6,1)}),flush=True)
