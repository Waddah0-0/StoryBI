"""Pydantic schemas for Story Planning."""

from enum import Enum
from typing import List
from pydantic import BaseModel, Field


class StoryShape(str, Enum):
    PERFORMANCE = "performance"
    COMPOSITION = "composition"
    TREND = "trend"
    RELATIONSHIP = "relationship"
    STAR_SCHEMA = "star_schema"
    PROFILE = "profile"


class PagePlan(BaseModel):
    page_number: int = Field(ge=1, description="Page sequence number")
    page_title: str = Field(description="Action-oriented page title stating the core finding")
    act_type: str = Field(description="Narrative role: hook, context_drivers, nuance_anomalies, prescriptive_actions")
    headline_claim: str = Field(description="Single takeaway message for this page")
    primary_fact_ids: List[str] = Field(description="Core fact IDs supporting this page")
    supporting_fact_ids: List[str] = Field(default_factory=list, description="Additional context fact IDs")
    suggested_visual_types: List[str] = Field(description="Recommended charts (card, line, bar, waterfall, scatter, table)")


class StoryPlan(BaseModel):
    story_shape: StoryShape = Field(description="Selected story archetype based on dataset structure")
    shape_rationale: str = Field(description="Explanation of why this shape was selected")
    executive_headline: str = Field(description="Overarching takeaway across all pages")
    pages: List[PagePlan] = Field(description="Planned pages matching the selected shape")
