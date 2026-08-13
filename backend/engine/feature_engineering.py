"""
feature_engineering.py — Build ML-ready feature matrix from demand history.
All features derived strictly from real columns in daily_demand_inventory.csv.
"""
import pandas as pd
import numpy as np


FEATURE_COLS = [
    "day_of_week", "month", "week_of_year", "days_since_start",
    "flu_season_index", "promo_flag",
    "demand_lag_1", "demand_lag_7", "demand_lag_14",
    "demand_7d_avg", "demand_14d_avg", "demand_28d_avg",
    "demand_7d_std", "flu_x_lag7", "promo_x_lag7",
]

TARGET_COL = "demand_units"


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Input: demand DataFrame sorted by (dc_id, sku_id, date).
    Output: same DataFrame with feature columns added.
    """
    df = df.copy().sort_values(["dc_id", "sku_id", "date"])

    # Time features
    df["day_of_week"] = df["date"].dt.dayofweek          # 0=Mon
    df["month"] = df["date"].dt.month
    df["week_of_year"] = df["date"].dt.isocalendar().week.astype(int)
    df["days_since_start"] = (df["date"] - df["date"].min()).dt.days

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

    # Fill remaining NaNs from lags at start of series
    for col in ["demand_lag_1", "demand_lag_7", "demand_lag_14"]:
        df[col] = df[col].fillna(df["demand_units"].mean())

    return df


def get_train_test(df: pd.DataFrame, test_days: int = 21):
    """
    Time-series aware split: last `test_days` days per group = test.
    Returns (X_train, X_test, y_train, y_test, test_df).
    """
    df = add_features(df)
    df = df.dropna(subset=FEATURE_COLS)

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
