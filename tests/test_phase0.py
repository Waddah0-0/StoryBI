"""Phase 0 Acceptance Tests: Foundations.

Verifies:
1. All Pydantic artifact schemas serialize and deserialize without loss.
2. Typer CLI skeleton runs with --help and displays commands.
3. Golden datasets with fixed seeds are generated and conform to planted truths:
   - Technology growth vs Furniture decline
   - Incomplete last month in Golden 1
   - Negative correlation (discount vs retention) and non-relationship (size vs churn) in Golden 2
   - Simpson's paradox present in Golden 2
   - Bottleneck defect rate and December surge in Golden 3
4. All 16 messy suite files exist and match their expected properties.
5. All story shape fixtures exist.
"""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from scipy import stats
from typer.testing import CliRunner

from storyteller.cli import app
from storyteller.schemas import (
    IngestReport,
    TableInfo,
    SemanticRole,
    AggregationRule,
    ColumnProfile,
    DataProfile,
    CleaningAction,
    MetricReconciliation,
    ReconciliationReport,
    CleaningLog,
    ColumnSpec,
    DatasetSpec,
    Fact,
    FactRegistry,
    StoryShape,
    PagePlan,
    StoryPlan,
    PrescriptiveAction,
    NarrativePage,
    Narrative,
    CheckType,
    ValidationIssue,
    ValidationReport,
    VisualPosition,
    VisualBinding,
    VisualSpec,
    PageSpec,
    ThemeSpec,
    ReportSpec,
)
from tests.generators.generate_golden import (
    generate_golden_ecommerce,
    generate_golden_saas,
    generate_golden_logistics,
)
from tests.generators.generate_messy import generate_all_messy_fixtures
from tests.generators.generate_shapes import generate_all_shape_fixtures

runner = CliRunner()
FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session", autouse=True)
def setup_all_fixtures():
    """Generate all golden, messy, and shape fixtures once for the test session."""
    golden_dir = FIXTURES_DIR / "golden"
    generate_golden_ecommerce(golden_dir / "golden_ecommerce.csv", seed=42)
    generate_golden_saas(golden_dir / "golden_saas.csv", seed=42)
    generate_golden_logistics(golden_dir / "golden_logistics.csv", seed=42)

    messy_dir = FIXTURES_DIR / "messy"
    generate_all_messy_fixtures(messy_dir)

    shapes_dir = FIXTURES_DIR / "shapes"
    generate_all_shape_fixtures(shapes_dir)


# ---------------------------------------------------------------------------
# 1. Pydantic Schemas Serialization / Deserialization Tests
# ---------------------------------------------------------------------------

def test_ingest_report_schema():
    report = IngestReport(
        file_path="data/sales.csv",
        file_format="csv",
        encoding="utf-8",
        delimiter=",",
        has_bom=False,
        tables=[
            TableInfo(
                name="sales",
                row_count=100,
                column_count=4,
                columns=["id", "date", "revenue", "category"],
                sample_preview=[{"id": 1, "revenue": 100.0}],
            )
        ],
        warnings=[],
    )
    json_str = report.model_dump_json()
    reloaded = IngestReport.model_validate_json(json_str)
    assert reloaded.file_format == "csv"
    assert reloaded.tables[0].row_count == 100


def test_profile_schemas():
    col = ColumnProfile(
        name="revenue",
        inferred_dtype="float",
        semantic_role=SemanticRole.METRIC_ADDITIVE,
        aggregation_rule=AggregationRule.SUM,
        null_rate=0.01,
        distinct_count=95,
        min_value=10.0,
        max_value=5000.0,
        mean=250.0,
        std_dev=45.0,
        coefficient_of_variation=0.18,
        sample_values=[120.0, 340.5],
        is_pii=False,
        role_confidence=0.98,
    )
    profile = DataProfile(
        table_name="orders",
        total_rows=1000,
        total_columns=1,
        columns=[col],
        primary_date_column="order_date",
        suggested_north_star="revenue",
        detected_grain="one row per order item",
    )
    json_str = profile.model_dump_json()
    reloaded = DataProfile.model_validate_json(json_str)
    assert reloaded.columns[0].semantic_role == SemanticRole.METRIC_ADDITIVE
    assert reloaded.suggested_north_star == "revenue"


def test_cleaning_log_and_reconciliation_schemas():
    recon = ReconciliationReport(
        rows_in=100,
        rows_removed=5,
        rows_out=95,
        is_row_reconciliation_valid=True,
        metrics=[
            MetricReconciliation(
                metric_name="sales",
                sum_before=10000.0,
                sum_after=10000.0,
                relative_difference=0.0,
                is_valid=True,
            )
        ],
        passed=True,
    )
    assert recon.is_row_reconciliation_valid is True
    assert recon.rows_in - recon.rows_removed == recon.rows_out

    log = CleaningLog(
        table_name="orders",
        actions=[
            CleaningAction(
                action_type="strip_whitespace",
                target_column="customer_name",
                rows_affected=12,
                details="Trimmed whitespace",
            ),
            CleaningAction(
                action_type="deduplicate",
                rows_affected=5,
                details="Removed exact duplicate rows",
            ),
        ],
        total_rows_removed=5,
        reconciliation=recon,
        assumptions=["Scale assumed as ratio (0.125 = 12.5%), unconfirmed."],
    )
    json_str = log.model_dump_json()
    reloaded = CleaningLog.model_validate_json(json_str)
    assert len(reloaded.actions) == 2
    assert reloaded.reconciliation.passed is True


def test_facts_schema():
    fact = Fact(
        id="F001",
        type="period_change",
        metric="Revenue",
        period="2024-Q3 vs 2024-Q2",
        value=0.184,
        components={"current": 1250000, "previous": 1055000},
        method="sum(Revenue) by quarter; pct change",
        n=4312,
        confidence="high",
        caveats=["last period is complete"],
        dual_recompute_match=True,
        relative_recompute_diff=0.0,
        importance_score=0.92,
    )
    registry = FactRegistry(
        dataset_name="Ecommerce",
        total_facts=1,
        facts=[fact],
        north_star_metric="Revenue",
        recompute_validation_passed=True,
    )
    json_str = registry.model_dump_json()
    reloaded = FactRegistry.model_validate_json(json_str)
    assert reloaded.facts[0].value == 0.184
    assert reloaded.recompute_validation_passed is True


def test_story_plan_and_narrative_schemas():
    plan = StoryPlan(
        story_shape=StoryShape.PERFORMANCE,
        shape_rationale="Date column and additive metric detected with dimension hierarchy",
        executive_headline="Revenue expanded +18.4% driven by Enterprise adoption",
        pages=[
            PagePlan(
                page_number=1,
                page_title="Executive Pulse",
                act_type="hook",
                headline_claim="Top-line growth remains strong across core divisions",
                primary_fact_ids=["F001", "F002"],
                suggested_visual_types=["card", "line"],
            )
        ],
    )
    assert plan.story_shape == StoryShape.PERFORMANCE

    narrative = Narrative(
        report_title="Q3 Executive Performance Briefing",
        story_shape=StoryShape.PERFORMANCE,
        pages=[
            NarrativePage(
                page_number=1,
                action_title="Revenue Surged +18.4% Quarter-over-Quarter",
                headline_banner="Growth was concentrated in Enterprise accounts, reaching {F001.value:currency}.",
                body_text="Overall sales reached {F001.components.current:currency}, an increase of {F001.value:pct} compared to the previous quarter.",
                bullet_insights=["Enterprise volume grew +24%", "Churn dropped by 2.1 percentage points"],
                actions=[
                    PrescriptiveAction(
                        action_item="Double down on Enterprise expansion pipeline",
                        supporting_fact_ids=["F001"],
                        hypothesis="Enterprise ARR retention outpaces SMB tier",
                        suggested_validation="Analyze 90-day pipeline conversion velocity",
                    )
                ],
                cited_fact_ids=["F001"],
            )
        ],
        is_fallback_template=False,
    )
    json_str = narrative.model_dump_json()
    reloaded = Narrative.model_validate_json(json_str)
    assert reloaded.pages[0].cited_fact_ids == ["F001"]


def test_validation_report_schema():
    report = ValidationReport(
        passed=True,
        claim_verification_rate=1.0,
        total_claims_checked=8,
        passed_claims=8,
        issues=[],
        retry_count=0,
        fell_back_to_template=False,
    )
    json_str = report.model_dump_json()
    reloaded = ValidationReport.model_validate_json(json_str)
    assert reloaded.claim_verification_rate == 1.0
    assert reloaded.passed is True


def test_report_spec_schema():
    theme = ThemeSpec(
        theme_name="light_executive_slate",
        palette=["#3B82F6", "#10B981", "#F59E0B", "#EF4444", "#8B5CF6"],
        background_color="#F8FAFC",
        card_background="#FFFFFF",
        primary_text="#0F172A",
        secondary_text="#64748B",
        positive_accent="#10B981",
        negative_accent="#EF4444",
    )
    visual = VisualSpec(
        id="vis_kpi_1",
        title="Total Revenue",
        visual_type="card",
        position=VisualPosition(x=20, y=20, width=280, height=140),
        bindings=VisualBinding(measure_names=["Total Revenue"]),
    )
    page = PageSpec(
        page_number=1,
        name="Executive_Pulse",
        display_name="1. Executive Pulse",
        action_title="Revenue Surged +18.4% QoQ",
        visuals=[visual],
    )
    spec = ReportSpec(
        report_title="Executive Performance Story",
        canvas_width=1280,
        canvas_height=720,
        theme=theme,
        pages=[page],
    )
    json_str = spec.model_dump_json()
    reloaded = ReportSpec.model_validate_json(json_str)
    assert reloaded.pages[0].visuals[0].position.width == 280
    assert reloaded.theme.theme_name == "light_executive_slate"


# ---------------------------------------------------------------------------
# 2. Typer CLI Skeleton Tests
# ---------------------------------------------------------------------------

def test_cli_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "StoryBI: Autonomous LLM-Powered Storytelling Agent" in result.output
    assert "run" in result.output
    assert "profile" in result.output
    assert "clean" in result.output
    assert "analyze" in result.output
    assert "build-pbip" in result.output


def test_cli_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "StoryBI version" in result.output


def test_cli_clean_confirmation_and_ascii_bullets(tmp_path):
    p = FIXTURES_DIR / "messy" / "percentages.csv"
    out_csv = tmp_path / "out.csv"
    out_log = tmp_path / "log.json"

    # Without --yes: cleanly catches UserConfirmationRequired, prints options with *, exit code 1
    res = runner.invoke(app, ["clean", str(p), "--output", str(out_csv), "--log", str(out_log)])
    assert res.exit_code == 1
    assert "Confirmation required" in res.output
    assert "*" in res.output
    assert "Traceback" not in res.output

    # With --yes: succeeds, prints assumptions with * (ASCII), not •
    res_yes = runner.invoke(app, ["clean", str(p), "--output", str(out_csv), "--log", str(out_log), "--yes"])
    assert res_yes.exit_code == 0
    assert "Cleaning complete!" in res_yes.output
    assert "•" not in res_yes.output
    assert "*" in res_yes.output


def test_cli_error_nonexistent_file():
    res = runner.invoke(app, ["ingest", "non_existent_file.csv"])
    assert res.exit_code == 1
    assert "Error:" in res.output
    assert "Traceback" not in res.output


# ---------------------------------------------------------------------------
# 3. Golden Datasets Verification with Planted Truths
# ---------------------------------------------------------------------------

def test_golden_ecommerce_planted_truths():
    path = FIXTURES_DIR / "golden" / "golden_ecommerce.csv"
    assert path.exists()
    df = pd.read_csv(path)
    assert len(df) == 2400

    df["order_date"] = pd.to_datetime(df["order_date"])
    df["quarter"] = df["order_date"].dt.to_period("Q")

    # Incomplete month check: October only has 10 days
    oct_dates = df[df["order_date"].dt.month == 10]["order_date"].dt.day
    assert not oct_dates.empty
    assert oct_dates.max() <= 10

    # Planted Technology growth vs Furniture decline between Q1 and Q3
    q1_tech = df[(df["quarter"] == "2024Q1") & (df["category"] == "Technology")]["sales"].mean()
    q3_tech = df[(df["quarter"] == "2024Q3") & (df["category"] == "Technology")]["sales"].mean()
    tech_growth = (q3_tech - q1_tech) / q1_tech
    assert tech_growth > 0.10, f"Expected Tech growth > 10%, got {tech_growth:.2%}"

    q1_furn = df[(df["quarter"] == "2024Q1") & (df["category"] == "Furniture")]["sales"].mean()
    q3_furn = df[(df["quarter"] == "2024Q3") & (df["category"] == "Furniture")]["sales"].mean()
    furn_growth = (q3_furn - q1_furn) / q1_furn
    assert furn_growth < -0.05, f"Expected Furniture decline < -5%, got {furn_growth:.2%}"

    # Planted 80/20 Pareto distribution: top 20% customers account for ~75%-85% revenue
    cust_rev = df.groupby("customer_id")["sales"].sum().sort_values(ascending=False)
    n_top_20 = int(len(cust_rev) * 0.20)
    top_20_share = cust_rev.iloc[:n_top_20].sum() / cust_rev.sum()
    assert 0.70 <= top_20_share <= 0.88, f"Expected Pareto share ~80%, got {top_20_share:.2%}"

    # Planted Q3 anomaly: West region in late August sales significantly higher
    west_aug = df[(df["region"] == "West") & (df["order_date"] >= "2024-08-20") & (df["order_date"] <= "2024-08-28")]["sales"].mean()
    west_normal = df[(df["region"] == "West") & ((df["order_date"] < "2024-08-20") | (df["order_date"] > "2024-08-28"))]["sales"].mean()
    assert west_aug > 2.0 * west_normal, "Planted West region late August anomaly not found"


def test_golden_saas_planted_truths():
    path = FIXTURES_DIR / "golden" / "golden_saas.csv"
    assert path.exists()
    df = pd.read_csv(path)
    assert len(df) == 2400

    # Planted strong negative correlation between discount_rate and retention_months (r < -0.60)
    r_disc_ret, p_disc_ret = stats.pearsonr(df["discount_rate"], df["retention_months"])
    assert r_disc_ret < -0.60, f"Expected strong negative correlation, got r={r_disc_ret:.3f}"

    # Planted NON-relationship between company_size and churned (|r| < 0.10, p > 0.05)
    r_size_churn, p_size_churn = stats.pearsonr(df["company_size"], df["churned"])
    assert abs(r_size_churn) < 0.10, f"Expected non-relationship, got r={r_size_churn:.3f}"
    assert p_size_churn > 0.05, f"Expected non-significant p-value, got p={p_size_churn:.3f}"

    # Planted Simpson's Paradox:
    # Within each tier, churn rate drops from 2023 to 2024
    for tier in ["Small", "Medium", "Enterprise"]:
        c23 = df[(df["tier"] == tier) & (df["cohort"] == 2023)]["churned"].mean()
        c24 = df[(df["tier"] == tier) & (df["cohort"] == 2024)]["churned"].mean()
        assert c24 < c23, f"Expected tier {tier} churn to drop from 2023 to 2024, got {c23:.2%} -> {c24:.2%}"

    # But overall aggregate churn rises from 2023 to 2024!
    agg_23 = df[df["cohort"] == 2023]["churned"].mean()
    agg_24 = df[df["cohort"] == 2024]["churned"].mean()
    assert agg_24 > agg_23, f"Expected aggregate churn to rise due to composition shift, got {agg_23:.2%} -> {agg_24:.2%}"


def test_golden_logistics_planted_truths():
    path = FIXTURES_DIR / "golden" / "golden_logistics.csv"
    assert path.exists()
    df = pd.read_csv(path)
    assert len(df) == 2000

    # Planted carrier bottleneck: ApexExpress damage rate significantly higher than others
    apex_rate = df[df["carrier"] == "ApexExpress"]["is_damaged"].mean()
    other_rate = df[df["carrier"] != "ApexExpress"]["is_damaged"].mean()
    assert apex_rate > 2.0 * other_rate, f"Expected Apex defect rate > 2x higher, got {apex_rate:.2%} vs {other_rate:.2%}"

    # Planted December volume surge
    df["month"] = pd.to_datetime(df["ship_date"]).dt.month
    dec_count = len(df[df["month"] == 12])
    avg_other_month_count = len(df[df["month"] != 12]) / 11.0
    assert dec_count > 1.8 * avg_other_month_count, f"Expected December surge, got {dec_count} vs avg {avg_other_month_count:.1f}"


# ---------------------------------------------------------------------------
# 4. Messy Suite & Shape Fixtures Verification
# ---------------------------------------------------------------------------

def test_all_16_messy_fixtures_exist():
    messy_dir = FIXTURES_DIR / "messy"
    expected_files = [
        "percentages.csv",
        "currency_symbols.csv",
        "utf8_bom.csv",
        "latin1.csv",
        "windows1252.csv",
        "mixed_dates.csv",
        "ambiguous_dates.csv",
        "duplicate_headers.csv",
        "duplicate_rows.csv",
        "all_null_column.csv",
        "single_row.csv",
        "no_date_data.csv",
        "no_numeric_data.csv",
        "wide_dataset.csv",
        "negative_values.csv",
        "excel_merged_headers.xlsx",
    ]
    for filename in expected_files:
        p = messy_dir / filename
        assert p.exists(), f"Missing messy fixture: {filename}"
        assert p.stat().st_size > 0, f"Empty messy fixture: {filename}"


def test_shape_fixtures_exist():
    shapes_dir = FIXTURES_DIR / "shapes"
    assert (shapes_dir / "fixture_trend.csv").exists()
    assert (shapes_dir / "fixture_relationship.csv").exists()
    assert (shapes_dir / "fixture_starschema" / "fact_orders.csv").exists()
    assert (shapes_dir / "fixture_starschema" / "dim_customers.csv").exists()
    assert (shapes_dir / "fixture_starschema" / "dim_products.csv").exists()
