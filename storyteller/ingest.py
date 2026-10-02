"""Universal Data Ingestion Module."""

import json
import sqlite3
from pathlib import Path
from typing import Dict, Tuple, Optional, Any, List

import pandas as pd

from storyteller.exceptions import IngestionError
from storyteller.schemas.ingest import IngestReport, TableInfo


def detect_encoding_and_bom(file_path: Path) -> Tuple[str, bool]:
    """Detect file encoding and whether a UTF-8 BOM is present."""
    with open(file_path, "rb") as f:
        raw_prefix = f.read(4)

    if raw_prefix.startswith(b"\xef\xbb\xbf"):
        return "utf-8-sig", True

    # Test encodings in order
    encodings_to_try = ["utf-8", "cp1252", "iso-8859-1"]
    with open(file_path, "rb") as f:
        raw_bytes = f.read(65536)

    for enc in encodings_to_try:
        try:
            raw_bytes.decode(enc)
            return enc, False
        except (UnicodeDecodeError, LookupError):
            continue

    return "utf-8", False


def detect_delimiter(file_path: Path, encoding: str) -> str:
    """Sniff delimiter for delimited text files."""
    try:
        with open(file_path, "r", encoding=encoding, errors="replace") as f:
            lines = [f.readline() for _ in range(5)]
            sample = "\n".join(l for l in lines if l.strip())

        counts = {
            ",": sample.count(","),
            "\t": sample.count("\t"),
            ";": sample.count(";"),
            "|": sample.count("|"),
        }
        best = max(counts.items(), key=lambda kv: kv[1])
        return best[0] if best[1] > 0 else ","
    except Exception:
        return ","


TABULAR_EXTENSIONS = {".csv", ".tsv", ".txt", ".xlsx", ".xls", ".parquet", ".pq", ".json", ".db", ".sqlite", ".sqlite3"}


def _ingest_single_file(
    path: Path,
    default_table_name: str = "main",
) -> Tuple[Dict[str, pd.DataFrame], List[TableInfo], List[str], str, str, Optional[str], bool]:
    """Internal helper to ingest a single tabular file."""
    ext = path.suffix.lower()
    frames: Dict[str, pd.DataFrame] = {}
    table_infos: List[TableInfo] = []
    warnings: List[str] = []
    detected_format = ext.lstrip(".")
    detected_encoding = "utf-8"
    has_bom = False
    delimiter: Optional[str] = None

    if ext in [".csv", ".tsv", ".txt"]:
        detected_encoding, has_bom = detect_encoding_and_bom(path)
        delimiter = "\t" if ext == ".tsv" else detect_delimiter(path, detected_encoding)
        detected_format = "tsv" if delimiter == "\t" else "csv"

        # Check if there are duplicate header names in raw line
        with open(path, "r", encoding=detected_encoding, errors="replace") as f:
            first_line = f.readline().strip()
            raw_headers = [h.strip() for h in first_line.split(delimiter)]
            if len(raw_headers) != len(set(raw_headers)):
                warnings.append("Duplicate headers detected in raw input file")

        df = pd.read_csv(
            path,
            encoding=detected_encoding,
            sep=delimiter,
            engine="python",
        )
        frames[default_table_name] = df
        table_infos.append(
            TableInfo(
                name=default_table_name,
                row_count=len(df),
                column_count=len(df.columns),
                columns=df.columns.astype(str).tolist(),
                sample_preview=df.head(5).to_dict(orient="records"),
            )
        )

    elif ext in [".xlsx", ".xls"]:
        detected_format = "xlsx"
        excel_file = pd.ExcelFile(path)
        for sheet_name in excel_file.sheet_names:
            df = excel_file.parse(sheet_name)
            tbl_key = sheet_name if default_table_name == "main" else f"{default_table_name}_{sheet_name}"
            frames[tbl_key] = df
            table_infos.append(
                TableInfo(
                    name=tbl_key,
                    row_count=len(df),
                    column_count=len(df.columns),
                    columns=df.columns.astype(str).tolist(),
                    sample_preview=df.head(5).to_dict(orient="records"),
                )
            )

    elif ext in [".parquet", ".pq"]:
        detected_format = "parquet"
        df = pd.read_parquet(path)
        frames[default_table_name] = df
        table_infos.append(
            TableInfo(
                name=default_table_name,
                row_count=len(df),
                column_count=len(df.columns),
                columns=df.columns.astype(str).tolist(),
                sample_preview=df.head(5).to_dict(orient="records"),
            )
        )

    elif ext == ".json":
        detected_format = "json"
        detected_encoding, has_bom = detect_encoding_and_bom(path)
        with open(path, "r", encoding=detected_encoding) as f:
            raw_text = f.read().lstrip("\ufeff")
            data = json.loads(raw_text)
        if isinstance(data, list):
            df = pd.json_normalize(data)
        elif isinstance(data, dict):
            df = pd.DataFrame(data)
        else:
            raise IngestionError(f"Unsupported JSON structure in {path}")

        frames[default_table_name] = df
        table_infos.append(
            TableInfo(
                name=default_table_name,
                row_count=len(df),
                column_count=len(df.columns),
                columns=df.columns.astype(str).tolist(),
                sample_preview=df.head(5).to_dict(orient="records"),
            )
        )

    elif ext in [".db", ".sqlite", ".sqlite3"]:
        detected_format = "sqlite"
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall() if not row[0].startswith("sqlite_")]

        for tbl in tables:
            df = pd.read_sql_query(f"SELECT * FROM \"{tbl}\"", conn)
            tbl_key = tbl if default_table_name == "main" else f"{default_table_name}_{tbl}"
            frames[tbl_key] = df
            table_infos.append(
                TableInfo(
                    name=tbl_key,
                    row_count=len(df),
                    column_count=len(df.columns),
                    columns=df.columns.astype(str).tolist(),
                    sample_preview=df.head(5).to_dict(orient="records"),
                )
            )
        conn.close()

    else:
        raise IngestionError(f"Unsupported file format: {ext}")

    return frames, table_infos, warnings, detected_format, detected_encoding, delimiter, has_bom


def ingest_file(file_path: Path | str) -> Tuple[Dict[str, pd.DataFrame], IngestReport]:
    """Ingest any dataset (file or directory) into a dictionary of DataFrames and an IngestReport."""
    path = Path(file_path)
    if not path.exists():
        raise IngestionError(f"File not found: {path}")

    try:
        if path.is_dir():
            tabular_files = [
                f for f in sorted(path.iterdir())
                if f.is_file()
                and f.suffix.lower() in TABULAR_EXTENSIONS
                and not f.name.startswith("~$")
                and not f.name.startswith(".")
            ]
            if not tabular_files:
                raise IngestionError(f"No tabular files found in directory: {path}")

            frames: Dict[str, pd.DataFrame] = {}
            table_infos: List[TableInfo] = []
            warnings: List[str] = []

            for tab_file in tabular_files:
                f_frames, f_infos, f_warns, _, _, _, _ = _ingest_single_file(tab_file, default_table_name=tab_file.stem)
                frames.update(f_frames)
                table_infos.extend(f_infos)
                warnings.extend(f_warns)

            report = IngestReport(
                file_path=str(path.resolve()),
                file_format="directory",
                encoding="utf-8",
                delimiter=None,
                has_bom=False,
                tables=table_infos,
                warnings=warnings,
            )
            return frames, report

        frames, table_infos, warnings, detected_format, detected_encoding, delimiter, has_bom = _ingest_single_file(path, "main")

    except Exception as e:
        if isinstance(e, IngestionError):
            raise
        raise IngestionError(f"Failed to ingest {path}: {str(e)}") from e

    report = IngestReport(
        file_path=str(path.resolve()),
        file_format=detected_format,
        encoding=detected_encoding,
        delimiter=delimiter,
        has_bom=has_bom,
        tables=table_infos,
        warnings=warnings,
    )
    return frames, report
