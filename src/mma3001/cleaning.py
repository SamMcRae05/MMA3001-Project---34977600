"""
Cleaning steps applied to the loaded data before analysis.

The loaders in ``mma3001.io`` return the raw data exactly as provided. This
module holds the separate, documented decisions about what to correct or
remove, so that every cleaning step is visible, tested, and can be switched
off to compare cleaned and raw results.

Functions:
    flag_repeated_uploads: mark each environmental upload as a repeat or not.
    remove_repeated_uploads: drop the repeated uploads, keeping the first copy.

Background (see notebooks/01_data_audit.ipynb, sections B4-B6): many
environmental sensors re-sent the same old reading - same measurement time,
same values - every ~13 minutes for months. About 76% of all uploads are
such repeats. They are copies of one measurement, not new measurements.

A handful of further uploads ("near-repeats", see notebooks/02_cleaning.ipynb
section 1.7) repeat an earlier upload's measurement time but with a value
missing. Every upload contains exactly one measurement time, and a sensor
cannot take two different sets of readings at the same instant, so the
project's cleaning rule keeps only one upload per sensor per measurement time.
"""

from __future__ import annotations

import pandas as pd

REQUIRED_ENV_COLUMNS = ["record_id", "sensorid", "time", "variable", "value", "createdate"]
"""Columns ``flag_repeated_uploads`` needs (all produced by ``load_env``)."""


def flag_repeated_uploads(env: pd.DataFrame, match: str = "time") -> pd.Series:
    """
    Mark each environmental upload as a repeat of an earlier upload, or not.

    An upload (one ``record_id``) is a **repeat** if an earlier upload from
    the **same sensor** matches it. What counts as a match depends on
    ``match``:

    - ``"time"`` (default, the project's cleaning rule): the earlier upload
      has the same measurement ``time``, whatever its values. This removes
      exact copies *and* "near-repeats" (the same time re-sent with a value
      missing), leaving one upload per sensor per measurement time.
    - ``"readings"``: the earlier upload contains exactly the same set of
      readings - the same variables, each with the same ``time`` and the same
      ``value``. This finds exact copies only; it is kept so the two kinds of
      repeat can be counted separately.

    "Earlier" means an earlier ``createdate`` (when the upload reached the
    database); ties are broken by ``record_id``. The first upload is
    therefore never flagged, so the copy that arrived first is the one kept.

    Assumptions:
        - Every upload contains one measurement time (true for the whole
          project dataset), so an upload's time is well defined.
        - A sensor cannot take two different sets of readings at the same
          instant, so a second upload with the same time is not new data.
        - Including the measurement ``time`` means two genuinely separate
          measurements that happen to give identical values are NOT treated
          as repeats, because they have different times.
        - With ``"readings"``, values are compared exactly (true copies come
          from identical JSON text) and a missing value counts as equal to
          another missing value.
        - ``error_code`` is not part of either comparison.

    Args:
        env: Long-format environmental data, as returned by
            ``mma3001.io.load_env`` (one row per reading).
        match: ``"time"`` (default) or ``"readings"`` - see above.

    Returns:
        Boolean Series indexed by ``record_id``: True if that upload is a
        repeat, False if it is the first occurrence.

    Raises:
        TypeError: If ``env`` is not a pandas DataFrame.
        ValueError: If any required column is missing, or ``match`` is not
            ``"time"`` or ``"readings"``.

    Example:
        >>> flags = flag_repeated_uploads(env)
        >>> flags.mean()            # fraction of uploads that are repeats
    """
    if not isinstance(env, pd.DataFrame):
        raise TypeError(f"env must be a pandas DataFrame, got {type(env).__name__}")
    missing = [c for c in REQUIRED_ENV_COLUMNS if c not in env.columns]
    if missing:
        raise ValueError(f"env is missing required columns: {missing}")
    if match not in ("time", "readings"):
        raise ValueError(f'match must be "time" or "readings", got {match!r}')
    if env.empty:
        return pd.Series(dtype=bool, index=pd.Index([], name="record_id"))

    # One row per upload: its sensor, its arrival time (createdate) and its
    # measurement time ("first" skips missing times, so a reading with no time
    # doesn't hide the upload's real time).
    uploads = (env.groupby("record_id")
                  .agg(sensorid=("sensorid", "first"),
                       createdate=("createdate", "first"),
                       time=("time", "first")))

    if match == "time":
        # The "signature" an upload is compared on is just its measurement time.
        # (Converted to text so that a missing time NaT compares equal to NaT.)
        uploads["signature"] = uploads["time"].astype(str)
    else:
        # 1. Turn each reading into one text "key": variable | time | value.
        #    Converting to text makes NaN/NaT compare equal to each other
        #    ("nan" == "nan"), which plain == does not.
        reading_key = (env["variable"].astype(str) + "|"
                       + env["time"].astype(str) + "|"
                       + env["value"].astype(str))
        # 2. Combine all reading keys of one upload into a single "signature".
        #    Sorting first means the order of readings inside an upload doesn't matter.
        uploads["signature"] = (reading_key.groupby(env["record_id"])
                                           .agg(lambda keys: "\n".join(sorted(keys))))

    # Put uploads in arrival order, then mark every upload whose
    #    (sensor, signature) pair has already appeared earlier in that order.
    uploads = uploads.sort_values(["createdate", "record_id"])
    is_repeat = uploads.duplicated(subset=["sensorid", "signature"], keep="first")

    # Return in record_id order so it lines up with the input.
    return is_repeat.sort_index().rename("is_repeat")


def remove_repeated_uploads(env: pd.DataFrame, match: str = "time") -> pd.DataFrame:
    """
    Remove repeated environmental uploads, keeping the first copy of each.

    Uses ``flag_repeated_uploads`` to identify repeats (with the same
    ``match`` rule - by default one upload per sensor per measurement time),
    then drops every row
    (reading) belonging to a repeated upload. The input DataFrame is not
    modified; a new DataFrame is returned.

    Args:
        env: Long-format environmental data, as returned by
            ``mma3001.io.load_env``.
        match: ``"time"`` (default) or ``"readings"`` - see
            ``flag_repeated_uploads``.

    Returns:
        A copy of ``env`` containing only the readings from non-repeated
        uploads, with the original row order and columns.

    Raises:
        TypeError: If ``env`` is not a pandas DataFrame.
        ValueError: If any required column is missing, or ``match`` is invalid.

    Example:
        >>> env_clean = remove_repeated_uploads(load_env())
    """
    is_repeat = flag_repeated_uploads(env, match=match)
    repeated_ids = is_repeat[is_repeat].index
    return env[~env["record_id"].isin(repeated_ids)].copy()
