# MedCare Pharma — Demand Sensing & Replenishment Planning

> Hackathon solution: AI-powered demand forecasting, inventory sensing, FEFO-aware replenishment, and Dual-Agent Cognitive Decision Framework (DACDF).

---

## Quick Start

### 1. Backend (FastAPI)
```bash
cd backend
# First run: generates model cache (~90s)
python -m engine.precompute

# Start API server
python -m uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend (Next.js)
```bash
cd frontend
npm run dev
# Visit http://localhost:3000
# Login: admin / medcare2026
```

---

## Architecture

```
data/                      ← 5 CSVs (daily_demand_inventory, sku_master,
                             dc_master, lead_times, batches)
backend/
  engine/
    data_loader.py         ← Load all CSVs, compute derived fields
    feature_engineering.py ← Lag/rolling features for ML
    forecasting.py         ← XGBoost + RF + baseline, SHAP, MAPE
    inventory.py           ← Usable inventory, FEFO expiry logic
    decision_engine.py     ← Transfer feasibility, option evaluation
    scoring.py             ← Multi-objective scoring formula
    dacdf.py               ← Dual-Agent Cognitive Decision Framework
    precompute.py          ← Orchestrator, caches to JSON
  api/
    main.py                ← FastAPI app + CORS
    routers/
      dc.py                ← /api/dcs, /api/dcs/{dc_id}/skus
      sku.py               ← /api/dcs/{dc_id}/skus/{sku_id}
      replenishment.py     ← /api/replenishment, /api/replenishment/kpis
      rules.py             ← /api/business-rules (CRUD)
frontend/
  src/app/
    page.tsx               ← Login
    dashboard/             ← DC network overview
    dc/[dc_id]/            ← SKU list for a DC
    dc/[dc_id]/[sku_id]/   ← 6-panel SKU detail
    replenishment/         ← Network replenishment table
```

---

## Data — Field Mapping & Derivation Log

| Concept | Source | Notes |
|---------|--------|-------|
| Daily demand | `daily_demand_inventory.demand_units` | Direct |
| Usable inventory | `physical - reserved - expired + inbound` | Derived |
| Expired batch qty | `batches WHERE expiry_date < analysis_date` | Derived |
| Holding cost | `unit_cost × holding_cost_pct / 365` | Derived |
| Demand during lead time | `forecast × lead_time_days` | Derived |
| Trend label | 14d rolling avg / 28d rolling avg | Derived |
| batches.csv shelf life | Pharmaceutical category defaults (2–5yr) | Synthetic assumption — replace with real data |

---

## Forecasting

- **Features:** day_of_week, month, week_of_year, flu_season_index, promo_flag, lag_1/7/14, rolling_7/14/28d avg, flu×lag, promo×lag
- **Models:** Random Forest (winner), XGBoost
- **Baseline:** 14-day rolling average
- **Horizon:** 14 days ahead per DC×SKU
- **SHAP:** Top 5 feature importances via `shap.TreeExplainer`
- **MAPE note:** Computed only on days with demand ≥ 5 units (near-zero actuals inflate the metric artificially)

---

## Decision Engine

### 4 Options Evaluated Per DC×SKU
| Option | Cost | Lead Time |
|--------|------|-----------|
| No Action | 0 | n/a |
| DC Transfer (best source) | `unit_cost + transfer_cost` × qty | 2–3 days |
| Regular Supplier | `purchase_cost_regular` × qty | 5–9 days |
| Local Supplier | `purchase_cost_local` × qty | 1–2 days |

### Multi-Objective Scoring Formula
```
Score = w1·stockout_risk + w2·expiry_risk - w3·cost - w4·lead_time + w5·service_level

Weights by criticality:
  High:   [0.35, 0.20, 0.15, 0.20, 0.10]
  Medium: [0.25, 0.20, 0.25, 0.15, 0.15]
  Low:    [0.15, 0.15, 0.40, 0.15, 0.15]
```

### FEFO Transfer Feasibility
- Sorts batches at source DC by expiry date ascending
- Transfer approved only if `dest_dc_daily_demand × days_remaining > batch_quantity`
- Partial transfers computed when only some qty can be consumed before expiry

---

## DACDF — Dual-Agent Cognitive Decision Framework

```
alpha = calibrated from recent MAPE:
  base_alpha = 1 - 0.5 × (MAPE / 30)
  −0.10 if MAPE > 40%  (high forecast uncertainty)
  −0.08 if CV > 0.4    (volatile demand)
  −0.10 if High-crit SKU near stockout (<3d)
  +0.05 if MAPE < 10%  (high model confidence)
  → clipped to [0.30, 0.90]

final_option  = AI if alpha ≥ 0.60, else Human rules
final_qty     = alpha × AI_qty + (1-alpha) × Human_qty
```

Business rules editable via `/api/business-rules` endpoint or directly in `backend/engine/business_rules.json`.

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/dcs` | All DC health summaries |
| GET | `/api/dcs/{dc_id}/skus` | All SKUs for a DC |
| GET | `/api/dcs/{dc_id}/skus/{sku_id}` | Full SKU analysis |
| GET | `/api/replenishment` | Network replenishment table |
| GET | `/api/replenishment/kpis` | Network KPIs |
| GET/POST | `/api/business-rules` | Read/update business rules |
| POST | `/api/retrain` | Re-run ML pipeline |

---

## Requirements

```
Python 3.9+
pandas, numpy, scipy, scikit-learn, xgboost, shap, fastapi, uvicorn

Node.js 18+
next@14, recharts, typescript
```
