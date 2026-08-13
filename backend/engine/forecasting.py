"""
forecasting.py — Train XGBoost, RandomForest, and rolling-avg baseline.
Compare on MAE, MAPE, RMSE. Generate SHAP feature importances.
Produce demand-during-lead-time forecast for replenishment planning.
"""
import numpy as np
import pandas as pd
import pickle
import warnings
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from xgboost import XGBRegressor

from .feature_engineering import (
    add_features, get_train_test, FEATURE_COLS, classify_trend
)

warnings.filterwarnings("ignore")

MODELS_DIR = Path(__file__).parent.parent / "models"
MODELS_DIR.mkdir(exist_ok=True)

HORIZON_DAYS = 14   # replenishment planning horizon


# ── Metric helpers ──────────────────────────────────────────────────────────

def mae(y_true, y_pred):
    """
    Mean Absolute Error — average absolute daily error in units.
    Business meaning: on average, the forecast is off by X units per day.
    """
    return float(mean_absolute_error(y_true, y_pred))


def rmse(y_true, y_pred):
    """
    Root Mean Squared Error — penalises large forecast errors more.
    Business meaning: useful for catching dangerous demand spikes/drops.
    """
    return float(np.sqrt(mean_squared_error(y_true, y_pred)))


def mape(y_true, y_pred, eps=1e-6):
    """
    Mean Absolute Percentage Error — scale-free accuracy metric.
    Business meaning: e.g. MAPE=12% means forecast is 12% off on average.
    NOTE: Days with actual demand < 5 units are excluded (near-zero denominator
    would inflate the metric unrealistically).
    """
    y_true = np.array(y_true, dtype=float)
    y_pred = np.array(y_pred, dtype=float)
    # Mask out near-zero actuals to avoid inflated MAPE
    mask = y_true >= 5
    if mask.sum() == 0:
        return float(np.mean(np.abs(y_true - y_pred)))  # fallback to MAE-style
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / (y_true[mask] + eps))) * 100)



# ── Baseline: rolling 14-day average ────────────────────────────────────────

def baseline_predict(df: pd.DataFrame, dc_id: str, sku_id: str,
                     test_days: int = 21) -> dict:
    sub = df[(df["dc_id"] == dc_id) & (df["sku_id"] == sku_id)].sort_values("date")
    if len(sub) < test_days + 14:
        return {"mae": None, "rmse": None, "mape": None, "model": "baseline"}

    y_true = sub["demand_units"].values[-test_days:]
    # Predict each test-day as the rolling 14d avg up to that point
    preds = []
    for i in range(test_days):
        lookback = sub["demand_units"].values[-(test_days + 14 - i): -(test_days - i)]
        preds.append(np.mean(lookback))
    y_pred = np.array(preds)
    return {
        "mae": mae(y_true, y_pred),
        "rmse": rmse(y_true, y_pred),
        "mape": mape(y_true, y_pred),
        "model": "baseline",
        "y_pred": y_pred.tolist(),
        "y_true": y_true.tolist(),
    }


# ── ML model training ────────────────────────────────────────────────────────

def train_models(df: pd.DataFrame) -> dict:
    """
    Train XGBoost and RF on all SKU x DC combos (pooled).
    Returns dict with models and global metrics.
    """
    X_train, X_test, y_train, y_test, test_df = get_train_test(df)

    # Random Forest
    rf = RandomForestRegressor(
        n_estimators=200, max_depth=8, min_samples_leaf=3,
        random_state=42, n_jobs=-1
    )
    rf.fit(X_train, y_train)
    rf_pred = rf.predict(X_test)
    rf_metrics = {
        "mae": mae(y_test, rf_pred),
        "rmse": rmse(y_test, rf_pred),
        "mape": mape(y_test, rf_pred),
    }

    # XGBoost
    xgb = XGBRegressor(
        n_estimators=300, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8,
        random_state=42, n_jobs=-1, verbosity=0,
        early_stopping_rounds=None
    )
    xgb.fit(X_train, y_train)
    xgb_pred = xgb.predict(X_test)
    xgb_metrics = {
        "mae": mae(y_test, xgb_pred),
        "rmse": rmse(y_test, xgb_pred),
        "mape": mape(y_test, xgb_pred),
    }

    # Pick winner: lower MAE
    winner = "xgboost" if xgb_metrics["mae"] <= rf_metrics["mae"] else "random_forest"
    best_model = xgb if winner == "xgboost" else rf

    # Save models
    with open(MODELS_DIR / "xgb_model.pkl", "wb") as f:
        pickle.dump(xgb, f)
    with open(MODELS_DIR / "rf_model.pkl", "wb") as f:
        pickle.dump(rf, f)

    return {
        "random_forest": rf_metrics,
        "xgboost": xgb_metrics,
        "winner": winner,
        "best_model": best_model,
        "xgb": xgb,
        "rf": rf,
        "X_test": X_test,
        "y_test": y_test.tolist(),
        "test_df": test_df,
        "feature_cols": FEATURE_COLS,
    }


def load_models():
    """Load saved models from disk."""
    with open(MODELS_DIR / "xgb_model.pkl", "rb") as f:
        xgb = pickle.load(f)
    with open(MODELS_DIR / "rf_model.pkl", "rb") as f:
        rf = pickle.load(f)
    return xgb, rf


# ── SHAP explainability ──────────────────────────────────────────────────────

def get_shap_top_drivers(xgb_model, X_sample: np.ndarray,
                          feature_names: list, top_n: int = 5) -> list:
    """
    Return top N SHAP feature importances for a single prediction.
    """
    try:
        import shap
        explainer = shap.TreeExplainer(xgb_model)
        shap_vals = explainer.shap_values(X_sample)
        if X_sample.ndim == 1:
            shap_vals = shap_vals.reshape(1, -1)
        mean_abs = np.abs(shap_vals).mean(axis=0)
        order = np.argsort(mean_abs)[::-1][:top_n]
        return [
            {"feature": feature_names[i], "importance": float(mean_abs[i])}
            for i in order
        ]
    except Exception as e:
        return [{"feature": fn, "importance": 0.0} for fn in feature_names[:top_n]]


# ── Per-SKU per-DC forecast ──────────────────────────────────────────────────

def forecast_sku_dc(df: pd.DataFrame, dc_id: str, sku_id: str,
                    xgb_model=None, horizon: int = HORIZON_DAYS) -> dict:
    """
    Produce a rolling horizon forecast for one dc x sku.
    Returns historical + predicted demand, metrics, SHAP, trend, and
    demand_during_lead_time per supplier type.
    """
    sub = df[(df["dc_id"] == dc_id) & (df["sku_id"] == sku_id)].sort_values("date").copy()
    if len(sub) < 28:
        avg = sub["demand_units"].mean()
        return {
            "dc_id": dc_id, "sku_id": sku_id,
            "forecast_next_14d": [avg] * horizon,
            "demand_during_lead_time_regular": avg * 7,
            "demand_during_lead_time_local": avg * 2,
            "demand_during_lead_time_transfer": avg * 3,
            "mae": None, "rmse": None, "mape": None,
            "winner": "baseline",
            "trend": "stable",
            "shap_drivers": [],
            "historical": sub[["date", "demand_units"]].rename(
                columns={"demand_units": "actual"}).to_dict("records"),
        }

    # Baseline metrics
    bl = baseline_predict(df, dc_id, sku_id)
    bl_mae = bl.get("mae") or 999

    # XGBoost forecast
    feat_df = add_features(sub)
    feat_df = feat_df.dropna(subset=FEATURE_COLS)
    if len(feat_df) < 14:
        avg = sub["demand_units"].mean()
        return {
            "dc_id": dc_id, "sku_id": sku_id,
            "forecast_next_14d": [round(avg)] * horizon,
            "demand_during_lead_time_regular": round(avg * 7),
            "demand_during_lead_time_local": round(avg * 2),
            "demand_during_lead_time_transfer": round(avg * 3),
            "mae": bl_mae, "rmse": bl.get("rmse"), "mape": bl.get("mape"),
            "winner": "baseline", "trend": classify_trend(df, dc_id, sku_id),
            "shap_drivers": [], "historical": [],
        }

    # Train/test split
    test_days = min(21, len(feat_df) // 4)
    cutoff = feat_df["date"].max() - pd.Timedelta(days=test_days)
    train_f = feat_df[feat_df["date"] <= cutoff]
    test_f = feat_df[feat_df["date"] > cutoff]

    if len(train_f) < 10 or len(test_f) < 5:
        avg = sub["demand_units"].mean()
        pred_list = [round(avg)] * horizon
    else:
        if xgb_model is None:
            try:
                xgb_model, _ = load_models()
            except Exception:
                xgb_model = XGBRegressor(
                    n_estimators=200, max_depth=5, learning_rate=0.05,
                    random_state=42, verbosity=0
                )
                xgb_model.fit(train_f[FEATURE_COLS].values, train_f["demand_units"].values)

        xgb_test_pred = xgb_model.predict(test_f[FEATURE_COLS].values)
        xgb_test_pred = np.clip(xgb_test_pred, 0, None)
        xgb_mae = mae(test_f["demand_units"].values, xgb_test_pred)
        xgb_rmse = rmse(test_f["demand_units"].values, xgb_test_pred)
        xgb_mape = mape(test_f["demand_units"].values, xgb_test_pred)

        # Pick winner vs baseline
        winner = "xgboost" if xgb_mae < bl_mae else "baseline"

        # Next 14-day forecast using last known row as seed
        last_row = feat_df.iloc[-1].copy()
        pred_list = []
        for _ in range(horizon):
            x = last_row[FEATURE_COLS].values.reshape(1, -1)
            p = max(0, float(xgb_model.predict(x)[0]))
            pred_list.append(round(p))

        # SHAP on last 5 test rows
        shap_drivers = get_shap_top_drivers(
            xgb_model,
            test_f[FEATURE_COLS].values[-5:],
            FEATURE_COLS,
        )

        # Historical + predicted for chart
        hist_actual = sub[["date", "demand_units"]].copy()
        hist_actual["date"] = hist_actual["date"].dt.strftime("%Y-%m-%d")
        hist_actual = hist_actual.rename(columns={"demand_units": "actual"})

        test_f_copy = test_f[["date", "demand_units"]].copy()
        test_f_copy["predicted"] = xgb_test_pred.round().astype(int)
        test_f_copy["date"] = test_f_copy["date"].dt.strftime("%Y-%m-%d")

        # Merge historical and predicted
        chart_data = hist_actual.merge(
            test_f_copy[["date", "predicted"]], on="date", how="left"
        )

        # Future dates
        last_date = sub["date"].max()
        future_dates = [
            (last_date + pd.Timedelta(days=i+1)).strftime("%Y-%m-%d")
            for i in range(horizon)
        ]
        future_df = pd.DataFrame({
            "date": future_dates,
            "actual": [None] * horizon,
            "predicted": pred_list,
        })
        chart_data = pd.concat([chart_data, future_df], ignore_index=True)

        return {
            "dc_id": dc_id,
            "sku_id": sku_id,
            "forecast_next_14d": pred_list,
            "demand_during_lead_time_regular": round(sum(pred_list[:7])),
            "demand_during_lead_time_local": round(sum(pred_list[:2])),
            "demand_during_lead_time_transfer": round(sum(pred_list[:3])),
            "mae": round(xgb_mae, 2),
            "rmse": round(xgb_rmse, 2),
            "mape": round(xgb_mape, 2),
            "baseline_mae": round(bl_mae, 2),
            "winner": winner,
            "trend": classify_trend(df, dc_id, sku_id),
            "shap_drivers": shap_drivers,
            "chart_data": chart_data.to_dict("records"),
        }

    return {
        "dc_id": dc_id, "sku_id": sku_id,
        "forecast_next_14d": pred_list,
        "demand_during_lead_time_regular": round(sum(pred_list[:7])),
        "demand_during_lead_time_local": round(sum(pred_list[:2])),
        "demand_during_lead_time_transfer": round(sum(pred_list[:3])),
        "mae": None, "rmse": None, "mape": None,
        "winner": "baseline",
        "trend": classify_trend(df, dc_id, sku_id),
        "shap_drivers": [],
        "chart_data": [],
    }
