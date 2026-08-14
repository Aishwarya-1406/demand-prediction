"""
escalation.py router — Escalation & review cadence API
"""
import math
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api", tags=["escalation"])


def _cache(request: Request):
    return request.app.state.get_cache()


def _safe(obj):
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe(v) for v in obj]
    return obj


@router.get("/escalation")
def get_escalation_dashboard(request: Request, tier: str = "", dc_id: str = "", criticality: str = ""):
    """
    Return all escalation records, optionally filtered by tier, dc_id, criticality.
    Returns summary counts + detail rows sorted by escalation_tier desc.
    """
    cache = _cache(request)
    rows = cache.get("replenishment_table", [])

    escalation_rows = []
    for r in rows:
        if "escalation_tier" not in r:
            continue
        if tier and str(r.get("escalation_tier", "")) != tier:
            continue
        if dc_id and r.get("dc_id") != dc_id:
            continue
        if criticality and r.get("criticality") != criticality:
            continue
        escalation_rows.append(r)

    # Sort: highest tier first, then by days_of_stock ascending
    escalation_rows.sort(key=lambda x: (-x.get("escalation_tier", 0), x.get("days_of_stock", 9999)))

    # Summary counts per tier
    tier_counts = {0: 0, 1: 0, 2: 0, 3: 0}
    for r in rows:
        t = r.get("escalation_tier", 0)
        tier_counts[t] = tier_counts.get(t, 0) + 1

    # Network-level summary
    summary = {
        "tier_3_emergency": tier_counts.get(3, 0),
        "tier_2_escalate": tier_counts.get(2, 0),
        "tier_1_reorder": tier_counts.get(1, 0),
        "tier_0_monitor": tier_counts.get(0, 0),
        "total_flagged": tier_counts.get(3, 0) + tier_counts.get(2, 0) + tier_counts.get(1, 0),
    }

    return JSONResponse(content=_safe({
        "summary": summary,
        "rows": escalation_rows,
        "total": len(escalation_rows),
    }))


@router.get("/escalation/{dc_id}/{sku_id}")
def get_sku_escalation(dc_id: str, sku_id: str, request: Request):
    """Return full escalation detail for a specific DC×SKU."""
    cache = _cache(request)
    data = cache.get("sku_dc_results", {}).get(dc_id, {}).get(sku_id)
    if data is None:
        return JSONResponse(status_code=404, content={"error": f"SKU {sku_id} at {dc_id} not found"})
    esc = data.get("escalation", {})
    freq = data.get("frequency_plan", {})
    return JSONResponse(content=_safe({
        "escalation": esc,
        "frequency_plan": freq,
    }))
