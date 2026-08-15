"""
evaluate_classification.py
==========================
Evaluates the decision layer (green/yellow/red flags and Tier 0-3 escalation)
as a classification problem using the 21-day chronological holdout.

Ground-truth definition (no future leakage):
  - For each SKU×DC on each day D in the holdout window, we reconstruct the
    health_flag and escalation_tier using ONLY data available on day D.
  - Ground-truth label: did usable_inventory breach safety_stock
    (health_flag == 'red') within the next N days, where N = lead_time_regular
    for that SKU×DC (same window used by the replenishment engine)?

Outputs: precision, recall, F1, confusion matrix for:
  (a) red flag → actual stockout/breach within lead time
  (b) Tier 2+3 (escalate/emergency) → actual high-severity outcome
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import (
    precision_score, recall_score, f1_score, confusion_matrix,
    classification_report
)

# ── Path setup ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from engine.data_loader import load_all, get_demand_enriched
from engine.escalation import classify_escalation_tier

# ── Constants ─────────────────────────────────────────────────────────────────
HOLDOUT_DAYS = 21
ANALYSIS_DATE = pd.Timestamp("2026-08-13")
HOLDOUT_START = ANALYSIS_DATE - pd.Timedelta(days=HOLDOUT_DAYS - 1)  # 2026-07-24
DEFAULT_LEAD_TIME = 7   # fallback if no lead-time row exists

print(f"Loading data...")
raw = load_all()
dd_full = get_demand_enriched(raw)
lt_df   = raw["lead_times"]
sm      = raw["sku"].set_index("sku_id")

# Only rows in the holdout window
dd_holdout = dd_full[dd_full["date"] >= HOLDOUT_START].copy()
all_dates  = sorted(dd_holdout["date"].unique())
print(f"Holdout window: {all_dates[0].date()} → {all_dates[-1].date()} ({len(all_dates)} days)")

sku_ids = sorted(dd_full["sku_id"].unique())
dc_ids  = sorted(dd_full["dc_id"].unique())
print(f"SKUs: {len(sku_ids)}, DCs: {len(dc_ids)}, Combinations: {len(sku_ids)*len(dc_ids)}")

# Build lead-time lookup per (dc_id, sku_id) → regular lead time
def get_lead_time(dc_id, sku_id):
    rows = lt_df[
        (lt_df["dc_id"] == dc_id) &
        (lt_df["sku_id"] == sku_id) &
        (lt_df["supplier_type"] == "regular")
    ]
    if rows.empty:
        return DEFAULT_LEAD_TIME
    return int(rows["lead_time_days"].iloc[0])


# ── Build evaluation records ──────────────────────────────────────────────────
records = []

for dc_id in dc_ids:
    for sku_id in sku_ids:
        lt_reg = get_lead_time(dc_id, sku_id)
        criticality = sm.loc[sku_id, "criticality"] if sku_id in sm.index else "Medium"

        sub = dd_full[
            (dd_full["dc_id"] == dc_id) & (dd_full["sku_id"] == sku_id)
        ].sort_values("date").copy()

        if len(sub) < HOLDOUT_DAYS + 14:
            continue  # insufficient history

        # Only iterate days that are in the holdout window
        holdout_sub = sub[sub["date"] >= HOLDOUT_START].reset_index(drop=True)

        for i, row in holdout_sub.iterrows():
            day_d = row["date"]

            # ── Predicted labels (from row's health_flag / escalation logic) ──
            # health_flag is already computed from day-of data (usable vs safety stock)
            health_flag = str(row["health_flag"])

            usable       = float(row["usable_inventory"])
            safety_stock = float(row["safety_stock"])
            inbound      = float(row["inbound_inventory"])
            demand_14d   = float(row.get("demand_14d_avg", 1) or 1)
            days_till_so = usable / demand_14d if demand_14d > 0 else 9999.0

            # near_expiry_qty: approximate from batch data (no future info)
            near_expiry_qty = 0  # conservative — batch details need separate join

            tier = classify_escalation_tier(
                criticality=criticality,
                health_flag=health_flag,
                days_till_stockout=days_till_so,
                lead_time_days=lt_reg,
                near_expiry_qty=near_expiry_qty,
                avg_daily_demand=demand_14d,
                safety_stock=safety_stock,
                usable_inventory=usable,
                inbound_inventory=inbound,
            )

            # ── Ground truth: did health_flag go 'red' within the next lt_reg days? ──
            future_rows = sub[
                (sub["date"] > day_d) &
                (sub["date"] <= day_d + pd.Timedelta(days=lt_reg))
            ]
            if future_rows.empty:
                continue   # no future data — skip this day (end of dataset)

            actual_breach = int((future_rows["health_flag"] == "red").any())
            actual_stockout = int(
                (future_rows["usable_inventory"] <= future_rows["safety_stock"]).any()
            )
            # Severity: 0=no breach, 1=yellow within window, 2=red (breach/stockout)
            if (future_rows["health_flag"] == "red").any():
                actual_severity = 2
            elif (future_rows["health_flag"] == "yellow").any():
                actual_severity = 1
            else:
                actual_severity = 0

            records.append({
                "dc_id":            dc_id,
                "sku_id":           sku_id,
                "date":             day_d,
                "criticality":      criticality,
                "health_flag_pred": health_flag,
                "escalation_tier":  tier,
                "actual_breach":    actual_breach,
                "actual_severity":  actual_severity,
                "days_till_so":     round(days_till_so, 1),
            })

df = pd.DataFrame(records)
print(f"\nTotal evaluation records: {len(df)}")
print(f"Actual breaches (red within lead time): {df['actual_breach'].sum()}")
print(f"Non-breach records: {(df['actual_breach']==0).sum()}")

# ── (a) RED FLAG → Actual stockout/breach within lead time ───────────────────
print("\n" + "="*65)
print("(a) RED FLAG PREDICTION → Actual breach within lead-time window")
print("="*65)

y_pred_red   = (df["health_flag_pred"] == "red").astype(int).values
y_true_breach = df["actual_breach"].values

prec_red  = precision_score(y_true_breach, y_pred_red, zero_division=0)
rec_red   = recall_score(y_true_breach, y_pred_red, zero_division=0)
f1_red    = f1_score(y_true_breach, y_pred_red, zero_division=0)
cm_red    = confusion_matrix(y_true_breach, y_pred_red)

print(f"\nPrecision : {prec_red:.3f}")
print(f"Recall    : {rec_red:.3f}")
print(f"F1 Score  : {f1_red:.3f}")
print(f"\nConfusion matrix (rows=Actual, cols=Predicted):")
print(f"           Pred-Green  Pred-Red")
print(f"True-OK    {cm_red[0,0]:>10d}  {cm_red[0,1]:>8d}")
print(f"True-Red   {cm_red[1,0]:>10d}  {cm_red[1,1]:>8d}")

# ── (b) ESCALATION TIER → Actual outcome severity ────────────────────────────
print("\n" + "="*65)
print("(b) ESCALATION TIER 2/3 (Escalate/Emergency) → Actual severity ≥ 2")
print("="*65)

# Binary: did we flag tier ≥ 2, and did actual severity hit level 2?
y_pred_esc    = (df["escalation_tier"] >= 2).astype(int).values
y_true_severe = (df["actual_severity"] >= 2).astype(int).values

prec_esc  = precision_score(y_true_severe, y_pred_esc, zero_division=0)
rec_esc   = recall_score(y_true_severe, y_pred_esc, zero_division=0)
f1_esc    = f1_score(y_true_severe, y_pred_esc, zero_division=0)
cm_esc    = confusion_matrix(y_true_severe, y_pred_esc)

print(f"\nPrecision : {prec_esc:.3f}")
print(f"Recall    : {rec_esc:.3f}")
print(f"F1 Score  : {f1_esc:.3f}")
print(f"\nConfusion matrix (rows=Actual, cols=Predicted):")
print(f"           Pred-Low/Med  Pred-Esc")
print(f"True-OK    {cm_esc[0,0]:>12d}  {cm_esc[0,1]:>8d}")
print(f"True-Severe{cm_esc[1,0]:>12d}  {cm_esc[1,1]:>8d}")

# ── Multi-class escalation tier ──────────────────────────────────────────────
print("\n" + "="*65)
print("(c) Multi-class escalation tier (0/1/2/3) classification report")
print("="*65)

y_pred_tier = df["escalation_tier"].values
# Ground truth tier: map actual_severity to tier-like labels
# 0 severity → tier 0, 1 severity → tier 1, 2 severity → tier 2+
y_true_tier_mapped = df["actual_severity"].values  # 0,1,2 scale

print(classification_report(
    y_true_tier_mapped, np.minimum(y_pred_tier, 2),
    target_names=["Severity-0 (OK)", "Severity-1 (Yellow)", "Severity-2+ (Red/Emergency)"],
    zero_division=0,
))

# ── Flag-level breakdown by criticality ──────────────────────────────────────
print("\n" + "="*65)
print("(d) Red-flag precision/recall by SKU criticality")
print("="*65)
for crit in ["High", "Medium", "Low"]:
    sub = df[df["criticality"] == crit]
    if len(sub) == 0:
        continue
    yp = (sub["health_flag_pred"] == "red").astype(int).values
    yt = sub["actual_breach"].values
    p  = precision_score(yt, yp, zero_division=0)
    r  = recall_score(yt, yp, zero_division=0)
    f  = f1_score(yt, yp, zero_division=0)
    n  = len(sub)
    n_pos = yt.sum()
    print(f"  {crit:6s} criticality: n={n:5d}, actual_breaches={n_pos:4d}  "
          f"Prec={p:.3f}  Rec={r:.3f}  F1={f:.3f}")

# ── Summary table for documentation ──────────────────────────────────────────
print("\n" + "="*65)
print("SUMMARY FOR DOCUMENTATION")
print("="*65)
print(f"""
Evaluation: {len(df):,} SKU×DC×day records over 21-day holdout
(window: {HOLDOUT_START.date()} – {ANALYSIS_DATE.date()})

(a) Red health flag → breach within lead-time window
    Precision : {prec_red:.3f}
    Recall    : {rec_red:.3f}
    F1        : {f1_red:.3f}
    CM: TN={cm_red[0,0]}, FP={cm_red[0,1]}, FN={cm_red[1,0]}, TP={cm_red[1,1]}

(b) Tier 2/3 escalation → actual severity ≥ 2
    Precision : {prec_esc:.3f}
    Recall    : {rec_esc:.3f}
    F1        : {f1_esc:.3f}
    CM: TN={cm_esc[0,0]}, FP={cm_esc[0,1]}, FN={cm_esc[1,0]}, TP={cm_esc[1,1]}
""")
