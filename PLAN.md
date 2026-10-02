# StoryBI v2: LLM-Powered Storytelling Agent for Power BI

## 1. Goal

Take any tabular dataset and produce a Power BI project (`.pbip`) that tells an accurate, well-designed data story: an executive headline, the evidence, the nuance, and recommended actions.

Two requirements outrank everything else:

1. **Accuracy.** Every number and claim in the story is traceable to a computed fact.
2. **Any dataset.** The agent adapts its story shape to the data, and asks the user when it is unsure instead of guessing.

## 2. Core Design Principles

1. **Code computes, the LLM writes.** Python calculates every number. The LLM never invents or types a number; it references `{fact_id.field:format}` placeholders, and the renderer fills in the values.
2. **Nothing is silent.** Every cleaning step, assumption, and dropped row goes into a log the user can read.
3. **Reconciliation.** `rows_in - rows_removed == rows_out`, with `rows_removed` explicitly logged. For metric sums and independent recomputations, use relative tolerance: `abs(metric_sum_after - metric_sum_before) / abs(metric_sum_before) < 1e-4` (with absolute epsilon for near-zero).
4. **Ask when ambiguous.** Unclear date format, unclear scale, unclear north-star metric, unclear grain: the agent asks. When `--yes` is supplied, use defined defaults, log each as `"assumed, unconfirmed"`, and carry it into the story as a caveat fact.
5. **Association, not causation.** The narrative may say "associated with" or "coincides with", strictly never "caused by", "due to", "because of", or "drove", unless the user supplies explicit causal context.
6. **Template-driven Power BI output.** Generate from a golden project saved by real Power BI Desktop (built by hand by the user and templatized), not from hand-written formats guessed from memory.
7. **Vertical slice first.** A tiny end-to-end pipeline that opens in Desktop beats a wide pipeline that doesn't.
8. **Deterministic where possible.** Column typing, aggregation rules, chart choice, and layout are rules-based. The LLM handles interpretation, storytelling strategy, and language only.
9. **Dual independent recomputation.** Critical facts are computed in Pandas and independently cross-checked in DuckDB SQL using relative tolerance to mathematically eliminate calculation glitches.
10. **Privacy-first:** Only aggregated facts and column metadata (names, dtypes, summary stats, non-PII sample values) are sent to the LLM. Raw rows and PII columns are strictly never sent.
11. **Gated Progression:** A phase does not start until the previous phase's acceptance commands pass with complete logged output.

## 3. Pipeline Overview

Every stage reads and writes a versioned JSON artifact (validated by Pydantic schemas). This keeps stages independently testable and lets the LLM layer be swapped or mocked.

```
Input file
  -> [1 Ingest]        -> raw_frames + ingest_report.json
  -> [2 Profile]       -> profile.json        (types, semantic roles, aggregation rules)
  -> [3 Clean]         -> clean data + cleaning_log.json (reconciliation: rows & relative metric tolerance)
  -> [4 Confirm]       -> dataset_spec.json   (user-approved roles, north star, grain, caveats)
  -> [5 Analyze]       -> facts.json          (verified facts with ID, provenance & DuckDB recompute)
  -> [6 Plan story]    -> story_plan.json     (adaptive story shape + fact ID selections)
  -> [7 Write story]   -> narrative.json      (LLM text with fact-ID placeholders e.g. {F012.value:pct})
  -> [8 Validate]      -> validation_report   (100% claim verification gate; loop back / fallback)
  -> [9 Report spec]   -> report_spec.json    (tool-agnostic pages, visuals, layout)
  -> [10 Render PBIP]  -> .pbip project       (TMDL semantic model, DAX measures, PBIR visual definitions)
  -> [11 Check output] -> automated pre-gate (JSON schema + TMDL parse), then manual open in Desktop
```

## 4. Stage Details

### 4.1 Ingest
- Support CSV/TSV, XLSX, Parquet, JSON, SQLite. Detect encoding, delimiter, header row, sheet names.
- Multi-sheet or multi-table inputs: load all, record them, and let profiling detect keys and relationships.
- Output: `ingest_report.json` (file type, encoding, shape, sheets, warnings).

### 4.2 Profile
Per column: inferred type, null rate, distinct count, min/max, sample values, skew, and a **semantic role**.

Roles: `temporal`, `identifier`, `metric_additive`, `metric_ratio`, `metric_non_additive`, `metric_semi_additive`, `dimension_categorical`, `dimension_ordinal`, `dimension_hierarchy_candidate`, `text_free`, `unknown`.

Aggregation rules:
- **Additive** (revenue, units): `SUM`.
- **Ratios** (margin %, conversion rate): compute as a ratio of sums (`SUM(profit)/SUM(revenue)`), never an average of row-level ratios.
- **Non-additive** (unit price, rating): `AVERAGE`, ideally weighted where a weight column exists.
- **Semi-additive** (balances, headcount): last value over time, not sum.

Wide-file handling: For datasets with hundreds of columns, compute normalized variance / Coefficient of Variation ($CV = \sigma / |\mu|$) for numerical columns and entropy/cardinality for categoricals. Log every column chosen for focus.

Detect & flag: duplicate rows, duplicate keys, constant columns, mixed-type columns, likely PII columns (flagged and excluded from LLM calls).

### 4.3 Clean (conservative, logged, reversible)
Two tiers:

**Safe auto-fixes** (applied and logged): trim whitespace, normalize header names, strip currency symbols and thousands separators, unify null tokens (`N/A`, `null`, `-`, empty).

**Judgment calls & Ambiguities** (ask when ambiguous; when `--yes` is passed, use defined defaults and log as `"assumed, unconfirmed"`):
- **Percentages:** mixed `0.125` and `12.5%` $\rightarrow$ `--yes` assumes $\le 1.0$ is ratio scale ($0.125 = 12.5\%$).
- **Currencies & Locales:** ambiguous separator (e.g. `1.234`) $\rightarrow$ `--yes` assumes US locale (`.` decimal, `,` thousands).
- **Dates:** scan entire column. If ambiguous (`01/02/2024`) $\rightarrow$ `--yes` assumes `MM/DD/YYYY`.
- **Merged headers:** Excel multi-row headers $\rightarrow$ `--yes` picks first row where $\ge 80\%$ cells are strings.
- **Wide files:** 300+ columns $\rightarrow$ `--yes` auto-selects top 10 metrics by $CV$ and top 5 categoricals.
- **Missing metrics:** keep as null by default; report null rate.
- **Duplicates:** remove exact duplicate rows only; log `rows_removed`.

**Reconciliation check:**
$$\text{rows\_in} - \text{rows\_removed} == \text{rows\_out}$$
For every additive metric $M$:
$$\frac{|M_{\text{out}} - M_{\text{in}}|}{|M_{\text{in}}| + \epsilon} < 10^{-4}$$
Any unexplained deviation fails the stage immediately.
Output: `cleaning_log.json` listing transformations, `rows_removed`, assumptions, and reconciliation status.

### 4.4 Confirm (human in the loop)
The agent presents a short summary and asks only what it cannot infer:
- Which metric is the **north star**? (default: highest-confidence additive metric)
- What is the **grain** (one row = one what)?
- Is the **date column** correct, and which is the primary one?
- Any ambiguous roles or scales.

CLI: interactive prompts with defaults, plus `--yes` to accept defaults. All `--yes` assumptions are logged as `"assumed, unconfirmed"` and attached as caveats in `dataset_spec.json`.

### 4.5 Analyze (the facts engine)
Produces `facts.json`. Each fact is a small, self-describing record with ID, type, metric, value, components, method, $n$, confidence, and caveats.

Analyses, gated on what the data supports:
- **Headline KPIs:** totals, period-over-period change (YoY, MoM, QoQ), with zero-division protection.
- **Trend:** direction, slope, seasonality hints, and change points.
- **Composition and concentration:** Pareto share, top-N share, HHI-style concentration.
- **Comparison:** gainers and decliners, ranked, with contribution to total change.
- **Drivers (association):** correlations (Pearson and Spearman), dimension-level variance explained. Report effect sizes and sample sizes; suppress results below minimum $n=30$.
- **Anomalies:** robust methods (IQR or median absolute deviation) rather than plain sigma, with a cap on reported count.
- **Segments:** performance tiers (volume vs. efficiency quadrant).

Accuracy safeguards:
- **Partial periods:** detect an incomplete last period (e.g. partial month) and either exclude it from period comparison or label it explicitly.
- **Small samples:** every fact carries $n$; low $n$ facts are tagged and cannot be headliners.
- **Simpson's paradox check:** check that top-level trends do not reverse inside major segments; add a caveat fact if detected.
- **Multiple comparisons:** apply stricter significance thresholds as tested hypothesis count grows.
- **Independent recompute:** top facts are recomputed with independent SQL queries in DuckDB. The relative difference must be $< 10^{-4}$. A mismatch fails the build.

### 4.6 Plan the story (LLM call 1)
Input: `dataset_spec.json` + a compact list of facts (ID, type, description, importance score). **No raw data.**

Story shapes (fallbacks so "any dataset" works):

| Data situation | Story shape | Page Arc |
|---|---|---|
| Date + additive metric + dimensions | **Performance story** | Pulse, Drivers, Segments & anomalies, Actions |
| No date column | **Composition story** | Overview, Breakdown, Concentration, Outliers, Actions |
| Date only, no useful dimensions | **Trend story** | Level, Trend, Seasonality, Anomalies, Watch-list |
| Many numeric columns, no clear north star | **Relationship story** | Distribution, Correlations, Clusters, Notable rows |
| Multiple related tables | **Star-schema story** | Fact-dimension relationships, Cross-filtering, Drilldowns |
| Very small or very wide data | **Profile story** | Data-quality and profile report with minimal story |

Output: `story_plan.json` with the chosen shape, one **headline claim** per page, and supporting fact IDs.

### 4.7 Write the story (LLM call 2)
Input: the story plan and selected facts (with values, so it can judge magnitude).

Rules enforced through prompt and JSON schema:
- Numbers appear **only as placeholders**, e.g. `{F012.value:pct}`. The renderer substitutes formatted values from `facts.json`.
- Every sentence lists the `fact_ids` it depends on.
- Approved verbs for drivers: "is associated with", "coincides with", "is concentrated in". Strictly banned: "caused by", "due to", "because of", "drove" (unless user-provided context).
- Recommendations must be labeled as hypotheses with a suggested check ("validate by X"), citing supporting facts.
- Style: action titles stating the insight (not "Sales by Category"), plain language, one message per page.

### 4.8 Validate (mandatory gate)
Automated code checks on `narrative.json`:
1. Every placeholder resolves to an existing fact in `facts.json`.
2. No literal numbers in text outside placeholders (regex scan), except dates and ordinal words.
3. Every named entity (region, product, etc.) exists in the data.
4. Direction words match the sign of the referenced fact ("grew" only when value is positive).
5. Causal-language lint strictly rejects banned causal verbs.
6. Every fact marked low-confidence carries its caveat in the text.
7. Every page's headline is backed by at least one high-confidence fact.

On failure: return specific errors to writer (max 2 retries). If still failing, fall back to a deterministic templated narrative.

### 4.9 Report spec (deterministic)
A tool-agnostic `report_spec.json` describes pages, visuals, data bindings, titles, and layout.
- Visual selection: Card with delta, Line chart, Sorted horizontal bar, Waterfall, Scatter with quadrant lines, Table with conditional formatting, Pareto (bar + cumulative line).
- 12-column grid layout with fixed margins to prevent overlapping.
- 2 curated themes initially (Light Executive Slate and Dark Midnight Obsidian).

### 4.10 Render the PBIP
1. **Template source of truth:** Built by hand in Power BI Desktop by the user, saved as `.pbip`, and committed to `storyteller/powerbi/templates/` before Phase 4 starts.
2. **Pinned Desktop version:** Pinned to user's Power BI Desktop version.
3. **Portable data paths:** Power Query parameter `DataFolder` references local clean data relatively so moving folders never breaks paths.
4. **Semantic model:** Clean table definitions, auto-generated `Calendar` date dimension, relationships, and a `_Measures` table with robust DAX (`DIVIDE`, `TOTALYTD`, `KEEPFILTERS`, Pareto cumulative share).
5. **Report:** PBIR / `report.json` with visual containers, bindings, titles, and theme JSON.
6. **Automated pre-gate:** JSON schema validation of report files + TMDL syntax parse check before manual Desktop check.
7. **Manual Desktop verification:** Open generated `.pbip` in Desktop. Must load with **zero repair prompts**. Exactly 5 named values from `facts.json` are compared against the visual outputs, and a screenshot is committed as evidence.

## 5. LLM Integration Specifications

- **Provider-Agnostic Interface**: `LLMClient.generate_json(schema: Type[BaseModel], prompt: str) -> BaseModel`. Supports Gemini, OpenAI, Anthropic, or local Ollama.
- **Structured Output**: Strictly enforced via Pydantic JSON schemas. Low temperature ($\le 0.2$) for planning and writing.
- **Record / Replay Harness**: All LLM calls can be recorded to disk (`tests/fixtures/llm_cassettes/`) and replayed offline so tests run deterministically without internet access or API spend.
- **Credential Safety**: API keys are loaded strictly from environment variables (e.g. `GEMINI_API_KEY`) and are never written to disk, committed to Git, or included in logs.
- **Versioned Prompts**: All prompt templates live in dedicated versioned files (`storyteller/prompts/v1/`) with changelogs.
- **Privacy Enforcement**: An automated test asserts that every outbound LLM request payload contains only aggregated facts, column metadata, and summary stats—and zero raw rows or PII columns.

## 6. Testing Strategy

### 6.1 Golden Datasets with Planted Truths (Fixed Seed = 42)
All golden datasets use `numpy.random.default_rng(42)`:
- Tests assert that **every planted truth is found**.
- Tests assert that **planted non-relationships are NOT flagged as significant** ($|r| < 0.10, p > 0.05$).
- Tests do **NOT** assert exact decimal correlation values or "only the planted truths".

1. **`golden_ecommerce.csv` (seed=42)**:
   - Planted +20% growth in Technology, -15% decline in Furniture.
   - Planted Q3 anomaly (spike in West region).
   - Planted 80/20 Pareto distribution (top ~20% customers drive ~80% revenue).
   - **Incomplete last month:** Contains a partial final month (e.g. 10 days of data). Tests assert the engine detects the partial month, labels it, and does not compare it as a full period.
2. **`golden_saas.csv` (seed=42)**:
   - Planted strong negative correlation between Discount Rate and Retention ($r < -0.6$).
   - Planted non-relationship between Company Size and Churn ($|r| < 0.10, p > 0.05$).
   - Planted Simpson's Paradox: overall aggregate churn rises, but inside every customer tier churn actually falls.
3. **`golden_logistics.csv` (seed=42)**:
   - Planted carrier bottleneck with ~3.5x higher defect rate.
   - Planted seasonal December volume surge.

### 6.2 Small Story-Shape Fixtures
- `fixture_trend.csv`: Date + single metric, no useful categorical dimensions (exercises Trend story shape).
- `fixture_relationship.csv`: 8 numeric columns, no clear date or north star (exercises Relationship story shape).
- `fixture_starschema/`: `fact_orders.csv`, `dim_customers.csv`, `dim_products.csv` (exercises Star-schema story shape).

### 6.3 Messy-Data Suite (16 Behavior-Gated Files)

| File | Issue Description | Expected Behavior | Handling / Rule | `--yes` Default Behavior |
|---|---|---|---|---|
| `percentages.csv` | Mixed `0.125` and `12.5%` | **(b) Ask user** | Ambiguous scale. | Assume $\le 1.0$ is ratio scale ($0.125 = 12.5\%$). Log assumed, unconfirmed. |
| `currency_symbols.csv` | `3.400,00` vs `3,400.00` | **(b) Ask user when ambiguous** | Clean unambiguous (`$1,234.50`); ask if ambiguous (`1.234`). | Assume US locale (`.` decimal, `,` thousands). Log assumed, unconfirmed. |
| `utf8_bom.csv` | UTF-8 with Byte Order Mark | **(a) Clean & proceed** | Auto-detect `utf-8-sig`, strip BOM. | Clean and proceed. |
| `latin1.csv` | ISO-8859-1 with accents | **(a) Clean & proceed** | Auto-detect Latin-1, convert to UTF-8. | Clean and proceed. |
| `windows1252.csv` | Windows-1252 smart quotes/dashes | **(a) Clean & proceed** | Auto-detect Windows-1252, convert to UTF-8. | Clean and proceed. |
| `mixed_dates.csv` | Mixed formats (`YYYY-MM-DD`, `31/01/2024`) | **(a) Clean & proceed** | Whole-column scan: day > 12 disambiguates. | Clean and proceed. |
| `ambiguous_dates.csv` | All dates like `01/02/2024` (components $\le 12$) | **(b) Ask user** | Genuinely ambiguous date format. | Assume `MM/DD/YYYY`. Log assumed, unconfirmed. |
| `duplicate_headers.csv` | Identical or empty header names | **(a) Clean & proceed** | Deduplicate to `Sales_1`, `Sales_2`; log renaming. | Clean and proceed. |
| `duplicate_rows.csv` | Exact duplicate rows present | **(a) Clean & proceed** | Deduplicate exact rows; log `rows_removed`. | Clean and proceed. |
| `all_null_column.csv` | 100% empty column | **(a) Clean & proceed** | Drop empty column; record in cleaning log. | Clean and proceed. |
| `single_row.csv` | Boundary condition: 1 row | **(a) Clean & proceed** | Route to profile story; attach $n=1$ caveat. | Clean and proceed. |
| `no_date_data.csv` | Categorical + numeric only (no temporal) | **(a) Clean & proceed** | Route to Composition story shape. | Clean and proceed. |
| `no_numeric_data.csv` | Survey/log with only string/categorical | **(a) Clean & proceed** | Route to Frequency/Count Profile story shape. | Clean and proceed. |
| `wide_dataset.csv` | Hundreds of columns (300+ features) | **(b) Ask user** | Ask user to select primary metrics and dimensions. | Auto-select top metrics by Coefficient of Variation ($CV$). Log chosen columns. |
| `negative_values.csv` | Legitimate negative numbers (Net Income) | **(a) Clean & proceed** | Sum metrics cleanly; handle negative numbers in waterfalls/bars; protect denominators. | Clean and proceed. |
| `excel_merged_headers.xlsx`| Multi-row merged headers in Excel | **(b) Ask user** | Ask user which row contains column labels. | Auto-detect row with $\ge 80\%$ strings. Log assumed, unconfirmed. |

---

## 7. Phased Implementation Roadmap & Concrete Acceptance Criteria

> [!IMPORTANT]
> **Strict Progression Rule**: A phase does **not** start until the previous phase's acceptance commands pass with complete logged output.

### Phase 0: Foundations
- Repository package structure (`storyteller/schemas/`, `storyteller/cli.py`, `tests/`).
- Complete Pydantic schemas for all pipeline artifacts.
- Typer CLI skeleton.
- Generators for the 3 planted-truth datasets (with fixed seeds + incomplete month in Golden 1).
- Generators for the 16 messy suite files.
- Generators for the 3 story-shape fixtures (`fixture_trend.csv`, `fixture_relationship.csv`, `fixture_starschema/`).
- **Done when:**
  ```powershell
  .venv\Scripts\pytest tests/test_phase0.py -v
  .venv\Scripts\python -m storyteller --help
  ```
  Both exit with code 0; all Pydantic schemas validate roundtrip; all golden, messy, and fixture datasets exist on disk; and CLI displays help text.

### Phase 1: Ingest, Profile, Clean
- Universal reader, column semantic classifier, conservative cleaner, and reconciliation check.
- **Done when:**
  ```powershell
  .venv\Scripts\pytest tests/test_phase1.py -v
  .venv\Scripts\python -m storyteller clean tests/fixtures/messy/percentages.csv --yes
  ```
  Passes assertions that:
  1. All 16 messy-suite test cases produce their exact expected behavior from the matrix (clean, ask, or fail clearly).
  2. Reconciliation passes: `rows_in - rows_removed == rows_out` and relative metric difference $< 10^{-4}$.
  3. `cleaning_log.json` logs 100% of actions and assumptions.

### Phase 2: Facts Engine & DuckDB Dual-Compute
- KPI math, period-over-period deltas, Pareto 80/20, IQR/MAD anomalies, driver correlations, Simpson's paradox detector, partial period detector, and DuckDB dual recompute.
- **Done when:**
  ```powershell
  .venv\Scripts\pytest tests/test_phase2.py -v
  ```
  Passes assertions that:
  1. All planted truths in `golden_ecommerce.csv`, `golden_saas.csv`, and `golden_logistics.csv` are detected.
  2. Planted non-relationships (Company Size vs Churn) have $|r| < 0.10, p > 0.05$ and are not flagged as significant.
  3. 100% of numerical facts computed by Pandas match DuckDB SQL within relative tolerance $< 10^{-4}$.
  4. Simpson's paradox caveat fact is emitted for `golden_saas.csv`.
  5. Incomplete last month in `golden_ecommerce.csv` is detected and excluded from standard period comparison.

### Phase 3: LLM Narrative, Story Planner & Validator Gate
- Adaptive story-shape planner, structured LLM narrative writer with `{fact_id}` placeholders, automated code validator gate, record/replay harness, and deterministic template fallback.
- Deliberately bad mock narrative tests (invented number, nonexistent entity, direction mismatch, causal wording).
- Automated privacy test verifying no raw data rows or PII columns in LLM payloads.
- **Done when:**
  ```powershell
  .venv\Scripts\pytest tests/test_phase3.py -v
  ```
  Passes assertions that:
  1. Claim verification rate is 100% across all golden datasets.
  2. Validator strictly rejects all 4 deliberately bad mock narratives.
  3. Offline record/replay test runs with zero network access.
  4. Privacy test confirms zero raw rows and zero PII columns in any LLM payload.
  5. All story-shape fallbacks are exercised.

### Phase 4: Minimal PBIP Vertical Slice
- Templatize the hand-built Golden Power BI template provided by the user (pinned Desktop version).
- Parameterize `DataFolder` in Power Query M script.
- Automated pre-gate: JSON schema validation of report files + TMDL parse check.
- Manual Desktop check: Open in Power BI Desktop with zero repair prompts; compare 5 named values from `facts.json` against visuals; commit screenshot evidence.
- **Done when:**
  ```powershell
  .venv\Scripts\pytest tests/test_phase4_pregate.py -v
  .venv\Scripts\python -m storyteller build-pbip tests/fixtures/golden/golden_ecommerce.csv --output output/Ecommerce_Test.pbip
  ```
  Pre-gate passes, and Desktop loads the generated project cleanly with numbers matching `facts.json`.

### Phase 5: Robustness & Confirmation UX
- Interactive confirmation prompts in Typer CLI, full messy-data suite integration test, and clean error messages.
- **Done when:**
  ```powershell
  .venv\Scripts\pytest tests/test_phase5.py -v
  ```
  Each of the 16 messy files produces its exact expected behavior from the matrix (clean, ask, or fail clearly).

### Phase 6: Visual Excellence & 2 Curated Themes
- 2 publication-grade themes: Light Executive Slate and Dark Midnight Obsidian.
- Visual hierarchy layout engine with automated bounds/overlap checking (12-column grid, no visual clipping).
- Dynamic DAX headline card measures using `KEEPFILTERS`.
- Human story-quality rubric (Headline clarity, Relevance, Non-obviousness, Action usefulness, Chart fit) scored 1-5 across 5 datasets (target average $\ge 4.0$).
- **Done when:**
  ```powershell
  .venv\Scripts\pytest tests/test_phase6.py -v
  ```
  Automated layout validator confirms zero visual container overlaps; both themes generate valid report JSON; and story-quality rubric evaluation document is generated.

### Phase 7 (Optional): Web Studio
- Built only if the CLI pipeline is fully verified and stable.
- Local FastAPI app allowing file upload, interactive confirm step, and lightweight executive preview.
- **Strictly no pixel-matching Power BI in the browser.**
- **Done when:**
  ```powershell
  .venv\Scripts\python -m storyteller studio --port 8000
  ```
  Web server launches, accepts an uploaded dataset, guides through the confirm step, renders the story preview, and exports the `.pbip` bundle.
