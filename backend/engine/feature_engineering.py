"""
feature_engineering.py — Build ML-ready feature matrix from demand history.
All features derived strictly from real columns in daily_demand_inventory.csv
plus SKU/DC identity encodings from master tables.
"""
import pandas as pd
import numpy as np
from pathlib import Path

DATA_DIR = Path(__file__).parent.parent.parent / "data"

FEATURE_COLS = [
    "day_of_week", "month", "week_of_year", "days_since_start",
    "flu_season_index", "promo_flag",
    "demand_lag_1", "demand_lag_7", "demand_lag_14",
    "demand_7d_avg", "demand_14d_avg", "demand_28d_avg",
    "demand_7d_std", "flu_x_lag7", "promo_x_lag7",
    "sku_enc", "dc_enc", "category_enc", "region_enc",
]

TARGET_COL = "demand_units"

FLU_INDEX_BY_MONTH = {
    1: 0.85, 2: 0.60, 3: 0.30, 4: 0.20, 5: 0.20,
    6: 0.40, 7: 0.80, 8: 0.90, 9: 0.55, 10: 0.50,
    11: 0.70, 12: 0.85,
}


def flu_index_for_month(month: int) -> float:
    return FLU_INDEX_BY_MONTH.get(int(month), 0.3)


def _load_masters():
    sku_df = pd.read_csv(DATA_DIR / "sku_master.csv")
    dc_df = pd.read_csv(DATA_DIR / "dc_master.csv")
    return sku_df, dc_df


def _identity_maps(sku_df: pd.DataFrame, dc_df: pd.DataFrame) -> dict:
    return {
        "sku": {k: i for i, k in enumerate(sorted(sku_df["sku_id"].unique()))},
        "dc": {k: i for i, k in enumerate(sorted(dc_df["dc_id"].unique()))},
        "category": {k: i for i, k in enumerate(sorted(sku_df["category"].dropna().unique()))},
        "region": {k: i for i, k in enumerate(sorted(dc_df["region"].dropna().unique()))},
        "sku_category": sku_df.set_index("sku_id")["category"].to_dict(),
        "dc_region": dc_df.set_index("dc_id")["region"].to_dict(),
    }


def _attach_identity_encodings(df: pd.DataFrame, maps: dict) -> pd.DataFrame:
    df = df.copy()
    df["sku_enc"] = df["sku_id"].map(maps["sku"]).fillna(-1).astype(int)
    df["dc_enc"] = df["dc_id"].map(maps["dc"]).fillna(-1).astype(int)
    categories = df["sku_id"].map(maps["sku_category"])
    regions = df["dc_id"].map(maps["dc_region"])
    df["category_enc"] = categories.map(maps["category"]).fillna(-1).astype(int)
    df["region_enc"] = regions.map(maps["region"]).fillna(-1).astype(int)
    return df


def add_features(df: pd.DataFrame, sku_df: pd.DataFrame | None = None,
                 dc_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """
    Input: demand DataFrame sorted by (dc_id, sku_id, date).
    Output: same DataFrame with feature columns added.
    """
    if sku_df is None or dc_df is None:
        sku_df, dc_df = _load_masters()
    maps = _identity_maps(sku_df, dc_df)

    df = df.copy().sort_values(["dc_id", "sku_id", "date"])
    df["date"] = pd.to_datetime(df["date"])
    dataset_start = df["date"].min()

    # Time features
    df["day_of_week"] = df["date"].dt.dayofweek          # 0=Mon
    df["month"] = df["date"].dt.month
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["days_since_start"] = (df["date"] - dataset_start).dt.days

    # Lag features (per dc x sku group)
    grp = df.groupby(["dc_id", "sku_id"])["demand_units"]
    df["demand_lag_1"] = grp.shift(1)
    df["demand_lag_7"] = grp.shift(7)
    df["demand_lag_14"] = grp.shift(14)

    # Rolling averages
    def rolling_mean(x, w):
        return x.shift(1).rolling(w, min_periods=1).mean()

    def rolling_std(x, w):
        return x.shift(1).rolling(w, min_periods=1).std().fillna(0)

    grp2 = df.groupby(["dc_id", "sku_id"])["demand_units"]
    df["demand_7d_avg"] = grp2.transform(lambda x: rolling_mean(x, 7))
    df["demand_14d_avg"] = grp2.transform(lambda x: rolling_mean(x, 14))
    df["demand_28d_avg"] = grp2.transform(lambda x: rolling_mean(x, 28))
    df["demand_7d_std"] = grp2.transform(lambda x: rolling_std(x, 7))

    # Interaction terms
    df["flu_x_lag7"] = df["flu_season_index"] * df["demand_lag_7"].fillna(0)
    df["promo_x_lag7"] = df["promo_flag"] * df["demand_lag_7"].fillna(0)

    # Fill remaining NaNs from lags at start of series (use group median, fallback to 0)
    for col in ["demand_lag_1", "demand_lag_7", "demand_lag_14"]:
        global_median = df["demand_units"].median()
        df[col] = df[col].fillna(global_median).fillna(0)

    # Fill any NaN in demand_units itself (290 rows from outlier removal)
    grp_med = df.groupby(["dc_id", "sku_id"])["demand_units"].transform("median")
    df["demand_units"] = df["demand_units"].fillna(grp_med).fillna(0)

    df = _attach_identity_encodings(df, maps)
    return df


def build_recursive_feature_row(
    history: list[float],
    next_date: pd.Timestamp,
    dataset_start: pd.Timestamp,
    promo_flag: int,
    identity: dict,
    lag_fill: float,
) -> dict:
    """
    Build one feature row for recursive multi-step forecasting.
    `history` contains observed and previously predicted demand up to the day before next_date.
    """
    hist = [float(x) for x in history]
    lag1 = hist[-1] if len(hist) >= 1 else lag_fill
    lag7 = hist[-7] if len(hist) >= 7 else lag_fill
    lag14 = hist[-14] if len(hist) >= 14 else lag_fill

    tail7 = hist[-7:] if hist else [lag_fill]
    tail14 = hist[-14:] if hist else [lag_fill]
    tail28 = hist[-28:] if hist else [lag_fill]

    month = int(next_date.month)
    flu = flu_index_for_month(month)

    return {
        "day_of_week": int(next_date.dayofweek),
        "month": month,
        "week_of_year": int(next_date.isocalendar().week),
        "days_since_start": int((next_date - dataset_start).days),
        "flu_season_index": flu,
        "promo_flag": int(promo_flag),
        "demand_lag_1": lag1,
        "demand_lag_7": lag7,
        "demand_lag_14": lag14,
        "demand_7d_avg": float(np.mean(tail7)),
        "demand_14d_avg": float(np.mean(tail14)),
        "demand_28d_avg": float(np.mean(tail28)),
        "demand_7d_std": float(np.std(tail7)) if len(tail7) > 1 else 0.0,
        "flu_x_lag7": flu * lag7,
        "promo_x_lag7": int(promo_flag) * lag7,
        "sku_enc": identity["sku_enc"],
        "dc_enc": identity["dc_enc"],
        "category_enc": identity["category_enc"],
        "region_enc": identity["region_enc"],
    }


def get_train_test(df: pd.DataFrame, test_days: int = 21):
    """
    Time-series aware split: last `test_days` calendar days = test holdout.
    Returns (X_train, X_test, y_train, y_test, test_df).
    """
    sku_df, dc_df = _load_masters()
    df = add_features(df, sku_df=sku_df, dc_df=dc_df)
    # Drop rows where key features OR target are NaN
    df = df.dropna(subset=FEATURE_COLS + [TARGET_COL])
    # Extra safety: clip infinite values
    for col in FEATURE_COLS:
        df[col] = df[col].replace([np.inf, -np.inf], 0)

    max_date = df["date"].max()
    cutoff = max_date - pd.Timedelta(days=test_days)

    train = df[df["date"] <= cutoff]
    test = df[df["date"] > cutoff]

    X_train = train[FEATURE_COLS].values
    y_train = train[TARGET_COL].values
    X_test = test[FEATURE_COLS].values
    y_test = test[TARGET_COL].values

    return X_train, X_test, y_train, y_test, test


def classify_trend(df: pd.DataFrame, dc_id: str, sku_id: str) -> str:
    """
    Classify demand trend for a SKU at a DC.
    Uses 14d vs 28d rolling avg ratio on last available date.
    """
    sub = df[(df["dc_id"] == dc_id) & (df["sku_id"] == sku_id)].sort_values("date")
    if len(sub) < 14:
        return "insufficient_data"

    recent_14 = sub["demand_units"].tail(14).mean()
    recent_28 = sub["demand_units"].tail(28).mean()
    flu_active = sub.iloc[-1]["flu_season_index"] == 1

    if recent_28 == 0:
        return "stable"

    ratio = recent_14 / recent_28

    if ratio > 1.40:
        return "surge"
    elif ratio > 1.15 and flu_active:
        return "seasonal"
    elif ratio > 1.15:
        return "rising"
    elif ratio < 0.85:
        return "falling"
    else:
        return "stable"
