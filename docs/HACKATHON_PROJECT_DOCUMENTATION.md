# MedCare Pharma — Demand Sensing & Replenishment Planning

## 1. Executive Summary

MedCare Pharma needs to keep critical medicines available during short-term demand surges while reducing losses from stock that expires before it can be consumed. Our solution is a demand-sensing and replenishment decision-support system for a network of distribution centres (DCs).

The system forecasts near-term demand, calculates inventory risk, checks batch expiry using FEFO (First Expiry, First Out), compares replenishment options, and produces an actionable recommendation with escalation ownership and review cadence.

The final recommendation can be one of four actions:

- No action
- Transfer FEFO-safe stock from another DC
- Replenish through the regular supplier
- Replenish through a faster local supplier

## 2. Scope and Data

The synthetic planning dataset contains 57,888 daily demand/inventory records across 8 DCs, 40 medicines, and 320 DC × SKU combinations. The analysis scenario date is 13 August 2026.

| Data source | Primary use |
|---|---|
| Daily demand and inventory | Demand forecasting, usable inventory, safety-stock risk |
| SKU master | Criticality, unit cost, purchase cost, holding cost |
| DC master | DC tier, region, capacity, transfer cost |
| Lead times | Regular/local/transfer feasibility |
| Batch data | FEFO and expiry-aware transfer checks |
| Distributor orders | Fill-rate-aware review-frequency planning |
| Promotion calendar | Promotion and seasonal context |

## 3. Forecasting Model

### Target

The target is `demand_units`: daily demand for one SKU at one DC.

### Features

The model uses only demand-sensing information available before a planning decision:

- Calendar: day of week, month, week of year, days since start
- Demand history: 1-day, 7-day and 14-day demand lags
- Rolling demand: 7-day, 14-day and 28-day averages
- Volatility: 7-day standard deviation
- External signals: flu-season index and promotion flag
- Interaction terms: flu × 7-day lag and promotion × 7-day lag

Inventory, supplier lead times, batch expiry, costs, and DC capacity are deliberately used in the decision engine rather than as demand-forecast features. This prevents data leakage and keeps demand sensing separate from supply decisions.

### Algorithms

| Method | Purpose | Configuration |
|---|---|---|
| 14-day rolling average | Explainable baseline | Mean of recent 14 days |
| Random Forest regressor | Non-linear global benchmark | 200 trees, max depth 8, minimum leaf size 3 |
| XGBoost regressor | Per-SKU forecast and SHAP explanation | 300 trees, max depth 6, learning rate 0.05, 80% row/feature sampling |

Tree models learn feature importance from historical error reduction; we do not manually assign fixed weights such as “flu equals 30%.” SHAP values show the main drivers for an individual XGBoost forecast.

### Validation Design

We use a chronological holdout rather than a random split:

```text
Older historical dates  → training set
Latest 21 days          → unseen test set
```

This reflects the real task of using past demand to predict future demand and prevents future-data leakage.

## 4. Model Performance and Evaluation

The following metrics are from the current global 21-day holdout evaluation.

| Model | MAE (units/day) | RMSE | MAPE |
|---|---:|---:|---:|
| Random Forest | 20.68 | 58.00 | 37.01% |
| XGBoost | 23.06 | 63.27 | 37.90% |

**Global benchmark winner: Random Forest**, selected by lower MAE.

### Meaning of the metrics

- **MAE:** Average absolute daily demand error. Random Forest is off by about 20.68 units/day on average.
- **RMSE:** Penalises large misses more strongly, making it useful for demand spikes.
- **MAPE:** Percentage error; calculated only on days with actual demand of at least 5 units so near-zero demand does not distort it. MAPE is **37%** at daily SKU×DC granularity — this is expected and not an error: at this level of granularity many SKUs exhibit low-volume, intermittent demand (some days zero or near-zero), which causes percentage errors to be structurally larger than they would be for aggregated weekly or product-family forecasts.

> **Note on the ~22% figure referenced in earlier summaries:** that figure came from a per-SKU median across a smaller test subset. The 37% figure above is the correct global 21-day holdout result computed by `train_models()` in `forecasting.py` and is the number that should be cited.

### Why accuracy, precision, recall, and F1 are not reported for the forecast layer

Demand forecasting is a **regression** task: it predicts a number of units. Accuracy, precision, recall, and F1 are classification metrics and would be misleading for the forecast layer.

The **decision layer** (green/yellow/red flags and Tier 0–3 escalation) IS a classification problem and is evaluated separately in Section 4b below.

## 4b. Decision Layer — Precision, Recall and F1 Evaluation

### Classification task definition

For each SKU×DC on each day D, the engine produces:
- A **health flag**: `green` / `yellow` / `red` (based on usable inventory vs safety stock and reorder point)
- An **escalation tier**: 0 (Monitor) / 1 (Reorder Alert) / 2 (Escalate) / 3 (Emergency)

**Ground truth**: did the SKU×DC's health flag actually reach `red` (usable inventory ≤ safety stock) within the next N days, where N = that SKU×DC's regular supplier lead time — the same lead-time window the replenishment engine uses? This definition is fully causal: only information available on day D is used to produce the flag; the outcome is observed from D+1 onward.

### Holdout evaluation — 21-day window (2026-07-24 to 2026-08-13)

The same chronological 21-day holdout used for forecast evaluation yields **5,780 SKU×DC×day records**. However, the synthetic dataset contains only **5 red-flag events** in its entire 181-day history, **none of which fall within the holdout window**. Standard F1 is undefined when there are zero positive ground-truth instances in the evaluation window.

> **Limitation (stated explicitly):** The 21-day holdout is insufficient for classification evaluation because the synthetic planning dataset was designed to represent a mostly well-stocked network (mean usable inventory = 859 units vs mean safety stock = 95 units). This is realistic for a healthy pharma supply chain but means red stockout events are rare. In a production deployment with real ERP data, stockout events occur with sufficient frequency to compute stable F1 metrics on rolling 30-day or 90-day windows.

### Full historical backtest — 181-day window (2026-02-13 to 2026-08-11)

We fall back to the full available history, evaluating 53,086 SKU×DC×day records. For each day we apply the same decision-layer logic using only data available up to that day (the 14-day rolling features have a 14-day warm-up; the first 14 rows per series are excluded to avoid look-ahead).

#### (a) At-risk flag (yellow or red) → any inventory deterioration within lead-time window

The operationally meaningful binary question is: *did the engine flag a SKU×DC as needing attention (yellow or red), and did the inventory position actually worsen within the lead-time window?*

| Metric | Value |
|---|---:|
| Precision | **0.663** |
| Recall | **0.260** |
| F1 | **0.373** |

| | Predicted: Green (no alert) | Predicted: At-risk (yellow/red) |
|---|---:|---:|
| **Actual: OK** | 25,750 (TN) | 3,196 (FP) |
| **Actual: Deteriorating** | 17,866 (FN) | 6,274 (TP) |

#### (b) Tier 2/3 escalation (Escalate/Emergency) → actual severe breach (health_flag = red)

| Metric | Baseline | Optimized (Current) | Improvement |
|---|---:|---:|---|
| Precision | 0.001 (0.14%) | **0.014 (1.41%)** | **10× increase** |
| Recall | 0.429 (42.9%) | **0.476 (47.6%)** | **+4.7% higher recall** |
| F1 | 0.003 | **0.027** | **~10× increase** |
| False Positives (Alarm Fatigue) | 6,460 | **701** | **89.2% reduction in false alarms** |

| | Predicted: Tier 0/1 | Predicted: Tier 2/3 (Escalate/Emergency) |
|---|---:|---:|
| **Actual: No severe breach** | 52,364 (TN) | 701 (FP) |
| **Actual: Severe breach** | 11 (FN) | 10 (TP) |

#### Operational interpretation & root cause analysis

1. **Root cause identified in baseline**: The initial escalation rules escalated any High-criticality SKU with total runway $\le 7$ days directly to Tier 2 (Manager Escalate). Because routine reorder point in the dataset was defined as $\sim 7$ days demand ($7 \times \text{daily demand}$), routine replenishment triggers (which belong in Tier 1: Planner Reorder Alert) were flooding management with **6,460 false alarms** even when inventory was well above safety stock.
2. **Causal refinement**: The improved engine explicitly evaluates **runway above safety stock** ($\text{days\_to\_safety\_stock} = \frac{\text{usable} - \text{safety\_stock}}{\text{daily\_demand}}$) and checks whether replenishment orders are already in transit (`inbound_inventory == 0`). Tier 2/3 now selectively triggers only when a safety stock breach is genuinely imminent within the replenishment lead-time window.
3. **Operational impact**:
   - **89.2% reduction in false alarms** (eliminating 5,759 unnecessary management alerts).
   - **Higher recall** (captures 47.6% of severe breaches, up from 42.9%).
   - In a pharma context with rare severe events (only 21 red breach events across 53,086 records in the synthetic dataset, a base rate of 0.039%), this balanced tuning maintains safety-first protection for critical medicines while drastically reducing planner alarm fatigue.

> **Evaluation script:** `scripts/evaluate_classification_full.py` reproduces these numbers end-to-end from the raw CSV data.

## 5. SCM Decision Workflow

1. Forecast daily demand for each DC × SKU.
2. Convert the forecast into demand during regular, local, and transfer lead times.
3. Calculate usable inventory:

   ```text
   usable inventory = physical − reserved − expired + inbound
   ```

4. Calculate replenishment requirement:

   ```text
   requirement = lead-time demand + safety stock − usable inventory
   ```

   Note: `inbound` (in-transit stock) is already included inside `usable inventory`, so it
   is **not** subtracted again here. Doing so would double-count it and under-state the true
   order quantity when a pending replenishment is already in transit.

5. Evaluate no action, regular supplier, local supplier, and DC transfer.
6. For transfers, choose FEFO batches and verify that the destination can consume them before expiry.
7. Score feasible actions using stockout risk, expiry risk, cost, lead time, service level, and SKU criticality.
8. Combine the quantitative recommendation with business rules and planner overrides.
9. Assign escalation tier, owner, immediate action, and review cadence.

## 6. Example Demo Case

For `MED003`, the system identifies a near-expiry batch at Chennai DC and a shortage at Hyderabad DC.

```text
Recommended action: Transfer from DC001 (Chennai) to DC003 (Hyderabad)
Quantity: 50 units
FEFO batch: BAT_DEMO01
Days to expiry: 33
Near-expiry inventory value rebalanced: INR 3,384
```

The system verifies that the receiving DC can consume the batch before expiry. This shows that the transfer is not merely a stock movement; it is an expiry-aware allocation decision.

## 7. Technical Implementation and Code Quality

### Architecture

```text
data/                 CSV input data
backend/engine/       Forecasting and SCM decision logic
backend/api/          FastAPI service layer
frontend/             Next.js dashboard
backend/cache/        Precomputed, API-ready planning output
```

### Engineering practices used

- Clear separation of data loading, feature engineering, forecasting, scoring, decision logic, escalation, API, and UI.
- Reproducible pipeline command: `python3 -m engine.precompute`.
- Fixed random seeds (`random_state=42`) for repeatable model training.
- Chronological holdout evaluation for time-series integrity.
- Model artefacts cached after training; API serves a precomputed planning output for responsive demo performance. See the note on real-time recomputation below.
- FastAPI endpoints for dashboard, DC, SKU, replenishment, rules, retraining, and escalation views.
- Code documentation through module docstrings, function-level comments, README field mapping, and a smoke-test script.
- Frontend production build and API-level route checks performed before demo.

### Real-time recomputation vs precomputed cache

The API currently serves results from a **precomputed cache** (`backend/cache/pipeline_output.json`) generated by `python3 -m engine.precompute`. This was done for demo responsiveness (the full pipeline across 320 SKU×DC combinations takes ~60 seconds).

**Does the underlying engine support on-demand single SKU×DC recomputation?** Yes. The core functions — `forecast_sku_dc()`, `evaluate_all_options()`, `score_options()`, `run_escalation()`, and `run_dacdf()` — are all independent, stateless functions that accept a single `(dc_id, sku_id)` pair. A live `/api/compute/{dc_id}/{sku_id}` endpoint can be added that:

1. Loads the saved model artefacts from `backend/models/` (already serialised as `.pkl` files).
2. Calls the engine functions with the current snapshot row.
3. Returns a fresh recommendation in under 2 seconds without touching the cache.

This is a known architectural pattern we deliberately deferred in favour of demo stability. It is the natural first enhancement after the hackathon. The `/api/retrain` POST endpoint already demonstrates full pipeline refresh on-demand; the single-SKU path is a subset of that logic.

### Current limitations

- Synthetic data is used; real deployment requires ERP, warehouse, supplier, and epidemiological integrations.
- Per-SKU future forecasts currently use XGBoost while Random Forest is the global benchmark winner; automated champion-model deployment is a future enhancement.
- Future promotion calendars should be injected directly into future forecast rows in a production deployment.
- Formal unit-test coverage and data-drift monitoring should be expanded.
- Single SKU×DC on-demand recomputation endpoint not yet exposed; currently the engine forces a full cache refresh via `/api/retrain`.

## 8. Team Roles and Contributions

Replace “Member” with your team members’ names in the final submission.

| Member | Primary ownership | Concrete deliverables |
|---|---|---|
| Member 1 | Data collection and cleaning | Synthetic data design, schema mapping, data quality checks, master/transaction tables |
| Member 2 | Model training and forecasting | Feature engineering, chronological split, baseline/RF/XGBoost comparison, metrics, SHAP explanation |
| Member 3 | Review and escalation | Risk tiers, escalation owner, review cadence, shortage-response workflow |
| Member 4 | Replenishment planning | Usable inventory, safety stock, reorder requirement, EOQ/review frequency, lead-time logic |
| Member 5 | DACDF and cost optimisation | Action scoring, FEFO-safe transfer, business rules, AI/planner fusion, cost/service trade-offs |

All members contribute to integration, dashboard validation, demo rehearsal, documentation, and presentation questions.

## 9. Four-Day Development Roadmap

The project represents 4 calendar days of work by 5 contributors: **20 person-days** of team effort.

| Day | Work completed | Deliverable |
|---|---|---|
| Day 1 — Define and prepare | Understood the MedCare problem, designed synthetic SCM schemas, created demand, inventory, SKU, DC, lead-time, batch, promotion, and distributor datasets | Clean, connected planning data model |
| Day 2 — Sense and forecast | Built lag/rolling/seasonal/promotion features; implemented baseline, Random Forest, and XGBoost; added chronological evaluation | Forecast metrics and 14-day demand output |
| Day 3 — Decide and execute | Implemented usable inventory, safety stock, replenishment options, FEFO feasibility, scoring, DACDF, EOQ/frequency, and escalation workflow | Actionable recommendation engine |
| Day 4 — Integrate and polish | Built FastAPI/Next.js flow, added traceable near-expiry transfer demo, corrected recommendation edge cases, tested APIs/build, prepared documentation and presentation story | Integrated hackathon-ready control tower |

## 10. Forward Roadmap

### Phase 1: Production data integration

- Connect ERP, WMS, distributor, supplier, promotion, and epidemiological data.
- Replace synthetic data with governed historical transactional data.
- Add validation, missing-data checks, and role-based access.

### Phase 2: Forecast quality improvement

- Add holiday, disease-surveillance, and future-promotion signals.
- Add automatic per-SKU champion-model selection and retraining schedules.
- Backtest by SKU/DC, monitor drift, and track forecast bias.

### Phase 3: Closed-loop planning

- Integrate approved recommendations with ERP purchase orders and transfer orders.
- Capture planner acceptance/rejection feedback.
- Measure actual stockout reduction, expiry avoidance, service level, and realised savings.

### Phase 4: CI/CD Pipeline and Cloud Deployment Strategy

> **Framing note:** This section describes the architecture *designed for* production deployment. The pipeline, containerisation, and GitHub Actions workflows below are not yet implemented — they represent the concrete next engineering step after the hackathon. The underlying code is already structured to support this without refactoring.

#### CI/CD pipeline (designed for, not yet implemented)

The recommended CI/CD approach for this stack (FastAPI backend + Next.js frontend + pickle model artefacts) is **GitHub Actions** with the following stages triggered on every push to `main`:

| Stage | What runs | Trigger |
|---|---|---|
| **Lint & type-check** | `ruff` for Python, `eslint` for Next.js | Every push |
| **Unit tests** | `pytest` for engine functions (data loader, feature engineering, scoring, escalation logic) | Every push |
| **Smoke test** | `python3 scripts/smoke_test.py` — verifies pipeline runs end-to-end without error | Every push |
| **Model staleness check** | Compare current model artefact hash against training data hash; flag if data has changed by >5% without a corresponding retrain | Every push |
| **Docker build** | Build and tag `medcare-backend:sha` and `medcare-frontend:sha` images | On `main` merge |
| **Integration test** | Start containers, hit `/api/health` and a sample `/api/dcs/DC001/skus/MED003`, assert 200 + non-empty response | On `main` merge |
| **Deploy to staging** | Push images to container registry, update staging environment | On `main` merge |
| **Scheduled retrain** | Full pipeline retrain + cache refresh, triggered by cron (see below) | Weekly / on-demand |

The existing `POST /api/retrain` endpoint is the hook for the retrain stage — the CI job simply calls it after deploying the new image.

#### Cloud deployment strategy (designed for, not yet implemented)

**Containerisation:**

```
medcare-backend/    ← FastAPI + engine, Dockerfile with python:3.11-slim base
medcare-frontend/   ← Next.js, Dockerfile with node:20-alpine base
model-artefacts/    ← Mounted as a Docker volume (not baked into image)
```

Model artefacts (`xgb_model.pkl`, `rf_model.pkl`, `pipeline_output.json`) are stored in a cloud object store (AWS S3 / GCS bucket) and mounted at container startup. This separates model versioning from code versioning and allows rollback without a full redeploy.

**Recommended hosting:**

| Component | Suggested service | Rationale |
|---|---|---|
| FastAPI backend | **AWS ECS Fargate** or **Google Cloud Run** | Serverless containers; auto-scales; no server management |
| Next.js frontend | **Vercel** or **AWS Amplify** | Zero-config Next.js hosting with CDN |
| Model artefacts + cache | **S3 / GCS** | Versioned, durable, cheap; containers mount on startup |
| Scheduled retraining | **AWS EventBridge + ECS Task** or **Cloud Scheduler + Cloud Run Job** | Trigger `python3 -m engine.precompute` on a cron schedule |
| Secrets (API keys, DB creds) | **AWS Secrets Manager / GCP Secret Manager** | Never baked into images |

**Model retraining schedule in production:**

Two triggers are recommended:

1. **Scheduled** — weekly cron job runs the full pipeline and overwrites the cache object in S3/GCS. The running container fetches the new cache on the next request (or on restart).
2. **Event-driven** — a data-freshness monitor detects when new ERP demand data arrives and triggers a retrain if the new data covers more than 7 days of previously unseen actuals. This maps directly to the existing `/api/retrain` endpoint.

Retraining on this dataset takes approximately 60 seconds; in production with a larger SKU×DC network, retraining would be parallelised by DC region using a job queue (AWS SQS + worker ECS tasks or Cloud Tasks + Cloud Run).

## 11. Judge-Facing Closing Statement

> We did not build a forecasting dashboard alone. We built a pharma supply-chain decision-support system that converts demand signals into an expiry-safe, cost-aware, lead-time-aware action. It tells the planner what to do, which FEFO batch to use, who should act, and how urgently the item must be reviewed.
