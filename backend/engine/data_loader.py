"""
data_loader.py — Load and merge all 5 CSVs into unified DataFrames.
All derived fields computed here as single source of truth.
"""
import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"
ANALYSIS_DATE = pd.Timestamp("2026-08-13")


def load_all():
    """Return dict of all raw DataFrames."""
    dd = pd.read_csv(DATA_DIR / "daily_demand_inventory.csv", parse_dates=["date"])
    sm = pd.read_csv(DATA_DIR / "sku_master.csv")
    dc = pd.read_csv(DATA_DIR / "dc_master.csv")
    lt = pd.read_csv(DATA_DIR / "lead_times.csv")
    bt = pd.read_csv(DATA_DIR / "batches.csv",
                     parse_dates=["expiry_date", "manufacture_date", "receipt_date_at_dc"])
    return {"demand": dd, "sku": sm, "dc": dc, "lead_times": lt, "batches": bt}


def get_demand_enriched(raw: dict) -> pd.DataFrame:
    """
    Merge demand with sku_master and dc_master.
    Add usable_inventory, expired_qty, days_of_stock, projected_stockout_date.
    """
    dd = raw["demand"].copy()
    sm = raw["sku"][["sku_id", "sku_name", "category", "criticality",
                      "unit_cost", "purchase_cost_regular", "purchase_cost_local",
                      "stockout_penalty_per_unit", "holding_cost_pct"]]
    dc = raw["dc"][["dc_id", "dc_name", "city", "region", "transfer_cost_per_unit"]]

    dd = dd.merge(sm, on="sku_id", how="left")
    dd = dd.merge(dc, on="dc_id", how="left")

    # Expired batch qty per dc x sku (as of ANALYSIS_DATE)
    expired_qty = (
        raw["batches"]
        .query("expiry_date < @ANALYSIS_DATE")
        .groupby(["dc_id", "sku_id"])["quantity"]
        .sum()
        .reset_index()
        .rename(columns={"quantity": "expired_qty"})
    )

    dd = dd.merge(expired_qty, on=["dc_id", "sku_id"], how="left")
    dd["expired_qty"] = dd["expired_qty"].fillna(0)

    # Usable inventory: physical − reserved − expired + inbound
    dd["usable_inventory"] = (
        dd["physical_inventory"]
        - dd["reserved_inventory"]
        - dd["expired_qty"]
        + dd["inbound_inventory"]
    ).clip(lower=0)

    # 14-day rolling avg demand per dc x sku
    dd = dd.sort_values(["dc_id", "sku_id", "date"])
    dd["demand_14d_avg"] = (
        dd.groupby(["dc_id", "sku_id"])["demand_units"]
        .transform(lambda x: x.rolling(14, min_periods=1).mean())
    )

    # Days of stock remaining (from last row's usable inventory)
    dd["days_of_stock"] = np.where(
        dd["demand_14d_avg"] > 0,
        dd["usable_inventory"] / dd["demand_14d_avg"],
        999,
    ).round(1)

    dd["projected_stockout_date"] = dd["date"] + pd.to_timedelta(
        dd["days_of_stock"].clip(upper=365).astype(int), unit="D"
    )

    # Holding cost per unit per day
    dd["holding_cost_daily"] = dd["unit_cost"] * dd["holding_cost_pct"] / 365

    # Inventory health flag
    conditions = [
        dd["usable_inventory"] <= dd["safety_stock"],
        dd["usable_inventory"] <= dd["reorder_point"],
    ]
    choices = ["red", "yellow"]
    dd["health_flag"] = np.select(conditions, choices, default="green")

    return dd


def get_latest_snapshot(raw: dict) -> pd.DataFrame:
    """Return one row per dc x sku = latest date (2026-08-13)."""
    enriched = get_demand_enriched(raw)
    latest = enriched[enriched["date"] == enriched["date"].max()].copy()
    return latest.reset_index(drop=True)


def get_lead_times(raw: dict) -> pd.DataFrame:
    return raw["lead_times"].copy()


def get_batches_for(raw: dict, dc_id: str, sku_id: str) -> pd.DataFrame:
    """Return batches for a specific dc x sku, sorted FEFO."""
    bt = raw["batches"]
    mask = (bt["dc_id"] == dc_id) & (bt["sku_id"] == sku_id)
    result = bt[mask].copy()
    result["days_to_expiry"] = (result["expiry_date"] - ANALYSIS_DATE).dt.days
    result["shelf_life_remaining_pct"] = (
        result["days_to_expiry"] / result["shelf_life_days"] * 100
    ).clip(0, 100).round(1)
    return result.sort_values("expiry_date").reset_index(drop=True)


def get_dc_health_summary(raw: dict) -> pd.DataFrame:
    """
    Per DC: #SKUs, #critical SKUs at risk, #stockout, near-expiry qty, pending inbound.
    """
    snap = get_latest_snapshot(raw)
    bt = raw["batches"].copy()
    bt["days_to_expiry"] = (bt["expiry_date"] - ANALYSIS_DATE).dt.days

    near_expiry_dc = (
        bt[bt["days_to_expiry"].between(0, 90)]
        .groupby("dc_id")["quantity"]
        .sum()
        .reset_index()
        .rename(columns={"quantity": "near_expiry_units"})
    )

    def agg(g):
        sm_sub = raw["sku"][["sku_id", "criticality"]].set_index("sku_id")
        crits = snap[snap["dc_id"] == g.name]["sku_id"].map(sm_sub["criticality"])
        return pd.Series({
            "n_skus": len(g),
            "n_critical_skus": int((crits == "High").sum()),
            "n_stockout_risk": int((g["health_flag"] == "red").sum()),
            "n_reorder_needed": int((g["health_flag"].isin(["red", "yellow"])).sum()),
            "pending_inbound": int(g["inbound_inventory"].sum()),
            "avg_health": g["health_flag"].map({"red": 0, "yellow": 1, "green": 2}).mean(),
        })

    summary = snap.groupby("dc_id").apply(agg).reset_index()
    summary = summary.merge(near_expiry_dc, on="dc_id", how="left")
    summary["near_expiry_units"] = summary["near_expiry_units"].fillna(0)
    summary["dc_health"] = summary["avg_health"].apply(
        lambda x: "green" if x > 1.5 else ("yellow" if x > 0.5 else "red")
    )
    dc_info = raw["dc"][["dc_id", "dc_name", "city", "region"]]
    summary = summary.merge(dc_info, on="dc_id", how="left")
    return summary
