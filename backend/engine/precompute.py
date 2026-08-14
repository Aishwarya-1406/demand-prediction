"""
precompute.py — Run the full pipeline and cache results as JSON.
Called once at startup (or on retrain). Results served by FastAPI.
"""
from __future__ import annotations
import json
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Optional

from .data_loader import load_all, get_latest_snapshot, get_dc_health_summary, get_batches_for, get_active_promo_events
from .feature_engineering import add_features, classify_trend
from .forecasting import train_models, forecast_sku_dc
from .decision_engine import evaluate_all_options
from .scoring import score_options, build_reason_string
from .dacdf import run_dacdf
from .frequency import compute_frequency_plan
from .escalation import run_escalation

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

ANALYSIS_DATE = pd.Timestamp("2026-08-13")


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy types and inf/nan floats safely."""
    def default(self, obj):
        if isinstance(obj, (np.integer,)): return int(obj)
        if isinstance(obj, (np.floating,)):
            v = float(obj)
            if np.isnan(v): return None
            if np.isinf(v): return 9999 if v > 0 else -9999
            return v
        if isinstance(obj, np.ndarray): return obj.tolist()
        if isinstance(obj, pd.Timestamp): return str(obj.date())
        return super().default(obj)

    def encode(self, obj):
        """Pre-sanitise the entire object tree to catch plain Python inf/nan."""
        return super().encode(self._sanitise(obj))

    def _sanitise(self, obj):
        if isinstance(obj, float):
            if np.isnan(obj): return None
            if np.isinf(obj): return 9999 if obj > 0 else -9999
            return obj
        if isinstance(obj, dict): return {k: self._sanitise(v) for k, v in obj.items()}
        if isinstance(obj, list): return [self._sanitise(v) for v in obj]
        return obj



def run_full_pipeline(verbose: bool = True) -> dict:
    if verbose: print("[1/6] Loading data...")
    raw = load_all()
    dd = raw["demand"]
    dist_orders = raw.get("distributor_orders")
    active_promo_events = get_active_promo_events(raw, ANALYSIS_DATE)
    sm = raw["sku"]
    dc = raw["dc"]
    lt = raw["lead_times"]
    bt = raw["batches"]

    if verbose: print("[2/6] Training ML models...")
    model_results = train_models(dd)
    xgb_model = model_results["xgb"]
    rf_model = model_results["rf"]
    global_metrics = {
        "xgboost": model_results["xgboost"],
        "random_forest": model_results["random_forest"],
        "winner": model_results["winner"],
    }
    if verbose:
        print(f"  XGBoost: MAE={model_results['xgboost']['mae']:.2f}, "
              f"RMSE={model_results['xgboost']['rmse']:.2f}, "
              f"MAPE={model_results['xgboost']['mape']:.1f}%")
        print(f"  RF:      MAE={model_results['random_forest']['mae']:.2f}, "
              f"RMSE={model_results['random_forest']['rmse']:.2f}, "
              f"MAPE={model_results['random_forest']['mape']:.1f}%")
        print(f"  Winner: {model_results['winner']}")

    if verbose: print("[3/6] Computing inventory snapshot...")
    snapshot = get_latest_snapshot(raw)
    dc_health = get_dc_health_summary(raw)

    if verbose: print("[4/6] Generating per-SKU-DC forecasts & recommendations...")
    sku_ids = sorted(dd["sku_id"].unique())
    dc_ids = sorted(dd["dc_id"].unique())

    all_results = {}
    replenishment_rows = []

    sku_meta = sm.set_index("sku_id").to_dict("index")
    dc_meta = dc.set_index("dc_id").to_dict("index")

    for dc_id in dc_ids:
        all_results[dc_id] = {}
        for sku_id in sku_ids:
            sku_info = sku_meta.get(sku_id, {})
            dc_info = dc_meta.get(dc_id, {})
            criticality = sku_info.get("criticality", "Medium")

            # Forecast
            fcast = forecast_sku_dc(dd, dc_id, sku_id, xgb_model)

            # Snapshot row
            snap_row = snapshot[(snapshot["dc_id"] == dc_id) & (snapshot["sku_id"] == sku_id)]
            if snap_row.empty:
                continue
            snap = snap_row.iloc[0]

            usable = float(snap["usable_inventory"])
            safety_stock = float(snap["safety_stock"])
            raw_avg = float(np.mean(fcast.get("forecast_next_14d", [1])))
            avg_daily = max(raw_avg, 0.5)  # minimum 0.5 units/day to avoid div-by-zero
            days_till_stockout = min(usable / avg_daily if avg_daily > 0 else 9999.0, 9999.0)

            # Demand volatility (CV)
            sub = dd[(dd["dc_id"] == dc_id) & (dd["sku_id"] == sku_id)]["demand_units"]
            sub_mean = sub.mean()
            cv_demand = float(sub.std() / sub_mean) if sub_mean > 0 else 0.5
            cv_demand = min(cv_demand, 5.0)  # clamp extreme CV

            # Batch info
            batches_sku = get_batches_for(raw, dc_id, sku_id)
            near_expiry_qty = int(
                batches_sku[batches_sku["days_to_expiry"].between(0, 90)]["quantity"].sum()
            )

            # Options evaluation
            options = evaluate_all_options(
                dc_id, sku_id, snapshot, bt, lt, fcast, sku_info, dc_info
            )

            # Score
            scored = score_options(
                options, criticality, days_till_stockout, near_expiry_qty, avg_daily
            )

            # Reason string for winner
            winner_opt = next((o for o in scored if o.get("feasible", True)), scored[0]) \
                if scored else {}
            reason = build_reason_string(
                winner_opt, criticality, days_till_stockout, near_expiry_qty, avg_daily
            )

            # DACDF
            dacdf = run_dacdf(
                dc_id, sku_id, scored, criticality,
                days_till_stockout, fcast.get("mape"), cv_demand, reason
            )

            # Replenishment requirement
            demand_lt = fcast.get("demand_during_lead_time_regular", avg_daily * 7)
            inbound = float(snap["inbound_inventory"])
            req_qty = max(0, demand_lt + safety_stock - usable - inbound)

            # Lead times for frequency + escalation
            lt_sub = lt[(lt["dc_id"] == dc_id) & (lt["sku_id"] == sku_id)]
            lt_reg = float(lt_sub[lt_sub["supplier_type"] == "regular"]["lead_time_days"].iloc[0]) \
                if not lt_sub[lt_sub["supplier_type"] == "regular"].empty else 7.0
            lt_loc = float(lt_sub[lt_sub["supplier_type"] == "local"]["lead_time_days"].iloc[0]) \
                if not lt_sub[lt_sub["supplier_type"] == "local"].empty else 2.0

            # Replenishment frequency optimisation
            freq_plan = compute_frequency_plan(
                dc_id=dc_id,
                sku_id=sku_id,
                avg_daily_demand=avg_daily,
                demand_std=float(sub.std()) if len(sub) > 1 else avg_daily * 0.3,
                unit_cost=float(sku_info.get("unit_cost", 10)),
                holding_cost_pct=float(sku_info.get("holding_cost_pct", 0.20)),
                lead_time_regular=lt_reg,
                lead_time_local=lt_loc,
                criticality=criticality,
                days_till_stockout=days_till_stockout,
                distributor_df=dist_orders if dist_orders is not None and not dist_orders.empty else None,
            )
            # Annotate next review date
            import datetime
            freq_plan["next_review_date"] = str(
                (ANALYSIS_DATE + pd.Timedelta(days=freq_plan["review_period_days"])).date()
            )

            # Escalation tier
            esc = run_escalation(
                dc_id=dc_id,
                sku_id=sku_id,
                criticality=criticality,
                health_flag=str(snap["health_flag"]),
                days_till_stockout=days_till_stockout,
                lead_time_regular=lt_reg,
                lead_time_local=lt_loc,
                near_expiry_qty=near_expiry_qty,
                avg_daily_demand=avg_daily,
                best_action=dacdf["final_option"],
                trend=fcast.get("trend", "stable"),
                mape=fcast.get("mape"),
            )

            result = {
                "dc_id": dc_id,
                "sku_id": sku_id,
                "sku_name": sku_info.get("sku_name", sku_id),
                "criticality": criticality,
                "category": sku_info.get("category", ""),
                "usable_inventory": int(usable),
                "physical_inventory": int(snap["physical_inventory"]),
                "reserved_inventory": int(snap["reserved_inventory"]),
                "inbound_inventory": int(inbound),
                "safety_stock": int(safety_stock),
                "reorder_point": int(snap["reorder_point"]),
                "health_flag": snap["health_flag"],
                "days_of_stock": round(min(days_till_stockout, 9999.0), 1),
                "projected_stockout_date": str((ANALYSIS_DATE + pd.Timedelta(
                    days=min(int(min(days_till_stockout, 365)), 365))).date()),
                "near_expiry_qty": near_expiry_qty,
                "forecast": fcast,
                "trend": fcast.get("trend", "stable"),
                "replenishment_requirement": round(req_qty),
                "batches": batches_sku.to_dict("records"),
                "options": scored,
                "dacdf": dacdf,
                "frequency_plan": freq_plan,
                "escalation": esc,
                "active_promo_events": active_promo_events,
            }
            all_results[dc_id][sku_id] = result

            # Add to replenishment table
            replenishment_rows.append({
                "dc_id": dc_id,
                "dc_name": dc_info.get("dc_name", dc_id),
                "sku_id": sku_id,
                "sku_name": sku_info.get("sku_name", sku_id),
                "criticality": criticality,
                "required_qty": round(req_qty),
                "stockout_risk": snap["health_flag"],
                "days_of_stock": round(days_till_stockout, 1),
                "best_action": dacdf["final_option"],
                "best_action_label": dacdf["final_label"],
                "source": dacdf.get("final_source_dc") or dacdf["final_option"],
                "lead_time_days": dacdf["final_lead_time_days"],
                "est_cost": dacdf["final_total_cost"],
                "ai_confidence": dacdf["alpha"],
                "near_expiry_qty": near_expiry_qty,
                "trend": fcast.get("trend", "stable"),
                # New fields
                "review_period_days": freq_plan["review_period_days"],
                "order_frequency": freq_plan["recommended_order_frequency"],
                "frequency_risk": freq_plan["frequency_risk_flag"],
                "escalation_tier": esc["escalation_tier"],
                "escalation_label": esc["escalation_label"],
                "escalation_color": esc["escalation_color"],
                "escalation_owner": esc["escalation_owner"],
                "escalation_action": esc["escalation_action"],
                "next_review_datetime": esc["next_review_datetime"],
            })

    if verbose: print("[5/6] Computing network KPIs...")
    critical_stockouts = sum(
        1 for r in replenishment_rows
        if r["stockout_risk"] == "red" and r["criticality"] == "High"
    )
    near_expiry_value = sum(
        r["near_expiry_qty"] * (sku_meta.get(r["sku_id"], {}).get("unit_cost", 10))
        for r in replenishment_rows
    )

    kpis = {
        "critical_stockouts": critical_stockouts,
        "total_stockout_risk": sum(1 for r in replenishment_rows if r["stockout_risk"] == "red"),
        "near_expiry_inventory_value": round(near_expiry_value),
        "estimated_total_replenishment_cost": sum(r["est_cost"] for r in replenishment_rows),
        "global_model_metrics": global_metrics,
        "analysis_date": str(ANALYSIS_DATE.date()),
        "total_dcs": len(dc_ids),
        "total_skus": len(sku_ids),
    }

    if verbose: print("[6/6] Saving cache...")
    output = {
        "dc_health": dc_health.to_dict("records"),
        "sku_dc_results": all_results,
        "replenishment_table": replenishment_rows,
        "kpis": kpis,
    }
    with open(CACHE_DIR / "pipeline_output.json", "w") as f:
        json.dump(output, f, cls=NumpyEncoder, indent=2)

    if verbose: print(f"\nDone. Cached to {CACHE_DIR / 'pipeline_output.json'}")
    return output


def load_cache() -> Optional[dict]:
    p = CACHE_DIR / "pipeline_output.json"
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None


if __name__ == "__main__":
    run_full_pipeline(verbose=True)
