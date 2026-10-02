"""Conservative, Reversible Data Cleaner Module with Mathematical Reconciliation."""

import re
from typing import Tuple, List, Dict, Any, Optional
import numpy as np
import pandas as pd

from storyteller.exceptions import UserConfirmationRequired, ReconciliationError
from storyteller.schemas.clean import (
    CleaningAction,
    MetricReconciliation,
    ReconciliationReport,
    CleaningLog,
)
from storyteller.schemas.profile import DataProfile, SemanticRole


def parse_currency_str(val: Any, assume_us_locale: bool = True) -> float:
    """Parse currency string while preserving negative values and handling locales."""
    if pd.isna(val):
        return np.nan
    if isinstance(val, (int, float, np.integer, np.floating)):
        return float(val)
    s = str(val).strip()
    if not s or s.lower() in ["-", "n/a", "null", "none", "nan"]:
        return np.nan

    # Detect negation if "-" in s or ("(" in s and ")" in s), handling cases like "$-100" and "$(100)"
    is_negative = False
    if "-" in s or ("(" in s and ")" in s):
        is_negative = True

    # Remove currency symbols and letters
    clean = re.sub(r"[^\d.,]", "", s)
    if not clean:
        return np.nan

    # Check separators
    if "," in clean and "." in clean:
        # Both present: determine which is decimal by last position
        if clean.rfind(",") > clean.rfind("."):
            # European: 3.400,00 or 1.000.000,50 -> remove dot, replace comma with dot
            clean = clean.replace(".", "").replace(",", ".")
        else:
            # US: 1,240.50 or 1,000,000.50 -> remove comma
            clean = clean.replace(",", "")
    elif "," in clean:
        parts = clean.split(",")
        if clean.count(",") > 1:
            # Multiple commas (e.g. 1,000,000)
            clean = clean.replace(",", "")
        elif len(parts) == 2 and len(parts[1]) != 3:
            # European decimal with non-3 decimal digits: 1200,5 or 1200,50
            clean = clean.replace(",", ".")
        elif assume_us_locale:
            # Likely thousands separator: 1,234
            clean = clean.replace(",", "")
        else:
            clean = clean.replace(",", ".")
    elif "." in clean:
        parts = clean.split(".")
        if clean.count(".") > 1:
            # Multiple dots in European numbers: 1.000.000 -> remove dot
            clean = clean.replace(".", "")
        elif len(parts) == 2 and len(parts[1]) == 3 and not assume_us_locale:
            # European thousands: 1.234
            clean = clean.replace(".", "")
        else:
            # Standard decimal: 1.234 or 12.50
            pass

    try:
        f = float(clean)
        return -f if is_negative else f
    except ValueError:
        return np.nan


def parse_percentage_str(val: Any, assume_ratio: bool = True) -> float:
    """Parse percentage string (e.g. '12.5%' -> 0.125, '0.125' -> 0.125)."""
    if pd.isna(val):
        return np.nan
    s = str(val).strip()
    if not s or s in ["-", "N/A", "null", "None"]:
        return np.nan

    if "%" in s:
        clean = s.replace("%", "").strip()
        try:
            return float(clean) / 100.0
        except ValueError:
            return np.nan
    else:
        try:
            f = float(s)
            # If assume_ratio is True, numbers <= 1.0 are treated as ratio scale (0.125 = 12.5%)
            return f
        except ValueError:
            return np.nan


def clean_dataframe(
    df: pd.DataFrame,
    profile: DataProfile,
    yes: bool = False,
) -> Tuple[pd.DataFrame, CleaningLog]:
    """Clean dataset, verify mathematical reconciliation, and return clean df and CleaningLog."""
    df_clean = df.copy()
    rows_in = len(df_clean)
    header_rows_dropped = 0
    actions: List[CleaningAction] = []
    assumptions: List[str] = []
    table_name = profile.table_name
    col_profile_map = {c.name: c for c in profile.columns}

    # 1. Detect and handle merged header row hierarchy (e.g. Excel title rows)
    if rows_in > 2:
        top_str_ratio = df_clean.iloc[0].apply(lambda x: isinstance(x, str) and not pd.isna(x)).mean()
        # If top row is mostly nulls or single title
        if top_str_ratio < 0.4 and df_clean.iloc[0].isna().sum() > len(df_clean.columns) * 0.5:
            # Find candidate header row
            candidate_idx = None
            for idx in range(min(5, rows_in)):
                row_vals = df_clean.iloc[idx]
                str_count = sum(1 for v in row_vals if isinstance(v, str) and len(str(v).strip()) > 0)
                # string threshold set to 0.8
                if str_count >= len(df_clean.columns) * 0.8:
                    candidate_idx = idx
                    break

            if candidate_idx is not None and candidate_idx > 0:
                if not yes:
                    raise UserConfirmationRequired(
                        issue_type="merged_headers",
                        message=f"Detected title/merged header rows in table '{table_name}'. Candidate header is at row index {candidate_idx}.",
                        options=[f"Promote row {candidate_idx} as header", "Keep current headers"],
                        default_assumption=candidate_idx,
                    )
                new_headers = df_clean.iloc[candidate_idx].astype(str).str.strip().tolist()
                header_rows_dropped = candidate_idx + 1
                df_clean = df_clean.iloc[header_rows_dropped:].reset_index(drop=True)
                df_clean.columns = new_headers
                # Coerce promoted columns with infer_objects and pd.to_numeric
                df_clean = df_clean.infer_objects()
                for c in df_clean.columns:
                    try:
                        df_clean[c] = pd.to_numeric(df_clean[c])
                    except (ValueError, TypeError):
                        pass

                actions.append(
                    CleaningAction(
                        action_type="promote_merged_header",
                        rows_affected=header_rows_dropped,
                        details=f"Promoted row index {candidate_idx} as column headers and dropped {header_rows_dropped} header/title rows",
                        is_assumption=True,
                        assumption_caveat=f"Header row assumed at index {candidate_idx}, unconfirmed.",
                    )
                )
                assumptions.append(f"Header row assumed at index {candidate_idx}, unconfirmed.")

    # 2. Header deduplication & normalization
    cols = df_clean.columns.astype(str).str.strip().tolist()
    seen: Dict[str, int] = {}
    deduped_cols: List[str] = []
    renamed = False

    for c in cols:
        base = c if c and c != "nan" and not c.startswith("Unnamed:") else "Column"
        # If pandas added .1, .2
        base = re.sub(r"\.\d+$", "", base)
        if base in seen:
            seen[base] += 1
            deduped_cols.append(f"{base}_{seen[base]}")
            renamed = True
        else:
            seen[base] = 0
            deduped_cols.append(base)

    if renamed:
        df_clean.columns = deduped_cols
        actions.append(
            CleaningAction(
                action_type="rename_duplicate_headers",
                rows_affected=0,
                details=f"Deduplicated duplicate column headers: {deduped_cols}",
            )
        )

    # 3. Cell whitespace trimming (.str.strip()) and null token unification ({"N/A", "null", "-", ""} -> np.nan)
    null_tokens = {"n/a", "null", "-", "", "none", "nan"}
    trimmed_cells = 0
    for col in df_clean.columns:
        if pd.api.types.is_object_dtype(df_clean[col]) or pd.api.types.is_string_dtype(df_clean[col]):
            def _clean_cell(v):
                nonlocal trimmed_cells
                if pd.isna(v):
                    return np.nan
                if isinstance(v, str):
                    stripped = v.strip()
                    if stripped.lower() in null_tokens:
                        trimmed_cells += 1
                        return np.nan
                    if stripped != v:
                        trimmed_cells += 1
                    return stripped
                return v

            df_clean[col] = df_clean[col].apply(_clean_cell)

    if trimmed_cells > 0:
        actions.append(
            CleaningAction(
                action_type="strip_whitespace_and_nulls",
                rows_affected=trimmed_cells,
                details=f"Trimmed cell whitespace and unified null tokens ({'N/A', 'null', '-', ''}) across {trimmed_cells} cells",
            )
        )

    # 4. High-dimensional / wide dataset handling
    if df_clean.shape[1] >= 100:
        if not yes:
            raise UserConfirmationRequired(
                issue_type="wide_dataset",
                message=f"Dataset has {df_clean.shape[1]} columns. Please select primary metrics and dimensions to focus the report.",
                options=["Auto-select top features by Coefficient of Variation", "Include all columns"],
                default_assumption="auto_select_cv",
            )
        # Identify IDENTIFIER, TEMPORAL, and Categorical columns using col_profile_map
        id_cols: List[str] = []
        temporal_cols: List[str] = []
        cat_cols: List[str] = []
        numeric_cols: List[str] = []

        for col in df_clean.columns:
            prof_c = col_profile_map.get(str(col))
            role = prof_c.semantic_role if prof_c else None
            if role == SemanticRole.IDENTIFIER or str(col).lower().endswith("_id") or str(col).lower() == "id":
                id_cols.append(col)
            elif role == SemanticRole.TEMPORAL:
                temporal_cols.append(col)
            elif role in (SemanticRole.DIMENSION_CATEGORICAL, SemanticRole.DIMENSION_ORDINAL, SemanticRole.DIMENSION_HIERARCHY_CANDIDATE, SemanticRole.TEXT_FREE):
                cat_cols.append(col)
            else:
                s = pd.to_numeric(df_clean[col], errors="coerce")
                if s.notna().sum() > 5 and not pd.api.types.is_string_dtype(df_clean[col]):
                    numeric_cols.append(col)
                else:
                    cat_cols.append(col)

        # Rank categoricals by cardinality
        cat_cols.sort(key=lambda c: df_clean[c].nunique(), reverse=True)
        top_cats = cat_cols[:5]

        # Select top metrics by CV
        cv_scores: List[Tuple[str, float]] = []
        for col in numeric_cols:
            s = pd.to_numeric(df_clean[col], errors="coerce")
            mean_val = s.mean()
            std_val = s.std()
            if abs(mean_val) > 1e-9 and std_val is not None:
                cv_scores.append((col, float(std_val / abs(mean_val))))

        cv_scores.sort(key=lambda kv: kv[1], reverse=True)
        scored_cols = [kv[0] for kv in cv_scores]
        remaining_numeric = [c for c in numeric_cols if c not in scored_cols]
        top_metrics = (scored_cols + remaining_numeric)[:10]

        # Preserve IDENTIFIER and TEMPORAL columns, combine with top categoricals and top metrics
        focus_cols = list(dict.fromkeys(id_cols + temporal_cols + top_cats + top_metrics))
        if not focus_cols:
            focus_cols = list(df_clean.columns[:15])
        df_clean = df_clean[focus_cols]
        assumptions.append("High-dimensional dataset: top metrics auto-selected by Coefficient of Variation, unconfirmed.")
        actions.append(
            CleaningAction(
                action_type="select_wide_features",
                rows_affected=0,
                details=f"Reduced from {df.shape[1]} columns to {len(focus_cols)} focus features based on CV, preserving identifiers and temporals",
                is_assumption=True,
                assumption_caveat="High-dimensional dataset: top metrics auto-selected by Coefficient of Variation, unconfirmed.",
            )
        )

    # 5. Drop 100% null columns
    for col in list(df_clean.columns):
        if df_clean[col].isna().all():
            df_clean = df_clean.drop(columns=[col])
            actions.append(
                CleaningAction(
                    action_type="drop_null_column",
                    target_column=str(col),
                    rows_affected=len(df_clean),
                    details=f"Dropped column '{col}' because it contained 100% null values",
                )
            )

    # 6. Record numeric baseline before deduplication (including currency metrics)
    metric_baselines: Dict[str, Dict[str, float]] = {}
    dupes_mask = df_clean.duplicated()
    dupes_removed = int(dupes_mask.sum())

    for col in df_clean.columns:
        series = df_clean[col]
        is_num = pd.api.types.is_numeric_dtype(series)
        is_currency = False
        parsed_s = None

        if is_num:
            parsed_s = series
        else:
            non_null_strs = series.dropna().astype(str).str.strip()
            if len(non_null_strs) > 0 and non_null_strs.apply(lambda s: any(c in s for c in ["$", "€", "£", "¥"])).any():
                parsed_s = series.apply(lambda v: parse_currency_str(v, assume_us_locale=True))
                if parsed_s.notna().sum() > 0:
                    is_currency = True

        if is_num or is_currency:
            m_raw = float(parsed_s.dropna().sum())
            m_removed = float(parsed_s.loc[dupes_mask].dropna().sum()) if dupes_removed > 0 else 0.0
            m_expected = m_raw - m_removed
            metric_baselines[col] = {
                "raw": m_raw,
                "removed": m_removed,
                "expected": m_expected,
            }

    # Deduplicate exact rows
    if dupes_removed > 0:
        df_clean = df_clean.drop_duplicates().reset_index(drop=True)
        actions.append(
            CleaningAction(
                action_type="deduplicate_exact_rows",
                rows_affected=dupes_removed,
                details=f"Removed {dupes_removed} exact duplicate rows",
            )
        )

    total_rows_removed = header_rows_dropped + dupes_removed

    # 7. Column-specific transformations: Currencies, Percentages, Dates
    for col in df_clean.columns:
        series = df_clean[col]
        non_null_strs = series.dropna().astype(str).str.strip()
        if len(non_null_strs) == 0:
            continue

        # Check for mixed percentages (e.g. '0.125' and '12.5%')
        has_pct_symbol = non_null_strs.str.contains("%").any()
        has_plain_float = non_null_strs.apply(lambda s: bool(re.match(r"^0?\.\d+$", s))).any()

        if has_pct_symbol and has_plain_float:
            # Ambiguous scale!
            if not yes:
                raise UserConfirmationRequired(
                    issue_type="percentage_scale",
                    message=f"Ambiguous percentage scale in column '{col}': contains both '12.5%' and '0.125'.",
                    options=["Assume 0.125 represents 12.5% (ratio scale)", "Assume 0.125 represents 0.125%"],
                    default_assumption="ratio_scale",
                )
            # Under --yes: assume ratio scale
            df_clean[col] = series.apply(lambda v: parse_percentage_str(v, assume_ratio=True))
            assumptions.append("Scale assumed as ratio (0.125 = 12.5%), unconfirmed.")
            actions.append(
                CleaningAction(
                    action_type="standardize_percentage_scale",
                    target_column=str(col),
                    rows_affected=len(series),
                    details=f"Standardized mixed percentage column '{col}' to decimal ratio scale",
                    is_assumption=True,
                    assumption_caveat="Scale assumed as ratio (0.125 = 12.5%), unconfirmed.",
                )
            )
            continue
        elif has_pct_symbol:
            df_clean[col] = series.apply(lambda v: parse_percentage_str(v, assume_ratio=True))
            actions.append(
                CleaningAction(
                    action_type="parse_percentages",
                    target_column=str(col),
                    rows_affected=len(series),
                    details=f"Converted percentage strings in '{col}' to ratios",
                )
            )
            continue

        # Check for currencies and locale formatting
        has_currency_sym = non_null_strs.apply(lambda s: any(c in s for c in ["$", "€", "£", "¥"])).any()
        # Potential thousands: plain floats with 3 decimals (e.g. 0.123 or 1.500) must not trigger
        # has_ambiguous_thousands unless has_currency_sym is True or column has conflicting separator conventions.
        # Exclude numbers starting with "0.".
        def _check_potential_thousands(val_str: str) -> bool:
            clean_s = re.sub(r"[^\d.,]", "", val_str)
            return bool(re.match(r"^\d+[.,]\d{3}$", clean_s)) and not clean_s.startswith("0.")

        has_potential_thousands = non_null_strs.apply(_check_potential_thousands).any()
        has_dot_decimal = non_null_strs.apply(lambda s: bool(re.search(r"\.\d{2}$", s))).any()
        has_comma_decimal = non_null_strs.apply(lambda s: bool(re.search(r",\d{2}$", s))).any()
        has_conflicting_separators = has_dot_decimal and has_comma_decimal

        has_ambiguous_thousands = has_potential_thousands and (has_currency_sym or has_conflicting_separators)
        is_conflicting_locale = has_conflicting_separators or has_ambiguous_thousands

        if has_currency_sym or has_ambiguous_thousands:
            if is_conflicting_locale and not yes:
                raise UserConfirmationRequired(
                    issue_type="currency_locale",
                    message=f"Ambiguous or conflicting currency/number decimal format in column '{col}' (e.g. '1.234' or mixed US/EU locales).",
                    options=["Assume US locale ('.' is decimal, ',' is thousands)", "Assume European locale (',' is decimal, '.' is thousands)"],
                    default_assumption="US_locale",
                )

            if is_conflicting_locale:
                assumptions.append("Currency decimal separator assumed as '.', unconfirmed.")

            df_clean[col] = series.apply(lambda v: parse_currency_str(v, assume_us_locale=True))
            actions.append(
                CleaningAction(
                    action_type="parse_currency_numbers",
                    target_column=str(col),
                    rows_affected=len(series),
                    details=f"Normalized currency and formatted numeric values in '{col}'",
                    is_assumption=is_conflicting_locale,
                    assumption_caveat="Currency decimal separator assumed as '.', unconfirmed." if is_conflicting_locale else None,
                )
            )
            continue

        # Check for Dates using col_profile_map
        is_temporal = False
        prof_c = col_profile_map.get(str(col))
        if prof_c:
            is_temporal = (prof_c.semantic_role == SemanticRole.TEMPORAL)
        else:
            date_keywords = ["date", "time", "created_at", "updated_at", "month", "quarter", "year"]
            if any(k in str(col).lower() for k in date_keywords):
                is_temporal = True

        if is_temporal and (pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)):
            # Check for ambiguous dates (all components <= 12) supporting '/', '-', and '.'
            ambig_dates = non_null_strs.str.extract(r"^(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{2,4})$")
            if not ambig_dates.empty and ambig_dates[0].notna().any():
                part1_max = pd.to_numeric(ambig_dates[0], errors="coerce").max()
                part2_max = pd.to_numeric(ambig_dates[1], errors="coerce").max()

                if part1_max <= 12 and part2_max <= 12:
                    # Ambiguous date format!
                    if not yes:
                        raise UserConfirmationRequired(
                            issue_type="ambiguous_date_format",
                            message=f"Ambiguous date format in column '{col}': all month/day numbers <= 12.",
                            options=["MM/DD/YYYY (US format)", "DD/MM/YYYY (International format)"],
                            default_assumption="MM/DD/YYYY",
                        )
                    # Assume MM/DD/YYYY
                    assumptions.append("Date format assumed as MM/DD/YYYY, unconfirmed.")
                    df_clean[col] = pd.to_datetime(series, format="mixed", dayfirst=False, errors="coerce").dt.strftime("%Y-%m-%d")
                elif part1_max > 12:
                    # Day is first -> DD/MM/YYYY
                    df_clean[col] = pd.to_datetime(series, format="mixed", dayfirst=True, errors="coerce").dt.strftime("%Y-%m-%d")
                else:
                    # Month is first -> MM/DD/YYYY
                    df_clean[col] = pd.to_datetime(series, format="mixed", dayfirst=False, errors="coerce").dt.strftime("%Y-%m-%d")

                actions.append(
                    CleaningAction(
                        action_type="standardize_dates",
                        target_column=str(col),
                        rows_affected=len(series),
                        details=f"Standardized dates in '{col}' to ISO YYYY-MM-DD",
                        is_assumption=(part1_max <= 12 and part2_max <= 12),
                        assumption_caveat="Date format assumed as MM/DD/YYYY, unconfirmed." if (part1_max <= 12 and part2_max <= 12) else None,
                    )
                )
            else:
                # Try generic ISO or flexible parse
                try:
                    parsed_dates = pd.to_datetime(series, format="mixed", errors="coerce")
                    # Only standardize if parsing succeeded without wiping out valid non-null rows
                    if parsed_dates.notna().sum() > 0 and parsed_dates.notna().sum() >= len(non_null_strs) * 0.5:
                        df_clean[col] = parsed_dates.dt.strftime("%Y-%m-%d")
                        actions.append(
                            CleaningAction(
                                action_type="standardize_dates",
                                target_column=str(col),
                                rows_affected=len(series),
                                details=f"Standardized dates in '{col}' to ISO YYYY-MM-DD",
                            )
                        )
                except Exception:
                    pass

    # 8. Mathematical Reconciliation Verification
    rows_out = len(df_clean)
    is_row_reconciliation_valid = (rows_in - total_rows_removed == rows_out)
    if not is_row_reconciliation_valid:
        raise ReconciliationError(
            f"Row reconciliation failed: rows_in ({rows_in}) - total_rows_removed ({total_rows_removed}) != rows_out ({rows_out})"
        )

    metric_reconciliations: List[MetricReconciliation] = []
    recon_passed = is_row_reconciliation_valid

    for col, baseline in metric_baselines.items():
        if col in df_clean.columns and pd.api.types.is_numeric_dtype(df_clean[col]):
            sum_after = float(df_clean[col].dropna().sum())
            m_expected = baseline["expected"]
            rel_diff = abs(sum_after - m_expected) / (abs(m_expected) + 1e-9)
            is_metric_valid = (rel_diff < 1e-4)
            if not is_metric_valid:
                recon_passed = False
            metric_reconciliations.append(
                MetricReconciliation(
                    metric_name=col,
                    sum_before=baseline["raw"],
                    sum_after=sum_after,
                    relative_difference=rel_diff,
                    is_valid=is_metric_valid,
                )
            )

    recon_report = ReconciliationReport(
        rows_in=rows_in,
        rows_removed=total_rows_removed,
        rows_out=rows_out,
        is_row_reconciliation_valid=is_row_reconciliation_valid,
        metrics=metric_reconciliations,
        passed=recon_passed,
    )

    if not recon_passed:
        failed_metrics = [m.metric_name for m in metric_reconciliations if not m.is_valid]
        raise ReconciliationError(f"Metric sum reconciliation failed for: {failed_metrics}")

    cleaning_log = CleaningLog(
        table_name=table_name,
        actions=actions,
        total_rows_removed=total_rows_removed,
        reconciliation=recon_report,
        assumptions=assumptions,
    )

    return df_clean, cleaning_log
