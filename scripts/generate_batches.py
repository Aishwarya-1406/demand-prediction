"""
Generate batches.csv from scratch based on the SKUs and DCs visible in
daily_demand_inventory.csv.  We synthesise realistic batch records that
have actual expiry dates and quantities — this is the ONLY generated file;
everything else is read from the user-supplied CSVs.

Assumptions (clearly flagged):
  - Batch shelf life: sampled per SKU category from a realistic range.
  - Batch quantity: matches approximate restocking amounts seen in the
    inbound_inventory column of the demand file.
  - Batch status: 'active' or 'expired'.
  - Manufacture date derived from expiry_date − shelf_life.
  - Receipt date at DC is manufacture_date + shipping days (2-7 days).

These assumptions will be stated in the field-mapping doc.
"""
import pandas as pd
import numpy as np
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
np.random.seed(42)

# ── Load demand data to know which dc×sku combos exist ───────────────────
dd_path = os.path.join(DATA_DIR, "daily_demand_inventory.csv")
if not os.path.exists(dd_path):
    print("daily_demand_inventory.csv not found; skipping batch generation.")
    exit()

dd = pd.read_csv(dd_path, parse_dates=["date"])

# SKU → shelf_life_days (typical pharmaceutical shelf life)
SKU_SHELF_LIFE = {
    "SKU001": 730,   # Amoxicillin 2yr
    "SKU002": 730,   # Azithromycin 2yr
    "SKU003": 1095,  # Metformin 3yr
    "SKU004": 1095,  # Paracetamol 3yr
    "SKU005": 1095,  # Ibuprofen 3yr
    "SKU006": 730,   # Omeprazole 2yr
    "SKU007": 1095,  # Atorvastatin 3yr
    "SKU008": 730,   # Losartan 2yr
    "SKU009": 1095,  # Amlodipine 3yr
    "SKU010": 730,   # Metronidazole 2yr
    "SKU011": 1460,  # Cetirizine 4yr
    "SKU012": 730,   # Pantoprazole 2yr
    "SKU013": 730,   # Doxycycline 2yr
    "SKU014": 1460,  # Ranitidine 4yr
    "SKU015": 1825,  # Folic Acid 5yr
}

analysis_date = pd.Timestamp("2026-08-13")  # "today" / latest date in data

records = []
batch_counter = 1

dc_sku_combos = dd[["dc_id", "sku_id"]].drop_duplicates().values

for dc_id, sku_id in dc_sku_combos:
    shelf_life = SKU_SHELF_LIFE.get(sku_id, 730)
    # Existing inventory on last date
    last_row = dd[(dd["dc_id"] == dc_id) & (dd["sku_id"] == sku_id)].sort_values("date").iloc[-1]
    phys_inv = last_row["physical_inventory"]
    if phys_inv <= 0:
        phys_inv = 0  # no active stock (stockout)

    # Generate 2-4 active batches that sum roughly to physical_inventory
    n_batches = np.random.randint(2, 5)
    if phys_inv > 0:
        splits = np.random.dirichlet(np.ones(n_batches)) * phys_inv
        splits = np.round(splits).astype(int)
        # Adjust rounding
        splits[-1] += int(phys_inv) - int(splits.sum())
        splits = np.clip(splits, 0, None)
    else:
        splits = np.zeros(n_batches, dtype=int)

    for i, qty in enumerate(splits):
        if qty == 0 and phys_inv > 0:
            continue
        # Manufacture date: between 6 months and shelf_life back from today
        days_old = np.random.randint(int(shelf_life * 0.1), int(shelf_life * 0.7))
        mfg_date = analysis_date - pd.Timedelta(days=days_old)
        expiry_date = mfg_date + pd.Timedelta(days=shelf_life)
        receipt_days = np.random.randint(2, 8)
        receipt_date = mfg_date + pd.Timedelta(days=receipt_days)
        status = "active" if expiry_date > analysis_date else "expired"
        # For expired batches force qty to small numbers
        if status == "expired":
            qty = int(np.random.randint(0, 50))

        records.append({
            "batch_id":       f"BATCH{batch_counter:05d}",
            "dc_id":          dc_id,
            "sku_id":         sku_id,
            "quantity":       max(0, int(qty)),
            "manufacture_date": mfg_date.date(),
            "expiry_date":    expiry_date.date(),
            "receipt_date_at_dc": receipt_date.date(),
            "shelf_life_days":  shelf_life,
            "batch_status":   status,
        })
        batch_counter += 1

    # Add 1–2 near-expiry batches (expire within 90 days)
    n_near = np.random.randint(0, 2)
    for _ in range(n_near):
        days_to_expiry = np.random.randint(5, 90)
        expiry_date = analysis_date + pd.Timedelta(days=days_to_expiry)
        mfg_date = expiry_date - pd.Timedelta(days=shelf_life)
        receipt_date = mfg_date + pd.Timedelta(days=np.random.randint(2, 8))
        qty = int(np.random.randint(10, 150))
        records.append({
            "batch_id":       f"BATCH{batch_counter:05d}",
            "dc_id":          dc_id,
            "sku_id":         sku_id,
            "quantity":       qty,
            "manufacture_date": mfg_date.date(),
            "expiry_date":    expiry_date.date(),
            "receipt_date_at_dc": receipt_date.date(),
            "shelf_life_days":  shelf_life,
            "batch_status":   "near_expiry",
        })
        batch_counter += 1

batches_df = pd.DataFrame(records)
out_path = os.path.join(DATA_DIR, "batches.csv")
batches_df.to_csv(out_path, index=False)
print(f"✓ Generated batches.csv: {batches_df.shape}")
print(batches_df.head(10).to_string(index=False))
print(f"\nbatch_status distribution:\n{batches_df['batch_status'].value_counts()}")
