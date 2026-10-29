import pandas as pd, glob, numpy as np, sys
sym=sys.argv[1]
m=pd.concat([pd.read_csv(f,usecols=["open_time","open","high","low","close","volume"]) for f in sorted(glob.glob(f"{sym}/1m/*.csv.gz"))])
h=pd.read_csv(f"{sym}/{sym}_1h.csv")
print(sym,"1m rows",len(m),"dups",m.open_time.duplicated().sum(),"sorted",m.open_time.is_monotonic_increasing,"off-minute",(m.open_time%60000!=0).sum())
print(" bad ohlc",((m.high<m[["open","close"]].max(axis=1))|(m.low>m[["open","close"]].min(axis=1))|(m.low<=0)).sum(), "1h bad",((h.high<h[["open","close"]].max(axis=1))|(h.low>h[["open","close"]].min(axis=1))).sum())
m["hr"]=m.open_time//3600000*3600000
g=m.groupby("hr").agg(open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"),volume=("volume","sum"),n=("open","size"))
full=g[g.n==60]; j=full.join(h.set_index("open_time")[["open","high","low","close","volume"]],rsuffix="_h",how="inner")
for c in ["open","high","low","close"]: print(f"  {c} mismatch",(~np.isclose(j[c],j[c+"_h"])).sum(),end="")
print("  volume mismatch",(~np.isclose(j.volume,j.volume_h,rtol=1e-6)).sum(),"| hours compared",len(j))
