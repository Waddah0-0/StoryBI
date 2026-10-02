"""Semantic Data Profiler Module."""

import re
from typing import Optional, List, Any
import numpy as np
import pandas as pd
from scipy import stats

from storyteller.schemas.profile import (
    SemanticRole,
    AggregationRule,
    ColumnProfile,
    DataProfile,
)

PII_PATTERNS = [
    re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"),  # Email
    re.compile(r"^\d{3}-\d{2}-\d{4}$"),  # US SSN
]

PHONE_PATTERNS = [
    re.compile(r"^\+[1-9]\d{6,14}$"),  # Strict international phone (E.164)
    re.compile(r"^\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}$"),  # Local phone with delimiters
]

PII_NAME_KEYWORDS = ["email", "ssn", "password", "phone", "tax_id", "credit_card", "first_name", "last_name"]


def is_pii_column(col_name: str, sample_series: pd.Series) -> bool:
    """Heuristic PII detection based on name keywords and regex scanning."""
    lower_name = col_name.lower()
    if any(k in lower_name for k in PII_NAME_KEYWORDS):
        return True

    is_numeric = pd.api.types.is_numeric_dtype(sample_series)

    # Test sample values
    non_null_samples = sample_series.dropna().astype(str).head(20)
    for val in non_null_samples:
        val_str = val.strip()
        for pat in PII_PATTERNS:
            if pat.match(val_str):
                return True
        if not is_numeric:
            for pat in PHONE_PATTERNS:
                if pat.match(val_str):
                    return True
    return False


def infer_semantic_role(col_name: str, series: pd.Series) -> tuple[SemanticRole, AggregationRule, float, str]:
    """Infer semantic role and valid aggregation rule for a column."""
    name_lower = col_name.lower().strip()
    n_rows = len(series)
    distinct_count = series.nunique(dropna=True)
    non_null = series.dropna()

    # 1. Identifier checks
    if name_lower.endswith("_id") or name_lower == "id" or name_lower.endswith("_key") or name_lower == "key":
        return SemanticRole.IDENTIFIER, AggregationRule.COUNT_DISTINCT, 0.95, "Matches identifier naming convention"
    if n_rows > 10 and distinct_count == n_rows and (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
        return SemanticRole.IDENTIFIER, AggregationRule.COUNT_DISTINCT, 0.85, "100% unique string column"

    # Postal / zip code check (classify as IDENTIFIER or DIMENSION_CATEGORICAL, not additive metrics)
    postal_keywords = ["zip", "postal", "postcode", "zipcode", "zip_code", "postal_code"]
    if any(k in name_lower for k in postal_keywords):
        if distinct_count == n_rows and n_rows > 0:
            return SemanticRole.IDENTIFIER, AggregationRule.COUNT_DISTINCT, 0.90, "Postal/zip code identifier"
        return SemanticRole.DIMENSION_CATEGORICAL, AggregationRule.NONE, 0.90, "Postal/zip code categorical dimension"

    # 2. Temporal checks
    if pd.api.types.is_datetime64_any_dtype(series):
        return SemanticRole.TEMPORAL, AggregationRule.NONE, 1.0, "Physical datetime dtype"
    date_keywords = ["date", "time", "timestamp", "year", "month", "quarter", "day", "created_at", "updated_at"]
    if any(k in name_lower for k in date_keywords):
        # Sample parsing check
        if len(non_null) > 0:
            sample = non_null.head(10).astype(str)
            try:
                pd.to_datetime(sample, errors="raise", format="mixed")
                return SemanticRole.TEMPORAL, AggregationRule.NONE, 0.95, "Date name and parseable values"
            except Exception:
                pass

    # 3. Numeric checks
    is_numeric = pd.api.types.is_numeric_dtype(series)

    # Check if string column contains formatted percentages or currencies
    if not is_numeric and len(non_null) > 0:
        sample_str = non_null.head(10).astype(str)
        if any("%" in s for s in sample_str):
            return SemanticRole.METRIC_RATIO, AggregationRule.RATIO_OF_SUMS, 0.90, "String containing percentage values"
        if any(any(c in s for c in ["$", "€", "£", "¥"]) for s in sample_str):
            return SemanticRole.METRIC_ADDITIVE, AggregationRule.SUM, 0.90, "String containing currency values"

    if is_numeric:
        ratio_keywords = ["margin", "rate", "pct", "percent", "ratio", "discount", "churn", "share"]
        if any(k in name_lower for k in ratio_keywords):
            return SemanticRole.METRIC_RATIO, AggregationRule.RATIO_OF_SUMS, 0.90, "Ratio metric name"

        non_additive_keywords = ["rating", "unit_price", "score", "temperature", "rank", "average", "avg"]
        if any(k in name_lower for k in non_additive_keywords):
            return SemanticRole.METRIC_NON_ADDITIVE, AggregationRule.AVERAGE, 0.85, "Non-additive metric name"

        semi_additive_keywords = ["headcount", "balance", "inventory"]
        if any(k in name_lower for k in semi_additive_keywords):
            return SemanticRole.METRIC_SEMI_ADDITIVE, AggregationRule.LAST_OVER_TIME, 0.85, "Semi-additive metric name"

        # Check if values are bounded in [0, 1] with ratio semantics
        if distinct_count > 5 and non_null.min() >= 0.0 and non_null.max() <= 1.0:
            if any(k in name_lower for k in ["margin", "rate", "ratio", "p_", "prob"]):
                return SemanticRole.METRIC_RATIO, AggregationRule.RATIO_OF_SUMS, 0.80, "Bounded [0, 1] ratio"

        # Default numeric to additive
        return SemanticRole.METRIC_ADDITIVE, AggregationRule.SUM, 0.85, "Numeric metric (SUM additive)"

    # 4. Free text check
    if (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)) and len(non_null) > 0:
        avg_len = non_null.astype(str).str.len().mean()
        if avg_len > 60 or any(k in name_lower for k in ["comment", "feedback", "notes", "description"]):
            return SemanticRole.TEXT_FREE, AggregationRule.NONE, 0.90, "Long free-form text"

    # 5. Categorical checks
    ordinal_keywords = ["priority", "level", "tier", "grade", "stage"]
    if any(k in name_lower for k in ordinal_keywords):
        return SemanticRole.DIMENSION_ORDINAL, AggregationRule.NONE, 0.85, "Ordinal dimension name"

    return SemanticRole.DIMENSION_CATEGORICAL, AggregationRule.NONE, 0.80, "Categorical dimension"


def profile_dataframe(df: pd.DataFrame, table_name: str = "main") -> DataProfile:
    """Generate a comprehensive semantic DataProfile for a DataFrame."""
    total_rows = len(df)
    total_columns = len(df.columns)
    column_profiles: List[ColumnProfile] = []
    quality_issues: List[str] = []

    # Dataset-level quality checks
    if total_rows > 0:
        try:
            dup_count = int(df.duplicated().sum())
            if dup_count > 0:
                quality_issues.append(f"Dataset contains {dup_count} duplicate rows")
        except TypeError:
            pass

    date_candidates: List[str] = []
    additive_candidates: List[tuple[str, float]] = []  # (name, variance/CV)

    for col in df.columns:
        series = df[col]
        null_count = series.isna().sum()
        null_rate = float(null_count / total_rows) if total_rows > 0 else 0.0
        distinct_count = int(series.nunique(dropna=True))
        non_null = series.dropna()

        # Flag quality issues
        if null_rate == 1.0:
            quality_issues.append(f"Column '{col}' has 100% missing values")
        if distinct_count == 1 and null_count == 0 and total_rows > 1:
            quality_issues.append(f"Column '{col}' has constant value across all rows")

        role, agg_rule, confidence, reasoning = infer_semantic_role(str(col), series)
        is_pii = is_pii_column(str(col), series)

        if role == SemanticRole.IDENTIFIER and distinct_count < len(non_null):
            quality_issues.append(f"Key collision detected in identifier column '{col}': {len(non_null) - distinct_count} duplicate keys")

        if is_pii:
            quality_issues.append(f"Column '{col}' flagged as potential PII")

        # Min, max, mean, std, CV, skew
        min_val = None
        max_val = None
        mean_val = None
        std_val = None
        cv_val = None
        skew_val = None

        if pd.api.types.is_numeric_dtype(series) and len(non_null) > 0:
            try:
                min_val = float(non_null.min())
                max_val = float(non_null.max())
                mean_val = float(non_null.mean())
                std_val = float(non_null.std(ddof=1)) if len(non_null) > 1 else 0.0
                if abs(mean_val) > 1e-9 and std_val is not None:
                    cv_val = float(std_val / abs(mean_val))
                if len(non_null) > 2:
                    skew_val = float(stats.skew(non_null))
            except Exception:
                pass
        elif len(non_null) > 0:
            try:
                min_val = str(non_null.min())
                max_val = str(non_null.max())
            except Exception:
                pass

        # Collect sanitized sample values (exclude PII)
        sample_vals: List[Any] = []
        if not is_pii and len(non_null) > 0:
            sample_vals = non_null.head(5).tolist()

        col_prof = ColumnProfile(
            name=str(col),
            inferred_dtype=str(series.dtype),
            semantic_role=role,
            aggregation_rule=agg_rule,
            null_rate=round(null_rate, 4),
            distinct_count=distinct_count,
            min_value=min_val,
            max_value=max_val,
            mean=mean_val,
            std_dev=std_val,
            coefficient_of_variation=cv_val,
            skew=skew_val,
            sample_values=sample_vals,
            is_pii=is_pii,
            role_confidence=round(confidence, 2),
            role_reasoning=reasoning,
        )
        column_profiles.append(col_prof)

        if role == SemanticRole.TEMPORAL:
            date_candidates.append(str(col))
        elif role == SemanticRole.METRIC_ADDITIVE:
            var_score = cv_val if cv_val is not None else 1.0
            additive_candidates.append((str(col), var_score))

    # Determine primary date column
    primary_date = date_candidates[0] if date_candidates else None

    # Determine suggested north star KPI
    suggested_north_star = None
    if additive_candidates:
        # Prefer names matching common KPI words (revenue, sales, profit, volume)
        kpi_priority = ["revenue", "sales", "net_income", "profit", "amount", "budget", "spend", "cost"]
        matched_priority = None
        for kpi in kpi_priority:
            for name, _ in additive_candidates:
                if kpi in name.lower():
                    matched_priority = name
                    break
            if matched_priority:
                break
        suggested_north_star = matched_priority or additive_candidates[0][0]

    # Inferred grain
    grain = "one row per record"
    id_cols = [c.name for c in column_profiles if c.semantic_role == SemanticRole.IDENTIFIER]
    if id_cols:
        grain = f"one row per {id_cols[0]}"

    return DataProfile(
        table_name=table_name,
        total_rows=total_rows,
        total_columns=total_columns,
        columns=column_profiles,
        primary_date_column=primary_date,
        suggested_north_star=suggested_north_star,
        detected_grain=grain,
        quality_issues=quality_issues,
    )
