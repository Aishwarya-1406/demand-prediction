"""
frequency.py — Replenishment frequency & EOQ optimisation.

Computes the optimal reorder frequency (review period) for each DC×SKU
using a modified Economic Order Quantity (EOQ) model that accounts for:
  - Demand variability (safety stock buffer)
  - Holding cost vs ordering cost trade-off
  - Lead time constraints
  - Criticality-driven service level targets

Outputs: review_period_days, eoq, reorder_cycles_per_year,
         recommended_order_frequency_label, frequency_risk_flag
"""
from __future__ import annotations
import numpy as np
from typing import Optional


# Ordering cost assumptions (INR per order placement)
ORDERING_COST = {
    "regular": 2500,
    "local": 1500,
    "transfer": 800,
}

# Service level Z-scores by criticality
SERVICE_LEVEL_Z = {
    "High":   2.05,  # 98% service level
    "Medium": 1.65,  # 95% service level
    "Low":    1.28,  # 90% service level
}

# Distributor fill-rate thresholds
FILL_RATE_GOOD = 0.95
FILL_RATE_WARN  = 0.85


def compute_eoq(
    avg_daily_demand: float,
    unit_cost: float,
    holding_cost_pct: float,
    ordering_cost: float,
) -> int:
    """
    Classic EOQ formula:
        EOQ = sqrt(2 * D * S / H)
    where:
        D = annual demand
        S = ordering cost per order
        H = holding cost per unit per year
    """
    annual_demand = avg_daily_demand * 365
    holding_cost_annual = unit_cost * holding_cost_pct
    if holding_cost_annual <= 0 or ordering_cost <= 0:
        return int(avg_daily_demand * 14)  # fallback: 14-day supply
    eoq = np.sqrt(2 * annual_demand * ordering_cost / holding_cost_annual)
    return max(int(round(eoq)), 50)  # minimum 50 units


def compute_safety_stock(
    avg_daily_demand: float,
    demand_std: float,
    lead_time_days: float,
    criticality: str,
) -> int:
    """
    Safety stock = Z * sqrt(lead_time) * demand_std
    Accounts for demand variability during lead time.
    """
    z = SERVICE_LEVEL_Z.get(criticality, 1.65)
    ss = z * np.sqrt(lead_time_days) * demand_std
    return max(int(round(ss)), 0)


def compute_review_period(
    eoq: int,
    avg_daily_demand: float,
) -> int:
    """
    Review period T* = EOQ / daily_demand  (in days)
    This is how many days between replenishment orders.
    """
    if avg_daily_demand <= 0:
        return 30
    t = eoq / avg_daily_demand
    return max(int(round(t)), 1)


def frequency_label(review_period_days: int) -> str:
    """Human-readable frequency label."""
    if review_period_days <= 3:
        return "Daily"
    elif review_period_days <= 7:
        return "Weekly"
    elif review_period_days <= 14:
        return "Bi-Weekly"
    elif review_period_days <= 30:
        return "Monthly"
    elif review_period_days <= 60:
        return "Bi-Monthly"
    else:
        return "Quarterly"


def frequency_risk_flag(
    review_period_days: int,
    days_till_stockout: float,
    lead_time_days: float,
    criticality: str,
) -> str:
    """
    Flag mismatches between review cadence and stockout urgency.
    Returns: 'ok', 'warning', or 'critical'
    """
    # If review period > days-till-stockout → critical
    if days_till_stockout < lead_time_days:
        return "critical"
    if review_period_days > days_till_stockout * 0.7:
        if criticality == "High":
            return "critical"
        return "warning"
    if review_period_days > 21 and criticality == "High":
        return "warning"
    return "ok"


def analyse_distributor_performance(
    distributor_df,
    dc_id: str,
    sku_id: str,
) -> dict:
    """
    Compute distributor reliability metrics for a DC×SKU pair.
    Returns fill_rate, on_time_rate, avg_order_cycle_days.
    """
    if distributor_df is None or distributor_df.empty:
        return {
            "fill_rate": None,
            "on_time_rate": None,
            "avg_order_cycle_days": None,
            "n_orders": 0,
        }

    sub = distributor_df[
        (distributor_df["dc_id"] == dc_id) &
        (distributor_df["sku_id"] == sku_id)
    ]
    if sub.empty:
        return {
            "fill_rate": None,
            "on_time_rate": None,
            "avg_order_cycle_days": None,
            "n_orders": 0,
        }

    return {
        "fill_rate": round(float(sub["fill_rate"].mean()), 3),
        "on_time_rate": round(float(sub["on_time"].mean()), 3),
        "avg_order_cycle_days": round(float(sub["order_frequency_days"].mean()), 1),
        "n_orders": int(len(sub)),
        "distributor_id": sub["distributor_id"].mode().iloc[0] if not sub.empty else None,
    }


def compute_frequency_plan(
    dc_id: str,
    sku_id: str,
    avg_daily_demand: float,
    demand_std: float,
    unit_cost: float,
    holding_cost_pct: float,
    lead_time_regular: float,
    lead_time_local: float,
    criticality: str,
    days_till_stockout: float,
    distributor_df=None,
) -> dict:
    """
    Full frequency planning for one DC×SKU.
    Returns a dict with EOQ, review period, safety stock, risk flag,
    distributor performance, and a plain-English recommendation.
    """
    ordering_cost = ORDERING_COST["regular"]
    eoq = compute_eoq(avg_daily_demand, unit_cost, holding_cost_pct, ordering_cost)
    review_period = compute_review_period(eoq, avg_daily_demand)
    safety_stock = compute_safety_stock(avg_daily_demand, demand_std, lead_time_regular, criticality)
    cycles_per_year = round(365 / review_period, 1) if review_period > 0 else 0
    risk = frequency_risk_flag(review_period, days_till_stockout, lead_time_regular, criticality)
    label = frequency_label(review_period)

    dist_perf = analyse_distributor_performance(distributor_df, dc_id, sku_id)

    # Fill rate penalty: if distributor is unreliable, shorten review period
    fill_rate = dist_perf.get("fill_rate") or 1.0
    adjusted_review = review_period
    fill_rate_note = ""
    if fill_rate < FILL_RATE_WARN:
        adjusted_review = max(int(review_period * 0.7), 3)
        fill_rate_note = f"Review period shortened from {review_period}d to {adjusted_review}d due to low distributor fill rate ({fill_rate:.0%})."
    elif fill_rate < FILL_RATE_GOOD:
        adjusted_review = max(int(review_period * 0.85), 3)
        fill_rate_note = f"Review period slightly shortened ({review_period}d→{adjusted_review}d) due to borderline fill rate ({fill_rate:.0%})."

    # Plain-English recommendation
    rec_parts = [
        f"Order every {adjusted_review} days ({frequency_label(adjusted_review)}).",
        f"Optimal order quantity: {eoq} units (EOQ).",
        f"Safety stock buffer: {safety_stock} units at {SERVICE_LEVEL_Z.get(criticality, 1.65):.2f}σ service level.",
        f"Estimated {cycles_per_year} replenishment cycles per year.",
    ]
    if fill_rate_note:
        rec_parts.append(fill_rate_note)
    if risk == "critical":
        rec_parts.append("⚠️ URGENT: Review cadence is misaligned with stockout timeline — expedite next order.")
    elif risk == "warning":
        rec_parts.append("Review cadence may be too infrequent given current stock position.")

    return {
        "dc_id": dc_id,
        "sku_id": sku_id,
        "eoq": eoq,
        "safety_stock_computed": safety_stock,
        "review_period_days": adjusted_review,
        "review_period_days_raw": review_period,
        "reorder_cycles_per_year": cycles_per_year,
        "recommended_order_frequency": frequency_label(adjusted_review),
        "frequency_risk_flag": risk,
        "distributor_performance": dist_perf,
        "recommendation": " ".join(rec_parts),
        "ordering_cost_assumption": ordering_cost,
        "holding_cost_annual_pct": holding_cost_pct,
        "next_review_date": None,  # set by precompute with analysis date
    }
