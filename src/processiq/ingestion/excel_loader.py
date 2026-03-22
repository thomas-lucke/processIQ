"""Excel file loader for ProcessIQ.

Loads process step data from Excel files (.xlsx, .xls) into ProcessData models.
Uses pandas with openpyxl engine for .xlsx files.
"""

import logging
from io import BytesIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from pydantic import ValidationError as PydanticValidationError

from processiq.exceptions import ExtractionError, ValidationError

# Reuse column mapping logic from csv_loader
from processiq.ingestion.csv_loader import (
    _convert_dtypes,
    _map_columns,
    _validate_required_columns,
)
from processiq.models.process import ProcessData, ProcessStep

logger = logging.getLogger(__name__)


def _detect_header_row(df: pd.DataFrame, max_rows: int = 10) -> int:
    """Detect which row contains headers by looking for expected column patterns.

    Args:
        df: DataFrame read without headers (header=None).
        max_rows: Maximum rows to scan for headers.

    Returns:
        Row index containing headers (0-based).
    """
    # Keywords that suggest a header row
    header_keywords = {
        "step",
        "name",
        "time",
        "hours",
        "resources",
        "cost",
        "error",
        "rate",
        "depends",
        "task",
        "activity",
        "duration",
    }

    for idx in range(min(max_rows, len(df))):
        row = df.iloc[idx]
        row_text = " ".join(str(v).lower() for v in row if pd.notna(v))
        matches = sum(1 for kw in header_keywords if kw in row_text)
        if matches >= 2:  # At least 2 header keywords found
            logger.debug("Detected header row at index %d", idx)
            return idx

    return 0  # Default to first row


def _df_to_process_steps(df: pd.DataFrame) -> list[ProcessStep]:
    """Convert DataFrame rows to ProcessStep models.

    Args:
        df: DataFrame with process step data.

    Returns:
        List of validated ProcessStep objects.

    Raises:
        ValidationError: If all rows fail validation.
    """
    steps: list[ProcessStep] = []
    errors: list[str] = []

    for idx, row in df.iterrows():
        try:
            step_data = row.to_dict()
            # Remove NaN values and ensure string keys
            step_data = {str(k): v for k, v in step_data.items() if pd.notna(v)}
            step = ProcessStep(**step_data)  # type: ignore[misc]
            steps.append(step)
        except PydanticValidationError as e:
            row_num = int(idx) + 2 if isinstance(idx, int | float) else idx
            errors.append(f"Row {row_num}: {e.error_count()} validation error(s)")
            logger.warning("Validation error in row %s: %s", row_num, e)

    if errors and not steps:
        raise ValidationError(
            message=f"All rows failed validation: {errors}",
            field="rows",
            user_message="All rows in the Excel file failed validation. Please check the data format.",
        )

    if errors:
        logger.warning("Skipped %d invalid rows out of %d total", len(errors), len(df))

    return steps


def load_excel(
    source: str | Path | BinaryIO | bytes,
    process_name: str = "Imported Process",
    sheet_name: str | int = 0,
    header_row: int | None = None,
) -> ProcessData:
    """Load process data from an Excel file.

    Args:
        source: File path, file object, or raw Excel bytes.
        process_name: Name to assign to the imported process.
        sheet_name: Sheet name or index to read (default: first sheet).
        header_row: Row index containing headers (0-based). If None, auto-detect.

    Returns:
        ProcessData with validated process steps.

    Raises:
        ExtractionError: If file cannot be read or parsed.
        ValidationError: If data validation fails.

    Example:
        >>> data = load_excel("process.xlsx", process_name="Order Fulfillment")
        >>> print(f"Loaded {len(data.steps)} steps")
    """
    logger.info("Loading Excel from %s", type(source).__name__)

    # Prepare source for pandas
    if isinstance(source, str | Path):
        path = Path(source)
        if not path.exists():
            raise ExtractionError(
                message=f"File not found: {path}",
                source=str(path),
                user_message=f"The file '{path.name}' was not found.",
            )
        excel_source: str | Path | BytesIO = path
    elif isinstance(source, bytes):
        excel_source = BytesIO(source)
    else:
        # Must be BinaryIO (file-like object) - all other types handled above
        file_obj: BinaryIO = source
        content = file_obj.read()
        file_obj.seek(0)
        # Excel files are binary; content should always be bytes
        if not isinstance(content, bytes):
            content = (
                bytes(content)
                if isinstance(content, bytearray | memoryview)
                else content.encode("utf-8")
            )
        excel_source = BytesIO(content)

    try:
        # If header_row not specified, read without headers first to detect
        if header_row is None:
            preview_df = pd.read_excel(
                excel_source,
                sheet_name=sheet_name,
                header=None,
                nrows=15,
                engine="openpyxl",
            )
            header_row = _detect_header_row(preview_df)
            # Reset source position if BytesIO
            if isinstance(excel_source, BytesIO):
                excel_source.seek(0)

        # Read Excel with detected/specified header row
        df = pd.read_excel(
            excel_source,
            sheet_name=sheet_name,
            header=header_row,
            engine="openpyxl",
            dtype=str,  # Read as string first, convert later
        )

        logger.debug("Read Excel with %d rows, %d columns", len(df), len(df.columns))

    except FileNotFoundError as e:
        raise ExtractionError(
            message=f"File not found: {e}",
            source="excel",
            user_message="The Excel file was not found.",
        ) from e
    except ValueError as e:
        # Sheet not found, invalid file, etc.
        raise ExtractionError(
            message=f"Failed to read Excel: {e}",
            source="excel",
            user_message=f"Could not read the Excel file: {e}",
        ) from e
    except Exception as e:
        # openpyxl or pandas errors
        raise ExtractionError(
            message=f"Excel parsing error: {e}",
            source="excel",
            user_message="The Excel file could not be parsed. Ensure it's a valid .xlsx file.",
        ) from e

    if df.empty:
        raise ExtractionError(
            message="Excel sheet has no data rows",
            source="excel",
            user_message="The Excel sheet has headers but no data rows.",
        )

    # Clean column names (strip whitespace)
    df.columns = pd.Index([str(c).strip() for c in df.columns])

    # Drop rows that are completely empty
    df = df.dropna(how="all")

    # Drop columns that are completely empty
    df = df.dropna(axis=1, how="all")

    # Map column names to standard names
    df = _map_columns(df)

    # Validate required columns
    _validate_required_columns(df)

    # Convert data types
    df = _convert_dtypes(df)

    # Convert to ProcessStep models
    steps = _df_to_process_steps(df)

    logger.info("Successfully loaded %d process steps from Excel", len(steps))

    return ProcessData(name=process_name, steps=steps)


def load_excel_from_bytes(
    data: bytes,
    process_name: str = "Imported Process",
    sheet_name: str | int = 0,
) -> ProcessData:
    """Convenience function for loading Excel from bytes (e.g., multipart file upload).

    Args:
        data: Raw Excel file bytes.
        process_name: Name for the process.
        sheet_name: Sheet name or index to read.

    Returns:
        ProcessData with validated process steps.
    """
    return load_excel(BytesIO(data), process_name=process_name, sheet_name=sheet_name)


def list_sheets(source: str | Path | BinaryIO | bytes) -> list[str]:
    """List available sheet names in an Excel file.

    Args:
        source: File path, file object, or raw Excel bytes.

    Returns:
        List of sheet names.

    Example:
        >>> sheets = list_sheets("multi_sheet.xlsx")
        >>> print(sheets)  # ['Process Data', 'Constraints', 'Notes']
    """
    if isinstance(source, str | Path):
        path = Path(source)
        if not path.exists():
            raise ExtractionError(
                message=f"File not found: {path}",
                source=str(path),
                user_message=f"The file '{path.name}' was not found.",
            )
        excel_source: str | Path | BytesIO = path
    elif isinstance(source, bytes):
        excel_source = BytesIO(source)
    else:
        excel_source = source  # type: ignore[assignment]

    try:
        xl = pd.ExcelFile(excel_source, engine="openpyxl")
        # sheet_names is typed as list[int | str] but always returns strings for .xlsx
        return [str(name) for name in xl.sheet_names]
    except Exception as e:
        raise ExtractionError(
            message=f"Failed to read Excel sheets: {e}",
            source="excel",
            user_message="Could not read the Excel file structure.",
        ) from e
