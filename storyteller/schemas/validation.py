"""Pydantic schemas for the Narrative Validator Gate."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class CheckType(str, Enum):
    PLACEHOLDER_RESOLUTION = "placeholder_resolution"
    NO_UNQUOTED_NUMBERS = "no_unquoted_numbers"
    DIRECTIONAL_ALIGNMENT = "directional_alignment"
    CAUSAL_LANGUAGE_LINT = "causal_language_lint"
    ENTITY_EXISTENCE = "entity_existence"
    CONFIDENCE_CAVEAT_INCLUSION = "confidence_caveat_inclusion"
    HEADLINE_HIGH_CONFIDENCE_BACKING = "headline_high_confidence_backing"


class ValidationIssue(BaseModel):
    check_type: CheckType = Field(description="Validation check category")
    page_number: Optional[int] = Field(default=None, description="Page where issue occurred")
    failed_text: str = Field(description="Offending text snippet")
    reason: str = Field(description="Detailed explanation of failure")


class ValidationReport(BaseModel):
    passed: bool = Field(description="True if zero validation issues exist")
    claim_verification_rate: float = Field(ge=0.0, le=1.0, description="Proportion of claims fully verified (must be 1.0)")
    total_claims_checked: int = Field(ge=0, description="Total verified statements scanned")
    passed_claims: int = Field(ge=0, description="Number of verified statements passing all checks")
    issues: List[ValidationIssue] = Field(default_factory=list, description="List of lint or verification errors")
    retry_count: int = Field(ge=0, default=0, description="Number of retry attempts made")
    fell_back_to_template: bool = Field(default=False, description="Whether deterministic template fallback was triggered")
