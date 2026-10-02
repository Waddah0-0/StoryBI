"""Generator for the three Golden Datasets with planted truths using fixed random seeds."""

import os
from pathlib import Path
import numpy as np
import pandas as pd


def generate_golden_ecommerce(output_path: Path, seed: int = 42) -> Path:
    """Golden 1: E-commerce Performance.

    Planted truths:
    1. Technology revenue grows by ~+20% between Q1 and Q3.
    2. Furniture revenue declines by ~-15% between Q1 and Q3.
    3. Planted Q3 anomaly: West region sales spike sharply (3x normal) in late August.
    4. Planted 80/20 Pareto distribution: top ~20% of customers generate ~80% of revenue.
    5. Incomplete last month: October 2024 only has 10 days of records (partial month).
    """
    rng = np.random.default_rng(seed)
    n_rows = 2400

    # Date range: 2024-01-01 through 2024-10-10 (October has only 10 days)
    start_date = pd.Timestamp("2024-01-01")
    full_dates = pd.date_range("2024-01-01", "2024-09-30", freq="D")
    oct_dates = pd.date_range("2024-10-01", "2024-10-10", freq="D")
    
    # 2200 rows spread across Jan-Sep, 200 rows across Oct 1-10
    dates_jan_sep = rng.choice(full_dates, size=2200)
    dates_oct = rng.choice(oct_dates, size=200)
    order_dates = np.concatenate([dates_jan_sep, dates_oct])
    rng.shuffle(order_dates)

    # Customers with Pareto distribution (power law weights)
    n_customers = 200
    customer_ids = [f"CUST-{i:04d}" for i in range(1, n_customers + 1)]
    # Pareto power-law alpha ~ 1.15 produces ~80% share for top 20%
    customer_weights = 1.0 / (np.arange(1, n_customers + 1) ** 1.18)
    customer_weights /= customer_weights.sum()
    assigned_customers = rng.choice(customer_ids, size=n_rows, p=customer_weights)

    categories = ["Technology", "Furniture", "Office Supplies"]
    regions = ["North", "South", "East", "West"]

    records = []
    for i in range(n_rows):
        od = pd.Timestamp(order_dates[i])
        cat = rng.choice(categories, p=[0.4, 0.35, 0.25])
        region = rng.choice(regions)

        # Baseline base price
        if cat == "Technology":
            # Growth over year: Q1 base 200 -> Q3 base 245 (+22%)
            quarter = od.quarter
            growth_factor = 1.0 + (quarter - 1) * 0.10
            sales = rng.normal(200 * growth_factor, 25)
        elif cat == "Furniture":
            # Decline over year: Q1 base 180 -> Q3 base 150 (-17%)
            quarter = od.quarter
            decline_factor = 1.0 - (quarter - 1) * 0.08
            sales = rng.normal(180 * decline_factor, 20)
        else:
            sales = rng.normal(80, 15)

        # Planted anomaly: West region in late August 2024 (2024-08-20 to 2024-08-28)
        if region == "West" and pd.Timestamp("2024-08-20") <= od <= pd.Timestamp("2024-08-28"):
            sales *= 3.8

        quantity = int(rng.integers(1, 6))
        profit = round(sales * rng.uniform(0.12, 0.28), 2)
        sales = round(max(10.0, sales), 2)

        records.append({
            "order_id": f"ORD-{i+1:05d}",
            "order_date": od.strftime("%Y-%m-%d"),
            "customer_id": assigned_customers[i],
            "category": cat,
            "region": region,
            "sales": sales,
            "quantity": quantity,
            "profit": profit,
        })

    df = pd.DataFrame(records).sort_values("order_date").reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path


def generate_golden_saas(output_path: Path, seed: int = 42) -> Path:
    """Golden 2: SaaS Retention & Simpson's Paradox.

    Planted truths:
    1. Strong negative correlation between discount_rate and retention_months (r < -0.6).
    2. Non-relationship between company_size (headcount) and churn_rate (|r| < 0.10, p > 0.05).
    3. Simpson's paradox: Churn drops within every tier (Small, Medium, Enterprise) over the 2 cohorts,
       but overall aggregate churn increases due to composition shift toward Small clients.
    """
    rng = np.random.default_rng(seed)
    n_accounts = 2400

    records = []
    # Two cohorts: Cohort 2023 vs Cohort 2024
    for i in range(n_accounts):
        account_id = f"ACC-{i+1:05d}"
        cohort = rng.choice(["2023", "2024"])

        # In 2023: 15% Small, 35% Medium, 50% Enterprise
        # In 2024: 65% Small, 20% Medium, 15% Enterprise (composition shift!)
        if cohort == "2023":
            tier = rng.choice(["Small", "Medium", "Enterprise"], p=[0.15, 0.35, 0.50])
        else:
            tier = rng.choice(["Small", "Medium", "Enterprise"], p=[0.65, 0.20, 0.15])

        # Headcount is independent of churn (non-relationship)
        company_size = int(rng.exponential(scale=150) + 10)

        # Discount rate (0.0 to 0.40)
        discount_rate = round(float(rng.uniform(0.0, 0.40)), 3)

        # Retention months negatively correlated with discount rate
        retention_months = round(max(1.0, 36.0 - (discount_rate * 45.0) + rng.normal(0, 3)), 1)

        # Churn probability inside tiers drops from 2023 to 2024:
        # Small: 2023 -> 25%, 2024 -> 18% (drops!)
        # Medium: 2023 -> 15%, 2024 -> 9% (drops!)
        # Enterprise: 2023 -> 8%, 2024 -> 3% (drops!)
        if tier == "Small":
            base_p = 0.25 if cohort == "2023" else 0.18
            mrr = round(float(rng.normal(250, 40)), 2)
        elif tier == "Medium":
            base_p = 0.15 if cohort == "2023" else 0.09
            mrr = round(float(rng.normal(1200, 150)), 2)
        else:
            base_p = 0.08 if cohort == "2023" else 0.03
            mrr = round(float(rng.normal(4500, 500)), 2)

        churned = int(rng.uniform() < base_p)

        records.append({
            "account_id": account_id,
            "cohort": cohort,
            "tier": tier,
            "company_size": company_size,
            "discount_rate": discount_rate,
            "retention_months": retention_months,
            "mrr": mrr,
            "churned": churned,
        })

    df = pd.DataFrame(records)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path


def generate_golden_logistics(output_path: Path, seed: int = 42) -> Path:
    """Golden 3: Operational Logistics & Bottleneck.

    Planted truths:
    1. Carrier 'ApexExpress' has ~3.5x higher defect/damage rate than other carriers.
    2. Seasonal December volume surge (~2.5x normal monthly volume).
    """
    rng = np.random.default_rng(seed)
    n_shipments = 2000

    dates = pd.date_range("2024-01-01", "2024-12-31", freq="D")
    carriers = ["FleetStar", "SwiftCargo", "ApexExpress"]

    records = []
    # Bias dates toward December
    month_weights = np.array([1.0] * 11 + [2.8])
    month_weights /= month_weights.sum()

    for i in range(n_shipments):
        shipment_id = f"SHP-{i+1:05d}"
        chosen_month = rng.choice(np.arange(1, 13), p=month_weights)
        month_dates = [d for d in dates if d.month == chosen_month]
        ship_date = rng.choice(month_dates)

        carrier = rng.choice(carriers, p=[0.40, 0.35, 0.25])
        weight_kg = round(float(rng.uniform(1.5, 45.0)), 2)
        freight_cost = round(15.0 + weight_kg * rng.uniform(1.2, 2.5), 2)

        # Defect rate: ApexExpress ~ 16%, others ~ 4% (~4x higher)
        defect_p = 0.16 if carrier == "ApexExpress" else 0.04
        is_damaged = int(rng.uniform() < defect_p)
        transit_days = int(rng.integers(1, 7) + (3 if is_damaged else 0))

        records.append({
            "shipment_id": shipment_id,
            "ship_date": pd.Timestamp(ship_date).strftime("%Y-%m-%d"),
            "carrier": carrier,
            "weight_kg": weight_kg,
            "freight_cost": freight_cost,
            "transit_days": transit_days,
            "is_damaged": is_damaged,
        })

    df = pd.DataFrame(records).sort_values("ship_date").reset_index(drop=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path
