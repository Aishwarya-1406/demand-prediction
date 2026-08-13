from fastapi import APIRouter, Request, HTTPException

router = APIRouter(prefix="/api", tags=["dc"])


def _cache(request: Request):
    return request.app.state.get_cache()


@router.get("/dcs")
def get_dcs(request: Request):
    """DC list with health status for dashboard cards."""
    cache = _cache(request)
    dc_health = cache.get("dc_health", [])
    kpis = cache.get("kpis", {})
    return {"dcs": dc_health, "kpis": kpis}


@router.get("/dcs/{dc_id}/skus")
def get_dc_skus(dc_id: str, request: Request):
    """All SKUs for a DC with per-SKU summary."""
    cache = _cache(request)
    dc_results = cache.get("sku_dc_results", {}).get(dc_id)
    if dc_results is None:
        raise HTTPException(404, f"DC {dc_id} not found")

    skus = []
    for sku_id, data in dc_results.items():
        skus.append({
            "sku_id": sku_id,
            "sku_name": data["sku_name"],
            "criticality": data["criticality"],
            "category": data["category"],
            "usable_inventory": data["usable_inventory"],
            "safety_stock": data["safety_stock"],
            "reorder_point": data["reorder_point"],
            "days_of_stock": data["days_of_stock"],
            "health_flag": data["health_flag"],
            "trend": data["trend"],
            "near_expiry_qty": data["near_expiry_qty"],
            "replenishment_requirement": data["replenishment_requirement"],
            "best_action": data["dacdf"]["final_option"],
            "best_action_label": data["dacdf"]["final_label"],
            "ai_confidence": data["dacdf"]["alpha"],
            "mae": data["forecast"].get("mae"),
            "mape": data["forecast"].get("mape"),
            "forecast_next_7d": data["forecast"].get("forecast_next_14d", [])[:7],
        })

    # Sort: red first, then yellow, then green
    order = {"red": 0, "yellow": 1, "green": 2}
    skus.sort(key=lambda x: (order.get(x["health_flag"], 2), x["criticality"] != "High"))

    dc_summary = next(
        (d for d in cache.get("dc_health", []) if d.get("dc_id") == dc_id), {}
    )
    return {"dc_id": dc_id, "dc_summary": dc_summary, "skus": skus}
