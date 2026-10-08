"""
Tests for ``mma3001.io`` (the data loaders).

The tests use small hand-made files in ``tests/fixtures/`` written in exactly
the same format as the real data. Because we wrote them by hand, we know
the correct answer for every value, which is what makes them useful tests.

``tmp_path`` (used in some tests) is a built-in pytest feature: it gives each
test a fresh, empty temporary folder to create throwaway files in.
"""

import numpy as np
import pandas as pd
import pytest

from mma3001.io import load_env, load_occupancy, load_sensor_locations
from mma3001.paths import TEST_FIXTURES_DIR

ENV_SAMPLE = TEST_FIXTURES_DIR / "env_sample.csv"
OCC_SAMPLE = TEST_FIXTURES_DIR / "occupancy_sample.csv"
LOC_SAMPLE = TEST_FIXTURES_DIR / "sensor_locations_sample.xlsx"


# =============================================================================
# load_occupancy
# =============================================================================

def test_occupancy_loads_all_rows_and_columns():
    """Positive: every row and the expected columns are loaded."""
    occ = load_occupancy(OCC_SAMPLE)
    assert len(occ) == 4
    assert list(occ.columns) == [
        "id", "deviceid", "floorspaceid", "occupancystatus", "headcount",
        "collecteddate", "occupancystatuschangedate", "previousoccupancystatus",
    ]


def test_occupancy_nrows_limits_rows():
    """Positive: nrows reads only the first n rows."""
    assert len(load_occupancy(OCC_SAMPLE, nrows=2)) == 2


def test_occupancy_types():
    """Positive: repeated text is stored as category, head counts as integers."""
    occ = load_occupancy(OCC_SAMPLE)
    assert occ["deviceid"].dtype == "category"
    assert occ["occupancystatus"].dtype == "category"
    assert pd.api.types.is_integer_dtype(occ["headcount"])


def test_occupancy_times_handle_daylight_saving():
    """
    Positive: both +11 (summer) and +10 (winter) offsets convert correctly.

    "2023-11-24 00:36:52+11" and "2024-06-14 09:00:00+10" should keep the same
    clock time in Melbourne, because those were the correct offsets on those dates.
    """
    occ = load_occupancy(OCC_SAMPLE)
    assert str(occ["collecteddate"].dt.tz) == "Australia/Melbourne"
    assert occ["collecteddate"].iloc[0] == pd.Timestamp("2023-11-24 00:36:52", tz="Australia/Melbourne")
    assert occ["collecteddate"].iloc[3] == pd.Timestamp("2024-06-14 09:00:00", tz="Australia/Melbourne")


def test_occupancy_missing_file_raises():
    """Negative: a missing file gives a clear FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="data/README.md"):
        load_occupancy("this_file_does_not_exist.csv")


@pytest.mark.parametrize("bad_nrows", [0, -5])
def test_occupancy_bad_nrows_raises(bad_nrows):
    """Negative: nrows of zero or below is rejected. (Runs once per value listed above.)"""
    with pytest.raises(ValueError, match="nrows"):
        load_occupancy(OCC_SAMPLE, nrows=bad_nrows)


def test_occupancy_missing_column_raises(tmp_path):
    """Negative: a CSV without the expected columns is rejected, naming what's missing."""
    bad = tmp_path / "bad.csv"
    bad.write_text("id,deviceid\n1,abc\n")
    with pytest.raises(ValueError, match="headcount"):
        load_occupancy(bad)


# =============================================================================
# load_env
# =============================================================================

def test_env_unpacks_one_row_per_reading():
    """
    Positive: the 3 CSV rows unpack to 5 readings.

    Record 1 has 2 readings, record 2 has 2, record 3 has 1 (with an empty value list).
    """
    env = load_env(ENV_SAMPLE)
    assert len(env) == 5
    assert list(env["record_id"]) == [1, 1, 2, 2, 3]
    assert list(env["variable"]) == ["Temperature", "Carbon dioxide", "Formaldehyde", "Humidity", "Pressure"]


def test_env_values_and_units():
    """Positive: values and units are read correctly (floats compared approximately)."""
    env = load_env(ENV_SAMPLE)
    assert env["value"].iloc[0] == pytest.approx(23.8)
    assert env["unit"].iloc[0] == "°C"
    assert env["value"].iloc[1] == pytest.approx(603.0)


def test_env_unix_time_converted_to_melbourne():
    """Positive: Unix time 1702273965 is 2023-12-11 16:52:45 in Melbourne (daylight saving, +11)."""
    env = load_env(ENV_SAMPLE)
    assert env["time"].iloc[0] == pd.Timestamp("2023-12-11 16:52:45", tz="Australia/Melbourne")


def test_env_createdate_keeps_time_zone():
    """
    Positive: the upload time keeps its time zone.

    (This test exists because an early version of load_env silently dropped it.)
    """
    env = load_env(ENV_SAMPLE)
    assert str(env["createdate"].dt.tz) == "Australia/Melbourne"
    assert env["createdate"].iloc[0] == pd.Timestamp("2024-02-29 03:11:58.210358", tz="Australia/Melbourne")


def test_env_error_code_kept():
    """Positive: a reading with an error code keeps both its value and the code."""
    env = load_env(ENV_SAMPLE)
    formaldehyde = env[env["variable"] == "Formaldehyde"].iloc[0]
    assert formaldehyde["value"] == pytest.approx(17.0)
    assert formaldehyde["error_code"] == 8
    # Readings without an error code have NaN in that column.
    assert np.isnan(env["error_code"].iloc[0])


def test_env_missing_value_becomes_nan():
    """Positive: a reading with a time but no value is kept, with value NaN."""
    env = load_env(ENV_SAMPLE)
    humidity = env[env["variable"] == "Humidity"].iloc[0]
    assert np.isnan(humidity["value"])
    assert not pd.isna(humidity["time"])


def test_env_empty_value_list_kept():
    """Positive: an empty value list is kept as one row with no time and no value."""
    env = load_env(ENV_SAMPLE)
    pressure = env[env["variable"] == "Pressure"].iloc[0]
    assert np.isnan(pressure["value"])
    assert pd.isna(pressure["time"])


def test_env_missing_file_raises():
    """Negative: a missing file gives a clear FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_env("this_file_does_not_exist.csv")


def test_env_bad_nrows_raises():
    """Negative: nrows of zero is rejected."""
    with pytest.raises(ValueError, match="nrows"):
        load_env(ENV_SAMPLE, nrows=0)


def test_env_invalid_json_raises(tmp_path):
    """Negative: broken JSON gives a ValueError naming the record it came from."""
    bad = tmp_path / "bad_env.csv"
    bad.write_text(
        "id,sensorid,devicetype,jsondata,status,processing_errors,createdate,processdate\n"
        '7,123,env,"[{not valid json",Processed,,2024-01-01 00:00:00+11,2024-01-01 00:00:00+11\n'
    )
    with pytest.raises(ValueError, match="Record 7"):
        load_env(bad)


# =============================================================================
# load_sensor_locations
# =============================================================================

def test_locations_returns_two_tables():
    """Positive: returns the ENV and OCC tables with their expected columns."""
    env_loc, occ_loc = load_sensor_locations(LOC_SAMPLE)
    assert "ID" in env_loc.columns and "Area" in env_loc.columns
    assert "SpaceId" in occ_loc.columns
    assert len(env_loc) > 0 and len(occ_loc) > 0


def test_locations_missing_file_raises():
    """Negative: a missing file gives a clear FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        load_sensor_locations("nope.xlsx")


def test_locations_one_sheet_raises(tmp_path):
    """Negative: a workbook with only one sheet is rejected."""
    one_sheet = tmp_path / "one_sheet.xlsx"
    pd.DataFrame({"a": [1]}).to_excel(one_sheet, index=False)
    with pytest.raises(ValueError, match="2 sheets"):
        load_sensor_locations(one_sheet)
