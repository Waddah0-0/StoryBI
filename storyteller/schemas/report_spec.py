"""Pydantic schemas for Report Specification (report_spec.json)."""

from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field


class VisualPosition(BaseModel):
    x: int = Field(ge=0, description="Horizontal coordinate on 1280 canvas")
    y: int = Field(ge=0, description="Vertical coordinate on 720 canvas")
    width: int = Field(gt=0, description="Pixel width")
    height: int = Field(gt=0, description="Pixel height")
    z: int = Field(default=0, description="Z-index layering")


class VisualBinding(BaseModel):
    category_column: Optional[str] = Field(default=None, description="Dimension for X-axis / categories")
    measure_names: List[str] = Field(default_factory=list, description="DAX measures / metric names bound to Y-axis / values")
    series_column: Optional[str] = Field(default=None, description="Legend / breakdown dimension")
    secondary_metric: Optional[str] = Field(default=None, description="Secondary metric (e.g. for scatter Y-axis or Pareto line)")


class VisualSpec(BaseModel):
    id: str = Field(description="Unique visual container ID on page")
    title: str = Field(description="Chart title in plain language")
    visual_type: str = Field(description="card, line, clustered_bar, waterfall, scatter, table, textbox")
    position: VisualPosition = Field(description="Visual layout position and dimensions")
    bindings: VisualBinding = Field(default_factory=VisualBinding, description="Data field bindings")
    text_content: Optional[str] = Field(default=None, description="Resolved text content if textbox")
    format_options: Dict[str, Any] = Field(default_factory=dict, description="Visual-specific formatting settings")


class PageSpec(BaseModel):
    page_number: int = Field(ge=1, description="Page index")
    name: str = Field(description="System identifier for page")
    display_name: str = Field(description="User-facing page tab label")
    action_title: str = Field(description="Top headline insight banner for page")
    visuals: List[VisualSpec] = Field(description="List of visuals on this page (max 6)")


class ThemeSpec(BaseModel):
    theme_name: str = Field(description="Name of theme: light_executive_slate or dark_midnight_obsidian")
    palette: List[str] = Field(description="Hex color codes for data series")
    background_color: str = Field(description="Canvas background hex")
    card_background: str = Field(description="Visual container background hex")
    primary_text: str = Field(description="Primary text hex")
    secondary_text: str = Field(description="Muted/secondary text hex")
    positive_accent: str = Field(description="Growth/positive accent hex (Emerald)")
    negative_accent: str = Field(description="Decline/alert accent hex (Coral/Rose)")


class ReportSpec(BaseModel):
    report_title: str = Field(description="Executive report title")
    canvas_width: int = Field(default=1280, description="Report canvas width in pixels")
    canvas_height: int = Field(default=720, description="Report canvas height in pixels")
    theme: ThemeSpec = Field(description="Color palette and formatting theme")
    pages: List[PageSpec] = Field(description="Complete page specifications")
