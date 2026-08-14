"""
FastAPI main application — MedCare Pharma Demand Sensing API
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from engine.precompute import run_full_pipeline, load_cache
from api.routers import dc, sku, replenishment, rules, escalation

# Global cache
_cache = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("Starting up — loading pipeline cache or running pipeline...")
    cached = load_cache()
    if cached is None:
        print("No cache found. Running full pipeline (this may take ~60s)...")
        cached = run_full_pipeline(verbose=True)
    _cache.update(cached)
    print(f"Cache ready. {len(_cache.get('replenishment_table', []))} replenishment rows.")
    yield
    _cache.clear()

app = FastAPI(
    title="MedCare Pharma — Demand Sensing & Replenishment API",
    description="Full demand sensing, inventory position, FEFO, DACDF replenishment decision engine.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inject cache into routers
def get_cache():
    return _cache

app.state.get_cache = get_cache

app.include_router(dc.router)
app.include_router(sku.router)
app.include_router(replenishment.router)
app.include_router(rules.router)
app.include_router(escalation.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "cache_loaded": bool(_cache)}


@app.post("/api/retrain")
def retrain():
    """Re-run the full pipeline and refresh the cache."""
    global _cache
    result = run_full_pipeline(verbose=False)
    _cache.clear()
    _cache.update(result)
    return {"status": "retrained", "rows": len(_cache.get("replenishment_table", []))}
