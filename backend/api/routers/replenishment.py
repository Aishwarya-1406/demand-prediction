from fastapi import APIRouter, Request, Query

router = APIRouter(prefix="/api", tags=["replenishment"])


def _cache(request: Request):
    return request.app.state.get_cache()


@router.get("/replenishment")
def get_replenishment_table(
    request: Request,
    dc_id: str = Query(None),
    criticality: str = Query(None),
    risk: str = Query(None),
    sort_by: str = Query("days_of_stock"),
):
    """Network-wide replenishment table with optional filters."""
    cache = _cache(request)
    rows = cache.get("replenishment_table", [])

    if dc_id:
        rows = [r for r in rows if r["dc_id"] == dc_id]
    if criticality:
        rows = [r for r in rows if r["criticality"] == criticality]
    if risk:
        rows = [r for r in rows if r["stockout_risk"] == risk]

    # Sort
    reverse = sort_by in ("est_cost", "required_qty", "near_expiry_qty")
    rows = sorted(rows, key=lambda x: x.get(sort_by, 0), reverse=reverse)

    return {"rows": rows, "total": len(rows)}


@router.get("/replenishment/kpis")
def get_kpis(request: Request):
    """Network KPI summary."""
    cache = _cache(request)
    return cache.get("kpis", {})
