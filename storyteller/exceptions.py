"""StoryBI Exception Classes."""

from typing import Optional, List, Any


class StoryBIError(Exception):
    """Base exception for all StoryBI errors."""
    pass


class IngestionError(StoryBIError):
    """Raised when a dataset cannot be read or parsed."""
    pass


class ProfilingError(StoryBIError):
    """Raised when profiling fails."""
    pass


class ReconciliationError(StoryBIError):
    """Raised when data cleaning reconciliation fails (rows or metric sums mismatch)."""
    pass


class UserConfirmationRequired(StoryBIError):
    """Raised when an ambiguous data situation requires user input (and --yes is not set)."""

    def __init__(
        self,
        issue_type: str,
        message: str,
        options: Optional[List[str]] = None,
        default_assumption: Optional[Any] = None,
    ):
        super().__init__(message)
        self.issue_type = issue_type
        self.message = message
        self.options = options or []
        self.default_assumption = default_assumption
