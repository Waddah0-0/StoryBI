"""Phase 1 Acceptance Tests: Ingest, Profile, Clean.

Verifies:
1. Universal ingestion across CSV, TSV, XLSX, Parquet, JSON, SQLite and encodings (UTF-8, UTF-8 BOM, Latin-1, Windows-1252).
2. Semantic column profiling with roles, aggregation rules, and wide-file CV ranking.
3. Conservative cleaner with strict mathematical reconciliation:
   - rows_in - rows_removed == rows_out
   - relative metric tolerance < 1e-4
4. All 16 messy suite files produce their exact behavior from the matrix:
   - percentages.csv: asks user without --yes, assumes ratio with --yes
   - currency_symbols.csv: locale detection, asks on ambiguous '1.234' without --yes
   - utf8_bom.csv, latin1.csv, windows1252.csv: auto-decode cleanly
   - mixed_dates.csv: column-wide scan unifies to ISO
   - ambiguous_dates.csv: asks without --yes, assumes MM/DD/YYYY with --yes
   - duplicate_headers.csv: deduplicates headers
   - duplicate_rows.csv: removes exact duplicates, reconciles rows_removed
   - all_null_column.csv: drops empty column and logs
   - single_row.csv, no_date_data.csv, no_numeric_data.csv: clean and proceed
   - wide_dataset.csv: asks without --yes, auto-selects top by CV with --yes
   - negative_values.csv: preserves negative values with exact sum reconciliation
   - excel_merged_headers.xlsx: detects headers, asks without --yes, cleans with --yes
"""

import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from storyteller.exceptions import UserConfirmationRequired
from storyteller.ingest import ingest_file
from storyteller.profiler import profile_dataframe
from storyteller.cleaner import clean_dataframe
from storyteller.schemas import (
    SemanticRole,
    AggregationRule,
    IngestReport,
    DataProfile,
    CleaningLog,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MESSY_DIR = FIXTURES_DIR / "messy"
GOLDEN_DIR = FIXTURES_DIR / "golden"


# ---------------------------------------------------------------------------
# 1. Multi-Format & Encoding Ingestion Tests
# ---------------------------------------------------------------------------

def test_ingest_formats(tmp_path):
    # CSV
    csv_p = tmp_path / "test.csv"
    pd.DataFrame({"a": [1, 2], "b": [3.0, 4.0]}).to_csv(csv_p, index=False)
    frames, report = ingest_file(csv_p)
    assert report.file_format == "csv"
    assert "main" in frames
    assert frames["main"].shape == (2, 2)

    # TSV
    tsv_p = tmp_path / "test.tsv"
    pd.DataFrame({"x": ["A", "B"], "y": [10, 20]}).to_csv(tsv_p, sep="\t", index=False)
    frames, report = ingest_file(tsv_p)
    assert report.file_format == "tsv"
    assert frames["main"].shape == (2, 2)

    # JSON
    json_p = tmp_path / "test.json"
    pd.DataFrame({"k": ["one", "two"], "v": [100, 200]}).to_json(json_p, orient="records")
    frames, report = ingest_file(json_p)
    assert report.file_format == "json"
    assert frames["main"].shape == (2, 2)

    # Parquet
    parquet_p = tmp_path / "test.parquet"
    pd.DataFrame({"col1": [1.1, 2.2], "col2": ["foo", "bar"]}).to_parquet(parquet_p)
    frames, report = ingest_file(parquet_p)
    assert report.file_format == "parquet"
    assert frames["main"].shape == (2, 2)

    # SQLite
    sqlite_p = tmp_path / "test.db"
    conn = sqlite3.connect(sqlite_p)
    pd.DataFrame({"id": [1, 2], "val": ["x", "y"]}).to_sql("my_table", conn, index=False)
    conn.close()
    frames, report = ingest_file(sqlite_p)
    assert report.file_format == "sqlite"
    assert "my_table" in frames
    assert frames["my_table"].shape == (2, 2)


def test_ingest_encodings():
    # UTF-8 BOM
    frames_bom, report_bom = ingest_file(MESSY_DIR / "utf8_bom.csv")
    assert report_bom.has_bom is True
    assert "product" in frames_bom["main"].columns
    assert len(frames_bom["main"]) == 2

    # Latin-1
    frames_lat, report_lat = ingest_file(MESSY_DIR / "latin1.csv")
    assert "city" in frames_lat["main"].columns
    assert "München" in frames_lat["main"]["city"].values

    # Windows-1252
    frames_win, report_win = ingest_file(MESSY_DIR / "windows1252.csv")
    assert "quote" in frames_win["main"].columns
    assert any("Smart Quotes" in str(x) for x in frames_win["main"]["quote"].values)


# ---------------------------------------------------------------------------
# 2. Semantic Profiler Tests
# ---------------------------------------------------------------------------

def test_profiler_roles_and_aggregation_rules():
    df = pd.DataFrame({
        "order_id": ["ORD-001", "ORD-002", "ORD-003", "ORD-004"],
        "order_date": ["2024-01-10", "2024-01-11", "2024-01-12", "2024-01-13"],
        "category": ["Technology", "Furniture", "Technology", "Office Supplies"],
        "revenue": [1200.50, 450.00, 890.25, 120.00],
        "profit_margin": [0.24, 0.15, 0.28, 0.10],
        "satisfaction_rating": [4.5, 3.8, 4.9, 4.0],
        "customer_email": ["alice@example.com", "bob@example.com", "carol@example.com", "dave@example.com"],
    })

    profile = profile_dataframe(df, table_name="orders")
    assert isinstance(profile, DataProfile)
    assert profile.total_rows == 4
    assert profile.primary_date_column == "order_date"
    assert profile.suggested_north_star == "revenue"

    col_map = {col.name: col for col in profile.columns}

    # order_id -> identifier
    assert col_map["order_id"].semantic_role == SemanticRole.IDENTIFIER
    assert col_map["order_id"].aggregation_rule == AggregationRule.COUNT_DISTINCT

    # order_date -> temporal
    assert col_map["order_date"].semantic_role == SemanticRole.TEMPORAL

    # category -> dimension_categorical
    assert col_map["category"].semantic_role == SemanticRole.DIMENSION_CATEGORICAL

    # revenue -> metric_additive, SUM
    assert col_map["revenue"].semantic_role == SemanticRole.METRIC_ADDITIVE
    assert col_map["revenue"].aggregation_rule == AggregationRule.SUM

    # profit_margin -> metric_ratio, RATIO_OF_SUMS
    assert col_map["profit_margin"].semantic_role == SemanticRole.METRIC_RATIO
    assert col_map["profit_margin"].aggregation_rule == AggregationRule.RATIO_OF_SUMS

    # satisfaction_rating -> metric_non_additive, AVERAGE
    assert col_map["satisfaction_rating"].semantic_role == SemanticRole.METRIC_NON_ADDITIVE
    assert col_map["satisfaction_rating"].aggregation_rule == AggregationRule.AVERAGE

    # customer_email -> is_pii flagged
    assert col_map["customer_email"].is_pii is True


# ---------------------------------------------------------------------------
# 3. Messy Suite Behavior Matrix Verification
# ---------------------------------------------------------------------------

def test_messy_percentages_ask_and_yes():
    p = MESSY_DIR / "percentages.csv"
    frames, _ = ingest_file(p)
    df = frames["main"]
    prof = profile_dataframe(df)

    # Without --yes, must ask user (raise UserConfirmationRequired)
    with pytest.raises(UserConfirmationRequired) as exc:
        clean_dataframe(df, prof, yes=False)
    assert "discount" in str(exc.value).lower() or "scale" in str(exc.value).lower()

    # With --yes, assumes ratio and completes with assumption logged
    clean_df, log = clean_dataframe(df, prof, yes=True)
    assert clean_df["discount"].dtype in [np.float64, np.float32, float]
    # 12.5% -> 0.125, 0.125 -> 0.125
    assert np.isclose(clean_df["discount"].iloc[0], 0.125)
    assert np.isclose(clean_df["discount"].iloc[1], 0.125)
    assert any("ratio" in a.lower() for a in log.assumptions)


def test_messy_currency_symbols_ask_and_yes():
    p = MESSY_DIR / "currency_symbols.csv"
    frames, _ = ingest_file(p)
    df = frames["main"]
    prof = profile_dataframe(df)

    # Without --yes: '1.234' is ambiguous in locale
    with pytest.raises(UserConfirmationRequired):
        clean_dataframe(df, prof, yes=False)

    # With --yes: completes assuming US locale
    clean_df, log = clean_dataframe(df, prof, yes=True)
    assert clean_df["amount"].dtype in [np.float64, np.float32, float]
    assert np.isclose(clean_df["amount"].iloc[0], 1240.50)
    assert np.isclose(clean_df["amount"].iloc[1], 3400.00)
    assert np.isclose(clean_df["amount"].iloc[2], 1.234)
    assert any("locale" in a.lower() or "decimal" in a.lower() for a in log.assumptions)


def test_messy_mixed_dates():
    p = MESSY_DIR / "mixed_dates.csv"
    frames, _ = ingest_file(p)
    df = frames["main"]
    prof = profile_dataframe(df)

    clean_df, log = clean_dataframe(df, prof, yes=False)
    # Day > 12 in pos 1 (31/01/2024) disambiguates to DD/MM/YYYY
    assert pd.to_datetime(clean_df["date_str"]).dt.month.tolist() == [1, 1, 2, 3]
    assert pd.to_datetime(clean_df["date_str"]).dt.day.tolist() == [15, 31, 14, 5]


def test_messy_ambiguous_dates_ask_and_yes():
    p = MESSY_DIR / "ambiguous_dates.csv"
    frames, _ = ingest_file(p)
    df = frames["main"]
    prof = profile_dataframe(df)

    with pytest.raises(UserConfirmationRequired):
        clean_dataframe(df, prof, yes=False)

    clean_df, log = clean_dataframe(df, prof, yes=True)
    # Assumes MM/DD/YYYY under --yes
    assert pd.to_datetime(clean_df["date_str"]).dt.month.tolist() == [1, 3, 5]
    assert any("date format" in a.lower() for a in log.assumptions)


def test_messy_duplicate_headers():
    p = MESSY_DIR / "duplicate_headers.csv"
    frames, _ = ingest_file(p)
    df = frames["main"]
    assert "Sales" in df.columns
    # Both sales columns must exist and be renamed uniquely
    prof = profile_dataframe(df)
    clean_df, log = clean_dataframe(df, prof, yes=False)
    cols = clean_df.columns.tolist()
    assert len(cols) == len(set(cols))
    assert any(a.action_type == "rename_duplicate_headers" for a in log.actions)


def test_messy_duplicate_rows_and_reconciliation():
    p = MESSY_DIR / "duplicate_rows.csv"
    frames, _ = ingest_file(p)
    df = frames["main"]
    assert len(df) == 4
    prof = profile_dataframe(df)

    clean_df, log = clean_dataframe(df, prof, yes=False)
    assert len(clean_df) == 3
    assert log.total_rows_removed == 1

    # Exact reconciliation checks
    recon = log.reconciliation
    assert recon.rows_in == 4
    assert recon.rows_removed == 1
    assert recon.rows_out == 3
    assert recon.is_row_reconciliation_valid is True
    assert recon.passed is True


def test_messy_all_null_column():
    p = MESSY_DIR / "all_null_column.csv"
    frames, _ = ingest_file(p)
    df = frames["main"]
    assert "empty_column" in df.columns
    prof = profile_dataframe(df)

    clean_df, log = clean_dataframe(df, prof, yes=False)
    assert "empty_column" not in clean_df.columns
    assert any(a.action_type == "drop_null_column" for a in log.actions)


def test_messy_single_row():
    p = MESSY_DIR / "single_row.csv"
    frames, _ = ingest_file(p)
    df = frames["main"]
    prof = profile_dataframe(df)

    clean_df, log = clean_dataframe(df, prof, yes=False)
    assert len(clean_df) == 1
    assert log.reconciliation.passed is True


def test_messy_wide_dataset_ask_and_yes():
    p = MESSY_DIR / "wide_dataset.csv"
    frames, _ = ingest_file(p)
    df = frames["main"]
    assert df.shape[1] >= 300
    prof = profile_dataframe(df)

    with pytest.raises(UserConfirmationRequired):
        clean_dataframe(df, prof, yes=False)

    clean_df, log = clean_dataframe(df, prof, yes=True)
    # Selected top variance columns
    assert clean_df.shape[1] < 50
    assert any("high-dimensional" in a.lower() or "coefficient of variation" in a.lower() for a in log.assumptions)


def test_messy_negative_values_reconciliation():
    p = MESSY_DIR / "negative_values.csv"
    frames, _ = ingest_file(p)
    df = frames["main"]
    prof = profile_dataframe(df)

    clean_df, log = clean_dataframe(df, prof, yes=False)
    assert clean_df["quarter"].notna().all(), f"Quarter was corrupted: {clean_df['quarter'].tolist()}"
    # Net income sum must be identical before and after
    orig_sum = df["net_income"].sum()
    clean_sum = clean_df["net_income"].sum()
    rel_diff = abs(clean_sum - orig_sum) / (abs(orig_sum) + 1e-9)
    assert rel_diff < 1e-4

    recon = log.reconciliation
    metric_check = [m for m in recon.metrics if m.metric_name == "net_income"][0]
    assert metric_check.is_valid is True
    assert recon.passed is True


def test_messy_excel_merged_headers_ask_and_yes():
    p = MESSY_DIR / "excel_merged_headers.xlsx"
    frames, report = ingest_file(p)
    df = frames["Summary"]
    prof = profile_dataframe(df)

    with pytest.raises(UserConfirmationRequired):
        clean_dataframe(df, prof, yes=False)

    clean_df, log = clean_dataframe(df, prof, yes=True)
    assert "Division" in clean_df.columns or any("Revenue" in str(c) for c in clean_df.columns)
    assert any("header" in a.lower() for a in log.assumptions)


def test_messy_no_date_data():
    p = MESSY_DIR / "no_date_data.csv"
    frames, _ = ingest_file(p)
    df = frames["main"]
    prof = profile_dataframe(df)
    assert prof.primary_date_column is None

    clean_df, log = clean_dataframe(df, prof, yes=False)
    assert len(clean_df) == 4
    assert log.reconciliation.passed is True


def test_messy_no_numeric_data():
    p = MESSY_DIR / "no_numeric_data.csv"
    frames, _ = ingest_file(p)
    df = frames["main"]
    prof = profile_dataframe(df)
    assert prof.suggested_north_star is None

    clean_df, log = clean_dataframe(df, prof, yes=False)
    assert len(clean_df) == 5
    assert log.reconciliation.passed is True

    # Validate that DatasetSpec and FactRegistry accept None for north_star_metric
    from storyteller.schemas.dataset_spec import DatasetSpec, ColumnSpec
    from storyteller.schemas.facts import FactRegistry

    spec = DatasetSpec(
        dataset_name="feedback",
        grain="one response per row",
        north_star_metric=None,
        columns={c: ColumnSpec(name=c, role=SemanticRole.TEXT_FREE, display_name=c) for c in clean_df.columns},
        focus_metrics=[],
        focus_dimensions=list(clean_df.columns),
    )
    assert spec.north_star_metric is None

    registry = FactRegistry(
        dataset_name="feedback",
        total_facts=0,
        facts=[],
        north_star_metric=None,
    )
    assert registry.north_star_metric is None


def test_messy_encodings_cleaning():
    # utf8_bom
    frames_bom, _ = ingest_file(MESSY_DIR / "utf8_bom.csv")
    df_bom = frames_bom["main"]
    prof_bom = profile_dataframe(df_bom)
    clean_bom, log_bom = clean_dataframe(df_bom, prof_bom, yes=False)
    assert len(clean_bom) == 2
    assert log_bom.reconciliation.passed is True
    assert "product" in clean_bom.columns

    # latin1
    frames_lat, _ = ingest_file(MESSY_DIR / "latin1.csv")
    df_lat = frames_lat["main"]
    prof_lat = profile_dataframe(df_lat)
    clean_lat, log_lat = clean_dataframe(df_lat, prof_lat, yes=False)
    assert len(clean_lat) == 3
    assert log_lat.reconciliation.passed is True
    assert "München" in clean_lat["city"].values

    # windows1252
    frames_win, _ = ingest_file(MESSY_DIR / "windows1252.csv")
    df_win = frames_win["main"]
    prof_win = profile_dataframe(df_win)
    clean_win, log_win = clean_dataframe(df_win, prof_win, yes=False)
    assert len(clean_win) == 2
    assert log_win.reconciliation.passed is True
    assert any("Smart Quotes" in str(x) for x in clean_win["quote"].values)


def test_ingest_directory():
    shapes_dir = FIXTURES_DIR / "shapes" / "fixture_starschema"
    frames, report = ingest_file(shapes_dir)
    assert report.file_format == "directory"
    assert "fact_orders" in frames
    assert "dim_customers" in frames
    assert "dim_products" in frames
    assert len(report.tables) == 3


def test_profiler_phone_and_zip_and_quality_checks():
    df = pd.DataFrame({
        "zip_code": [90210, 10001, 94105, 90210],
        "phone_num": ["+12345678901", "+19876543210", "+12345678901", "+11234567890"],
        "normal_int": [10, 20, 30, 40],
        "constant_col": ["A", "A", "A", "A"],
    })
    prof = profile_dataframe(df)
    col_map = {c.name: c for c in prof.columns}

    # Zip code must NOT be additive metric
    assert col_map["zip_code"].semantic_role != SemanticRole.METRIC_ADDITIVE
    assert col_map["zip_code"].semantic_role in (SemanticRole.IDENTIFIER, SemanticRole.DIMENSION_CATEGORICAL)

    # Phone number flagged as PII
    assert col_map["phone_num"].is_pii is True

    # Normal integer should NOT be flagged as phone or PII
    assert col_map["normal_int"].is_pii is False
    assert col_map["normal_int"].semantic_role == SemanticRole.METRIC_ADDITIVE

    # Quality checks include duplicate keys/PII/constant col
    issues_str = " ".join(prof.quality_issues)
    assert "constant" in issues_str.lower()
    assert "pii" in issues_str.lower()


def test_cleaner_currency_and_dots_and_whitespace():
    from storyteller.cleaner import parse_currency_str

    # Preserves $-100 and $(100)
    assert np.isclose(parse_currency_str("$-100"), -100.0)
    assert np.isclose(parse_currency_str("$(100)"), -100.0)
    assert np.isclose(parse_currency_str("-$100"), -100.0)
    assert np.isclose(parse_currency_str("($1,200.50)"), -1200.50)

    # European multiple dots
    assert np.isclose(parse_currency_str("1.000.000"), 1000000.0)
    assert np.isclose(parse_currency_str("€ 1.000.000,50"), 1000000.50)

    # Whitespace and null tokens
    df = pd.DataFrame({
        "cat": ["  Tech  ", "N/A", "-", "Finance"],
        "val": [1.500, 2.750, 0.123, 4.000],  # Plain floats with 3 decimals
    })
    prof = profile_dataframe(df)
    clean_df, log = clean_dataframe(df, prof, yes=False)

    # Plain floats with 3 decimals must NOT raise UserConfirmationRequired
    assert clean_df["cat"].iloc[0] == "Tech"
    assert pd.isna(clean_df["cat"].iloc[1])
    assert pd.isna(clean_df["cat"].iloc[2])
    assert any(a.action_type == "strip_whitespace_and_nulls" for a in log.actions)


def test_cleaner_date_dash_and_dot():
    df = pd.DataFrame({
        "order_id": [1, 2, 3],
        "date_str": ["01-02-2024", "03-04-2024", "05-06-2024"],
        "sales": [10, 20, 30],
    })
    prof = profile_dataframe(df)

    # Ambiguous date with dashes should ask without --yes
    with pytest.raises(UserConfirmationRequired):
        clean_dataframe(df, prof, yes=False)

    clean_df, log = clean_dataframe(df, prof, yes=True)
    assert any(a.action_type == "standardize_dates" for a in log.actions)
    assert clean_df["date_str"].iloc[0] == "2024-01-02"


def test_excel_merged_headers_row_accounting():
    p = MESSY_DIR / "excel_merged_headers.xlsx"
    frames, _ = ingest_file(p)
    df = frames["Summary"]
    prof = profile_dataframe(df)

    clean_df, log = clean_dataframe(df, prof, yes=True)
    assert log.reconciliation.rows_in == len(df)
    assert log.reconciliation.rows_removed == log.total_rows_removed
    assert log.reconciliation.rows_in - log.reconciliation.rows_removed == log.reconciliation.rows_out
    assert log.reconciliation.is_row_reconciliation_valid is True
    assert log.reconciliation.passed is True


def test_cleaner_quarter_non_temporal():
    df = pd.DataFrame({
        "quarter": ["Q1", "Q2", "Q3", "Q4"],
        "sales": [100, 200, 300, 400],
    })
    prof = profile_dataframe(df)
    clean_df, log = clean_dataframe(df, prof, yes=False)
    assert clean_df["quarter"].tolist() == ["Q1", "Q2", "Q3", "Q4"]


def test_cleaner_currency_symbol_with_potential_thousands():
    df = pd.DataFrame({
        "item": ["A", "B"],
        "price": ["$1.234", "$2.345"],
    })
    prof = profile_dataframe(df)
    # Since has_currency_sym is True and values are $1.234, it is ambiguous thousands ($1.234 vs $1234)!
    # It must raise UserConfirmationRequired without --yes!
    with pytest.raises(UserConfirmationRequired):
        clean_dataframe(df, prof, yes=False)


def test_cleaner_single_comma_decimal_digits():
    from storyteller.cleaner import parse_currency_str
    assert np.isclose(parse_currency_str("€ 12,5"), 12.5)
    assert np.isclose(parse_currency_str("12,5"), 12.5)
    assert np.isclose(parse_currency_str("-€ 12,5"), -12.5)
    assert np.isclose(parse_currency_str("€ -1.000.000,50"), -1000000.5)
    assert np.isclose(parse_currency_str("€ (1.000.000,50)"), -1000000.5)


def test_cleaner_wide_dataset_zero_variance():
    data = {"id": [f"ID_{i}" for i in range(10)]}
    for i in range(105):
        data[f"metric_{i}"] = [0.0] * 10
    df = pd.DataFrame(data)
    prof = profile_dataframe(df)
    clean_df, log = clean_dataframe(df, prof, yes=True)
    assert clean_df.shape[1] > 1
    assert any(c.startswith("metric_") for c in clean_df.columns)


def test_profiler_single_non_null_value_not_constant_all_rows():
    df = pd.DataFrame({
        "status": ["Active"] + [None] * 9,
        "id": range(10),
    })
    prof = profile_dataframe(df)
    issues_str = " ".join(prof.quality_issues)
    assert "constant value across all rows" not in issues_str.lower()


def test_ingest_directory_ignores_lock_and_hidden_files(tmp_path):
    # Valid csv
    csv_p = tmp_path / "valid.csv"
    pd.DataFrame({"a": [1, 2], "b": [3, 4]}).to_csv(csv_p, index=False)

    # Windows Excel temporary lock file (~$...)
    lock_p = tmp_path / "~$valid.xlsx"
    lock_p.write_bytes(b"corrupt lock file content")

    # Hidden file
    hidden_p = tmp_path / ".hidden.csv"
    hidden_p.write_text("a,b\n1,2", encoding="utf-8")

    frames, report = ingest_file(tmp_path)
    assert "valid" in frames
    assert len(report.tables) == 1
    assert report.tables[0].name == "valid"


def test_ingest_json_utf8_bom(tmp_path):
    json_p = tmp_path / "data_bom.json"
    content = '\ufeff[{"id": 1, "name": "Alpha"}, {"id": 2, "name": "Beta"}]'
    json_p.write_text(content, encoding="utf-8-sig")

    frames, report = ingest_file(json_p)
    assert report.has_bom is True
    assert "main" in frames
    assert len(frames["main"]) == 2
    assert frames["main"]["name"].tolist() == ["Alpha", "Beta"]


def test_cli_nested_output_directory(tmp_path):
    from typer.testing import CliRunner
    from storyteller.cli import app

    runner = CliRunner()
    csv_p = tmp_path / "input.csv"
    pd.DataFrame({"x": [10, 20], "y": [30, 40]}).to_csv(csv_p, index=False)

    out_csv = tmp_path / "nested" / "deep" / "cleaned.csv"
    out_log = tmp_path / "nested" / "deep" / "log.json"

    res = runner.invoke(app, ["clean", str(csv_p), "--output", str(out_csv), "--log", str(out_log), "--yes"])
    assert res.exit_code == 0
    assert out_csv.exists()
    assert out_log.exists()
