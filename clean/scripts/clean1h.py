# Rebuild the 1-hour files from the cleaned 1-minute files (so the raw 1h downloads aren't needed).
import pandas as pd, glob, os
base=os.path.expanduser("~/mnt/BTC/clean")
for sym in ["BTCUSDT","ETHUSDT"]:
    m=pd.concat([pd.read_csv(f) for f in sorted(glob.glob(f"{base}/{sym}/1m/*.csv.gz"))])
    m["hr"]=m.open_time//3600000*3600000
    h=m.groupby("hr").agg(open=("open","first"),high=("high","max"),low=("low","min"),close=("close","last"),
        volume=("volume","sum"),quote_volume=("quote_volume","sum"),trades=("trades","sum"),
        taker_buy_base_volume=("taker_buy_base_volume","sum"),taker_buy_quote_volume=("taker_buy_quote_volume","sum")).reset_index()
    h=h.rename(columns={"hr":"open_time"})
    h.insert(1,"open_time_utc",pd.to_datetime(h.open_time,unit="ms",utc=True).dt.strftime("%Y-%m-%d %H:%M"))
    h.insert(7,"close_time",h.open_time+3599999)
    p=f"{base}/{sym}/{sym}_1h.csv"; h.to_csv(p,index=False); print(sym,len(h),h.open_time_utc.iloc[-1])
