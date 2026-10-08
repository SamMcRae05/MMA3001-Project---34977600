"""
Loading the raw project data into pandas DataFrames.

This module is the single entry point for reading the raw files in
``data/raw/``. Every other part of the project should load data through
these functions, so that parsing decisions (column types, time zones,
unpacking the JSON readings) are made once, documented once, and tested.

Functions:
    load_occupancy: occupancy-sensor events (one row per status change).
    load_env: environmental-sensor readings (one row per reading).
    load_sensor_locations: the sensor ID -> building/room lookup tables.

All timestamps are returned as time-zone-aware values in Melbourne local
time (``Australia/Melbourne``), so daylight-saving changes are handled
correctly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from mma3001.paths import RAW_DATA_DIR

# --- File names and settings ------------------------------------------------

OCCUPANCY_FILE = RAW_DATA_DIR / "5occupancySensor_MayToDec2024_9MRows.csv"
"""Default location of the occupancy CSV."""

ENV_FILE = RAW_DATA_DIR / "5EnvSensor_MayToDec2024_180kRows.csv"
"""Default location of the environmental CSV."""

LOCATIONS_FILE = RAW_DATA_DIR / "Sensor ID and Locations.xlsx"
"""Default location of the sensor-location spreadsheet."""

LOCAL_TZ = "Australia/Melbourne"
"""Time zone all timestamps are converted to."""

OCCUPANCY_COLUMNS = [
    "id", "deviceid", "floorspaceid", "occupancystatus", "headcount",
    "collecteddate", "occupancystatuschangedate", "previousoccupancystatus",
]
"""Columns the occupancy CSV must contain."""

ENV_COLUMNS = [
    "id", "sensorid", "devicetype", "jsondata", "status",
    "processing_errors", "createdate", "processdate",
]
"""Columns the environmental CSV must contain."""


# --- Helper functions (internal) --------------------------------------------

def _check_file(path: Path) -> Path:
    """
    Check a data file exists, raising a helpful error if it does not.

    Args:
        path: Path to the file.

    Returns:
        The same path, as a ``Path`` object.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"Data file not found: {path}\n"
            "See data/README.md for how to obtain the dataset and where to put it."
        )
    return path


def _check_nrows(nrows: int | None) -> None:
    """
    Validate the ``nrows`` argument shared by the CSV loaders.

    Args:
        nrows: Number of rows to read, or None for all rows.

    Raises:
        ValueError: If ``nrows`` is not None and is less than 1.
    """
    if nrows is not None and nrows < 1:
        raise ValueError(f"nrows must be a positive integer or None, got {nrows}")


def _check_columns(df: pd.DataFrame, expected: list[str], path: Path) -> None:
    """
    Check a loaded CSV has all the columns the parser relies on.

    Args:
        df: The DataFrame just read from ``path``.
        expected: Column names that must be present.
        path: The file it came from (used in the error message).

    Raises:
        ValueError: If any expected column is missing.
    """
    missing = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name} is missing expected columns: {missing}")


def _to_local_time(series: pd.Series) -> pd.Series:
    """
    Convert timestamp strings such as ``"2023-11-24 00:36:52+11"`` to local time.

    The raw strings include a UTC offset (+11 in daylight-saving time,
    +10 otherwise). Parsing to UTC first and then converting means every
    value ends up on one consistent time axis, whatever its original offset.

    Args:
        series: Timestamp strings with UTC offsets.

    Returns:
        Time-zone-aware timestamps in ``LOCAL_TZ``.
    """
    return pd.to_datetime(series, format="ISO8601", utc=True).dt.tz_convert(LOCAL_TZ)


# --- Public loaders ---------------------------------------------------------

def load_occupancy(path: str | Path = OCCUPANCY_FILE, nrows: int | None = None) -> pd.DataFrame:
    """
    Load the occupancy-sensor CSV.

    Each row is one event reported by an occupancy sensor for one floor
    space: its occupancy status, head count, and when it was recorded.

    Text columns that repeat a small set of values (device IDs, space IDs,
    statuses) are stored as pandas ``category`` type, which uses far less
    memory than plain text - important for a 9-million-row file.

    Args:
        path: CSV file to read. Defaults to the project's raw occupancy file.
        nrows: Read only the first ``nrows`` rows (useful for quick
            exploration). None reads the whole file.

    Returns:
        DataFrame with columns:

        - ``id`` (int): record ID from the source database.
        - ``deviceid`` (category): occupancy sensor ID.
        - ``floorspaceid`` (category): ID of the floor space being monitored.
        - ``occupancystatus`` (category): e.g. "CurrentlyOccupied".
        - ``headcount`` (int): number of people detected.
        - ``collecteddate`` (datetime, Melbourne time): when the event was recorded.
        - ``occupancystatuschangedate`` (datetime, Melbourne time): when the status last changed.
        - ``previousoccupancystatus`` (category): the status before this event.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If ``nrows`` is less than 1 or expected columns are missing.

    Example:
        >>> occ = load_occupancy(nrows=1000)   # first 1000 rows only
    """

    # 1. does the file exist? clear error if not
    path = _check_file(path)
    # 2. is nrows sensible (None, or 1 or more)?
    _check_nrows(nrows)

    category_cols = ["deviceid", "floorspaceid", "occupancystatus", "previousoccupancystatus"]
    df = pd.read_csv(
        path,
        nrows=nrows,
        dtype={c: "category" for c in category_cols},
         # 3. read, storing repeated text as categories. 
         # E.g: for the "occupancystatus" data it  is stored as one of three text values
         # Converts written values to categories
    )
    _check_columns(df, OCCUPANCY_COLUMNS, path)

    for col in ["collecteddate", "occupancystatuschangedate"]:
        df[col] = _to_local_time(df[col])
    return df


def load_env(path: str | Path = ENV_FILE, nrows: int | None = None) -> pd.DataFrame:
    """
    Load the environmental-sensor CSV and unpack its JSON readings.

    In the raw file, each row is one upload from one sensor, and the
    actual measurements (temperature, CO2, ...) are packed inside the
    ``jsondata`` column as JSON text. This function unpacks them into a
    "long" (tidy) table with **one row per individual reading**.

    Readings come in several shapes in the raw JSON. Some have no
    ``value`` (or an empty value list), and some carry an ``errorCode``
    reported by the sensor, with or without a value. These are all kept:
    a missing value becomes ``NaN`` and the error code is stored in its own
    column, so that problem readings remain visible rather than silently
    disappearing.

    Args:
        path: CSV file to read. Defaults to the project's raw environmental file.
        nrows: Read only the first ``nrows`` CSV rows (each expands to about
            11 readings). None reads the whole file.

    Returns:
        DataFrame with columns:

        - ``record_id`` (int): ID of the upload (the CSV row) it came from.
        - ``sensorid`` (int): environmental sensor ID.
        - ``time`` (datetime, Melbourne time): when the reading was measured.
        - ``variable`` (category): what was measured, e.g. "Temperature".
        - ``unit`` (category): its unit, e.g. "°C".
        - ``value`` (float): the measured value (NaN if missing).
        - ``error_code`` (float): sensor error code, or NaN if none was reported.
        - ``createdate`` (datetime, Melbourne time): when the upload reached the database.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If ``nrows`` is less than 1, expected columns are missing,
            or a row's ``jsondata`` is not valid JSON.

    Example:
        >>> env = load_env(nrows=100)
        >>> temps = env[env["variable"] == "Temperature"]
    """
    path = _check_file(path) # if file doesn't exist, raise error
    _check_nrows(nrows)

    # Gives a table where JSON data is still just text values
    raw = pd.read_csv(path, nrows=nrows)
    _check_columns(raw, ENV_COLUMNS, path)

    # Build the long table as plain Python lists first (fast), then make one
    # DataFrame at the end. Appending to a DataFrame row by row is very slow.
    record_ids, sensor_ids, times, variables, units, values, errors = [], [], [], [], [], [], []
    for record_id, sensor_id, text in zip(raw["id"], raw["sensorid"], raw["jsondata"]):
        try:
            readings = json.loads(text) # turns JSON data into real python list
        except (TypeError, json.JSONDecodeError) as err:
            raise ValueError(f"Record {record_id}: jsondata is not valid JSON ({err})") from err # returns which ID cauused the error

        for reading in readings: # each item = one variable (Batter, C02...)
            name = reading["variable"]["name"]
            unit = reading["variable"]["unit"]
            measured = reading["values"]
            if not measured:
                # Empty value list: keep a row so the gap is visible.
                measured = [{"time": None}]
            for m in measured: # each measurement of that variable, appends the measurement to that variable column
                record_ids.append(record_id)
                sensor_ids.append(sensor_id)
                times.append(m["time"])
                variables.append(name)
                units.append(unit)
                # .get() returns NaN instead of crashing when a key is absent.
                values.append(m.get("value", float("nan")))
                errors.append(m.get("errorCode", float("nan")))

    env = pd.DataFrame({
        "record_id": record_ids,
        "sensorid": sensor_ids,
        # JSON times are Unix timestamps: seconds since 1970-01-01 UTC.
        "time": pd.to_datetime(times, unit="s", utc=True).tz_convert(LOCAL_TZ),
        "variable": pd.Categorical(variables),
        "unit": pd.Categorical(units),
        "value": pd.to_numeric(values, errors="coerce").astype(float),
        "error_code": pd.to_numeric(errors, errors="coerce").astype(float),
    })

    # Attach the upload time of each record (one value per CSV row).
    # (.array keeps the time zone; .values would silently strip it.)
    created = pd.Series(_to_local_time(raw["createdate"]).array, index=raw["id"])
    env["createdate"] = env["record_id"].map(created)
    return env


def load_sensor_locations(path: str | Path = LOCATIONS_FILE) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load the sensor-location lookup tables from the Excel file.

    The spreadsheet has two sheets: environmental sensors and occupancy
    sensors. They are read by position (first and second sheet) because
    the second sheet's name is long and was truncated by Excel.

    Args:
        path: Excel file to read. Defaults to the project's raw locations file.

    Returns:
        A tuple ``(env_locations, occ_locations)``:

        - ``env_locations``: one row per environmental sensor, with columns
          Building, Floor/Room, Area, Physical Label, Sensor, ID.
        - ``occ_locations``: one row per occupancy sensor, with columns
          Building, Floor/Room, Area, ID, Note, FloorId, SpaceId.
          Note: the sheet itself is labelled "Incorrect Data", so treat
          it with caution.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the workbook does not have at least two sheets.
    """
    path = _check_file(path) # if file doesn't exist, raise error
    sheets = pd.read_excel(path, sheet_name=None)  # dict: sheet name -> DataFrame
    if len(sheets) < 2:
        raise ValueError(f"{path.name} should have 2 sheets (ENV and OCC), found {len(sheets)}")
    env_locations, occ_locations = list(sheets.values())[:2]
    return env_locations, occ_locations
