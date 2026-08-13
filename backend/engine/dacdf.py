"""
dacdf.py — Dual-Agent Cognitive Decision Framework.

AI Agent:     scored recommendation from quantitative engine.
Human Agent:  rule-based override layer (configurable JSON).
Fusion:       Final = alpha * AI + (1-alpha) * Human
              where alpha is calibrated from recent forecast error.
"""
from __future__ import annotations
import json
import numpy as np
from pathlib import Path
from typing import Optional, Tuple, Dict, List, Any

RULES_PATH = Path(__file__).parent / "business_rules.json"


def load_rules() -> dict:
    if RULES_PATH.exists():
        with open(RULES_PATH) as f:
            return json.load(f)
    return {}


def save_rules(rules: dict):
    with open(RULES_PATH, "w") as f:
        json.dump(rules, f, indent=2)


# ── Alpha calibration ───────────────────────────────────────────────────────

def calibrate_alpha(
    recent_mape: Optional[float],
    criticality: str,
    days_till_stockout: float,
    cv_demand: float,
) -> Tuple[float, str]:
    """
    Calibrate confidence weight alpha for the AI recommendation.

    Formula:
      base_alpha = 1 - 0.5 * (recent_mape / 30)
      Adjustments:
        - If MAPE > 40%: shift down 0.10 (high forecast uncertainty)
        - If CV > 0.4 (volatile demand): shift down 0.08
        - If criticality==High and stockout imminent (<3d): shift down 0.10
        - If MAPE < 10%: shift up 0.05 (high model confidence)
      Final: clip to [0.30, 0.90]

    alpha close to 1.0 = trust AI more.
    alpha close to 0.3 = trust human/business rules more.
    """
    mape = recent_mape if recent_mape is not None else 25.0  # default assumption
    base_alpha = 1.0 - 0.5 * (mape / 30.0)

    reason_parts = [f"base_alpha={base_alpha:.2f} (MAPE={mape:.1f}%)"]

    if mape > 40:
        base_alpha -= 0.10
        reason_parts.append("−0.10 (high forecast error)")
    if cv_demand > 0.4:
        base_alpha -= 0.08
        reason_parts.append("−0.08 (volatile demand)")
    if criticality == "High" and days_till_stockout < 3:
        base_alpha -= 0.10
        reason_parts.append("−0.10 (critical SKU near stockout → conservative)")
    if mape < 10:
        base_alpha += 0.05
        reason_parts.append("+0.05 (low forecast error → high model confidence)")

    alpha = float(np.clip(base_alpha, 0.30, 0.90))
    calibration_note = "; ".join(reason_parts) + f" → final alpha={alpha:.2f}"
    return alpha, calibration_note


# ── Human Agent ─────────────────────────────────────────────────────────────

def human_agent_recommendation(
    dc_id: str,
    sku_id: str,
    criticality: str,
    days_till_stockout: float,
    ai_recommendation: dict,
    rules: dict,
) -> dict:
    """
    Apply business rules to produce a human-agent recommendation.
    Rules can agree with AI, or override with a different action.
    """
    manual = rules.get("manual_overrides", {}).get(dc_id, {}).get(sku_id)
    if manual:
        return {
            "option": manual.get("action", ai_recommendation["option"]),
            "qty": manual.get("qty", ai_recommendation["qty"]),
            "reason": f"Manual planner override: {manual.get('note', 'no note')}",
            "source": "manual_override",
        }

    reserved = sku_id in rules.get("reserved_dc_stock", {}).get(dc_id, [])
    if reserved:
        return {
            "option": "no_action",
            "qty": 0,
            "reason": f"DC {dc_id} stock for {sku_id} is reserved by planner — do not transfer.",
            "source": "reserved_stock_rule",
        }

    emergency = rules.get("emergency_policy", {}).get(criticality, "")
    if days_till_stockout <= 3 and "prefer_local_if_stockout_within_3d" in emergency:
        return {
            "option": "local_supplier",
            "qty": ai_recommendation.get("qty", 100),
            "reason": f"Emergency policy: High-criticality stockout within {round(days_till_stockout, 1)}d → force local supplier.",
            "source": "emergency_policy",
        }

    # Default: agree with AI
    return {
        "option": ai_recommendation["option"],
        "qty": ai_recommendation["qty"],
        "reason": "Business rules agree with AI recommendation.",
        "source": "ai_agreement",
    }


# ── Fusion ────────────────────────────────────────────────────────────────────

def fuse(
    ai_recommendation: dict,
    human_recommendation: dict,
    alpha: float,
    scored_options: list,
) -> dict:
    """
    Fuse AI and human recommendations.

    For discrete actions (option selection), we use a weighted voting approach:
    - If both agree: direct recommendation, confidence = alpha
    - If they disagree: pick AI if alpha >= 0.6, else human (with note)
    - Quantity is alpha-weighted average of AI and human qtys
    """
    ai_opt = ai_recommendation["option"]
    hu_opt = human_recommendation["option"]
    agree = ai_opt == hu_opt

    if agree:
        final_option = ai_opt
        final_qty = ai_recommendation.get("qty", 0)
        consensus = "AI and business rules agree"
    else:
        if alpha >= 0.60:
            final_option = ai_opt
            final_qty = ai_recommendation.get("qty", 0)
            consensus = f"AI overrides business rules (alpha={alpha:.2f} ≥ 0.60)"
        else:
            final_option = hu_opt
            final_qty = human_recommendation.get("qty", 0)
            consensus = f"Business rules override AI (alpha={alpha:.2f} < 0.60)"

    # Weighted quantity blend
    ai_qty = float(ai_recommendation.get("qty", 0))
    hu_qty = float(human_recommendation.get("qty", ai_qty))
    blended_qty = int(round(alpha * ai_qty + (1 - alpha) * hu_qty))

    # Find the winning option details
    opt_detail = next(
        (o for o in scored_options if o["option"] == final_option),
        scored_options[0] if scored_options else {}
    )

    return {
        "ai_option": ai_opt,
        "ai_qty": int(ai_qty),
        "ai_confidence": round(alpha, 2),
        "human_option": hu_opt,
        "human_qty": int(hu_qty),
        "human_source": human_recommendation.get("source", "rules"),
        "human_reason": human_recommendation.get("reason", ""),
        "alpha": round(alpha, 2),
        "agree": agree,
        "consensus_note": consensus,
        "final_option": final_option,
        "final_qty": blended_qty,
        "final_label": opt_detail.get("label", final_option),
        "final_total_cost": opt_detail.get("total_cost", 0),
        "final_lead_time_days": opt_detail.get("lead_time_days", 0),
        "final_source_dc": opt_detail.get("source_dc"),
    }


# ── Main entry point ─────────────────────────────────────────────────────────

def run_dacdf(
    dc_id: str,
    sku_id: str,
    scored_options: list,
    criticality: str,
    days_till_stockout: float,
    recent_mape: Optional[float],
    cv_demand: float,
    reason_string: str,
) -> dict:
    """Full DACDF pipeline: calibrate alpha, AI agent, human agent, fusion."""
    rules = load_rules()
    alpha, calibration_note = calibrate_alpha(
        recent_mape, criticality, days_till_stockout, cv_demand
    )

    # AI agent picks top scored option
    feasible_opts = [o for o in scored_options if o.get("feasible", True)]
    ai_pick = feasible_opts[0] if feasible_opts else (scored_options[0] if scored_options else {})
    ai_rec = {
        "option": ai_pick.get("option", "no_action"),
        "qty": ai_pick.get("qty", 0),
        "total_score": ai_pick.get("total_score", 0),
        "reason": reason_string,
    }

    # Human agent
    human_rec = human_agent_recommendation(
        dc_id, sku_id, criticality, days_till_stockout, ai_rec, rules
    )

    # Fuse
    result = fuse(ai_rec, human_rec, alpha, scored_options)
    result["calibration_note"] = calibration_note
    result["ai_reason"] = reason_string
    return result
