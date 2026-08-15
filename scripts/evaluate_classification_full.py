"""
evaluate_classification_full.py
================================
Full-dataset classification evaluation for documentation.
Since the 21-day holdout has 0 red events (no stockouts in that period),
we use the full historical backtest (~181 days) with rolling forward windows.

This is reported honestly with the limitation noted.
"""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import (
    precision_score, recall_score, f1_score, confusion_matrix,
    classification_report
)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from engine.data_loader import load_all, get_demand_enriched
from engine.escalation import classify_escalation_tier

print("Loading data...")
raw = load_all()
dd_full = get_demand_enriched(raw)
lt_df   = raw["lead_times"]
sm      = raw["sku"].set_index("sku_id")

ANALYSIS_DATE = pd.Timestamp("2026-08-13")
HOLDOUT_START = ANALYSIS_DATE - pd.Timedelta(days=20)   # 21-day holdout window

def get_lead_time(dc_id, sku_id):
    rows = lt_df[
        (lt_df["dc_id"] == dc_id) &
        (lt_df["sku_id"] == sku_id) &
        (lt_df["supplier_type"] == "regular")
    ]
    if rows.empty:
        return 7
    return int(rows["lead_time_days"].iloc[0])


# ─────────────────────────────────────────────────────────────────────────────
# PART 1: 21-day holdout — report honestly that breaches are 0
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("PART 1: 21-day holdout window (2026-07-24 to 2026-08-13)")
print("="*70)

holdout_records = []
for (dc_id, sku_id), grp in dd_full.groupby(["dc_id", "sku_id"]):
    lt_reg = get_lead_time(dc_id, sku_id)
    criticality = sm.loc[sku_id, "criticality"] if sku_id in sm.index else "Medium"
    grp = grp.sort_values("date")
    holdout_grp = grp[grp["date"] >= HOLDOUT_START]
    for _, row in holdout_grp.iterrows():
        day_d = row["date"]
        health_flag = str(row["health_flag"])
        usable = float(row["usable_inventory"])
        safety_stock = float(row["safety_stock"])
        inbound = float(row["inbound_inventory"])
        demand_14d = float(row.get("demand_14d_avg", 1) or 1)
        days_till_so = min(usable / demand_14d, 9999) if demand_14d > 0 else 9999
        tier = classify_escalation_tier(
            criticality=criticality,
            health_flag=health_flag,
            days_till_stockout=days_till_so,
            lead_time_days=lt_reg,
            near_expiry_qty=0,
            avg_daily_demand=demand_14d,
            safety_stock=safety_stock,
            usable_inventory=usable,
            inbound_inventory=inbound,
        )
        future = grp[(grp["date"] > day_d) & (grp["date"] <= day_d + pd.Timedelta(days=lt_reg))]
        if future.empty:
            continue
        actual_breach = int((future["health_flag"] == "red").any())
        actual_severity = 2 if (future["health_flag"] == "red").any() else (1 if (future["health_flag"] == "yellow").any() else 0)
        holdout_records.append({
            "dc_id": dc_id, "sku_id": sku_id, "date": day_d,
            "criticality": criticality,
            "health_flag_pred": health_flag,
            "escalation_tier": tier,
            "actual_breach": actual_breach,
            "actual_severity": actual_severity,
        })

df_holdout = pd.DataFrame(holdout_records)
n_red_holdout = (df_holdout["health_flag_pred"] == "red").sum()
n_breach_holdout = df_holdout["actual_breach"].sum()
print(f"Records evaluated: {len(df_holdout):,}")
print(f"Predicted red flags: {n_red_holdout}")
print(f"Actual breaches (red within lead time): {n_breach_holdout}")
print(f"Yellow-flag records: {(df_holdout['health_flag_pred']=='yellow').sum()}")
print(f"Tier 2/3 escalations predicted: {(df_holdout['escalation_tier']>=2).sum()}")
print("\n⚠️  LIMITATION: 0 actual red-flag breaches in the 21-day holdout.")
print("   This is a data artifact — the synthetic dataset has only 5 red-flag")
print("   events in the entire 181-day history, none falling within this window.")
print("   Standard F1 is undefined for this window.")
print("\n→ Falling back to full historical backtest for F1 computation.")


# ─────────────────────────────────────────────────────────────────────────────
# PART 2: Full historical backtest (all 181 days)
# ─────────────────────────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("PART 2: Full historical backtest (2026-02-13 to 2026-08-11, 181 days)")
print("="*70)

all_records = []
for (dc_id, sku_id), grp in dd_full.groupby(["dc_id", "sku_id"]):
    lt_reg = get_lead_time(dc_id, sku_id)
    criticality = sm.loc[sku_id, "criticality"] if sku_id in sm.index else "Medium"
    grp = grp.sort_values("date")
    # Need at least 14 days of history before each evaluation day
    eval_rows = grp.iloc[14:]   # skip first 14 rows (warm-up for features)
    for _, row in eval_rows.iterrows():
        day_d = row["date"]
        health_flag = str(row["health_flag"])
        usable = float(row["usable_inventory"])
        safety_stock = float(row["safety_stock"])
        inbound = float(row["inbound_inventory"])
        demand_14d = float(row.get("demand_14d_avg", 1) or 1)
        days_till_so = min(usable / demand_14d, 9999) if demand_14d > 0 else 9999
        tier = classify_escalation_tier(
            criticality=criticality,
            health_flag=health_flag,
            days_till_stockout=days_till_so,
            lead_time_days=lt_reg,
            near_expiry_qty=0,
            avg_daily_demand=demand_14d,
            safety_stock=safety_stock,
            usable_inventory=usable,
            inbound_inventory=inbound,
        )
        future = grp[(grp["date"] > day_d) & (grp["date"] <= day_d + pd.Timedelta(days=lt_reg))]
        if future.empty:
            continue
        actual_breach = int((future["health_flag"] == "red").any())
        actual_severity = 2 if (future["health_flag"] == "red").any() else (1 if (future["health_flag"] == "yellow").any() else 0)
        all_records.append({
            "dc_id": dc_id, "sku_id": sku_id, "date": day_d,
            "criticality": criticality,
            "health_flag_pred": health_flag,
            "escalation_tier": tier,
            "actual_breach": actual_breach,
            "actual_severity": actual_severity,
        })

df_all = pd.DataFrame(all_records)
print(f"Total records: {len(df_all):,}")
print(f"Actual breaches (red within lead time): {df_all['actual_breach'].sum()}")
print(f"Predicted red flags: {(df_all['health_flag_pred']=='red').sum()}")
print(f"Predicted yellow flags: {(df_all['health_flag_pred']=='yellow').sum()}")

# ── (a) Red flag → breach ─────────────────────────────────────────────────────
print(f"\n{'─'*60}")
print("(a) RED flag → actual breach within lead-time window")
print("─"*60)

y_pred_red    = (df_all["health_flag_pred"] == "red").astype(int).values
y_true_breach = df_all["actual_breach"].values

prec_red  = precision_score(y_true_breach, y_pred_red, zero_division=0)
rec_red   = recall_score(y_true_breach, y_pred_red, zero_division=0)
f1_red    = f1_score(y_true_breach, y_pred_red, zero_division=0)
cm_red    = confusion_matrix(y_true_breach, y_pred_red, labels=[0, 1])

print(f"Precision : {prec_red:.3f}")
print(f"Recall    : {rec_red:.3f}")
print(f"F1        : {f1_red:.3f}")
print(f"Confusion matrix:")
print(f"            Pred-Green/Yellow  Pred-Red")
print(f"True-OK         {cm_red[0,0]:>9d}   {cm_red[0,1]:>8d}")
print(f"True-Breach     {cm_red[1,0]:>9d}   {cm_red[1,1]:>8d}")

# ── Yellow-inclusive: treat yellow+red as "at-risk" prediction ───────────────
print(f"\n{'─'*60}")
print("(a2) AT-RISK flag (yellow OR red) → any breach within lead time")
print("─"*60)

y_pred_atrisk  = (df_all["health_flag_pred"].isin(["yellow","red"])).astype(int).values
# ground truth: any severity >= 1
y_true_any = (df_all["actual_severity"] >= 1).astype(int).values

prec_ar  = precision_score(y_true_any, y_pred_atrisk, zero_division=0)
rec_ar   = recall_score(y_true_any, y_pred_atrisk, zero_division=0)
f1_ar    = f1_score(y_true_any, y_pred_atrisk, zero_division=0)
cm_ar    = confusion_matrix(y_true_any, y_pred_atrisk, labels=[0, 1])

print(f"Precision : {prec_ar:.3f}")
print(f"Recall    : {rec_ar:.3f}")
print(f"F1        : {f1_ar:.3f}")
print(f"Confusion matrix:")
print(f"            Pred-Green  Pred-AtRisk")
print(f"True-OK      {cm_ar[0,0]:>9d}   {cm_ar[0,1]:>9d}")
print(f"True-AtRisk  {cm_ar[1,0]:>9d}   {cm_ar[1,1]:>9d}")

# ── (b) Tier 2/3 → actual severe breach ──────────────────────────────────────
print(f"\n{'─'*60}")
print("(b) Tier 2/3 escalation → actual severity ≥ 2 (red breach)")
print("─"*60)

y_pred_esc     = (df_all["escalation_tier"] >= 2).astype(int).values
y_true_severe  = (df_all["actual_severity"] >= 2).astype(int).values

prec_esc  = precision_score(y_true_severe, y_pred_esc, zero_division=0)
rec_esc   = recall_score(y_true_severe, y_pred_esc, zero_division=0)
f1_esc    = f1_score(y_true_severe, y_pred_esc, zero_division=0)
cm_esc    = confusion_matrix(y_true_severe, y_pred_esc, labels=[0, 1])

print(f"Precision : {prec_esc:.3f}")
print(f"Recall    : {rec_esc:.3f}")
print(f"F1        : {f1_esc:.3f}")
print(f"Confusion matrix:")
print(f"             Pred-Low  Pred-Escalate")
print(f"True-OK       {cm_esc[0,0]:>9d}   {cm_esc[0,1]:>9d}")
print(f"True-Severe   {cm_esc[1,0]:>9d}   {cm_esc[1,1]:>9d}")

# ── By criticality ────────────────────────────────────────────────────────────
print(f"\n{'─'*60}")
print("(c) Red-flag precision/recall by SKU criticality (full backtest)")
print("─"*60)
for crit in ["High", "Medium", "Low"]:
    sub = df_all[df_all["criticality"] == crit]
    if len(sub) == 0:
        continue
    yp = (sub["health_flag_pred"] == "red").astype(int).values
    yt = sub["actual_breach"].values
    p  = precision_score(yt, yp, zero_division=0)
    r  = recall_score(yt, yp, zero_division=0)
    f  = f1_score(yt, yp, zero_division=0)
    n_pos = yt.sum()
    print(f"  {crit:6s}: n={len(sub):6d}, breaches={n_pos:4d}  Prec={p:.3f}  Rec={r:.3f}  F1={f:.3f}")

# ── Tier distribution ─────────────────────────────────────────────────────────
print(f"\n{'─'*60}")
print("(d) Escalation tier distribution (full backtest)")
print("─"*60)
for tier in [0, 1, 2, 3]:
    n = (df_all["escalation_tier"] == tier).sum()
    pct = n / len(df_all) * 100
    print(f"  Tier {tier}: {n:7,} ({pct:.1f}%)")

print(f"\n{'='*70}")
print("FINAL SUMMARY FOR DOCUMENTATION")
print("="*70)
print(f"""
21-day holdout evaluation:
  Records: {len(df_holdout):,}
  Actual red-flag breaches: {n_breach_holdout} → F1 undefined (insufficient positives)

Full historical backtest (181-day, n={len(df_all):,} SKU×DC×day records):
  [a] Red health flag → breach within lead-time window
      Precision: {prec_red:.3f}  Recall: {rec_red:.3f}  F1: {f1_red:.3f}
      CM: TN={cm_red[0,0]:,}  FP={cm_red[0,1]:,}  FN={cm_red[1,0]:,}  TP={cm_red[1,1]:,}

  [a2] At-risk (yellow/red) → any severity breach within window  
      Precision: {prec_ar:.3f}  Recall: {rec_ar:.3f}  F1: {f1_ar:.3f}
      CM: TN={cm_ar[0,0]:,}  FP={cm_ar[0,1]:,}  FN={cm_ar[1,0]:,}  TP={cm_ar[1,1]:,}

  [b] Tier 2/3 escalation → actual severe breach (red)
      Precision: {prec_esc:.3f}  Recall: {rec_esc:.3f}  F1: {f1_esc:.3f}
      CM: TN={cm_esc[0,0]:,}  FP={cm_esc[0,1]:,}  FN={cm_esc[1,0]:,}  TP={cm_esc[1,1]:,}
""")
