"""
decision_engine.py — Core replenishment decision logic.
Evaluates Transfer / Regular Supplier / Local Supplier / No Action
for each SKU x DC using real data: costs, lead times, expiry, criticality.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional

ANALYSIS_DATE = pd.Timestamp("2026-08-13")
HORIZON_DAYS = 14


# ── FEFO & Expiry Feasibility ─────────────────────────────────────────────

def fefo_transfer_feasibility(
    batches: pd.DataFrame,
    source_dc: str,
    dest_dc: str,
    sku_id: str,
    dest_daily_demand: float,
    transfer_lead_time: int,
) -> dict:
    """
    Check whether batches at source_dc can be transferred to dest_dc
    before they expire. Returns transferable_qty and feasibility details.

    FEFO rule: consume earliest-expiring batches first.
    Transfer is safe only if dest_dc can consume the batch before it expires.
    """
    source_batches = batches[
        (batches["dc_id"] == source_dc) &
        (batches["sku_id"] == sku_id) &
        (batches["quantity"] > 0)
    ].copy()
    source_batches["days_to_expiry"] = (
        source_batches["expiry_date"] - ANALYSIS_DATE
    ).dt.days
    source_batches = source_batches[source_batches["days_to_expiry"] > 0]
    source_batches = source_batches.sort_values("expiry_date")  # FEFO order

    feasible_qty = 0
    expiry_risk_qty = 0
    batch_details = []

    for _, batch in source_batches.iterrows():
        days_remaining_after_transfer = batch["days_to_expiry"] - transfer_lead_time
        if days_remaining_after_transfer <= 0:
            # Would arrive already expired
            batch_details.append({
                "batch_id": batch["batch_id"],
                "qty": int(batch["quantity"]),
                "days_to_expiry": int(batch["days_to_expiry"]),
                "feasible": False,
                "reason": "arrives_expired",
            })
            continue

        consumable_at_dest = dest_daily_demand * days_remaining_after_transfer
        if consumable_at_dest >= batch["quantity"]:
            feasible_qty += batch["quantity"]
            batch_details.append({
                "batch_id": batch["batch_id"],
                "qty": int(batch["quantity"]),
                "days_to_expiry": int(batch["days_to_expiry"]),
                "consumable_at_dest": round(consumable_at_dest),
                "feasible": True,
                "reason": "dest_can_consume_before_expiry",
            })
        else:
            # Partial: dest can consume some before expiry
            safe_qty = min(int(consumable_at_dest), int(batch["quantity"]))
            waste_qty = int(batch["quantity"]) - safe_qty
            if safe_qty > 0:
                feasible_qty += safe_qty
            expiry_risk_qty += waste_qty
            batch_details.append({
                "batch_id": batch["batch_id"],
                "qty": int(batch["quantity"]),
                "days_to_expiry": int(batch["days_to_expiry"]),
                "consumable_at_dest": round(consumable_at_dest),
                "safe_transfer_qty": safe_qty,
                "waste_qty": waste_qty,
                "feasible": safe_qty > 0,
                "reason": "partial_consumption_risk",
            })

    return {
        "source_dc": source_dc,
        "dest_dc": dest_dc,
        "sku_id": sku_id,
        "total_source_qty": int(source_batches["quantity"].sum()),
        "feasible_transfer_qty": int(feasible_qty),
        "expiry_risk_qty": int(expiry_risk_qty),
        "batch_details": batch_details,
    }


# ── Best Transfer Source ──────────────────────────────────────────────────

def find_best_transfer_source(
    snapshot: pd.DataFrame,
    batches: pd.DataFrame,
    lead_times: pd.DataFrame,
    dc_id: str,
    sku_id: str,
    required_qty: int,
    dest_daily_demand: float,
    unit_cost: float,
    transfer_cost_per_unit: float,
) -> Optional[dict]:
    """
    Among all other DCs, find the best source for a transfer.
    Returns the best option dict or None if no viable source.
    """
    other_dcs = snapshot[
        (snapshot["dc_id"] != dc_id) &
        (snapshot["sku_id"] == sku_id)
    ].copy()

    candidates = []
    for _, row in other_dcs.iterrows():
        src_dc = row["dc_id"]
        src_usable = row["usable_inventory"]
        if src_usable < 50:
            continue  # Too little to transfer

        lt_row = lead_times[
            (lead_times["dc_id"] == dc_id) &
            (lead_times["sku_id"] == sku_id) &
            (lead_times["supplier_type"] == "transfer")
        ]
        if lt_row.empty:
            continue
        lt = int(lt_row["lead_time_days"].iloc[0])

        # FEFO feasibility check
        fefo = fefo_transfer_feasibility(
            batches, src_dc, dc_id, sku_id, dest_daily_demand, lt
        )
        avail_qty = min(fefo["feasible_transfer_qty"], int(src_usable * 0.5))
        if avail_qty < 1:
            continue

        transfer_qty = min(avail_qty, required_qty)
        cost = transfer_qty * (unit_cost + transfer_cost_per_unit)
        expiry_savings = fefo["expiry_risk_qty"] * unit_cost  # wastage prevented

        candidates.append({
            "source_dc": src_dc,
            "transfer_qty": transfer_qty,
            "lead_time": lt,
            "total_cost": round(cost),
            "expiry_risk_qty": fefo["expiry_risk_qty"],
            "expiry_savings": round(expiry_savings),
            "fefo_detail": fefo,
        })

    if not candidates:
        return None

    # Pick source with most available feasible qty first, then lowest cost
    candidates.sort(key=lambda x: (-x["transfer_qty"], x["total_cost"]))
    return candidates[0]


# ── Option Evaluation ────────────────────────────────────────────────────────

def evaluate_all_options(
    dc_id: str,
    sku_id: str,
    snapshot: pd.DataFrame,
    batches: pd.DataFrame,
    lead_times: pd.DataFrame,
    forecast: dict,
    sku_info: dict,
    dc_info: dict,
) -> list:
    """
    Evaluate 4 replenishment options and return structured comparison.
    """
    snap_row = snapshot[
        (snapshot["dc_id"] == dc_id) & (snapshot["sku_id"] == sku_id)
    ]
    if snap_row.empty:
        return []
    snap = snap_row.iloc[0]

    usable = float(snap["usable_inventory"])
    safety_stock = float(snap["safety_stock"])
    reorder_point = float(snap["reorder_point"])
    inbound = float(snap["inbound_inventory"])

    demand_lt_regular = forecast.get("demand_during_lead_time_regular", 0)
    demand_lt_local = forecast.get("demand_during_lead_time_local", 0)
    demand_lt_transfer = forecast.get("demand_during_lead_time_transfer", 0)

    unit_cost = sku_info.get("unit_cost", 10)
    cost_regular = sku_info.get("purchase_cost_regular", unit_cost)
    cost_local = sku_info.get("purchase_cost_local", unit_cost * 1.5)
    stockout_penalty = sku_info.get("stockout_penalty_per_unit", 200)
    holding_cost_daily = unit_cost * sku_info.get("holding_cost_pct", 0.20) / 365
    transfer_cost_pu = dc_info.get("transfer_cost_per_unit", 3.0)
    criticality = sku_info.get("criticality", "Medium")
    daily_demand = forecast.get("forecast_next_14d", [max(usable / 14, 1)])
    avg_daily = float(np.mean(daily_demand)) if daily_demand else max(usable / 14, 1)
    days_till_stockout = (usable / avg_daily) if avg_daily > 0 else 999

    # Replenishment requirement
    req_qty_regular = max(0, demand_lt_regular + safety_stock - usable - inbound)
    req_qty_local = max(0, demand_lt_local + safety_stock - usable - inbound)
    req_qty_transfer = max(0, demand_lt_transfer + safety_stock - usable - inbound)
    req_qty_regular = max(req_qty_regular, 50)  # minimum meaningful order
    req_qty_local = max(req_qty_local, 50)
    req_qty_transfer = max(req_qty_transfer, 50)

    options = []

    # ── 1. No Action ────────────────────────────────────────────────────
    stockout_risk_days = max(0, demand_lt_regular - usable)
    options.append({
        "option": "no_action",
        "label": "No Action",
        "qty": 0,
        "lead_time_days": 0,
        "unit_cost": 0,
        "total_cost": 0,
        "expiry_risk": 0,
        "stockout_risk_qty": round(stockout_risk_days * avg_daily) if days_till_stockout < 7 else 0,
        "feasible": days_till_stockout > 14,
        "reject_reason": "stockout_imminent" if days_till_stockout <= 14 else None,
    })

    # ── 2. Regular Supplier ────────────────────────────────────────────
    lt_reg_rows = lead_times[
        (lead_times["dc_id"] == dc_id) &
        (lead_times["sku_id"] == sku_id) &
        (lead_times["supplier_type"] == "regular")
    ]
    if not lt_reg_rows.empty:
        lt_reg = int(lt_reg_rows["lead_time_days"].iloc[0])
        can_beat_stockout = days_till_stockout > lt_reg
        qty = int(req_qty_regular)
        total_cost_reg = qty * cost_regular + qty * holding_cost_daily * lt_reg
        if not can_beat_stockout and days_till_stockout < lt_reg:
            penalty = (lt_reg - days_till_stockout) * avg_daily * stockout_penalty
            total_cost_reg += penalty
        options.append({
            "option": "regular_supplier",
            "label": "Regular Supplier",
            "qty": qty,
            "lead_time_days": lt_reg,
            "unit_cost": cost_regular,
            "total_cost": round(total_cost_reg),
            "expiry_risk": 0,
            "stockout_risk_qty": 0 if can_beat_stockout else round(
                (lt_reg - days_till_stockout) * avg_daily
            ),
            "feasible": can_beat_stockout or criticality == "Low",
            "reject_reason": None if can_beat_stockout else
                f"lead_time({lt_reg}d) > stockout_in({round(days_till_stockout)}d)",
        })

    # ── 3. Local Supplier ────────────────────────────────────────────
    lt_loc_rows = lead_times[
        (lead_times["dc_id"] == dc_id) &
        (lead_times["sku_id"] == sku_id) &
        (lead_times["supplier_type"] == "local")
    ]
    if not lt_loc_rows.empty:
        lt_loc = int(lt_loc_rows["lead_time_days"].iloc[0])
        can_beat_stockout_loc = days_till_stockout > lt_loc
        qty_loc = int(req_qty_local)
        total_cost_loc = qty_loc * cost_local + qty_loc * holding_cost_daily * lt_loc
        options.append({
            "option": "local_supplier",
            "label": "Local Supplier",
            "qty": qty_loc,
            "lead_time_days": lt_loc,
            "unit_cost": cost_local,
            "total_cost": round(total_cost_loc),
            "expiry_risk": 0,
            "stockout_risk_qty": 0,
            "feasible": True,
            "reject_reason": None,
            "local_premium_pct": round((cost_local / cost_regular - 1) * 100, 1),
        })

    # ── 4. DC Transfer ────────────────────────────────────────────────
    best_transfer = find_best_transfer_source(
        snapshot, batches, lead_times,
        dc_id, sku_id, int(req_qty_transfer),
        avg_daily, unit_cost, transfer_cost_pu,
    )
    if best_transfer:
        lt_tr = best_transfer["lead_time"]
        can_beat_tr = days_till_stockout > lt_tr
        qty_tr = best_transfer["transfer_qty"]
        total_cost_tr = qty_tr * (unit_cost + transfer_cost_pu)
        options.append({
            "option": "dc_transfer",
            "label": f"Transfer from {best_transfer['source_dc']}",
            "source_dc": best_transfer["source_dc"],
            "qty": qty_tr,
            "lead_time_days": lt_tr,
            "unit_cost": unit_cost + transfer_cost_pu,
            "total_cost": round(total_cost_tr),
            "expiry_risk": best_transfer["expiry_risk_qty"],
            "expiry_savings": best_transfer["expiry_savings"],
            "stockout_risk_qty": 0 if can_beat_tr else round(
                (lt_tr - days_till_stockout) * avg_daily
            ),
            "feasible": can_beat_tr,
            "reject_reason": None if can_beat_tr else
                f"transfer_lead_time({lt_tr}d) > stockout_in({round(days_till_stockout)}d)",
            "fefo_detail": best_transfer.get("fefo_detail", {}),
        })

    return options
