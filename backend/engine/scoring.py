"""
scoring.py — Multi-objective scoring formula across stockout risk,
expiry/wastage risk, cost, lead time, service level, and criticality.
"""
import numpy as np


# Criticality-specific weights
WEIGHTS = {
    "High":   {"stockout": 0.35, "expiry": 0.20, "cost": 0.15, "lead_time": 0.20, "service": 0.10},
    "Medium": {"stockout": 0.25, "expiry": 0.20, "cost": 0.25, "lead_time": 0.15, "service": 0.15},
    "Low":    {"stockout": 0.15, "expiry": 0.15, "cost": 0.40, "lead_time": 0.15, "service": 0.15},
}


def score_options(options: list, criticality: str, days_till_stockout: float,
                  near_expiry_qty: int, avg_daily_demand: float) -> list:
    """
    Score each replenishment option using the multi-objective formula:

    Score = w1*stockout_risk_score
          + w2*expiry_risk_score
          - w3*normalized_cost
          - w4*normalized_lead_time
          + w5*service_level_score

    Higher score = better option.
    """
    w = WEIGHTS.get(criticality, WEIGHTS["Medium"])

    # Normalise costs and lead times across options
    costs = [o["total_cost"] for o in options if o.get("total_cost", 0) > 0]
    leads = [o["lead_time_days"] for o in options if o.get("lead_time_days", 0) > 0]

    max_cost = max(costs) if costs else 1
    max_lead = max(leads) if leads else 1

    scored = []
    for opt in options:
        # 1. Stockout risk score: how urgently does this option prevent stockout?
        lt = opt.get("lead_time_days", 0)
        if lt == 0:
            # No action: only safe if days_till_stockout is high
            stockout_score = min(1.0, days_till_stockout / 14)
        else:
            # Faster options get higher score when stockout is near
            urgency = max(0, 1 - days_till_stockout / 14)
            speed = 1 - (lt / (max_lead + 1))
            stockout_score = urgency * speed + (1 - urgency) * 0.5

        # 2. Expiry risk score: does this option prevent expiry wastage?
        expiry_savings = opt.get("expiry_savings", 0)
        expiry_score = min(1.0, expiry_savings / max(near_expiry_qty * 10, 1))

        # 3. Cost score (inverted — lower cost = higher score)
        total_cost = opt.get("total_cost", 0)
        cost_score = 1 - (total_cost / (max_cost + 1)) if max_cost > 0 else 1.0

        # 4. Lead time score (inverted)
        lead_score = 1 - (lt / (max_lead + 1)) if max_lead > 0 else 1.0

        # 5. Service level / criticality fit
        if criticality == "High" and lt <= 3:
            service_score = 1.0
        elif criticality == "High" and lt <= 7:
            service_score = 0.6
        elif criticality in ("Medium", "Low") and opt["option"] == "regular_supplier":
            service_score = 0.8
        elif opt["option"] == "no_action" and days_till_stockout > 21:
            service_score = 1.0
        else:
            service_score = 0.4

        # Penalty: if not feasible, reduce score sharply
        feasibility_penalty = 0 if opt.get("feasible", True) else 0.4

        total_score = (
            w["stockout"] * stockout_score
            + w["expiry"] * expiry_score
            + w["cost"] * cost_score
            + w["lead_time"] * lead_score
            + w["service"] * service_score
            - feasibility_penalty
        )

        scored.append({
            **opt,
            "scores": {
                "stockout_risk": round(stockout_score, 3),
                "expiry_risk": round(expiry_score, 3),
                "cost": round(cost_score, 3),
                "lead_time": round(lead_score, 3),
                "service_level": round(service_score, 3),
            },
            "total_score": round(total_score, 4),
        })

    # Sort: infeasible to bottom, then by total_score desc
    scored.sort(key=lambda x: (0 if x.get("feasible", True) else -1, x["total_score"]), reverse=True)
    return scored


def build_reason_string(winner: dict, criticality: str, days_till_stockout: float,
                        near_expiry_qty: int, avg_daily: float) -> str:
    """Generate plain-English reason for the recommendation."""
    opt = winner["option"]
    qty = winner.get("qty", 0)
    lt = winner.get("lead_time_days", 0)
    cost = winner.get("total_cost", 0)
    scores = winner.get("scores", {})

    days_str = f"{round(days_till_stockout, 1)}d" if days_till_stockout < 999 else ">30d"

    if opt == "no_action":
        return (
            f"No action needed: usable inventory covers ~{days_str} of demand "
            f"(safety stock not at risk). Stockout risk is low for {criticality.lower()}-criticality SKU."
        )

    base = f"Order {qty} units via {winner['label']} (lead time: {lt}d, cost: INR {cost:,}). "

    if opt == "local_supplier":
        premium = winner.get("local_premium_pct", 50)
        base += (
            f"Chosen despite {premium}% local premium because stockout in {days_str} "
            f"leaves insufficient time for regular supplier ({lt}d < {round(days_till_stockout)}d). "
        )
    elif opt == "regular_supplier":
        base += (
            f"Regular supplier chosen as most cost-efficient option (stockout in {days_str} > lead time {lt}d). "
        )
    elif opt == "dc_transfer":
        src = winner.get("source_dc", "other DC")
        savings = winner.get("expiry_savings", 0)
        base += (
            f"Transfer from {src} is fastest available option (lead time {lt}d < stockout in {days_str}). "
        )
        if savings > 0:
            base += f"Also prevents INR {savings:,} expiry write-off at source. "

    if criticality == "High":
        base += f"High-criticality SKU: service level and speed weighted above cost."
    elif criticality == "Low":
        base += f"Low-criticality SKU: cost efficiency weighted highest."

    return base
