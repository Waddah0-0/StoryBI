"""Pydantic schemas for the Cleaning & Reconciliation stage."""

from typing import List, Dict, Optional
from pydantic import BaseModel, Field


class CleaningAction(BaseModel):
    action_type: str = Field(description="Type of cleaning performed (e.g. strip_whitespace, parse_currency, deduplicate)")
    target_column: Optional[str] = Field(default=None, description="Column modified, or None if table-level")
    rows_affected: int = Field(ge=0, default=0, description="Number of rows modified or removed")
    details: str = Field(description="Human-readable description of transformation")
    is_assumption: bool = Field(default=False, description="Whether this change was an unconfirmed assumption")
    assumption_caveat: Optional[str] = Field(default=None, description="Caveat message if assumed under --yes")


class MetricReconciliation(BaseModel):
    metric_name: str = Field(description="Name of the additive metric checked")
    sum_before: float = Field(description="Metric sum before cleaning")
    sum_after: float = Field(description="Metric sum after cleaning")
    relative_difference: float = Field(description="abs(sum_after - sum_before) / (abs(sum_before) + 1e-9)")
    is_valid: bool = Field(description="Whether relative difference is within 1e-4 tolerance")


class ReconciliationReport(BaseModel):
    rows_in: int = Field(ge=0, description="Row count before cleaning")
    rows_removed: int = Field(ge=0, default=0, description="Row count removed (e.g. exact duplicates)")
    rows_out: int = Field(ge=0, description="Row count after cleaning")
    is_row_reconciliation_valid: bool = Field(description="True if rows_in - rows_removed == rows_out")
    metrics: List[MetricReconciliation] = Field(default_factory=list, description="Per-metric sum reconciliation checks")
    passed: bool = Field(description="Overall pass status (all row and metric checks valid)")


class CleaningLog(BaseModel):
    table_name: str = Field(description="Name of the cleaned table")
    actions: List[CleaningAction] = Field(default_factory=list, description="All actions executed during cleaning")
    total_rows_removed: int = Field(ge=0, default=0, description="Total duplicate rows dropped")
    reconciliation: ReconciliationReport = Field(description="Mathematical reconciliation verification")
    assumptions: List[str] = Field(default_factory=list, description="Unconfirmed assumptions logged under --yes")
