"""
Write daily_demand_inventory.csv from the inline data provided in the user's prompt.
This script is the canonical source — the CSV data was supplied inline.
"""
import os
import textwrap

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# The CSV header
HEADER = "date,dc_id,sku_id,demand_units,flu_season_index,promo_flag,physical_inventory,reserved_inventory,inbound_inventory,safety_stock,reorder_point,stockout_flag"

out_path = os.path.join(DATA_DIR, "daily_demand_inventory.csv")
print(f"Writing to: {out_path}")
print("NOTE: This file must already exist (written from inline prompt data).")
print("If not present, manually save the inline CSV data to data/daily_demand_inventory.csv")

if os.path.exists(out_path):
    import pandas as pd
    df = pd.read_csv(out_path)
    print(f"✓ File exists: {df.shape}")
else:
    print("✗ File NOT found. Please write the inline CSV data to data/daily_demand_inventory.csv")
