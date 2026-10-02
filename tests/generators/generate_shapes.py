"""Generators for the three small Story-Shape fixtures (Trend, Relationship, Star-Schema)."""

from pathlib import Path
import numpy as np
import pandas as pd


def generate_all_shape_fixtures(base_dir: Path) -> dict:
    """Generate shape fixtures and return dict of paths."""
    base_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    # 1. fixture_trend.csv: Date + single metric, no useful categorical dimensions
    p_trend = base_dir / "fixture_trend.csv"
    dates = pd.date_range("2023-01-01", "2024-06-30", freq="MS")
    # Trend with seasonality
    t = np.arange(len(dates))
    values = 1000 + 35 * t + 120 * np.sin(2 * np.pi * t / 12) + np.random.default_rng(42).normal(0, 20, len(t))
    pd.DataFrame({
        "month_start": [d.strftime("%Y-%m-%d") for d in dates],
        "active_users": np.round(values).astype(int),
    }).to_csv(p_trend, index=False)
    paths["trend"] = p_trend

    # 2. fixture_relationship.csv: 8 numeric columns, no clear date or north star
    p_rel = base_dir / "fixture_relationship.csv"
    rng = np.random.default_rng(42)
    n = 150
    # Correlation cluster: X1 and X2 correlated, X3 independent, X4 negative to X1
    x1 = rng.normal(50, 10, n)
    x2 = 2.5 * x1 + rng.normal(0, 5, n)
    x3 = rng.uniform(10, 100, n)
    x4 = -1.8 * x1 + rng.normal(0, 4, n)
    x5 = rng.exponential(15, n)
    x6 = rng.normal(0, 1, n)
    x7 = rng.poisson(8, n)
    x8 = rng.uniform(0, 1, n)
    pd.DataFrame({
        "metric_a": np.round(x1, 2),
        "metric_b": np.round(x2, 2),
        "metric_c": np.round(x3, 2),
        "metric_d": np.round(x4, 2),
        "metric_e": np.round(x5, 2),
        "metric_f": np.round(x6, 3),
        "metric_g": x7,
        "metric_h": np.round(x8, 4),
    }).to_csv(p_rel, index=False)
    paths["relationship"] = p_rel

    # 3. fixture_starschema/: fact_orders.csv, dim_customers.csv, dim_products.csv
    star_dir = base_dir / "fixture_starschema"
    star_dir.mkdir(parents=True, exist_ok=True)

    # dim_customers
    p_cust = star_dir / "dim_customers.csv"
    pd.DataFrame({
        "customer_key": [101, 102, 103, 104, 105],
        "customer_name": ["Acme Corp", "Globex", "Initech", "Umbrella", "Soylent"],
        "segment": ["Enterprise", "Mid-Market", "SMB", "Enterprise", "Mid-Market"],
        "country": ["USA", "Germany", "USA", "UK", "Canada"],
    }).to_csv(p_cust, index=False)

    # dim_products
    p_prod = star_dir / "dim_products.csv"
    pd.DataFrame({
        "product_key": [201, 202, 203],
        "product_name": ["Cloud Server", "Database Pro", "Security Suite"],
        "category": ["Infrastructure", "Data", "Security"],
        "unit_cost": [150.0, 80.0, 120.0],
    }).to_csv(p_prod, index=False)

    # fact_orders
    p_orders = star_dir / "fact_orders.csv"
    pd.DataFrame({
        "order_id": [1001, 1002, 1003, 1004, 1005, 1006],
        "order_date": ["2024-01-10", "2024-01-15", "2024-02-01", "2024-02-18", "2024-03-05", "2024-03-22"],
        "customer_key": [101, 102, 101, 103, 104, 105],
        "product_key": [201, 202, 203, 201, 202, 203],
        "revenue": [5000.0, 1200.0, 3400.0, 4800.0, 1500.0, 3600.0],
        "quantity": [5, 2, 4, 5, 2, 4],
    }).to_csv(p_orders, index=False)

    paths["starschema_fact"] = p_orders
    paths["starschema_dim_cust"] = p_cust
    paths["starschema_dim_prod"] = p_prod

    return paths
