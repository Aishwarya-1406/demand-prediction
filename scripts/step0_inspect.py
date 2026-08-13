"""
Step 0: Data Inspection Script for MedCare Pharma Demand Sensing Project
Reads all 5 CSVs and produces shape, dtypes, sample rows, null %, 
join key analysis, and field mapping.
"""

import pandas as pd
import numpy as np
import os
import sys

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

def pct_null(df):
    return (df.isnull().sum() / len(df) * 100).round(2)

def inspect(name, df):
    print(f"\n{'='*70}")
    print(f"  FILE: {name}")
    print(f"{'='*70}")
    print(f"Shape: {df.shape[0]:,} rows × {df.shape[1]} columns")
    print(f"\nColumns & dtypes:")
    for c in df.columns:
        print(f"  {c:<35} {str(df[c].dtype):<12} null%={pct_null(df)[c]:.1f}%")
    print(f"\nSample rows (head 5):")
    print(df.head(5).to_string(index=False))
    print(f"\nNull counts:")
    nulls = df.isnull().sum()
    print(nulls[nulls > 0].to_string() if nulls.sum() > 0 else "  (none)")

def main():
    print("\n" + "█"*70)
    print("  STEP 0: MedCare Pharma — Data Inspection Report")
    print("█"*70)

    # ── Load all files ───────────────────────────────────────────────────
    files = {
        "daily_demand_inventory.csv": None,
        "sku_master.csv": None,
        "dc_master.csv": None,
        "lead_times.csv": None,
        "batches.csv": None,
    }
    for fname in list(files.keys()):
        fpath = os.path.join(DATA_DIR, fname)
        if not os.path.exists(fpath):
            print(f"\n⚠  {fname} NOT FOUND at {fpath}")
            files[fname] = None
        else:
            df = pd.read_csv(fpath)
            files[fname] = df
            print(f"✓  Loaded {fname}: {df.shape}")

    # ── Inspect each file ────────────────────────────────────────────────
    for fname, df in files.items():
        if df is not None:
            inspect(fname, df)
        else:
            print(f"\n{'='*70}\n  FILE: {fname}  — MISSING\n{'='*70}")

    # ── Join Key Analysis ────────────────────────────────────────────────
    print("\n\n" + "="*70)
    print("  JOIN KEY ANALYSIS")
    print("="*70)

    dd = files.get("daily_demand_inventory.csv")
    sm = files.get("sku_master.csv")
    dc = files.get("dc_master.csv")
    lt = files.get("lead_times.csv")
    bt = files.get("batches.csv")

    if dd is not None:
        print(f"\ndaily_demand_inventory.csv:")
        print(f"  dc_id   unique: {dd['dc_id'].nunique()}  → {sorted(dd['dc_id'].unique())}")
        print(f"  sku_id  unique: {dd['sku_id'].nunique()} → {sorted(dd['sku_id'].unique())}")
        print(f"  date    range: {dd['date'].min()} → {dd['date'].max()}")
        print(f"  rows per (dc×sku): {dd.groupby(['dc_id','sku_id']).size().describe().to_dict()}")

    if sm is not None:
        print(f"\nsku_master.csv:")
        print(f"  sku_id unique: {sm['sku_id'].nunique()} → {sorted(sm['sku_id'].unique())}")
        if 'criticality' in sm.columns:
            print(f"  criticality values: {sm['criticality'].value_counts().to_dict()}")

    if dc is not None:
        print(f"\ndc_master.csv:")
        print(f"  dc_id unique: {dc['dc_id'].nunique()} → {sorted(dc['dc_id'].unique())}")

    if lt is not None:
        print(f"\nlead_times.csv:")
        print(f"  sku_id unique: {lt['sku_id'].nunique()}")
        print(f"  dc_id  unique: {lt['dc_id'].nunique()}")
        print(f"  supplier_type values: {lt['supplier_type'].value_counts().to_dict()}")
        print(f"  lead_time_days range: {lt['lead_time_days'].min()} – {lt['lead_time_days'].max()}")

    if bt is not None:
        print(f"\nbatches.csv:")
        print(f"  batch_id unique: {bt['batch_id'].nunique()}")
        print(f"  sku_id   unique: {bt['sku_id'].nunique()}")
        print(f"  dc_id    unique: {bt['dc_id'].nunique()}")
        if 'expiry_date' in bt.columns:
            print(f"  expiry_date range: {bt['expiry_date'].min()} → {bt['expiry_date'].max()}")

    # ── Key column summaries ─────────────────────────────────────────────
    if dd is not None:
        print(f"\n\n{'='*70}")
        print("  KEY COLUMN STATISTICS — daily_demand_inventory.csv")
        print("="*70)
        num_cols = ['demand_units','flu_season_index','promo_flag',
                    'physical_inventory','reserved_inventory','inbound_inventory',
                    'safety_stock','reorder_point','stockout_flag']
        num_cols = [c for c in num_cols if c in dd.columns]
        print(dd[num_cols].describe().round(2).to_string())

        print(f"\nstockout_flag distribution:")
        print(f"  {dd['stockout_flag'].value_counts().to_dict()}")
        print(f"  Stockout rate: {dd['stockout_flag'].mean()*100:.1f}%")

        print(f"\npromo_flag distribution: {dd['promo_flag'].value_counts().to_dict()}")
        print(f"flu_season_index distribution: {dd['flu_season_index'].value_counts().to_dict()}")

    # ── Field Mapping ─────────────────────────────────────────────────────
    print("\n\n" + "="*70)
    print("  FIELD MAPPING: Concept → Real Column → Status")
    print("="*70)
    mapping = [
        ("Demand","daily_demand_inventory.demand_units","DIRECT"),
        ("Physical Inventory","daily_demand_inventory.physical_inventory","DIRECT"),
        ("Reserved / Committed Inventory","daily_demand_inventory.reserved_inventory","DIRECT"),
        ("Inbound Inventory","daily_demand_inventory.inbound_inventory","DIRECT"),
        ("Safety Stock","daily_demand_inventory.safety_stock","DIRECT"),
        ("Reorder Point","daily_demand_inventory.reorder_point","DIRECT"),
        ("Stockout Flag","daily_demand_inventory.stockout_flag","DIRECT"),
        ("Flu Season Signal","daily_demand_inventory.flu_season_index","DIRECT (binary 0/1)"),
        ("Promotion Flag","daily_demand_inventory.promo_flag","DIRECT (binary 0/1)"),
        ("Usable Inventory","physical − reserved − expired + inbound","DERIVED: physical_inventory - reserved_inventory + inbound_inventory (expired handled via batches)"),
        ("Batch Expiry Date","batches.expiry_date","DIRECT (from batches.csv)"),
        ("Batch Quantity","batches.quantity","DIRECT (from batches.csv)"),
        ("Shelf Life Remaining","TODAY - expiry_date","DERIVED from expiry_date"),
        ("Expired / Unusable Qty","batches where expiry_date < today","DERIVED: sum qty of expired batches"),
        ("SKU Criticality","sku_master.criticality","DIRECT (High/Medium/Low)"),
        ("Purchase Cost (regular)","sku_master.purchase_cost_regular","DIRECT"),
        ("Purchase Cost (local)","sku_master.purchase_cost_local","DIRECT"),
        ("Stockout Penalty","sku_master.stockout_penalty_per_unit","DIRECT"),
        ("Transfer Cost","dc_master.transfer_cost_per_unit","DIRECT"),
        ("Lead Time (regular supplier)","lead_times.lead_time_days WHERE supplier_type=regular","DIRECT"),
        ("Lead Time (local supplier)","lead_times.lead_time_days WHERE supplier_type=local","DIRECT"),
        ("Lead Time (DC transfer)","lead_times.lead_time_days WHERE supplier_type=transfer","DIRECT"),
        ("Expiry Wastage Cost","unit_cost × expired_quantity","DERIVED: sku_master.unit_cost × expired batch qty"),
        ("Demand During Lead Time","forecast × lead_time_days","DERIVED from forecast model output"),
        ("Stockout Risk","days until usable_inventory < safety_stock","DERIVED from usable inventory + forecast"),
        ("Trend / Seasonality","engineered from date, flu_season_index, promo_flag","DERIVED: DOW, month, rolling avg, flu/promo interaction"),
        ("Expiry Wastage Cost per Option","unit_cost × transferred_qty_that_expires","DERIVED in decision engine"),
    ]
    print(f"\n{'Concept':<40} {'Status':<12} {'Source / Derivation'}")
    print("-"*120)
    for concept, source, status in mapping:
        print(f"{concept:<40} {status.split(':')[0]:<12} {source}")

    print("\n\n" + "="*70)
    print("  MISSING FIELDS & DERIVATION STRATEGY")
    print("="*70)
    missing = [
        ("Expired/Unusable Qty at day level",
         "daily_demand_inventory has no column for expired stock",
         "DERIVATION: Use batches.csv expiry_date + quantity; sum qty of batches with expiry_date < current_date per dc/sku. Will be recomputed at each analysis date."),
        ("Trend classification label",
         "No explicit trend label column",
         "DERIVATION: Compute from rolling 14-day vs 28-day avg demand ratio → label as rising/falling/stable/seasonal/surge."),
        ("Supplier reliability flag",
         "No unreliable_supplier or supplier_flag column",
         "DERIVATION: Implemented as a configurable business-rule override in the Human Agent layer (DACDF), not from data."),
        ("Holding cost",
         "No daily holding cost column",
         "DERIVATION: sku_master.unit_cost × sku_master.holding_cost_pct / 365 per unit per day."),
        ("Batch allocation to DC",
         "batches.csv provides this",
         "DIRECT — handled via dc_id in batches.csv"),
    ]
    for field, gap, strategy in missing:
        print(f"\n  MISSING: {field}")
        print(f"    Gap:      {gap}")
        print(f"    Strategy: {strategy}")

    print("\n\n✅ Step 0 Complete. Ready to proceed to forecasting module.")

if __name__ == "__main__":
    main()
