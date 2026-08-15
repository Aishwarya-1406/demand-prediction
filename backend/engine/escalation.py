"""
escalation.py — Review cadence & escalation process for shortage situations.

Implements a structured 4-tier escalation framework:
  Tier 0 (Monitor)   — Normal: automated daily review
  Tier 1 (Alert)     — Reorder triggered: planner notified within 24h
  Tier 2 (Escalate)  — High-criticality stockout < 7 days: manager review
  Tier 3 (Emergency) — Critical stockout < 3 days: supply-chain head + emergency sourcing

For each DC×SKU generates:
  - escalation_tier (0–3)
  - escalation_label
  - escalation_action (recommended immediate action)
  - review_cadence_hours (how often to check this item)
  - escalation_owner (who should act)
  - estimated_resolution_date
  - shortage_notes
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Optional

ANALYSIS_DATE = pd.Timestamp("2026-08-13")


# ── Tier definitions ────────────────────────────────────────────────────────

TIERS = {
    0: {
        "label": "Monitor",
        "color": "green",
        "review_cadence_hours": 24,
        "owner": "Automated System",
        "description": "Inventory healthy. Daily automated review.",
    },
    1: {
        "label": "Reorder Alert",
        "color": "yellow",
        "review_cadence_hours": 12,
        "owner": "DC Planner",
        "description": "Stock below reorder point. Planner to confirm and place order within 24h.",
    },
    2: {
        "label": "Escalate to Manager",
        "color": "orange",
        "review_cadence_hours": 6,
        "owner": "Supply Chain Manager",
        "description": "High-criticality SKU at risk. Manager review required. Evaluate emergency sourcing.",
    },
    3: {
        "label": "Emergency",
        "color": "red",
        "review_cadence_hours": 2,
        "owner": "Supply Chain Head",
        "description": "Critical stockout imminent. Emergency sourcing + escalation to leadership required.",
    },
}


def classify_escalation_tier(
    criticality: str,
    health_flag: str,
    days_till_stockout: float,
    lead_time_days: float,
    near_expiry_qty: int = 0,
    avg_daily_demand: float = 1.0,
    safety_stock: float = 0.0,
    usable_inventory: float = 0.0,
    inbound_inventory: float = 0.0,
    days_to_safety_stock: Optional[float] = None,
) -> int:
    """
    Assign escalation tier based on criticality, stock health, and urgency.

    Tier 3 (Emergency): Critical stockout imminent within 1-2 days or zero stock on critical SKU
    Tier 2 (Escalate to Manager): Imminent safety stock breach within lead time with no inbound
    Tier 1 (Reorder Alert): Inventory below reorder point (routine replenishment needed)
    Tier 0 (Monitor): Inventory healthy
    """
    if days_to_safety_stock is None:
        if safety_stock > 0 and avg_daily_demand > 0 and usable_inventory > 0:
            days_to_safety_stock = (usable_inventory - safety_stock) / avg_daily_demand
        elif days_till_stockout is not None:
            days_to_safety_stock = days_till_stockout
        else:
            days_to_safety_stock = 9999.0

    # Tier 3: Emergency
    # Imminent zero stockout within 1 day, or already red on High/Medium,
    # or High-criticality item with safety stock runway <= 1.0 day and no pending inbound.
    if days_till_stockout <= 1.0:
        return 3
    if health_flag == "red" and criticality in ("High", "Medium"):
        return 3
    if days_to_safety_stock <= 1.0 and criticality == "High" and inbound_inventory == 0:
        return 3

    # Tier 2: Escalate to Manager
    # Already red on Low criticality, or High-criticality item with safety stock runway <= 2.5 days (no inbound),
    # or Medium-criticality item with safety stock runway <= 1.5 days (no inbound),
    # or total runway <= 3.0 days on High criticality with no inbound.
    if health_flag == "red":
        return 2
    if days_to_safety_stock <= 2.5 and criticality == "High" and inbound_inventory == 0:
        return 2
    if days_to_safety_stock <= 1.5 and criticality == "Medium" and inbound_inventory == 0:
        return 2
    if days_till_stockout <= 3.0 and criticality == "High" and inbound_inventory == 0:
        return 2

    # Tier 1: Reorder Alert
    # Stock at or below reorder point (routine replenishment triggered)
    if health_flag in ("red", "yellow"):
        return 1
    if near_expiry_qty > avg_daily_demand * 30:
        return 1  # Large expiry risk triggers planner review

    # Tier 0: Monitor
    return 0


def build_escalation_action(
    tier: int,
    criticality: str,
    days_till_stockout: float,
    lead_time_local: float,
    best_action: str,
    near_expiry_qty: int,
    avg_daily_demand: float,
) -> str:
    """
    Generate a specific, actionable escalation recommendation.
    """
    if tier == 3:
        parts = []
        if lead_time_local <= days_till_stockout:
            parts.append(f"Activate emergency local supplier procurement immediately (lead time {int(lead_time_local)}d).")
        else:
            parts.append("Initiate DC-to-DC emergency transfer from nearest surplus DC.")
        parts.append("Notify Supply Chain Head and Regional Medical Director.")
        parts.append("Place safety buffer order to avoid recurrence.")
        if near_expiry_qty > 0:
            parts.append(f"Simultaneously expedite consumption of {near_expiry_qty} near-expiry units.")
        return " ".join(parts)

    elif tier == 2:
        return (
            f"Manager to review and approve '{best_action.replace('_', ' ')}' recommendation within 6h. "
            f"Confirm lead time feasibility (days till stockout: {round(days_till_stockout, 1)}d). "
            "Evaluate DC transfer as faster alternative if regular supplier cannot meet timeline."
        )

    elif tier == 1:
        action_text = best_action.replace('_', ' ').title()
        note = ""
        if near_expiry_qty > avg_daily_demand * 14:
            note = f" Also expedite use of {near_expiry_qty} near-expiry units to avoid write-off."
        return f"DC Planner to confirm and place '{action_text}' order within 24h.{note}"

    else:
        return "No action required. Continue automated daily monitoring."


def compute_estimated_resolution(
    days_till_stockout: float,
    lead_time_days: float,
    tier: int,
) -> Optional[str]:
    """
    Estimate when the shortage situation will be resolved (stock replenished).
    """
    if tier == 0:
        return None
    # Resolution = analysis date + lead time (earliest replenishment arrival)
    resolution_days = int(np.ceil(lead_time_days))
    resolution_date = ANALYSIS_DATE + pd.Timedelta(days=resolution_days)
    return str(resolution_date.date())


def build_shortage_notes(
    tier: int,
    criticality: str,
    days_till_stockout: float,
    trend: str,
    near_expiry_qty: int,
    avg_daily_demand: float,
    mape: Optional[float],
) -> list:
    """Build a list of contextual notes for the escalation record."""
    notes = []

    if trend == "rising" or trend == "surge":
        notes.append(f"⚠️ Demand trend is '{trend}' — actual stockout may occur sooner than projected.")

    if mape and mape > 30:
        notes.append(f"Forecast uncertainty is high (MAPE={mape:.1f}%). Add extra safety buffer.")

    if near_expiry_qty > 0 and near_expiry_qty > avg_daily_demand * 7:
        waste_value_flag = "high" if near_expiry_qty > avg_daily_demand * 21 else "moderate"
        notes.append(f"{waste_value_flag.capitalize()} expiry risk: {near_expiry_qty} units expire soon. Prioritise consumption or inter-DC transfer.")

    if criticality == "High" and tier >= 2:
        notes.append("Critical SKU: stockout will directly impact patient care. Zero-tolerance policy applies.")

    if days_till_stockout < 0:
        notes.append("Stockout has already occurred (usable inventory = 0). Expedite all options.")

    return notes


def run_escalation(
    dc_id: str,
    sku_id: str,
    criticality: str,
    health_flag: str,
    days_till_stockout: float,
    lead_time_regular: float,
    lead_time_local: float,
    near_expiry_qty: int,
    avg_daily_demand: float,
    best_action: str,
    trend: str,
    mape: Optional[float],
    safety_stock: float = 0.0,
    usable_inventory: float = 0.0,
    inbound_inventory: float = 0.0,
) -> dict:
    """
    Full escalation classification for one DC×SKU.
    """
    tier = classify_escalation_tier(
        criticality=criticality,
        health_flag=health_flag,
        days_till_stockout=days_till_stockout,
        lead_time_days=lead_time_regular,
        near_expiry_qty=near_expiry_qty,
        avg_daily_demand=avg_daily_demand,
        safety_stock=safety_stock,
        usable_inventory=usable_inventory,
        inbound_inventory=inbound_inventory,
    )
    tier_info = TIERS[tier]

    action = build_escalation_action(
        tier, criticality, days_till_stockout,
        lead_time_local, best_action, near_expiry_qty, avg_daily_demand
    )

    resolution = compute_estimated_resolution(days_till_stockout, lead_time_regular, tier)

    notes = build_shortage_notes(
        tier, criticality, days_till_stockout,
        trend, near_expiry_qty, avg_daily_demand, mape
    )

    # Next review datetime
    next_review_hours = tier_info["review_cadence_hours"]
    next_review = ANALYSIS_DATE + pd.Timedelta(hours=next_review_hours)

    return {
        "dc_id": dc_id,
        "sku_id": sku_id,
        "escalation_tier": tier,
        "escalation_label": tier_info["label"],
        "escalation_color": tier_info["color"],
        "escalation_description": tier_info["description"],
        "escalation_action": action,
        "escalation_owner": tier_info["owner"],
        "review_cadence_hours": next_review_hours,
        "next_review_datetime": str(next_review),
        "estimated_resolution_date": resolution,
        "shortage_notes": notes,
        "days_till_stockout": round(min(days_till_stockout, 9999), 1),
        "criticality": criticality,
        "health_flag": health_flag,
        "trend": trend,
    }
