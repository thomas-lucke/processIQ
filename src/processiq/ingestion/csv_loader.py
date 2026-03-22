"""CSV file loader for ProcessIQ.

Loads process step data from CSV files into ProcessData models.
Handles common issues: encoding, delimiters, missing columns.
"""

import logging
import re
from io import BytesIO, StringIO
from pathlib import Path
from typing import BinaryIO

import pandas as pd
from pydantic import ValidationError as PydanticValidationError

from processiq.exceptions import ExtractionError, ValidationError
from processiq.models.process import ProcessData, ProcessStep

logger = logging.getLogger(__name__)

# Required columns (must be present)
REQUIRED_COLUMNS = {"step_name", "average_time_hours", "resources_needed"}

# Common column name variations for auto-mapping
COLUMN_ALIASES: dict[str, list[str]] = {
    "step_name": [
        "step",
        "name",
        "step_name",
        "process_step",
        "task",
        "activity",
        "step_name_",
        "task_name",
        "activity_name",
    ],
    "average_time_hours": [
        "time",
        "hours",
        "duration",
        "avg_time",
        "time_hours",
        "average_time",
        "time_hours_",
        "duration_hours",
        "cycle_time",
    ],
    "resources_needed": [
        "resources",
        "people",
        "headcount",
        "staff",
        "fte",
        "people_needed",
        "resources_needed",
        "num_people",
        "team_size",
    ],
    "error_rate_pct": [
        "error_rate",
        "error",
        "errors",
        "defect_rate",
        "rework_rate",
        "error_pct",
        "failure_rate",
        "failure_rate_",
        "error_rate_pct",
    ],
    "cost_per_instance": [
        "cost",
        "unit_cost",
        "cost_per_unit",
        "price",
        "expense",
        "cost_",
        "cost_per_instance",
        "cost_per_run",
    ],
    "depends_on": [
        "dependencies",
        "depends",
        "predecessors",
        "after",
        "requires",
        "depends_on",
        "prerequisites",
        "prerequisite",
        "blocked_by",
    ],
}


def _normalize_column_name(col: str) -> str:
    """Normalize column name for matching (lowercase, strip, replace spaces).

    Also removes common suffixes like (hours), ($), %, etc.
    """
    normalized = col.lower().strip()
    # Remove parenthetical suffixes like (hours), ($), (%)
    normalized = re.sub(r"\s*\([^)]*\)\s*$", "", normalized)
    # Remove standalone currency/percent symbols at end
    normalized = re.sub(r"\s*[$%]+\s*$", "", normalized)
    # Replace spaces and hyphens with underscores
    normalized = normalized.replace(" ", "_").replace("-", "_")
    # Remove trailing underscores
    normalized = normalized.rstrip("_")
    return normalized


def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Map common column name variations to expected names.

    Args:
        df: DataFrame with potentially non-standard column names.

    Returns:
        DataFrame with standardized column names.
    """
    column_mapping: dict[str, str] = {}
    normalized_cols = {_normalize_column_name(c): c for c in df.columns}

    for standard_name, aliases in COLUMN_ALIASES.items():
        # Check if standard name already exists
        if standard_name in df.columns:
            continue

        # Look for aliases
        for alias in aliases:
            normalized_alias = _normalize_column_name(alias)
            if normalized_alias in normalized_cols:
                original_col = normalized_cols[normalized_alias]
                column_mapping[original_col] = standard_name
                logger.debug("Mapped column '%s' -> '%s'", original_col, standard_name)
                break

    if column_mapping:
        df = df.rename(columns=column_mapping)
        logger.info("Mapped %d columns to standard names", len(column_mapping))

    return df


def _validate_required_columns(df: pd.DataFrame) -> None:
    """Check that all required columns are present.

    Args:
        df: DataFrame to validate.

    Raises:
        ValidationError: If required columns are missing.
    """
    present_columns = set(df.columns)
    missing = REQUIRED_COLUMNS - present_columns

    if missing:
        raise ValidationError(
            message=f"Missing required columns: {missing}",
            field="columns",
            value=str(list(df.columns)),
            user_message=f"The CSV is missing required columns: {', '.join(sorted(missing))}. "
            f"Expected columns: {', '.join(sorted(REQUIRED_COLUMNS))}",
        )


def _parse_csv_content(
    content: str | bytes,
    delimiter: str | None = None,
    encoding: str = "utf-8",
) -> pd.DataFrame:
    """Parse CSV content into DataFrame with error handling.

    Args:
        content: CSV content as string or bytes.
        delimiter: CSV delimiter. If None, pandas will auto-detect.
        encoding: Character encoding for bytes content.

    Returns:
        Parsed DataFrame.

    Raises:
        ExtractionError: If parsing fails.
    """
    try:
        # Convert bytes to string if needed
        if isinstance(content, bytes):
            content = content.decode(encoding)

        # Create StringIO for pandas (content is guaranteed to be str after decode)
        buffer = StringIO(content)

        # Read CSV with common options
        df = pd.read_csv(
            buffer,
            sep=delimiter,  # None = auto-detect
            engine="python" if delimiter is None else "c",
            on_bad_lines="warn",
            skip_blank_lines=True,
            dtype=str,  # Read everything as string first, convert later
        )

        logger.debug("Parsed CSV with %d rows, %d columns", len(df), len(df.columns))
        return df

    except pd.errors.EmptyDataError as e:
        raise ExtractionError(
            message=f"CSV file is empty: {e}",
            source="csv",
            user_message="The CSV file is empty. Please provide a file with process data.",
        ) from e
    except pd.errors.ParserError as e:
        raise ExtractionError(
            message=f"Failed to parse CSV: {e}",
            source="csv",
            user_message="The CSV file could not be parsed. Check that it's properly formatted "
            "with consistent delimiters and no corrupted rows.",
        ) from e
    except UnicodeDecodeError as e:
        raise ExtractionError(
            message=f"Encoding error: {e}",
            source="csv",
            user_message=f"The file encoding is not {encoding}. Try saving the file as UTF-8.",
        ) from e


def _convert_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """Convert columns to appropriate data types.

    Args:
        df: DataFrame with string columns.

    Returns:
        DataFrame with converted types.

    Raises:
        ValidationError: If conversion fails for required columns.
    """
    # Numeric columns and their expected types
    numeric_columns = {
        "average_time_hours": float,
        "resources_needed": int,
        "error_rate_pct": float,
        "cost_per_instance": float,
    }

    for col, dtype in numeric_columns.items():
        if col not in df.columns:
            continue

        try:
            # Clean common formatting issues
            series = df[col].astype(str)
            series = series.str.replace(r"[$,]", "", regex=True)  # Remove $ and commas
            series = series.str.replace(
                r"\s*%\s*$", "", regex=True
            )  # Remove trailing %
            # Remove unit words like "hours", "minutes", "percent", "person", "people"
            series = series.str.replace(
                r"\s*(hours?|mins?|minutes?|percent|persons?|people)\s*",
                "",
                regex=True,
                case=False,
            )
            series = series.str.strip()

            # Convert to numeric, coercing errors to NaN
            df[col] = pd.to_numeric(series, errors="coerce")

            # For integer columns, convert NaN to 0 then to int
            if dtype is int:
                df[col] = df[col].fillna(0).astype(int)

        except (ValueError, TypeError) as e:
            logger.warning(
                "Failed to convert column '%s' to %s: %s", col, dtype.__name__, e
            )

    # Fill NaN with defaults for optional columns
    if "error_rate_pct" in df.columns:
        df["error_rate_pct"] = df["error_rate_pct"].fillna(0.0)
    if "cost_per_instance" in df.columns:
        df["cost_per_instance"] = df["cost_per_instance"].fillna(0.0)
    if "depends_on" in df.columns:
        df["depends_on"] = df["depends_on"].fillna("")

    return df


def _df_to_process_steps(df: pd.DataFrame) -> list[ProcessStep]:
    """Convert DataFrame rows to ProcessStep models.

    Args:
        df: DataFrame with process step data.

    Returns:
        List of validated ProcessStep objects.

    Raises:
        ValidationError: If any row fails validation.
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
        # All rows failed
        raise ValidationError(
            message=f"All rows failed validation: {errors}",
            field="rows",
            user_message="All rows in the CSV failed validation. Please check the data format.",
        )

    if errors:
        logger.warning("Skipped %d invalid rows out of %d total", len(errors), len(df))

    return steps


def load_csv(
    source: str | Path | BinaryIO | bytes,
    process_name: str = "Imported Process",
    delimiter: str | None = None,
    encoding: str = "utf-8",
) -> ProcessData:
    """Load process data from a CSV file or content.

    Args:
        source: File path, file object, or raw CSV bytes/string.
        process_name: Name to assign to the imported process.
        delimiter: CSV delimiter (auto-detect if None).
        encoding: Character encoding (default: utf-8).

    Returns:
        ProcessData with validated process steps.

    Raises:
        ExtractionError: If file cannot be read or parsed.
        ValidationError: If data validation fails.

    Example:
        >>> data = load_csv("process.csv", process_name="Expense Approval")
        >>> print(f"Loaded {len(data.steps)} steps")
    """
    logger.info("Loading CSV from %s", type(source).__name__)

    # Read content from source
    if isinstance(source, str | Path):
        path = Path(source)
        if not path.exists():
            raise ExtractionError(
                message=f"File not found: {path}",
                source=str(path),
                user_message=f"The file '{path.name}' was not found.",
            )
        content = path.read_bytes()
    elif isinstance(source, bytes):
        content = source
    else:
        # Must be BinaryIO (file-like object) - all other types handled above
        file_obj: BinaryIO = source
        content = file_obj.read()
        file_obj.seek(0)  # Reset for potential re-read
        # Ensure content is bytes
        if not isinstance(content, bytes):
            content = (
                bytes(content)
                if isinstance(content, bytearray | memoryview)
                else content.encode("utf-8")
            )

    # Parse CSV
    df = _parse_csv_content(content, delimiter=delimiter, encoding=encoding)

    if df.empty:
        raise ExtractionError(
            message="CSV has no data rows",
            source="csv",
            user_message="The CSV file has headers but no data rows.",
        )

    # Map column names
    df = _map_columns(df)

    # Validate required columns
    _validate_required_columns(df)

    # Convert data types
    df = _convert_dtypes(df)

    # Convert to ProcessStep models
    steps = _df_to_process_steps(df)

    logger.info("Successfully loaded %d process steps", len(steps))

    return ProcessData(name=process_name, steps=steps)


def load_csv_from_bytes(
    data: bytes,
    process_name: str = "Imported Process",
    encoding: str = "utf-8",
) -> ProcessData:
    """Convenience function for loading CSV from bytes (e.g., multipart file upload).

    Args:
        data: Raw CSV bytes.
        process_name: Name for the process.
        encoding: Character encoding.

    Returns:
        ProcessData with validated process steps.
    """
    return load_csv(BytesIO(data), process_name=process_name, encoding=encoding)
