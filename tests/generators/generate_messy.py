"""Generators for the 16-file Messy-Data Suite with predefined expected behaviors."""

from pathlib import Path
import numpy as np
import pandas as pd


def generate_all_messy_fixtures(base_dir: Path) -> dict:
    """Generate all 16 messy test fixtures and return dict of paths."""
    base_dir.mkdir(parents=True, exist_ok=True)
    paths = {}

    # 1. percentages.csv (mixed 0.125 and 12.5%) -> Ask user
    p1 = base_dir / "percentages.csv"
    pd.DataFrame({
        "item": ["Alpha", "Beta", "Gamma", "Delta"],
        "discount": ["12.5%", "0.125", "15.0%", "0.08"],
        "revenue": [1000, 1500, 2000, 2500],
    }).to_csv(p1, index=False)
    paths["percentages"] = p1

    # 2. currency_symbols.csv (unambiguous and ambiguous strings) -> Ask user when ambiguous
    p2 = base_dir / "currency_symbols.csv"
    pd.DataFrame({
        "region": ["US", "EU", "Unknown"],
        "amount": ["$1,240.50", "€ 3.400,00", "1.234"],
        "units": [10, 20, 30],
    }).to_csv(p2, index=False)
    paths["currency_symbols"] = p2

    # 3. utf8_bom.csv -> Clean & proceed
    p3 = base_dir / "utf8_bom.csv"
    content = "\ufeffid,product,price\n1,Widget,19.99\n2,Gadget,29.99\n"
    p3.write_text(content, encoding="utf-8-sig")
    paths["utf8_bom"] = p3

    # 4. latin1.csv -> Clean & proceed
    p4 = base_dir / "latin1.csv"
    content = "id,city,metric\n1,München,100\n2,Zürich,200\n3,São Paulo,300\n"
    p4.write_bytes(content.encode("iso-8859-1"))
    paths["latin1"] = p4

    # 5. windows1252.csv -> Clean & proceed
    p5 = base_dir / "windows1252.csv"
    content = "id,quote,score\n1,“Smart Quotes”,95\n2,En—Dash,88\n"
    p5.write_bytes(content.encode("cp1252"))
    paths["windows1252"] = p5

    # 6. mixed_dates.csv -> Clean & proceed (scan column finds day > 12)
    p6 = base_dir / "mixed_dates.csv"
    pd.DataFrame({
        "order_id": [1, 2, 3, 4],
        "date_str": ["2024-01-15", "31/01/2024", "14/02/2024", "05/03/2024"],
        "sales": [100, 200, 150, 300],
    }).to_csv(p6, index=False)
    paths["mixed_dates"] = p6

    # 7. ambiguous_dates.csv -> Ask user (all <= 12)
    p7 = base_dir / "ambiguous_dates.csv"
    pd.DataFrame({
        "order_id": [1, 2, 3],
        "date_str": ["01/02/2024", "03/04/2024", "05/06/2024"],
        "sales": [120, 220, 320],
    }).to_csv(p7, index=False)
    paths["ambiguous_dates"] = p7

    # 8. duplicate_headers.csv -> Clean & proceed
    p8 = base_dir / "duplicate_headers.csv"
    content = "id,Sales,Sales,Profit\n1,100,200,50\n2,150,250,75\n"
    p8.write_text(content, encoding="utf-8")
    paths["duplicate_headers"] = p8

    # 9. duplicate_rows.csv -> Clean & proceed
    p9 = base_dir / "duplicate_rows.csv"
    pd.DataFrame({
        "id": [1, 2, 2, 3],
        "category": ["A", "B", "B", "C"],
        "revenue": [100, 200, 200, 300],
    }).to_csv(p9, index=False)
    paths["duplicate_rows"] = p9

    # 10. all_null_column.csv -> Clean & proceed
    p10 = base_dir / "all_null_column.csv"
    pd.DataFrame({
        "id": [1, 2, 3],
        "valid_metric": [10.5, 20.0, 30.5],
        "empty_column": [None, None, None],
    }).to_csv(p10, index=False)
    paths["all_null_column"] = p10

    # 11. single_row.csv -> Clean & proceed
    p11 = base_dir / "single_row.csv"
    pd.DataFrame({
        "metric_a": [5000],
        "category": ["SoleEntity"],
        "status": ["Active"],
    }).to_csv(p11, index=False)
    paths["single_row"] = p11

    # 12. no_date_data.csv -> Clean & proceed (Composition shape)
    p12 = base_dir / "no_date_data.csv"
    pd.DataFrame({
        "department": ["Engineering", "Sales", "Support", "Marketing"],
        "headcount": [120, 85, 45, 30],
        "budget": [2400000, 1700000, 900000, 600000],
    }).to_csv(p12, index=False)
    paths["no_date_data"] = p12

    # 13. no_numeric_data.csv -> Clean & proceed (Frequency profile)
    p13 = base_dir / "no_numeric_data.csv"
    pd.DataFrame({
        "respondent_id": ["R1", "R2", "R3", "R4", "R5"],
        "feedback_category": ["UI", "Performance", "UI", "Pricing", "Support"],
        "sentiment": ["Positive", "Negative", "Neutral", "Negative", "Positive"],
    }).to_csv(p13, index=False)
    paths["no_numeric_data"] = p13

    # 14. wide_dataset.csv (300+ columns) -> Ask user
    p14 = base_dir / "wide_dataset.csv"
    rng = np.random.default_rng(42)
    wide_data = {"entity_id": [f"E-{i:03d}" for i in range(1, 21)]}
    for col_i in range(1, 305):
        # Varying variance across columns
        scale = float(col_i % 10 + 1)
        wide_data[f"feature_{col_i:03d}"] = rng.normal(100, scale, size=20).round(2)
    pd.DataFrame(wide_data).to_csv(p14, index=False)
    paths["wide_dataset"] = p14

    # 15. negative_values.csv -> Clean & proceed
    p15 = base_dir / "negative_values.csv"
    pd.DataFrame({
        "quarter": ["2023-Q1", "2023-Q2", "2023-Q3", "2023-Q4"],
        "net_income": [120000.0, -45000.0, -15000.0, 85000.0],
        "cash_flow": [90000.0, -20000.0, 5000.0, 60000.0],
    }).to_csv(p15, index=False)
    paths["negative_values"] = p15

    # 16. excel_merged_headers.xlsx -> Ask user
    p16 = base_dir / "excel_merged_headers.xlsx"
    with pd.ExcelWriter(p16, engine="openpyxl") as writer:
        raw_rows = [
            ["Financial Report - Confidential", None, None],
            ["Fiscal Year 2024", None, None],
            ["Division", "Q1 Revenue", "Q2 Revenue"],
            ["North America", 100000, 120000],
            ["Europe", 85000, 92000],
            ["Asia Pacific", 64000, 78000],
        ]
        df_merged = pd.DataFrame(raw_rows)
        df_merged.to_excel(writer, sheet_name="Summary", header=False, index=False)
    paths["excel_merged_headers"] = p16

    return paths
