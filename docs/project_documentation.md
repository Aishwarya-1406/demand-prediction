# MedCare Pharma — Demand Sensing & Replenishment Planning

## 1. PROJECT OVERVIEW
**[IMPLEMENTED]**

**Project Name:** MedCare Pharma Demand Sensing & Replenishment API
**What problem it solves:** The system predicts and prevents stock-outs of critical medical SKUs (like antibiotics) during demand surges (e.g., flu season) in Tier-2 distribution centers, while simultaneously identifying and redistributing excess near-expiry stock from Metro distribution centers.
**Why this exists:** Real pharma networks suffer from siloed data. Planners react too late to demand surges, leading to stock-outs of life-saving drugs in smaller cities. Meanwhile, larger cities overstock and let drugs expire, causing massive financial wastage.
**Who uses it:** Supply Chain Planners, Regional Directors, and DC Managers.
**What it does overall:** It takes daily demand and inventory data, uses Machine Learning to forecast the next 14 days, calculates inventory health risks, evaluates replenishment options (including expiry-aware DC-to-DC transfers), and escalates severe risks to human owners.
**The main objective:** Maximize service level (prevent stockouts) while minimizing wastage (prevent expiry) and replenishment costs.
**Why it's not simple CRUD:** Instead of just recording inventory, the system *predicts* when it will run out and *recommends* the optimal action to fix it using ML and business rules.

**30-second explanation:** 
"My project is an AI-driven Supply Chain Control Tower for pharmaceuticals. It predicts drug demand using ML, identifies which distribution centers will face stock-outs or expiry wastage in the next 14 days, and automatically recommends the best replenishment action—like transferring near-expiry stock from a Metro DC to a Tier-2 DC to save costs and prevent stock-outs."

**2-minute Hackathon Pitch:**
"Hello everyone. In the pharmaceutical industry, supply chain failures don't just cost money—they cost lives. Currently, pharma networks suffer from a dual-crisis: Tier-2 cities frequently run out of critical drugs during demand surges like flu season, while Metro cities sit on excess inventory that eventually expires and is thrown away. 
To solve this, we built the MedCare Pharma Demand Sensing & Replenishment platform. Our system takes historical daily demand and inventory data and runs it through an ML forecasting engine to predict the next 14 days. But predicting isn't enough. We built a Decision Engine that evaluates four replenishment options—regular supplier, local supplier, DC transfer, or no action. Crucially, it uses FEFO (First-Expire-First-Out) logic to recommend transferring near-expiry stock from Metro DCs to Tier-2 DCs before they expire, solving both crises at once. Finally, a Dual-Agent Fusion engine ensures ML recommendations strictly adhere to business rules, and high-risk stock-outs are automatically escalated to human directors. It's a proactive, intelligent control tower, not just a dashboard."

---

## 2. REAL-WORLD PROBLEM
**[IMPLEMENTED]**

*   **Stock-outs during surges:** Flu seasons cause unpredictable spikes. Our system solves this by feeding a `flu_season_index` and promotional events into a Random Forest/XGBoost ML model to proactively forecast demand spikes. **[IMPLEMENTED]**
*   **Overstocking & Expiry Wastage:** Metro DCs hold too much stock. Our system solves this by tracking batch-level expiry dates and flagging "Near Expiry Units", calculating their financial risk on the dashboard. **[IMPLEMENTED]**
*   **Siloed Inventory:** Planners can't see network-wide stock. Our system provides a unified Network Dashboard aggregating all DCs. **[IMPLEMENTED]**
*   **Delayed Reorder Decisions:** Humans reorder too late. Our system calculates `days_of_stock` and assigns a `health_flag` (red/yellow/green) to force early action. **[IMPLEMENTED]**
*   **Distributor Reliability:** Suppliers often deliver late. Our system uses `distributor_fill_rate` to inflate order quantities (EOQ) if a supplier is unreliable. **[IMPLEMENTED]**

---

## 3. USERS / ROLES (TEAM MEMBER MODULES)
**[IMPLEMENTED AS SYSTEM MODULES]**

The system is designed around five core operational roles, each handling a distinct segment of the supply chain intelligence pipeline:

1.  **Data & Supply Chain Intelligence:** Responsible for ingesting raw data (`daily_demand_inventory.csv`, `sku_master.csv`, etc.), merging datasets, and conducting feature engineering (`feature_engineering.py`). They ensure data cleanliness, calculate historical lags and rolling averages, and define the base metrics required for all downstream ML operations.
2.  **Demand Sensing & Forecasting:** Responsible for the Machine Learning predictive layer (`forecasting.py`). They train and evaluate the XGBoost and Random Forest models, ensure strict chronological train/test splits to prevent data leakage, and extract SHAP values to provide explainability for demand spikes (like flu-season surges).
3.  **Inventory & Expiry Risk Management:** Responsible for tracking usable inventory, safety stock, and reorder points. Crucially, they manage the FEFO (First-Expire-First-Out) logic, tracking batch-level expiry dates in `batches.csv` to flag "Near Expiry Units" and prevent the distribution of soon-to-expire drugs.
4.  **Risk Review & Escalation:** Responsible for defining health flags (Red, Yellow, Green) based on inventory thresholds (`escalation.py`). They construct the multi-tier escalation matrix (Tier 1-3) to ensure that High-criticality SKUs facing stockouts are flagged with extreme urgency for human intervention.
5.  **Replenishment & Cost Optimization:** Responsible for the Decision Engine and DACDF fusion (`decision_engine.py`, `scoring.py`, `dacdf.py`). They evaluate the four replenishment options, score them mathematically on cost vs. lead time, and apply business rule constraints to output the final, optimized replenishment action and Economic Order Quantity (EOQ).

*(Note: While the system is designed conceptually around these operational areas, it does not currently implement distinct backend security permissions or separate user login portals for these roles. All functionality is visible on the unified dashboard).*

---

## 4. COMPLETE SYSTEM ARCHITECTURE
**[IMPLEMENTED]**

1.  **User** clicks the Next.js **Frontend** dashboard.
2.  **Frontend** sends a `fetch` request to the **API Layer**.
3.  **Backend Route** (FastAPI `main.py`) receives the request.
4.  Instead of computing in real-time, the route fetches from the **Cache Layer** (an in-memory dictionary loaded from `pipeline_output.json`).
5.  *Behind the scenes (on startup/retrain)*, the **Engine Layer** runs sequentially:
    *   `data_loader.py`: Merges CSVs.
    *   `feature_engineering.py`: Creates rolling averages and lags.
    *   `forecasting.py`: Trains ML models and forecasts demand.
    *   `decision_engine.py` & `scoring.py`: Evaluates and ranks replenishment options.
    *   `dacdf.py`: Fuses ML with business rules.
    *   `frequency.py`: Calculates EOQ.
    *   `escalation.py`: Assigns escalation tiers.
    *   `precompute.py`: Saves results to the JSON cache.
6.  **Backend Route** serves the cached JSON.
7.  **Frontend UI** renders the charts and tables.

---

## 5. TECHNOLOGY STACK
**[IMPLEMENTED]**

*   **Frontend:** Next.js (React Framework), HTML/Vanilla CSS. Used for client-side rendering (`"use client"`) of the control tower dashboard.
*   **Backend:** FastAPI (Python). Used for lightning-fast API routing and orchestrating the Python ML engine.
*   **Data Storage:** Local CSV files (`data/` folder). **[IMPLEMENTED]** (No traditional SQL/NoSQL database is used).
*   **Cache:** JSON file (`pipeline_output.json`). Used to avoid running a 60-second ML pipeline on every API request.
*   **ML Libraries:** 
    *   `scikit-learn`: Random Forest Regressor and chronological train/test splitting.
    *   `xgboost`: Gradient boosting regressor for demand prediction.
    *   `shap`: Used for explainable AI (SHAP values) to show users *why* the forecast spiked.
*   **Data Processing:** `pandas`, `numpy`. Used for vectorized data manipulation, merging, and feature engineering.
*   **Notifications/Email:** **[NOT IMPLEMENTED]**.

---

## 6. COMPLETE FEATURE LIST

**Dashboard**
*   Network KPIs (Critical Stockouts, Risk, Expiry Value) **[IMPLEMENTED]**
*   DC Summary Cards with Health Indicators **[IMPLEMENTED]**

**SKU Detail View**
*   Historical vs Predicted Demand Chart **[IMPLEMENTED]**
*   SHAP Forecast Explainability **[IMPLEMENTED]**
*   FEFO Batch Expiry Table **[IMPLEMENTED]**
*   Recommended Action Panel **[IMPLEMENTED]**

**Engine / Business Logic**
*   Demand Forecasting (XGBoost/RF champion selection) **[IMPLEMENTED]**
*   Usable Inventory & Health Flag (Green/Yellow/Red) **[IMPLEMENTED]**
*   Replenishment Recommendation (Regular/Local/Transfer) **[IMPLEMENTED]**
*   FEFO Expiry-Aware Constraints **[IMPLEMENTED]**
*   DACDF (ML + Business Rule Fusion) **[IMPLEMENTED]**
*   Replenishment Frequency / EOQ Planning **[IMPLEMENTED]**
*   Escalation Tiers & Register **[IMPLEMENTED]**
*   Retrain / Pipeline Refresh **[IMPLEMENTED]**

---

## 7. DASHBOARD — DEEP EXPLANATION
**[IMPLEMENTED]**

*   **Critical Stockouts:** Sum of SKUs across all DCs where `health_flag` == 'red'. Acts as a severe **Risk** indicator.
*   **Total Stockout Risk:** Sum of SKUs where `health_flag` == 'yellow'. Acts as a **Warning**.
*   **Near Expiry Inventory Value:** Sum of `quantity * unit_cost` for batches expiring in $\le$ 90 days. 
*   **DC Summary Cards:** Shows total 'At Risk' SKUs and 'Near Expiry Units' per DC. Allows a Regional Director to instantly see which facility needs intervention.
*   **Real-time vs Cached:** **[PARTIALLY IMPLEMENTED]** The dashboard *looks* real-time but is served from a precomputed cache generated on server startup or via a manual retrain trigger.

---

## 8. INVENTORY & DEMAND MANAGEMENT
**[IMPLEMENTED]**

**Lifecycle Flow:**
1.  **Usable Inventory** is calculated as: `Physical Inventory - Reserved Quantity - Expired Quantity + Inbound Pipeline`. 
2.  **Safety Stock** is statically defined in `sku_master.csv`.
3.  **Reorder Point** is calculated as: `Safety Stock + (Lead Time * Average Daily Demand)`.
4.  **Days of Stock** is calculated as: `Usable Inventory / Forecasted Average Daily Demand`. If demand is 0, it defaults to 999 (infinite).
5.  **Health Flag:** 
    *   **Red:** `usable_inventory` < `safety_stock`
    *   **Yellow:** `usable_inventory` < `reorder_point`
    *   **Green:** Healthy

---

## 9. DEMAND FORECASTING LOGIC
**[IMPLEMENTED]**

**HOW:**
1.  **Feature Engineering:** Computes 7-day and 14-day rolling demand averages, 1-day and 7-day lags, `flu_season_index`, and `promo_active`.
2.  **Chronological Split:** Data is sorted by date. The last 14 days of historical data are used as the test set to avoid **data leakage** (future data influencing the past).
3.  **Model Training:** Trains both XGBoost and Random Forest.
4.  **Champion Selection:** Compares Mean Absolute Error (MAE). The model with the lowest MAE "wins" and becomes the production model.
5.  **Recursive Forecasting:** To predict 14 days into the future, the model predicts Day 1, appends it to the dataset, recalculates rolling averages/lags, predicts Day 2, and so on.
6.  **SHAP:** Explains which features (e.g., flu index) drove the prediction up or down.

---

## 10. RISK / HEALTH FLAG SYSTEM
**[IMPLEMENTED]**

**Trigger Conditions:**
*   **Red Flag:** Usable stock is below the absolute safety stock. Planner action: Urgent local reorder or emergency transfer.
*   **Yellow Flag:** Usable stock is below the reorder point (but above safety stock). Planner action: Place a regular supplier order.
*   **Green Flag:** Stock is above reorder point. Planner action: None.

**Characteristics:**
*   **When created:** Recomputed every pipeline run (`precompute.py`).
*   **Persisted?** **[NOT IMPLEMENTED]** Flags are not stored in a database; they exist only in the JSON cache until the next run.
*   **Resolution:** **[NOT IMPLEMENTED]** Users cannot click "Mark as Resolved".
*   **Notifications:** **[NOT IMPLEMENTED]** No actual emails are sent.

*Example:* Usable Inventory = 80. Safety Stock = 95. The system flags this as **RED**, generating a critical escalation.

---

## 11. ESCALATION REGISTER
**[IMPLEMENTED]**

*   **Tier 0 (System Auto-Resolved):** Green health flag.
*   **Tier 1 (DC Planner):** Yellow flag, Medium/Low criticality. Standard review cadence.
*   **Tier 2 (Supply Chain Manager):** Red flag OR High criticality with Yellow flag. Urgent review.
*   **Tier 3 (Regional Director):** Red flag AND High criticality. Immediate intervention required.
*   **State:** The register reflects the *latest pipeline run snapshot*, not a historical audit log of past resolved issues.

---

## 12. REPLENISHMENT DECISION ENGINE — VERY DETAILED
**[IMPLEMENTED]**

**Workflow:**
1.  If Health == Green, Option 0 (No Action) scores highest.
2.  If Replenishment is needed, 3 active options are evaluated:
    *   **Option 1 (Regular Supplier):** Cheapest, longest lead time.
    *   **Option 2 (Local Supplier):** Expensive, fast lead time.
    *   **Option 3 (DC Transfer):** Uses existing network stock.
3.  **FEFO Check (`decision_engine.py`):** For Option 3, the system checks `batches.csv` of the *source* DC. If the stock expires *before* the destination DC's `days_of_stock` runs out, the transfer is blocked (preventing shipping expired drugs).
4.  **Scoring (`scoring.py`):** Normalizes Cost (0-1), Lead Time (0-1), and Expiry Risk (0-1). Computes a weighted score.
5.  **DACDF (`dacdf.py`):** ML provides the top-scored option. Business rules act as constraints (e.g., "If criticality is HIGH and days of stock < 2, force Local Supplier"). DACDF overrides ML if constraints are violated, outputting an `alpha` confidence score.

---

## 13. DISTRIBUTOR / SUPPLIER LOGIC
**[IMPLEMENTED]**

**Distributor Fill Rate impact (`frequency.py`):**
The system looks at `distributor_orders.csv` to find historical `fill_rate` (delivered qty / ordered qty). 
*Business Logic:* If a distributor only delivers 80% of what is ordered, the system automatically inflates the Economic Order Quantity (EOQ) by dividing by 0.8 to compensate for the unreliability.

**Supplier Selection:** 
The system does not have complex vendor bidding. It statically assumes two archetypes per SKU: "Regular" (cheap/slow) and "Local" (expensive/fast) based on `lead_times.csv`.

---

## 14. EXPIRY MANAGEMENT (FEFO)
**[IMPLEMENTED]**

*   **Tracking:** `batches.csv` tracks individual lot quantities and `expiry_date`.
*   **Detection:** Any batch expiring in $\le$ 90 days is flagged as "Near Expiry".
*   **Action:** The system attempts to use this near-expiry stock as the source for Option 3 (DC Transfer) to offload it to a DC experiencing a demand surge, eliminating wastage.

---

## 15. REPORTS / ANALYTICS
**[PARTIALLY IMPLEMENTED]**

*   **Implemented:** Network KPIs (Total Cost, Near Expiry Value, Stockouts) are calculated in `precompute.py` as a single snapshot of the current state.
*   **Not Implemented:** There are no historical trend charts (e.g., "Stockouts over the last 6 months"). Analytics are strictly point-in-time.

---

## 16. NOTIFICATION SYSTEM
**[NOT IMPLEMENTED]**

Notifications are currently not implemented. Escalation owner and action fields describe who *should* act, but no automated email, SMS, or push notification is actually sent by the backend.

---

## 17. BACKEND ARCHITECTURE
**[IMPLEMENTED]**

*   `data_loader.py`: Merges static CSV files into Pandas DataFrames.
*   `feature_engineering.py`: Calculates mathematical indicators (lags/rolling).
*   `forecasting.py`: Pure ML model training and inference.
*   `decision_engine.py`: Evaluates the 4 fulfillment options.
*   `scoring.py`: Ranks the options via weighted algorithms.
*   `dacdf.py`: Applies override rules to the highest scored option.
*   `frequency.py`: Computes EOQ and adjusts for distributor fill rate.
*   `escalation.py`: Assigns risk tiers and owners based on thresholds.
*   `precompute.py`: The orchestrator that calls all the above functions in sequence and writes to `pipeline_output.json`.
*   `api/routers/`: FastAPI routes that blindly serve the JSON file to the frontend, ensuring sub-10ms response times.
*   **Why this matters:** The engine functions are stateless and decoupled from the API. This means they can be easily moved into an Apache Airflow DAG or an AWS Lambda function in the future without rewriting business logic.

---

## 18. FRONTEND ARCHITECTURE
**[IMPLEMENTED]**

*   **Structure:** Next.js App Router (`src/app/`). All components are client-side (`"use client"`).
*   **API Communication:** Uses standard native `fetch()` heavily utilizing `{ cache: 'no-store' }` to prevent Next.js from aggressively caching the API responses.
*   **Workflow Example:** 
    User opens SKU detail page for `MED003` at `DC001` 
    $\rightarrow$ Frontend requests `/api/dcs/DC001/skus/MED003`
    $\rightarrow$ Backend router reads the global cache dictionary in memory 
    $\rightarrow$ Backend returns the precomputed JSON object 
    $\rightarrow$ Frontend React component renders the SHAP bar chart, FEFO table, and recommendation.

---

## 19. API WORKFLOW
**[IMPLEMENTED]**

| Endpoint | Method | Purpose | Frontend Usage |
| :--- | :--- | :--- | :--- |
| `/api/replenishment/kpis` | GET | Returns top-level summary numbers (stockouts, value). | Dashboard |
| `/api/dcs` | GET | Returns list of all DCs and their summarized health. | Dashboard |
| `/api/dcs/{dc_id}/skus` | GET | Returns all SKUs for a specific DC. | DC Detail Page |
| `/api/dcs/{dc_id}/skus/{sku_id}` | GET | Returns deep forecast, batches, and DACDF logic for one item. | SKU Detail Page |
| `/api/replenishment` | GET | Returns the master list of all recommended actions. | Replenishment Table |
| `/api/escalation` | GET | Returns the master list of Tier 1-3 escalated items. | Escalation Register |
| `/api/retrain` | POST | Triggers `run_full_pipeline()` to regenerate the JSON cache. | Dashboard (Refresh Btn) |

---

## 20. DATA MODEL
**[IMPLEMENTED]**

**(Uses CSV files + JSON Cache, NOT a relational database)**
*   `daily_demand_inventory.csv`: Core timeseries. Keys: `date`, `dc_id`, `sku_id`. Contains `demand_units`, `physical_inventory`.
*   `sku_master.csv`: Static metadata. Contains `criticality`, `unit_cost`, `safety_stock`.
*   `dc_master.csv`: Metadata. Contains `dc_tier` (Metro vs Tier-2).
*   `lead_times.csv`: Supplier matrices. Defines transit days for local/regular/transfer options.
*   `batches.csv`: FEFO data. Keys: `dc_id`, `sku_id`, `batch_id`. Contains `expiry_date`.
*   `distributor_orders.csv`: Contains `ordered_qty` and `delivered_qty` used for fill-rate math.

---

## 21. COMPLETE END-TO-END WORKFLOW
**[IMPLEMENTED]**

1.  Raw CSV data is loaded for `DC003` (Tier-2) and `MED003` (High Criticality).
2.  Features engineered: `flu_season_index` shows a massive spike.
3.  Forecast generated: XGBoost predicts a massive surge in demand.
4.  Usable inventory is calculated and found to be lower than the safety stock due to the predicted surge.
5.  Health flag assigned: **RED**.
6.  Decision Engine evaluates options. DC Transfer is evaluated.
7.  FEFO check confirms `DC001` (Metro) has a near-expiry batch of `MED003` that will survive the transit time.
8.  Scoring ranks DC Transfer highly because it saves expiry wastage.
9.  DACDF confirms the ML recommendation doesn't violate rules.
10. Escalation module sees a RED flag + High Criticality and assigns **Tier 3 (Regional Director)**.
11. Frequency planning adjusts EOQ for bad distributor fill-rate.
12. Output is cached to `pipeline_output.json`.
13. Frontend fetches API and displays the RED flag and "Transfer from DC001" recommendation.

---

## 22. BUSINESS LOGIC
**[IMPLEMENTED]**

1.  **WHAT: Health Flag Determination**
    *   *IF* Usable Inventory < Safety Stock $\rightarrow$ *THEN* Flag = Red.
    *   *WHY:* Prevents total stockouts of life-saving drugs.
2.  **WHAT: DACDF Constraint Override**
    *   *IF* Criticality is High AND Days of Stock < 2 AND ML suggests Regular Supplier $\rightarrow$ *THEN* Override to Local Supplier.
    *   *WHY:* You cannot wait 7 days for a regular supplier when a critical drug runs out in 2 days.
3.  **WHAT: FEFO Batch Block**
    *   *IF* Transfer Transit Time + Target Days of Stock > Batch Days to Expiry $\rightarrow$ *THEN* Block Transfer.
    *   *WHY:* Prevents shipping a drug that will expire on the truck or sit on a shelf and expire before it is consumed.
4.  **WHAT: EOQ Distributor Adjustment**
    *   *IF* Distributor Fill Rate = 50% $\rightarrow$ *THEN* EOQ = Base EOQ / 0.5.
    *   *WHY:* If a supplier only delivers half of what you order, you must order double to maintain stock levels.

---

## 23. DATA FLOW
**[IMPLEMENTED]**

**Scenario: Dashboard Request**
Data Source (`pipeline_output.json`) $\rightarrow$ API Route (`/api/replenishment/kpis`) $\rightarrow$ Business Logic (None, purely serving cache) $\rightarrow$ Output (JSON object) $\rightarrow$ Frontend UI (React KPIs state update).

**Scenario: Pipeline Run (Precompute)**
Data Source (`CSV files`) $\rightarrow$ Engine (`feature_engineering` $\rightarrow$ `forecasting` $\rightarrow$ `decision_engine` $\rightarrow$ `dacdf` $\rightarrow$ `escalation`) $\rightarrow$ Output (In-memory dict) $\rightarrow$ Cached to `pipeline_output.json`.

---

## 24. REAL-WORLD DC SCENARIO
**[IMPLEMENTED]**

**Scenario:** A Tier-2 DC (Hyderabad, `DC003`) is hit by flu season. They have 100 units of Paracetamol (`MED004`, High Criticality). 
1.  **Forecast:** The XGBoost model sees the `flu_season_index` spike and forecasts 150 units of demand over the next 14 days. 
2.  **Health Flag:** The system calculates Days of Stock will drop to 0 in 9 days. Usable inventory drops below Safety Stock. Flag turns **RED**.
3.  **Replenishment:** The system evaluates regular suppliers (too slow), local suppliers (fast but expensive), and DC Transfers. 
4.  **FEFO:** It finds `DC001` (Metro, Mumbai) sitting on 500 units of Paracetamol expiring in 40 days. 
5.  **DACDF:** Selects Option 3 (DC Transfer from DC001). 
6.  **Escalation:** Because it's High Criticality and RED, it assigns **Tier 3** to the Regional Director. 

---

## 25. WHAT IS AUTOMATED VS MANUAL
**[IMPLEMENTED]**

| Process | Automated by System | User Action Required |
| :--- | :--- | :--- |
| Demand Forecasting | **YES** | No |
| Health Flag Detection | **YES** | No |
| Replenishment Option Evaluation | **YES** | No |
| DACDF Fusion Decision | **YES** | No |
| FEFO Batch Selection | **YES** | No |
| Escalation Tier Assignment | **YES** | No |
| Pipeline Refresh / Retrain | No | **YES** (Click Button) |
| Approving the DC Transfer | No | **YES** (Outside System) |

---

## 26. CURRENT PROJECT STATUS
**[PARTIALLY IMPLEMENTED]**

*   **Frontend UI:** Fully implemented.
*   **Backend API & Engine:** Fully implemented.
*   **Data Layer:** Partially implemented (Synthetic CSVs, no DB).
*   **Auth / Notifications:** UI/Descriptive only, not implemented.

---

## 27. LIMITATIONS
**[IMPLEMENTED]**

*   **Static Data Source:** Relying on CSVs means it cannot ingest live ERP streams (like SAP/Oracle) without writing a new data connector.
*   **No Actual Authentication:** The login is a frontend mock.
*   **No Automated Notifications:** The system assigns an "owner" but doesn't email them.
*   **Asynchronous Processing UI:** Clicking "Retrain" locks the UI and waits for the HTTP request to finish (~30-60s), which can cause browser timeouts. A real system would use WebSockets or Polling.

---

## 28. FUTURE ENHANCEMENTS
**[FUTURE]**

*   **Short-term:** Implement a proper PostgreSQL database via SQLAlchemy to replace the CSV files. Implement JWT authentication.
*   **Medium-term:** Add Celery/Redis for background task processing of the ML pipeline, with WebSocket progress bars on the frontend. Add email notifications via SendGrid.
*   **Advanced:** Integrate Reinforcement Learning to continuously optimize the DACDF business rules rather than relying on hardcoded overrides. Add live API integrations with logistics providers (e.g., FedEx) to pull dynamic transit times instead of static `lead_times.csv`.

---

## 29. WHY THIS PROJECT IS NOT JUST CRUD
**[IMPLEMENTED]**

A CRUD app simply stores that a DC has 50 boxes of Medicine X. 
This project is an intelligent decision engine. It takes that "50 boxes" and passes it through a 6-stage pipeline:
**Demand Signal $\rightarrow$ Forecast $\rightarrow$ Risk Detection $\rightarrow$ Multi-option Scoring $\rightarrow$ FEFO checking $\rightarrow$ DACDF Fusion $\rightarrow$ Escalation.**
It doesn't just tell the user *what is happening*; it tells them *what will happen* (forecast), *why it matters* (health flag), and *how to fix it* (replenishment recommendation).

---

## 30. POSSIBLE VIVA / JUDGE QUESTIONS AND ANSWERS

**Q1: How do you prevent data leakage in your ML model?**
*Short:* By using chronological splitting.
*Detailed:* We sort the data by date and use the last 14 days strictly as the test set. If we used random splitting, the model would peek at future data points (e.g., using December 5th to predict December 4th), which is impossible in the real world.

**Q2: What happens if the ML model recommends a slow supplier for a critical drug that is about to stock out?**
*Short:* The DACDF module overrides it.
*Detailed:* Dual-Agent Confidence-Driven Fusion (DACDF) treats the ML output as a recommendation but passes it through hard business constraints. If Days of Stock < 2 and Criticality is High, DACDF will discard the slow ML recommendation and force a Local Supplier order to save lives.

**Q3: How does the system prevent expiry wastage?**
*Short:* Through FEFO (First-Expire-First-Out) batch checks.
*Detailed:* When evaluating a DC Transfer, the system checks the `expiry_date` of the specific batch at the source DC. If the batch will expire during transit or before it is consumed at the destination, the system mathematically blocks the transfer, preventing expired drugs from entering the supply chain.

**Q4: Is the dashboard truly real-time?**
*Short:* No, it is cached.
*Detailed:* Training ML models and predicting 40 SKUs across 8 DCs takes ~60 seconds. To provide sub-second dashboard load times, the backend runs the pipeline in the background and caches the output to a JSON file. The API serves this precomputed cache.

**Q5: How does distributor reliability affect the system?**
*Short:* It alters the Economic Order Quantity (EOQ).
*Detailed:* The `frequency.py` module divides the base EOQ by the historical `distributor_fill_rate`. If a supplier only delivers 50% of ordered goods, the system doubles the recommended order quantity to compensate.

---

## 31. "EXPLAIN THIS PROJECT TO A NON-TECHNICAL PERSON"
Imagine a large pharmacy chain. The branch in the small town runs out of flu medicine every winter because they don't order enough in advance. Meanwhile, the giant branch in the big city ordered too much, and the medicine expires and gets thrown in the trash. Our software is like a smart manager that sits above all the branches. It predicts the flu surge, sees the small town is about to run out, and automatically orders the big city to ship their expiring medicine to the small town. We save money on wasted drugs and ensure the small town gets the medicine it needs.

---

## 32. "EXPLAIN THIS PROJECT TO A TECHNICAL INTERVIEWER"
The architecture is a decoupled, multi-stage Python pipeline orchestrated by FastAPI, feeding a Next.js React frontend. The data layer uses pandas to ingest and feature-engineer timeseries data. For forecasting, we evaluate XGBoost and Random Forest, using chronological holdouts to prevent leakage, and dynamically select the champion model based on MAE. We use SHAP for interpretability. 
The core innovation is the Decision Engine: it evaluates 4 discrete fulfillment paths, scoring them on normalized cost, lead time, and expiry risk matrices (FEFO). To ensure AI safety, the DACDF module fuses the probabilistic ML output with deterministic business heuristics. Finally, the backend precomputes the entire state into a static JSON cache to ensure O(1) time complexity (sub-10ms latency) on all API GET requests from the client.

---

## 33. 1-MINUTE PROJECT EXPLANATION
"MedCare Pharma is an AI-driven Supply Chain Control Tower designed to solve a dual-crisis in pharma distribution: critical stock-outs in Tier-2 regions and expiry wastage in Metro regions. Built on Next.js and FastAPI, it uses XGBoost to forecast 14-day demand based on flu and promotional indicators. It detects inventory risks, evaluates multiple replenishment paths, and uses FEFO batch-tracking to recommend transferring near-expiry stock from Metro centers to Tier-2 centers facing shortages. A Dual-Agent Fusion engine ensures ML recommendations adhere to strict business rules, and critical outages are escalated to human directors automatically. It shifts supply chains from reactive tracking to proactive optimization."

---

## 34. 3-MINUTE PROJECT EXPLANATION
*(Combine the 1-minute explanation with the Deep Architecture and Business Logic sections, focusing on DACDF, FEFO, and the problem statement).*

---

## 35. FINAL CHEAT SHEET
**PROJECT:** MedCare Pharma Demand Sensing & Replenishment API
**PROBLEM:** Tier-2 stockouts vs Metro expiry wastage.
**SOLUTION:** ML forecasting + FEFO-aware transfer recommendations.
**USERS:** DC Planners, Supply Chain Managers, Regional Directors.
**FRONTEND:** Next.js (React), CSS.
**BACKEND:** FastAPI (Python).
**DATA LAYER:** Static CSV files.
**AUTHENTICATION:** [UI ONLY] Mock login.
**MAIN MODULES:** Forecasting, Decision Engine, Scoring, DACDF, Escalation.
**FORECASTING LOGIC:** XGBoost/RF, 14-day chronological holdout.
**HEALTH FLAG / RISK LOGIC:** Red if Usable < Safety Stock.
**REPLENISHMENT DECISION LOGIC:** Evaluates 4 options, scores on Cost/LeadTime/Expiry.
**DACDF LOGIC:** Fuses ML recommendation with hard business rules.
**FEFO/EXPIRY LOGIC:** Blocks transfers if batch expires before consumption.
**ESCALATION LOGIC:** Tier 1-3 based on Criticality + Health Flag.
**DISTRIBUTOR LOGIC:** Adjusts EOQ based on historical fill rate.
**NOTIFICATION LOGIC:** [NOT IMPLEMENTED].
**MAIN API FLOW:** API serves static JSON cache `pipeline_output.json`.
**DATA FLOW:** CSVs $\rightarrow$ Engine Pipeline $\rightarrow$ JSON Cache $\rightarrow$ FastAPI $\rightarrow$ Next.js.
**REAL-WORLD VALUE:** Saves lives (prevents stockouts) + Saves money (prevents expiry).
**CURRENT LIMITATIONS:** Synthetic data, no real DB, no live auth/notifications.
**FUTURE SCOPE:** PostgreSQL, Celery task queues, SendGrid emails, RL optimization.

---

### VERY IMPORTANT FINAL REQUIREMENT: MODULE EXPLANATIONS

**data_loader.py [IMPLEMENTED]**
1. WHAT: Loads and joins multiple CSV files into pandas DataFrames.
2. WHY: Standardizes raw siloed data into a unified structure.
3. HOW: Uses `pd.read_csv()` and merges on `dc_id` and `sku_id`.
4. WHAT NEXT: Passes the clean DataFrames to `feature_engineering.py`.

**feature_engineering.py [IMPLEMENTED]**
1. WHAT: Generates 7/14-day lags and rolling averages.
2. WHY: ML models need historical context to predict time-series trends.
3. HOW: Uses pandas `.shift()` and `.rolling().mean()`.
4. WHAT NEXT: Passes augmented data to `forecasting.py`.

**forecasting.py [IMPLEMENTED]**
1. WHAT: Predicts daily demand for the next 14 days.
2. WHY: To identify stock-outs before they happen.
3. HOW: Trains XGBoost/RF, prevents leakage via chronological split, selects champion by MAE, and extracts SHAP values.
4. WHAT NEXT: Passes the forecasted demand to `decision_engine.py`.

**decision_engine.py [IMPLEMENTED]**
1. WHAT: Calculates usable inventory and evaluates 4 fulfillment options.
2. WHY: Forecasting alone doesn't tell a planner how to fix the problem.
3. HOW: Checks physical stock vs safety stock. Uses FEFO logic to check if batches at other DCs are viable for transfer.
4. WHAT NEXT: Sends the viable options to `scoring.py`.

**scoring.py [IMPLEMENTED]**
1. WHAT: Ranks the fulfillment options.
2. WHY: To determine the mathematically optimal choice.
3. HOW: Normalizes Cost, Lead Time, and Expiry Risk to a 0-1 scale and applies weighted math.
4. WHAT NEXT: Sends the top ML choice to `dacdf.py`.

**dacdf.py [IMPLEMENTED]**
1. WHAT: Validates the ML recommendation against business rules.
2. WHY: ML is probabilistic and might recommend a cheap, slow supplier for a critical drug that runs out tomorrow.
3. HOW: Applies `IF-THEN` overrides (e.g., IF Critical AND Days of Stock < 2 THEN force Local Supplier).
4. WHAT NEXT: Sends the final approved action to `escalation.py`.

**frequency.py [IMPLEMENTED]**
1. WHAT: Calculates how much to order (EOQ).
2. WHY: Recommending a supplier isn't enough; the system must provide exact unit quantities.
3. HOW: Uses standard EOQ formulas modified by historical distributor fill rates.
4. WHAT NEXT: Appends quantity to the final action.

**escalation.py [IMPLEMENTED]**
1. WHAT: Assigns a human owner and urgency tier to the risk.
2. WHY: Ensures critical issues aren't ignored in a sea of data.
3. HOW: Checks the `health_flag` and `criticality`. Red + High = Tier 3.
4. WHAT NEXT: Data is passed to `precompute.py`.

**precompute.py [IMPLEMENTED]**
1. WHAT: Orchestrates the pipeline and caches the output.
2. WHY: Prevents the backend from running a 60-second calculation on every page refresh.
3. HOW: Calls all engine modules, formats a master dictionary, sanitizes NaNs, and runs `json.dump()`.
4. WHAT NEXT: The FastApi routes in `api/routers/` serve this JSON to the Next.js frontend.
