"""
investigate_data.py — understand the health_flag distribution and data structure
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from engine.data_loader import load_all, get_demand_enriched

raw = load_all()
dd_full = get_demand_enriched(raw)

print("=== Date range ===")
print(f"Min date: {dd_full['date'].min().date()}")
print(f"Max date: {dd_full['date'].max().date()}")
print(f"Total rows: {len(dd_full)}")

ANALYSIS_DATE = pd.Timestamp("2026-08-13")
HOLDOUT_START = ANALYSIS_DATE - pd.Timedelta(days=20)   # 21-day holdout
print(f"\nHoldout: {HOLDOUT_START.date()} to {ANALYSIS_DATE.date()}")

holdout = dd_full[dd_full["date"] >= HOLDOUT_START]
print(f"Holdout rows: {len(holdout)}")

print("\n=== Health flag distribution (whole dataset) ===")
print(dd_full["health_flag"].value_counts())

print("\n=== Health flag distribution (holdout) ===")
print(holdout["health_flag"].value_counts())

print("\n=== Health flag distribution (training = pre-holdout) ===")
train = dd_full[dd_full["date"] < HOLDOUT_START]
print(train["health_flag"].value_counts())

print("\n=== Sample inventory vs safety stock (holdout, red flag rows) ===")
red = holdout[holdout["health_flag"] == "red"][["dc_id","sku_id","date","usable_inventory","safety_stock","reorder_point","demand_14d_avg"]].head(20)
print(red.to_string())

print("\n=== Unique health flags per SKUxDC in holdout ===")
counts = holdout.groupby(["dc_id","sku_id"])["health_flag"].nunique()
print(f"SKUxDC pairs with changing flags: {(counts>1).sum()} / {len(counts)}")
print(f"Always green: {(holdout.groupby(['dc_id','sku_id'])['health_flag'].apply(lambda x: (x=='green').all())).sum()}")
print(f"Ever red:     {(holdout.groupby(['dc_id','sku_id'])['health_flag'].apply(lambda x: (x=='red').any())).sum()}")

# Check if red flags transition in next 7 days for any row
print("\n=== Forward breach check (ANY day has red in next 7 days) ===")
breach_count = 0
checked = 0
for (dc_id, sku_id), grp in dd_full.groupby(["dc_id","sku_id"]):
    grp = grp.sort_values("date")
    holdout_grp = grp[grp["date"] >= HOLDOUT_START]
    for _, row in holdout_grp.iterrows():
        future = grp[grp["date"] > row["date"]].head(7)
        if (future["health_flag"] == "red").any():
            breach_count += 1
        checked += 1
print(f"Checked: {checked}, Forward breaches: {breach_count}")

# Check on full dataset
print("\n=== FULL dataset forward breach (health_flag→red within 7 days) ===")
breach_count_full = 0
checked_full = 0
for (dc_id, sku_id), grp in dd_full.groupby(["dc_id","sku_id"]):
    grp = grp.sort_values("date")
    for _, row in grp.iterrows():
        future = grp[grp["date"] > row["date"]].head(7)
        if (future["health_flag"] == "red").any():
            breach_count_full += 1
        checked_full += 1
print(f"Full dataset checked: {checked_full}, Forward breaches: {breach_count_full}")

print("\n=== Sample: rows that ARE currently red ===")
red_rows = dd_full[dd_full["health_flag"] == "red"]
print(f"Total red rows: {len(red_rows)}")
print(red_rows[["dc_id","sku_id","date","usable_inventory","safety_stock"]].head(30).to_string())

print("\n=== Check safety_stock distribution ===")
print(dd_full["safety_stock"].describe())
print(dd_full["usable_inventory"].describe())
