"""
Tests for ``mma3001.cleaning`` (removing repeated environmental uploads).

Each test builds a tiny table by hand in the same format ``load_env`` returns,
so the correct answer is known in advance. The helper ``make_env`` keeps the
tests short: each upload is written as (record_id, sensor, upload time, readings).
"""

import numpy as np
import pandas as pd
import pytest

from mma3001.cleaning import flag_repeated_uploads, remove_repeated_uploads

TZ = "Australia/Melbourne"


def make_env(uploads):
    """
    Build a small long-format table like ``load_env`` returns.

    Args:
        uploads: list of (record_id, sensorid, createdate, readings), where
            readings is a list of (variable, time, value).

    Returns:
        DataFrame with columns record_id, sensorid, time, variable, unit,
        value, error_code, createdate.
    """
    rows = []
    for record_id, sensor, created, readings in uploads:
        for variable, t, value in readings:
            rows.append({
                "record_id": record_id,
                "sensorid": sensor,
                "time": pd.Timestamp(t, tz=TZ) if t is not None else pd.NaT,
                "variable": variable,
                "unit": "x",
                "value": value,
                "error_code": np.nan,
                "createdate": pd.Timestamp(created, tz=TZ),
            })
    return pd.DataFrame(rows)


# Two readings taken at 09:00 on 1 March 2024, used in most tests.
READINGS = [("Temperature", "2024-03-01 09:00", 22.5), ("Carbon dioxide", "2024-03-01 09:00", 600.0)]


# =============================================================================
# Positive tests: what IS and ISN'T a repeat
# =============================================================================

def test_exact_copy_is_flagged_and_first_kept():
    """Positive: the second identical upload from the same sensor is a repeat."""
    env = make_env([
        (1, "A", "2024-03-01 09:05", READINGS),
        (2, "A", "2024-03-01 09:18", READINGS),   # same readings, uploaded again
    ])
    flags = flag_repeated_uploads(env)
    assert list(flags) == [False, True]
    assert list(remove_repeated_uploads(env)["record_id"].unique()) == [1]


def test_many_copies_keep_only_one():
    """Positive: five copies of the same upload reduce to one."""
    env = make_env([(i, "A", f"2024-03-01 09:{i:02d}", READINGS) for i in range(1, 6)])
    assert flag_repeated_uploads(env).sum() == 4
    assert remove_repeated_uploads(env)["record_id"].nunique() == 1


def test_first_means_earliest_upload_not_lowest_id():
    """Positive: 'first' is decided by upload time (createdate), not by record_id."""
    env = make_env([
        (10, "A", "2024-03-01 10:00", READINGS),  # higher id, but arrived first
        (5,  "A", "2024-03-01 11:00", READINGS),  # lower id, arrived later -> the repeat
    ])
    flags = flag_repeated_uploads(env)
    assert flags.loc[10] == False and flags.loc[5] == True


def test_same_values_at_a_different_time_are_not_repeats():
    """Positive: identical values measured at a different time are a genuine new reading."""
    later = [("Temperature", "2024-03-01 09:15", 22.5), ("Carbon dioxide", "2024-03-01 09:15", 600.0)]
    env = make_env([(1, "A", "2024-03-01 09:05", READINGS), (2, "A", "2024-03-01 09:20", later)])
    assert not flag_repeated_uploads(env).any()


def test_same_readings_from_a_different_sensor_are_not_repeats():
    """Positive: two sensors reporting identical readings are both kept."""
    env = make_env([(1, "A", "2024-03-01 09:05", READINGS), (2, "B", "2024-03-01 09:06", READINGS)])
    assert not flag_repeated_uploads(env).any()


def test_readings_mode_one_different_value_is_not_a_repeat():
    """Positive: with match="readings" (exact copies only), one differing value means not a repeat."""
    changed = [("Temperature", "2024-03-01 09:00", 22.5), ("Carbon dioxide", "2024-03-01 09:00", 601.0)]
    env = make_env([(1, "A", "2024-03-01 09:05", READINGS), (2, "A", "2024-03-01 09:18", changed)])
    assert not flag_repeated_uploads(env, match="readings").any()


# =============================================================================
# Positive tests: the default rule, match="time" (one upload per sensor per time)
# =============================================================================

def test_time_mode_same_time_different_values_is_a_repeat():
    """Positive: by default, a second upload with the same sensor and measurement time is a repeat."""
    changed = [("Temperature", "2024-03-01 09:00", 22.5), ("Carbon dioxide", "2024-03-01 09:00", 601.0)]
    env = make_env([(1, "A", "2024-03-01 09:05", READINGS), (2, "A", "2024-03-01 09:18", changed)])
    assert list(flag_repeated_uploads(env)) == [False, True]


def test_time_mode_near_repeat_with_missing_value_removed_complete_copy_kept():
    """
    Positive: the real-data case - an old reading re-sent later with one value missing (NaN).

    The earlier, complete upload is kept; the later copy with the missing value is removed.
    """
    with_gap = [("Temperature", "2024-03-01 09:00", 22.5), ("Carbon dioxide", "2024-03-01 09:00", np.nan)]
    env = make_env([(1, "A", "2024-03-01 09:05", READINGS), (2, "A", "2024-03-01 09:18", with_gap)])
    clean = remove_repeated_uploads(env)
    assert list(clean["record_id"].unique()) == [1]
    assert not clean["value"].isna().any()


def test_time_mode_finds_everything_readings_mode_finds():
    """Positive: every exact copy is also a same-time repeat, so "time" flags at least as much as "readings"."""
    changed = [("Temperature", "2024-03-01 09:00", 22.5), ("Carbon dioxide", "2024-03-01 09:00", 601.0)]
    env = make_env([(1, "A", "2024-03-01 09:05", READINGS),
                    (2, "A", "2024-03-01 09:18", READINGS),     # exact copy
                    (3, "A", "2024-03-01 09:31", changed)])     # near-repeat
    by_readings = flag_repeated_uploads(env, match="readings")
    by_time = flag_repeated_uploads(env, match="time")
    assert list(by_readings) == [False, True, False]
    assert list(by_time) == [False, True, True]
    assert (by_time | ~by_readings).all()     # nothing flagged by "readings" is missed by "time"


def test_time_mode_same_time_different_sensor_is_kept():
    """Positive: two different sensors measuring at the same moment are both kept."""
    env = make_env([(1, "A", "2024-03-01 09:05", READINGS), (2, "B", "2024-03-01 09:06", READINGS)])
    assert not flag_repeated_uploads(env).any()


def test_reading_order_inside_an_upload_does_not_matter():
    """Positive: the same readings listed in a different order still count as a repeat."""
    env = make_env([(1, "A", "2024-03-01 09:05", READINGS),
                    (2, "A", "2024-03-01 09:18", list(reversed(READINGS)))])
    assert list(flag_repeated_uploads(env)) == [False, True]


def test_repeated_missing_values_are_repeats():
    """Positive: an upload repeating the same missing (NaN, no time) reading is a repeat."""
    missing = [("Pressure", None, np.nan)]
    env = make_env([(1, "A", "2024-03-01 09:05", missing), (2, "A", "2024-03-01 09:18", missing)])
    assert list(flag_repeated_uploads(env)) == [False, True]


def test_all_readings_of_a_repeat_are_removed_and_columns_kept():
    """Positive: every row of a repeated upload is dropped; columns are unchanged."""
    env = make_env([(1, "A", "2024-03-01 09:05", READINGS), (2, "A", "2024-03-01 09:18", READINGS)])
    clean = remove_repeated_uploads(env)
    assert len(clean) == 2                      # the 2 readings of upload 1 only
    assert list(clean.columns) == list(env.columns)


def test_input_is_not_modified():
    """Positive: the function returns a new table and leaves the input as it was."""
    env = make_env([(1, "A", "2024-03-01 09:05", READINGS), (2, "A", "2024-03-01 09:18", READINGS)])
    before = env.copy()
    remove_repeated_uploads(env)
    pd.testing.assert_frame_equal(env, before)


def test_cleaning_twice_changes_nothing():
    """Positive: cleaning already-clean data removes nothing more."""
    env = make_env([(i, "A", f"2024-03-01 09:{i:02d}", READINGS) for i in range(1, 4)])
    once = remove_repeated_uploads(env)
    pd.testing.assert_frame_equal(remove_repeated_uploads(once), once)


def test_empty_table_returns_empty():
    """Positive (edge case): an empty table gives an empty result instead of crashing."""
    empty = pd.DataFrame(columns=["record_id", "sensorid", "time", "variable", "value", "createdate"])
    assert flag_repeated_uploads(empty).empty
    assert remove_repeated_uploads(empty).empty


# =============================================================================
# Negative tests: invalid input
# =============================================================================

def test_not_a_dataframe_raises():
    """Negative: passing something that isn't a DataFrame gives a TypeError."""
    with pytest.raises(TypeError, match="DataFrame"):
        flag_repeated_uploads([1, 2, 3])


def test_invalid_match_raises():
    """Negative: an unknown match rule is rejected."""
    env = make_env([(1, "A", "2024-03-01 09:05", READINGS)])
    with pytest.raises(ValueError, match="match"):
        flag_repeated_uploads(env, match="values")


def test_missing_column_raises():
    """Negative: a table without the required columns is rejected, naming what's missing."""
    env = make_env([(1, "A", "2024-03-01 09:05", READINGS)]).drop(columns="createdate")
    with pytest.raises(ValueError, match="createdate"):
        remove_repeated_uploads(env)
