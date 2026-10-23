"""
Reconstructing gaps in an environmental sensor time series.

Project question:
Can missing values in C02 readings be reasonably reliably reconstructed using interpolation?

Workflow:
    1. ``prepare_series``   - one sensor, one variable, as a time series.
    2. ``split_dev_test``   - time-ordered development / test split with a buffer.
    3. ``valid_gap_starts`` - where an artificial gap of a given length can go.
    4. ``make_gap``         - hide real readings, keeping them as the truth.
    5. ``fill_gap``         - reconstruct the hidden readings ("linear", "cubic"
                              or "smoothing").
    6. ``evaluate``         - repeat 3-5 at many random positions and score.

Design choices (see docs in each function, and Appendix A of report/MMA3001_Report.pdf):
    - Original timestamps are kept (no resampling to an exact grid), because
      resampling is itself an interpolation and would add error before the
      experiment starts. All methods work with unevenly spaced times.
    - The sensor's own single missed readings (20-minute spacings) are
      tolerated; artificial gaps are only placed where no spacing exceeds
      ``max_spacing``.
    - Each fill only uses readings within ``context`` of the gap on each side.
    - All methods are scored on exactly the same gaps (a paired comparison).
    - Time is measured in hours inside the fitting functions. Linear and cubic
      results do not depend on the time unit, but the smoothing spline's
      automatically chosen smoothing does, and hours are well scaled.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
from scipy.interpolate import CubicSpline, make_smoothing_spline

METHODS = ("linear", "cubic", "smoothing")
"""Supported reconstruction methods."""

BC_TYPES = ("not-a-knot", "natural", "clamped")
"""Supported cubic-spline boundary (end) conditions - see ``fill_gap``."""

DEFAULT_CONTEXT = pd.Timedelta("2h")
"""Default amount of real data used on EACH side of a gap when filling it."""

DEFAULT_MAX_SPACING = pd.Timedelta("25min")
"""Largest spacing between real readings allowed around/inside an artificial gap.
25 minutes tolerates one missed reading (a 20-minute spacing) but not more."""

MIN_SIDE_READINGS = 3
"""Fewest real readings required within the context on EACH side of a gap.
The cubic spline needs 2 per side and the smoothing spline 5 in total, so 3
per side lets every method fill every gap that ``valid_gap_starts`` allows."""


# =============================================================================
# 1. Preparing the series
# =============================================================================

def _in_tz(value, tz) -> pd.Timestamp:
    """
    Convert ``value`` to a Timestamp comparable with times in time zone ``tz``.

    A value without a time zone is interpreted as local time in ``tz``;
    a value that already has a time zone is converted to ``tz``.
    """
    ts = pd.Timestamp(value)
    if tz is None:
        return ts.tz_localize(None) if ts.tzinfo is not None else ts
    return ts.tz_localize(tz) if ts.tzinfo is None else ts.tz_convert(tz)


def prepare_series(env: pd.DataFrame, sensorid: int, variable: str = "Carbon dioxide",
                   start=None, end=None) -> pd.Series:
    """
    Extract one sensor's readings of one variable as a time series.

    Args:
        env: Long-format environmental data (e.g. from
            ``mma3001.cleaning.remove_repeated_uploads(load_env())``).
        sensorid: The sensor to select.
        variable: The variable to select, e.g. "Carbon dioxide".
        start: Optional first time to include (inclusive). A plain date or time
            without a time zone (e.g. "2024-02-29") is taken as local time in
            the data's own time zone.
        end: Optional last time to include (inclusive), treated the same way.

    Returns:
        Float Series of values indexed by measurement time (sorted, unique),
        with missing values and missing times removed.

    Raises:
        ValueError: If required columns are missing, no readings match, or
            two readings share a measurement time (data should be
            de-duplicated first).
    """
    needed = ["sensorid", "variable", "time", "value"]
    missing = [c for c in needed if c not in env.columns]
    if missing:
        raise ValueError(f"env is missing required columns: {missing}")

    rows = env[(env["sensorid"] == sensorid) & (env["variable"] == variable)]
    rows = rows.dropna(subset=["time", "value"])
    series = rows.set_index("time")["value"].astype(float).sort_index()
    if start is not None:
        series = series[series.index >= _in_tz(start, series.index.tz)]
    if end is not None:
        series = series[series.index <= _in_tz(end, series.index.tz)]

    if series.empty:
        raise ValueError(f"No {variable!r} readings for sensor {sensorid} in the requested period")
    if series.index.duplicated().any():
        raise ValueError("Two readings share a measurement time; remove repeated uploads first")
    series.name = variable
    return series


# =============================================================================
# 2. Development / test split
# =============================================================================

def split_dev_test(series: pd.Series, test_fraction: float = 0.25,
                   buffer: pd.Timedelta = pd.Timedelta("1D")) -> tuple[pd.Series, pd.Series]:
    """
    Split a series by time into a development part and a later test part.

    The boundary is placed ``test_fraction`` of the way from the end of the
    period. Readings within ``buffer`` after the boundary belong to neither
    part, so no gap or its surrounding context can draw on both parts
    (MMA3001 notes 5.5.5 and 5.6.6-5.6.7).

    Args:
        series: Time series from ``prepare_series``.
        test_fraction: Fraction of the time span used for testing (0 < f < 1).
        buffer: Length of the excluded period after the boundary.

    Returns:
        ``(dev, test)``: readings before the boundary, and readings from
        boundary + buffer onwards.

    Raises:
        ValueError: If ``test_fraction`` is not strictly between 0 and 1, or
            either part would be empty.
    """
    if not 0 < test_fraction < 1:
        raise ValueError(f"test_fraction must be between 0 and 1, got {test_fraction}")
    first, last = series.index.min(), series.index.max()
    boundary = first + (1 - test_fraction) * (last - first)
    dev = series[series.index < boundary]
    test = series[series.index >= boundary + buffer]
    if dev.empty or test.empty:
        raise ValueError("Split leaves the development or test part empty")
    return dev, test


# =============================================================================
# 3-5. Gaps: where they can go, making them, filling them
# =============================================================================

def valid_gap_starts(series: pd.Series, gap_length: pd.Timedelta,
                     context: pd.Timedelta = DEFAULT_CONTEXT,
                     max_spacing: pd.Timedelta = DEFAULT_MAX_SPACING,
                     min_side_readings: int = MIN_SIDE_READINGS) -> pd.DatetimeIndex:
    """
    Find the reading times where an artificial gap of ``gap_length`` can start.

    A start time ``t`` is valid if the window from ``t - context`` to
    ``t + gap_length + context`` lies inside the series and contains no
    spacing between real readings larger than ``max_spacing`` (including at
    the window edges), and at least ``min_side_readings`` readings fall
    within ``context`` on each side of the gap (counted the same way as
    ``context_readings``). This guarantees real readings to score against
    inside the gap and enough real readings on both sides for every method.
    The spacing rule alone is not enough for short contexts: with a 30-minute
    context and a 20-minute spacing, one side can hold a single reading.

    Args:
        series: Time series to place gaps in.
        gap_length: Length of the artificial gap.
        context: Amount of data required on each side of the gap.
        max_spacing: Largest allowed spacing between consecutive readings.
        min_side_readings: Fewest readings needed within ``context`` on each
            side of the gap (at least 2).

    Returns:
        The valid start times (a subset of the series' own timestamps).

    Raises:
        ValueError: If ``gap_length`` or ``context`` is not positive, or
            ``min_side_readings`` is less than 2.
    """
    if gap_length <= pd.Timedelta(0) or context <= pd.Timedelta(0):
        raise ValueError("gap_length and context must be positive")
    if min_side_readings < 2:
        raise ValueError(f"min_side_readings must be at least 2, got {min_side_readings}")
    t = series.index
    n = len(t)
    if n < 2:
        return t[:0]

    # big[i] is 1 if the spacing between readings i and i+1 is too large.
    big = (np.diff(t.asi8) > max_spacing.value).astype(int)
    big_cum = np.concatenate([[0], np.cumsum(big)])    # big_cum[k] = number of big spacings before reading k

    win_start = t - context
    win_end = t + gap_length + context
    lo = t.searchsorted(win_start, side="left")          # first reading inside the window
    hi = t.searchsorted(win_end, side="right") - 1       # last reading inside the window

    inside = (win_start >= t[0]) & (win_end <= t[-1]) & (hi > lo)
    lo_c, hi_c = np.clip(lo, 0, n - 1), np.clip(hi, 0, n - 1)
    no_big_spacing = (big_cum[hi_c] - big_cum[lo_c]) == 0
    edges_ok = ((t[lo_c] - win_start) <= max_spacing) & ((win_end - t[hi_c]) <= max_spacing)

    # Readings fill_gap will use on each side (same windows as context_readings):
    # before = [t - context, t);  after = (last gap reading, last gap reading + context].
    n_before = np.arange(n) - lo                              # lo = first reading >= t - context
    after_gap = t.searchsorted(t + gap_length, side="left")    # first reading after the gap
    last_in_gap = t[np.clip(after_gap - 1, 0, n - 1)]
    n_after = t.searchsorted(last_in_gap + context, side="right") - after_gap
    enough = (n_before >= min_side_readings) & (n_after >= min_side_readings)

    return t[inside & no_big_spacing & edges_ok & enough]


def make_gap(series: pd.Series, start, gap_length: pd.Timedelta) -> tuple[pd.Series, pd.Series]:
    """
    Hide the readings in ``[start, start + gap_length)``.

    Args:
        series: The complete time series.
        start: Start time of the gap.
        gap_length: Length of the gap.

    Returns:
        ``(observed, truth)``: the series with the gap's readings removed, and
        the removed readings (the true values the methods must reconstruct).

    Raises:
        ValueError: If no readings fall inside the gap.
    """
    start = pd.Timestamp(start)
    in_gap = (series.index >= start) & (series.index < start + gap_length)
    if not in_gap.any():
        raise ValueError("No readings fall inside the requested gap")
    return series[~in_gap], series[in_gap]


def context_readings(observed: pd.Series, gap_times: pd.DatetimeIndex,
                     context: pd.Timedelta = DEFAULT_CONTEXT) -> tuple[pd.Series, pd.Series]:
    """
    Return the observed readings used to fill a gap: those within ``context``
    before the first gap time, and within ``context`` after the last gap time.

    Args:
        observed: Series with the gap removed.
        gap_times: Times of the gap.
        context: Amount of data used on each side.

    Returns:
        ``(before, after)`` Series of readings.
    """
    first, last = gap_times.min(), gap_times.max()
    before = observed[(observed.index < first) & (observed.index >= first - context)]
    after = observed[(observed.index > last) & (observed.index <= last + context)]
    return before, after


def fill_gap(observed: pd.Series, gap_times: pd.DatetimeIndex, method: str,
             context: pd.Timedelta = DEFAULT_CONTEXT, lam: float | None = None,
             bc_type: str = "not-a-knot") -> pd.Series:
    """
    Reconstruct values at ``gap_times`` from the surrounding observed readings.

    Only observed readings within ``context`` before the first gap time and
    after the last gap time are used.

    Methods:
        - ``"linear"``: straight line between the readings either side
          (``numpy.interp``). The baseline.
        - ``"cubic"``: cubic spline through the context readings
          (``scipy.interpolate.CubicSpline``). Passes exactly through every
          reading, including its noise. Its end conditions are set by
          ``bc_type``.
        - ``"smoothing"``: cubic smoothing spline
          (``scipy.interpolate.make_smoothing_spline``, as in MMA3001 notes
          3.2 and 3.4). Does NOT pass exactly through the readings: it trades
          closeness to the data against curvature, which suits noisy data
          (notes 3.4.16). The trade-off is set by ``lam``.

    Args:
        observed: Series with the gap removed (from ``make_gap``).
        gap_times: Times to reconstruct.
        method: ``"linear"``, ``"cubic"`` or ``"smoothing"``.
        context: Amount of data used on each side of the gap.
        lam: Smoothing-spline only. ``None`` (default) lets SciPy choose the
            amount of smoothing for each fit by generalised cross-validation
            (GCV); a number >= 0 fixes it (larger = smoother). Its scale
            depends on time being measured in hours. Ignored by other methods.
        bc_type: Cubic-spline only. End (boundary) condition at the first and
            last context readings (MMA3001 notes 3.4.13): ``"not-a-knot"``
            (default; SciPy's default), ``"natural"`` (zero curvature at the
            ends) or ``"clamped"`` (zero slope at the ends). Ignored by other
            methods.

    Returns:
        Reconstructed values, indexed by ``gap_times``.

    Raises:
        ValueError: If ``method`` or ``bc_type`` is unknown, ``lam`` is negative, there are
            fewer than 2 context readings on either side of the gap, or (for
            the smoothing spline) fewer than 5 context readings in total.
    """
    if method not in METHODS:
        raise ValueError(f"method must be one of {METHODS}, got {method!r}")
    if lam is not None and lam < 0:
        raise ValueError(f"lam must be non-negative or None, got {lam}")
    if bc_type not in BC_TYPES:
        raise ValueError(f"bc_type must be one of {BC_TYPES}, got {bc_type!r}")
    before, after = context_readings(observed, gap_times, context)
    if len(before) < 2 or len(after) < 2:
        raise ValueError("Need at least 2 readings within the context on each side of the gap")
    known = pd.concat([before, after])
    if method == "smoothing" and len(known) < 5:
        raise ValueError("The smoothing spline needs at least 5 context readings in total")

    # Work in hours since the first known reading: small, well-scaled numbers.
    origin = known.index[0]
    x = (known.index - origin).total_seconds().to_numpy() / 3600
    x_new = (gap_times - origin).total_seconds().to_numpy() / 3600
    y = known.to_numpy()

    if method == "linear":
        y_new = np.interp(x_new, x, y)
    elif method == "cubic":
        y_new = CubicSpline(x, y, bc_type=bc_type)(x_new)
    else:
        y_new = make_smoothing_spline(x, y, lam=lam)(x_new)
    return pd.Series(y_new, index=gap_times, name=observed.name)


# =============================================================================
# 6. The experiment
# =============================================================================

RESULT_COLUMNS = ["gap_length", "gap_start", "method", "n_points", "mae", "rmse",
                  "max_abs_error", "bias", "frac_outside_range", "max_overshoot",
                  "min_estimate", "max_estimate", "fill_seconds"]
"""Columns of the table returned by ``evaluate``."""


def evaluate(series: pd.Series, gap_lengths, methods=METHODS, n_gaps: int = 200,
             context: pd.Timedelta = DEFAULT_CONTEXT,
             max_spacing: pd.Timedelta = DEFAULT_MAX_SPACING, seed: int = 0,
             lam: float | None = None, bc_type: str = "not-a-knot") -> pd.DataFrame:
    """
    Run the gap-filling experiment: random gaps, every method, scored against the truth.

    For each gap length, up to ``n_gaps`` start times are drawn at random
    (without replacement) from ``valid_gap_starts``. Every method fills the
    **same** gaps, so methods are compared on identical cases.

    Args:
        series: The series to test on (development OR test part - never both).
        gap_lengths: Iterable of gap lengths (Timedeltas or strings like "2h").
        methods: Methods to compare.
        n_gaps: Maximum number of random gaps per length.
        context: Data used on each side of a gap.
        max_spacing: Largest allowed spacing between readings near a gap.
        seed: Random seed, so results are reproducible.
        lam: Smoothing-spline setting passed to ``fill_gap`` (None = automatic).
        bc_type: Cubic-spline end condition passed to ``fill_gap``.

    Returns:
        DataFrame with one row per (gap length, gap, method) and columns:

        - ``gap_length``, ``gap_start``, ``method``
        - ``n_points``: number of readings reconstructed
        - ``mae``, ``rmse``, ``max_abs_error``: error size (variable's units)
        - ``bias``: mean signed error (estimate - truth); positive means the
          method over-estimates on average
        - ``frac_outside_range``: fraction of estimates outside the range
          (min to max) of the context readings used to make them - a measure
          of overshoot (MMA3001 notes 3.4: shape preservation)
        - ``max_overshoot``: largest distance of an estimate beyond that
          range (0 if none)
        - ``min_estimate``, ``max_estimate``: for physical-plausibility checks
        - ``fill_seconds``: time taken to fill the gap

    Raises:
        ValueError: If ``n_gaps`` is less than 1 or a method is unknown.
    """
    if n_gaps < 1:
        raise ValueError("n_gaps must be at least 1")
    for m in methods:
        if m not in METHODS:
            raise ValueError(f"method must be one of {METHODS}, got {m!r}")
    rng = np.random.default_rng(seed)
    rows = []
    for gap_length in gap_lengths:
        gap_length = pd.Timedelta(gap_length)
        starts = valid_gap_starts(series, gap_length, context, max_spacing)
        if len(starts) == 0:
            continue
        chosen = rng.choice(len(starts), size=min(n_gaps, len(starts)), replace=False)
        for start in starts[np.sort(chosen)]:
            observed, truth = make_gap(series, start, gap_length)
            for method in methods:
                t0 = time.perf_counter()
                estimate = fill_gap(observed, truth.index, method, context,
                                    lam=lam, bc_type=bc_type)
                elapsed = time.perf_counter() - t0
                est = estimate.to_numpy()
                err = est - truth.to_numpy()
                # Overshoot: how far estimates go beyond the range of the readings used.
                before, after = context_readings(observed, truth.index, context)
                lo = min(before.min(), after.min())
                hi = max(before.max(), after.max())
                beyond = np.maximum(est - hi, 0) + np.maximum(lo - est, 0)
                rows.append({
                    "gap_length": gap_length, "gap_start": start, "method": method,
                    "n_points": len(truth),
                    "mae": float(np.mean(np.abs(err))),
                    "rmse": float(np.sqrt(np.mean(err ** 2))),
                    "max_abs_error": float(np.max(np.abs(err))),
                    "bias": float(np.mean(err)),
                    "frac_outside_range": float(np.mean(beyond > 0)),
                    "max_overshoot": float(np.max(beyond)),
                    "min_estimate": float(np.min(est)),
                    "max_estimate": float(np.max(est)),
                    "fill_seconds": elapsed,
                })
    return pd.DataFrame(rows, columns=RESULT_COLUMNS)
