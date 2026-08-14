"""
adapt_medcare_data.py
─────────────────────
Adapts medcare-ai datasets (57,888 rows, 40 SKUs, 8 DCs)
into the demand-prediction project's CSV format.

Run from the demand-prediction root:
    python3 scripts/adapt_medcare_data.py
"""

import pandas as pd
import numpy as np
import os
from pathlib import Path

SRC  = Path("/Users/surya/model/medcare-ai/data/raw")
DEST = Path("/Users/surya/cts/demand-prediction/data")
DEST.mkdir(exist_ok=True)

print("=" * 62)
print("  MedCare AI → Demand-Prediction  Data Adapter")
print("=" * 62)

# ── 1. Load source tables ───────────────────────────────────────
demand   = pd.read_csv(SRC / "demand_history.csv",        parse_dates=["date"])
inv      = pd.read_csv(SRC / "inventory_snapshots.csv",   parse_dates=["date"])
skus_src = pd.read_csv(SRC / "skus.csv")
dcs_src  = pd.read_csv(SRC / "dcs.csv")
batches  = pd.read_csv(SRC / "batches.csv",
                        parse_dates=["manufacturing_date", "expiry_date"])
dist_ord = pd.read_csv(SRC / "distributor_orders.csv",    parse_dates=["order_date"])
promos   = pd.read_csv(SRC / "promotions.csv",            parse_dates=["start_date", "end_date"])
sku_sup  = pd.read_csv(SRC / "sku_suppliers.csv")
suppliers= pd.read_csv(SRC / "suppliers.csv")

print(f"Loaded: demand={len(demand):,}  inv={len(inv):,}  dist_orders={len(dist_ord):,}  batches={len(batches):,}")


# ── 2. sku_master.csv ───────────────────────────────────────────
#  Map 4-level criticality to 3-level: CRITICAL→High, HIGH→High, MEDIUM→Medium, LOW→Low
CRIT_MAP = {"CRITICAL": "High", "HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}

skus_src["criticality_mapped"] = skus_src["criticality"].map(CRIT_MAP).fillna("Low")

sku_master = pd.DataFrame({
    "sku_id":                  skus_src["sku_id"],
    "sku_name":                skus_src["name"],
    "category":                skus_src["category"],
    "criticality":             skus_src["criticality_mapped"],
    "unit_cost":               skus_src["unit_cost"],
    "purchase_cost_regular":   skus_src["unit_cost"] * 1.00,
    "purchase_cost_local":     skus_src["unit_cost"] * 1.50,
    "stockout_penalty_per_unit": skus_src.apply(
        lambda r: r["unit_cost"] * (5 if r["criticality"] in ("CRITICAL","HIGH") else 3), axis=1
    ),
    "holding_cost_pct": 0.20,
})
sku_master.to_csv(DEST / "sku_master.csv", index=False)
print(f"✓ sku_master.csv  → {len(sku_master)} SKUs")


# ── 3. dc_master.csv ────────────────────────────────────────────
# City-level lat/lon lookup
CITY_COORDS = {
    "Chennai":   (13.0827, 80.2707),
    "Bangalore": (12.9716, 77.5946),
    "Hyderabad": (17.3850, 78.4867),
    "Mumbai":    (19.0760, 72.8777),
    "Delhi":     (28.7041, 77.1025),
    "Kolkata":   (22.5726, 88.3639),
    "Pune":      (18.5204, 73.8567),
    "Ahmedabad": (23.0225, 72.5714),
}

def region_map(r):
    loc = r["location"]
    if loc in ("Chennai","Bangalore","Hyderabad"): return "South"
    if loc in ("Mumbai","Pune","Ahmedabad"):        return "West"
    if loc == "Delhi":                              return "North"
    return "East"

dcs_src["region"] = dcs_src.apply(region_map, axis=1)

dc_master = pd.DataFrame({
    "dc_id":               dcs_src["dc_id"],
    "dc_name":             dcs_src["name"],
    "city":                dcs_src["location"],
    "region":              dcs_src["region"],
    "transfer_cost_per_unit": dcs_src["lead_time_days"] * 2.5,  # proxy
    "latitude":            dcs_src["location"].map(lambda l: CITY_COORDS.get(l, (20.0,78.0))[0]),
    "longitude":           dcs_src["location"].map(lambda l: CITY_COORDS.get(l, (20.0,78.0))[1]),
})
dc_master.to_csv(DEST / "dc_master.csv", index=False)
print(f"✓ dc_master.csv   → {len(dc_master)} DCs")


# ── 4. daily_demand_inventory.csv ──────────────────────────────
# Merge demand with inventory snapshots
merged = pd.merge(
    demand,
    inv[["date","sku_id","dc_id","closing_inventory","reserved_inventory","incoming_inventory","available_inventory"]],
    on=["date","sku_id","dc_id"],
    how="left"
)

# Build active-promotion flag per row using promotions.csv
# promos is per-SKU/DC with start/end dates
def make_promo_flag(demand_df, promos_df):
    """Mark demand rows that fall within a promotional period."""
    flags = np.zeros(len(demand_df), dtype=int)
    for _, p in promos_df.iterrows():
        mask = (
            (demand_df["sku_id"] == p["sku_id"]) &
            (demand_df["dc_id"]  == p["dc_id"]) &
            (demand_df["date"]   >= p["start_date"]) &
            (demand_df["date"]   <= p["end_date"])
        )
        flags[mask.values] = 1
    return flags

promo_flags = make_promo_flag(merged, promos)
merged["promo_flag"] = promo_flags

# Flu season index: derive from month (higher in winter/monsoon months)
def flu_index(month):
    FLU = {1:0.85, 2:0.60, 3:0.30, 4:0.20, 5:0.20,
           6:0.40, 7:0.80, 8:0.90, 9:0.55, 10:0.50,
           11:0.70, 12:0.85}
    return FLU.get(month, 0.3)

merged["flu_season_index"] = merged["date"].dt.month.map(flu_index)

# Stockout flag from lost sales
merged["stockout_flag"] = (merged["out_of_stock_lost_sales"] > 0).astype(int)

# Compute safety stock = 1.65 × std of last 28 days demand per SKU×DC
safety_stock_map = (
    demand.groupby(["sku_id","dc_id"])["quantity"]
    .std()
    .fillna(0)
    .mul(1.65)
    .round()
    .astype(int)
)

reorder_point_map = (
    demand.groupby(["sku_id","dc_id"])["quantity"]
    .mean()
    .fillna(0)
    .mul(7)   # 7-day demand
    .round()
    .astype(int)
)

merged["safety_stock"]  = merged.set_index(["sku_id","dc_id"]).index.map(safety_stock_map.to_dict())
merged["reorder_point"] = merged.set_index(["sku_id","dc_id"]).index.map(reorder_point_map.to_dict())

daily_demand_inv = pd.DataFrame({
    "date":               merged["date"].dt.date.astype(str),
    "dc_id":              merged["dc_id"],
    "sku_id":             merged["sku_id"],
    "demand_units":       merged["quantity"].round(2),
    "flu_season_index":   merged["flu_season_index"],
    "promo_flag":         merged["promo_flag"],
    "physical_inventory": merged["closing_inventory"].fillna(0).round(1),
    "reserved_inventory": merged["reserved_inventory"].fillna(0).round(1),
    "inbound_inventory":  merged["incoming_inventory"].fillna(0).round(1),
    "safety_stock":       merged["safety_stock"].fillna(0).astype(int),
    "reorder_point":      merged["reorder_point"].fillna(0).astype(int),
    "stockout_flag":      merged["stockout_flag"],
})

daily_demand_inv.to_csv(DEST / "daily_demand_inventory.csv", index=False)
print(f"✓ daily_demand_inventory.csv → {len(daily_demand_inv):,} rows")


# ── 5. lead_times.csv ───────────────────────────────────────────
# Build per-SKU×DC lead times from sku_suppliers + dcs
lt_base = sku_sup.merge(
    dcs_src[["dc_id","lead_time_days"]].rename(columns={"lead_time_days":"dc_lt"}),
    on="dc_id", how="left"
)
lt_base["lead_time_days"] = lt_base["lead_time_days"].fillna(7)

lead_rows = []
for _, r in lt_base.iterrows():
    lt_reg   = float(r["lead_time_days"])
    lt_local = max(2.0, lt_reg * 0.4)
    lt_trans = max(1.0, lt_reg * 0.25)
    lt_urg   = max(1.0, lt_reg * 0.6)
    for stype, lt, min_q, max_q in [
        ("regular",  lt_reg,   50,  10000),
        ("local",    lt_local,  20,  2000),
        ("transfer", lt_trans,  0,   5000),
        ("urgent",   lt_urg,    50,  1000),
    ]:

        lead_rows.append({
            "sku_id": r["sku_id"],
            "supplier_type": stype,
            "dc_id": r["dc_id"],
            "lead_time_days": round(lt, 1),
            "min_order_qty": min_q,
            "max_order_qty": max_q,
        })

lead_times = pd.DataFrame(lead_rows)
lead_times.to_csv(DEST / "lead_times.csv", index=False)
print(f"✓ lead_times.csv  → {len(lead_times):,} rows")


# ── 6. batches.csv ──────────────────────────────────────────────
ANALYSIS_DATE = pd.Timestamp("2026-08-13")

batches_out = pd.DataFrame({
    "batch_id":           batches["batch_id"],
    "dc_id":              batches["dc_id"],
    "sku_id":             batches["sku_id"],
    "quantity":           batches["remaining_quantity"],
    "manufacture_date":   batches["manufacturing_date"].dt.date.astype(str),
    "expiry_date":        batches["expiry_date"].dt.date.astype(str),
    "receipt_date_at_dc": batches["manufacturing_date"].dt.date.astype(str),  # proxy
    "shelf_life_days":    (batches["expiry_date"] - batches["manufacturing_date"]).dt.days,
    "batch_status":       batches["expiry_date"].apply(
        lambda d: "near_expiry" if (d - ANALYSIS_DATE).days < 90 else "active"
    ),
})
batches_out.to_csv(DEST / "batches.csv", index=False)
print(f"✓ batches.csv     → {len(batches_out):,} rows")


# ── 7. distributor_orders.csv ───────────────────────────────────
dist_ord["fill_rate"] = (
    dist_ord["fulfilled_quantity"] / dist_ord["ordered_quantity"].replace(0, np.nan)
).clip(0, 1).fillna(1.0)

dist_ord["on_time"] = (dist_ord["status"] == "FULFILLED").astype(bool)

# Compute order_frequency_days per DC×SKU
freq = (
    dist_ord.sort_values(["dc_id","sku_id","order_date"])
    .groupby(["dc_id","sku_id"])["order_date"]
    .diff().dt.days.fillna(7)
)
dist_ord["order_frequency_days"] = freq.values

# Map supplier_id from sku_suppliers
sku_sup_lookup = sku_sup.groupby(["sku_id","dc_id"])["supplier_id"].first().reset_index()
dist_ord2 = dist_ord.merge(sku_sup_lookup, on=["sku_id","dc_id"], how="left")

dist_out = pd.DataFrame({
    "order_id":              dist_ord2["order_id"],
    "dc_id":                 dist_ord2["dc_id"],
    "sku_id":                dist_ord2["sku_id"],
    "distributor_id":        dist_ord2["supplier_id"].fillna("DIST01"),
    "order_date":            dist_ord2["order_date"].dt.date.astype(str),
    "promised_delivery_date":dist_ord2["order_date"].dt.date.astype(str),  # not in source
    "actual_delivery_date":  dist_ord2["order_date"].dt.date.astype(str),  # not in source
    "ordered_qty":           dist_ord2["ordered_quantity"],
    "received_qty":          dist_ord2["fulfilled_quantity"],
    "on_time":               dist_ord2["on_time"],
    "fill_rate":             dist_ord2["fill_rate"].round(3),
    "order_frequency_days":  dist_ord2["order_frequency_days"].round(1),
})
dist_out.to_csv(DEST / "distributor_orders.csv", index=False)
print(f"✓ distributor_orders.csv → {len(dist_out):,} rows")


# ── 8. promo_calendar.csv ───────────────────────────────────────
# Network-level calendar from per-SKU promos
promo_cal = pd.DataFrame({
    "event_name":         promos["promotion_type"].fillna("Promo"),
    "start_date":         promos["start_date"].dt.date.astype(str),
    "end_date":           promos["end_date"].dt.date.astype(str),
    "demand_multiplier":  1.0 + promos["discount_percentage"].fillna(0) / 100,
    "affected_categories": "all",
    "event_type":         "promo",
    "promo_flag":         1,
    "flu_season_flag":    0,
})
# Add seasonal flu events derived from data date range
flu_events = [
    {"event_name": "Winter Flu Season", "start_date": "2026-01-01", "end_date": "2026-02-28",
     "demand_multiplier": 1.60, "affected_categories": "antibiotic,analgesic",
     "event_type": "flu_season", "promo_flag": 0, "flu_season_flag": 1},
    {"event_name": "Monsoon Disease Peak", "start_date": "2026-07-01", "end_date": "2026-08-31",
     "demand_multiplier": 1.50, "affected_categories": "antibiotic,antifungal",
     "event_type": "flu_season", "promo_flag": 0, "flu_season_flag": 1},
]
promo_cal = pd.concat([promo_cal, pd.DataFrame(flu_events)], ignore_index=True)
promo_cal.to_csv(DEST / "promo_calendar.csv", index=False)
print(f"✓ promo_calendar.csv → {len(promo_cal)} events")


print()
print("=" * 62)
print("  Data adaptation complete.")
print(f"  Files written to: {DEST}")
print("=" * 62)
