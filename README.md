# StoryBI

> Autonomous LLM-Powered Storytelling Agent for Power BI.

StoryBI takes any tabular dataset and produces a complete Power BI Project (`.pbip`) that tells an accurate, well-designed executive data story.

## Core Guarantees
- **Accuracy First:** Python computes every number; the LLM references `{fact_id.field:format}` placeholders.
- **Dual Recompute:** Critical facts are computed in Pandas and cross-checked with in-process DuckDB SQL.
- **Reconciliation:** $\text{rows\_in} - \text{rows\_removed} == \text{rows\_out}$ and metric sums match within relative tolerance $< 10^{-4}$.
- **Zero Hallucination:** 100% claim verification gate with regex unquoted number scan, causal language lint, and directional checks.
- **Privacy:** Only aggregated facts and column metadata are sent to the LLM; raw data rows and PII are never sent.
- **Template-Driven PBIP:** Rendered from a verified golden Power BI template with relative data folder parameterization.

## Quickstart

```powershell
# Run test suite
.venv\Scripts\pytest -v

# Inspect CLI
.venv\Scripts\python -m storyteller --help
```
