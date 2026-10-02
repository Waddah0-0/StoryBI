"""Pydantic schemas for the Ingestion stage."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class TableInfo(BaseModel):
    name: str = Field(description="Name of the table or sheet")
    row_count: int = Field(ge=0, description="Total number of rows in the table")
    column_count: int = Field(ge=0, description="Total number of columns in the table")
    columns: List[str] = Field(description="List of detected column names")
    sample_preview: List[Dict[str, Any]] = Field(default_factory=list, description="Non-PII head sample records")


class IngestReport(BaseModel):
    file_path: str = Field(description="Original file path or URI")
    file_format: str = Field(description="Detected format (csv, tsv, xlsx, parquet, json, sqlite)")
    encoding: str = Field(default="utf-8", description="Detected text encoding")
    delimiter: Optional[str] = Field(default=None, description="Detected delimiter for delimited files")
    has_bom: bool = Field(default=False, description="Whether Byte Order Mark was detected")
    tables: List[TableInfo] = Field(description="List of ingested tables or sheets")
    warnings: List[str] = Field(default_factory=list, description="Warnings encountered during ingestion")
