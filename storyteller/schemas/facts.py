"""Pydantic schemas for the Facts Engine & Verified Fact Registry."""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class Fact(BaseModel):
    id: str = Field(description="Unique fact identifier, e.g. F001")
    type: str = Field(description="Type of fact: total, period_change, pareto_share, correlation, anomaly, segment_ranking, caveat")
    metric: str = Field(description="Associated metric name")
    period: Optional[str] = Field(default=None, description="Time period or comparison span, e.g. '2024-Q3 vs 2024-Q2'")
    dimension: Optional[str] = Field(default=None, description="Associated dimension if segmented, e.g. 'Category'")
    dimension_value: Optional[str] = Field(default=None, description="Specific dimension value, e.g. 'Technology'")
    value: float = Field(description="Primary numerical value (e.g. 0.184 for +18.4% or 1250000.0 for Total Revenue)")
    components: Dict[str, Any] = Field(default_factory=dict, description="Underlying components e.g. {'current': 1250000, 'previous': 1055000}")
    method: str = Field(description="Calculation method description")
    n: int = Field(ge=0, description="Sample size underlying this fact")
    confidence: str = Field(default="high", description="'high', 'medium', or 'low'")
    caveats: List[str] = Field(default_factory=list, description="Specific caveats attached to this fact")
    dual_recompute_match: bool = Field(default=True, description="Whether independent DuckDB SQL recomputation matched")
    relative_recompute_diff: float = Field(default=0.0, description="Relative difference between Pandas and DuckDB computation")
    importance_score: float = Field(ge=0.0, le=1.0, default=0.5, description="Significance ranking for story selection")


class FactRegistry(BaseModel):
    dataset_name: str = Field(description="Name of the analyzed dataset")
    total_facts: int = Field(ge=0, description="Number of facts registered")
    facts: List[Fact] = Field(description="List of verified facts")
    north_star_metric: Optional[str] = Field(default=None, description="Primary metric around which facts are centered")
    recompute_validation_passed: bool = Field(default=True, description="Whether 100% of numerical facts passed dual recompute")
