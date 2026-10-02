"""Pydantic schemas for the Dataset Confirmation stage."""

from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from storyteller.schemas.profile import SemanticRole


class ColumnSpec(BaseModel):
    name: str = Field(description="Column name")
    role: SemanticRole = Field(description="Confirmed semantic role")
    display_name: str = Field(description="User-friendly display label")
    format_string: Optional[str] = Field(default=None, description="DAX/Power BI formatting string")


class DatasetSpec(BaseModel):
    dataset_name: str = Field(description="Short identifier for dataset")
    grain: str = Field(description="Confirmed entity grain (e.g. 'one order line per row')")
    north_star_metric: Optional[str] = Field(default=None, description="Confirmed primary north-star KPI")
    primary_date_column: Optional[str] = Field(default=None, description="Confirmed primary date column, if any")
    columns: Dict[str, ColumnSpec] = Field(description="Mapping of column names to approved specs")
    focus_metrics: List[str] = Field(description="Ordered list of primary metrics to highlight")
    focus_dimensions: List[str] = Field(description="Ordered list of primary categorical dimensions")
    caveats: List[str] = Field(default_factory=list, description="Unconfirmed assumptions or caveats carried to story")
