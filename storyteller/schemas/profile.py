"""Pydantic schemas for the Profiling stage."""

from enum import Enum
from typing import List, Optional, Any
from pydantic import BaseModel, Field


class SemanticRole(str, Enum):
    TEMPORAL = "temporal"
    IDENTIFIER = "identifier"
    METRIC_ADDITIVE = "metric_additive"
    METRIC_RATIO = "metric_ratio"
    METRIC_NON_ADDITIVE = "metric_non_additive"
    METRIC_SEMI_ADDITIVE = "metric_semi_additive"
    DIMENSION_CATEGORICAL = "dimension_categorical"
    DIMENSION_ORDINAL = "dimension_ordinal"
    DIMENSION_HIERARCHY_CANDIDATE = "dimension_hierarchy_candidate"
    TEXT_FREE = "text_free"
    UNKNOWN = "unknown"


class AggregationRule(str, Enum):
    SUM = "SUM"
    RATIO_OF_SUMS = "RATIO_OF_SUMS"
    AVERAGE = "AVERAGE"
    LAST_OVER_TIME = "LAST_OVER_TIME"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    NONE = "NONE"


class ColumnProfile(BaseModel):
    name: str = Field(description="Column name")
    inferred_dtype: str = Field(description="Inferred physical data type (int, float, date, string, bool)")
    semantic_role: SemanticRole = Field(description="Assigned semantic role")
    aggregation_rule: AggregationRule = Field(default=AggregationRule.NONE, description="Valid aggregation method")
    null_rate: float = Field(ge=0.0, le=1.0, description="Proportion of missing values")
    distinct_count: int = Field(ge=0, description="Number of unique non-null values")
    min_value: Optional[Any] = Field(default=None, description="Minimum value")
    max_value: Optional[Any] = Field(default=None, description="Maximum value")
    mean: Optional[float] = Field(default=None, description="Mean for numerical columns")
    std_dev: Optional[float] = Field(default=None, description="Standard deviation for numerical columns")
    coefficient_of_variation: Optional[float] = Field(default=None, description="sigma / abs(mu) for wide-file ranking")
    skew: Optional[float] = Field(default=None, description="Statistical skewness")
    sample_values: List[Any] = Field(default_factory=list, description="Sanitized, non-PII sample values")
    is_pii: bool = Field(default=False, description="Whether column was flagged as potential PII")
    role_confidence: float = Field(ge=0.0, le=1.0, default=1.0, description="Confidence score of role assignment")
    role_reasoning: str = Field(default="", description="Rule or LLM explanation for role assignment")


class DataProfile(BaseModel):
    table_name: str = Field(description="Name of the profiled table")
    total_rows: int = Field(ge=0, description="Total rows in dataset")
    total_columns: int = Field(ge=0, description="Total columns in dataset")
    columns: List[ColumnProfile] = Field(description="Profile for each column")
    primary_date_column: Optional[str] = Field(default=None, description="Inferred primary temporal column")
    suggested_north_star: Optional[str] = Field(default=None, description="Inferred primary KPI metric")
    detected_grain: Optional[str] = Field(default=None, description="Inferred row grain")
    quality_issues: List[str] = Field(default_factory=list, description="List of detected anomalies or quality issues")
