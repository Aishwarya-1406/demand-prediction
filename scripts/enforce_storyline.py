import pandas as pd
import numpy as np
from pathlib import Path

# Paths
DATA_DIR = Path("data")
DEMAND_CSV = DATA_DIR / "daily_demand_inventory.csv"
BATCHES_CSV = DATA_DIR / "batches.csv"
SKU_CSV = DATA_DIR / "sku_master.csv"
DC_CSV = DATA_DIR / "dc_master.csv"
ANALYSIS_DATE = pd.Timestamp("2026-08-13")

print("Enforcing Problem Statement Storyline on Data...")

# Load Data
demand = pd.read_csv(DEMAND_CSV, parse_dates=["date"])
batches = pd.read_csv(BATCHES_CSV, parse_dates=["manufacture_date", "expiry_date", "receipt_date_at_dc"])
skus = pd.read_csv(SKU_CSV)
dcs = pd.read_csv(DC_CSV)

# Identify Tiers and SKUs
tier2_dcs = dcs[dcs["dc_tier"] == "Tier-2"]["dc_id"].tolist()
metro_dcs = dcs[dcs["dc_tier"] == "Metro"]["dc_id"].tolist()
critical_skus = skus[skus["criticality"] == "High"]["sku_id"].tolist()

print(f"Tier-2 DCs: {tier2_dcs}")
print(f"Metro DCs: {metro_dcs}")
print(f"Critical SKUs: {len(critical_skus)} total")

# 1. Enforce Tier-2 Critical Stockouts (Flu Season Spikes)
# Target: Last 14 days, Tier-2, Critical SKUs
mask_tier2 = (
    (demand["dc_id"].isin(tier2_dcs)) & 
    (demand["sku_id"].isin(critical_skus)) & 
    (demand["date"] >= (ANALYSIS_DATE - pd.Timedelta(days=14)))
)

# Inflate demand by 60% - 100%
spike_multiplier = np.random.uniform(1.6, 2.0, size=mask_tier2.sum())
demand.loc[mask_tier2, "demand_units"] = (demand.loc[mask_tier2, "demand_units"] * spike_multiplier).fillna(0).astype(int)

# Crash physical inventory to simulate stockout (making it near 0 in the last 7 days)
mask_tier2_stockout = (
    (demand["dc_id"].isin(tier2_dcs)) & 
    (demand["sku_id"].isin(critical_skus)) & 
    (demand["date"] >= (ANALYSIS_DATE - pd.Timedelta(days=7)))
)
demand.loc[mask_tier2_stockout, "physical_inventory"] = np.random.randint(0, 5, size=mask_tier2_stockout.sum())
demand.loc[mask_tier2_stockout, "usable_inventory"] = demand.loc[mask_tier2_stockout, "physical_inventory"]

# 2. Enforce Metro Excess Near-Expiry Stock
# Target: Metro DCs, random SKUs
np.random.seed(42)
new_batches = []
batch_counter = 90000 # Use high batch ID to avoid collisions
near_expiry_sku_dc = []

for dc in metro_dcs:
    # Pick 5-10 random SKUs per Metro DC to be flooded with near expiry stock
    chosen_skus = np.random.choice(skus["sku_id"], size=np.random.randint(5, 11), replace=False)
    for sku in chosen_skus:
        # Create a massive near expiry batch
        qty = np.random.randint(2000, 5000)
        days_to_expiry = np.random.randint(10, 60)
        expiry_date = ANALYSIS_DATE + pd.Timedelta(days=days_to_expiry)
        mfg_date = expiry_date - pd.Timedelta(days=365)
        
        new_batches.append({
            "batch_id": f"BAT{batch_counter}",
            "dc_id": dc,
            "sku_id": sku,
            "quantity": qty,
            "manufacture_date": mfg_date.date(),
            "expiry_date": expiry_date.date(),
            "receipt_date_at_dc": (mfg_date + pd.Timedelta(days=10)).date(),
            "shelf_life_days": 365,
            "batch_status": "active"
        })
        batch_counter += 1
        near_expiry_sku_dc.append((dc, sku, qty))

new_batches_df = pd.DataFrame(new_batches)
new_batches_df["manufacture_date"] = pd.to_datetime(new_batches_df["manufacture_date"])
new_batches_df["expiry_date"] = pd.to_datetime(new_batches_df["expiry_date"])
new_batches_df["receipt_date_at_dc"] = pd.to_datetime(new_batches_df["receipt_date_at_dc"])

batches = pd.concat([batches, new_batches_df], ignore_index=True)

# 3. Inflate Metro Inventory to match the new batches
# If we added 3000 units of a batch, the physical_inventory must be at least 3000
for dc, sku, qty in near_expiry_sku_dc:
    mask = (demand["dc_id"] == dc) & (demand["sku_id"] == sku) & (demand["date"] >= (ANALYSIS_DATE - pd.Timedelta(days=90)))
    demand.loc[mask, "physical_inventory"] += qty
    demand.loc[mask, "usable_inventory"] += qty

# Save modifications back to disk
print("Saving modified datasets...")
demand.to_csv(DEMAND_CSV, index=False)
batches.to_csv(BATCHES_CSV, index=False)

print(f"Added {len(new_batches)} massive near-expiry batches to Metro DCs.")
print(f"Crashed inventory for {len(critical_skus)} critical SKUs in Tier-2 DCs.")
print("Done!")
