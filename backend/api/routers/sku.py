import math
import json
import numpy as np
import pandas as pd
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api", tags=["sku"])


def _cache(request: Request):
    return request.app.state.get_cache()


def _safe(obj):
    """Recursively sanitise values so JSON serialisation never fails.
    Handles: float inf/nan, numpy scalars, numpy arrays, pandas Timestamps.
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        v = float(obj)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(obj, np.ndarray):
        return [_safe(x) for x in obj.tolist()]
    if isinstance(obj, (pd.Timestamp,)):
        return str(obj.date())
    if isinstance(obj, dict):
        return {k: _safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe(v) for v in obj]
    return obj


@router.get("/dcs/{dc_id}/skus/{sku_id}")
def get_sku_detail(dc_id: str, sku_id: str, request: Request):
    """Full SKU detail: forecast, inventory, batches, options, DACDF."""
    cache = _cache(request)
    data = cache.get("sku_dc_results", {}).get(dc_id, {}).get(sku_id)
    if data is None:
        raise HTTPException(404, f"SKU {sku_id} at DC {dc_id} not found")
    # Sanitise before returning
    safe_data = _safe(data)
    return JSONResponse(content=safe_data)
