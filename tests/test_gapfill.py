"""
Tests for ``mma3001.gapfill`` (gap reconstruction).

Most tests use synthetic series built from known functions, so the correct
answer is known exactly:
  - linear interpolation must reproduce a straight line exactly;
  - a cubic spline must reproduce a cubic polynomial (to rounding error);
  - a smoothing spline must reproduce a straight line (it only penalises curvature),
    and on noisy data must land closer to the true curve than the exact spline.
"""

import numpy as np
import pandas as pd
import pytest

from mma3001.gapfill import (context_readings, evaluate, fill_gap, make_gap, prepare_series,
                             split_dev_test, valid_gap_starts)

TZ = "Australia/Melbourne"


def make_series(values_fn, n=200, step="10min", start="2024-03-01 00:00"):
    """Series of n readings every `step`, with value = values_fn(hours since start)."""
    idx = pd.date_range(start, periods=n, freq=step, tz=TZ)
    hours = np.arange(n) * pd.Timedelta(step) / pd.Timedelta("1h")
    return pd.Series(values_fn(hours), index=idx, name="Carbon dioxide", dtype=float)


LINE = make_series(lambda h: 400 + 5 * h)                                  # straight line
CUBIC = make_series(lambda h: 450 + 2 * h - 0.3 * h**2 + 0.01 * h**3)      # cubic polynomial


# =============================================================================
# prepare_series
# =============================================================================

def make_env():
    """Tiny long-format table with two sensors and two variables."""
    t = pd.date_range("2024-03-01 09:00", periods=3, freq="10min", tz=TZ)
    rows = []
    for sensor in (1, 2):
        for var, base in (("Carbon dioxide", 500.0), ("Temperature", 22.0)):
            for i, ti in enumerate(t[::-1]):                 # deliberately unsorted
                rows.append({"sensorid": sensor, "variable": var, "time": ti, "value": base + i})
    rows.append({"sensorid": 1, "variable": "Carbon dioxide", "time": pd.NaT, "value": 999.0})
    return pd.DataFrame(rows)


def test_prepare_selects_sorts_and_drops_missing():
    """Positive: only the requested sensor/variable, sorted by time, missing times dropped."""
    s = prepare_series(make_env(), sensorid=1, variable="Carbon dioxide")
    assert len(s) == 3
    assert s.index.is_monotonic_increasing
    assert 999.0 not in s.values


def test_prepare_accepts_plain_dates():
    """Positive: a plain date without a time zone is treated as local time."""
    s = prepare_series(make_env(), sensorid=1, start="2024-03-01 09:05")
    assert len(s) == 2


def test_prepare_no_matching_readings_raises():
    """Negative: an unknown sensor gives a clear error."""
    with pytest.raises(ValueError, match="No"):
        prepare_series(make_env(), sensorid=99)


def test_prepare_duplicate_times_raises():
    """Negative: two readings at the same time mean the data wasn't de-duplicated."""
    env = make_env()
    env = pd.concat([env, env.iloc[[0]]])
    with pytest.raises(ValueError, match="share a measurement time"):
        prepare_series(env, sensorid=1)


def test_prepare_missing_column_raises():
    """Negative: required columns must be present."""
    with pytest.raises(ValueError, match="value"):
        prepare_series(make_env().drop(columns="value"), sensorid=1)


# =============================================================================
# split_dev_test
# =============================================================================

def test_split_is_time_ordered_with_buffer():
    """Positive: all development readings come before the buffer, all test readings after it."""
    dev, test = split_dev_test(LINE, test_fraction=0.25, buffer=pd.Timedelta("2h"))
    assert dev.index.max() < test.index.min() - pd.Timedelta("2h") + pd.Timedelta("10min")
    assert len(dev) + len(test) < len(LINE)               # the buffer's readings are in neither
    assert set(dev.index).isdisjoint(test.index)


@pytest.mark.parametrize("bad", [0, 1, -0.2, 1.5])
def test_split_bad_fraction_raises(bad):
    """Negative: test_fraction must be strictly between 0 and 1."""
    with pytest.raises(ValueError, match="test_fraction"):
        split_dev_test(LINE, test_fraction=bad)


# =============================================================================
# valid_gap_starts
# =============================================================================

def test_gap_starts_leave_room_for_context():
    """Positive: every valid start has `context` of data before it and after the gap."""
    gap, ctx = pd.Timedelta("1h"), pd.Timedelta("2h")
    starts = valid_gap_starts(LINE, gap, context=ctx)
    assert len(starts) > 0
    assert starts.min() - ctx >= LINE.index.min()
    assert starts.max() + gap + ctx <= LINE.index.max()


def test_gap_starts_avoid_real_gaps_in_the_data():
    """Positive: no gap window may span across a real hole larger than max_spacing."""
    holey = LINE.drop(LINE.index[100:106])                 # a 70-minute hole in the data
    gap, ctx = pd.Timedelta("30min"), pd.Timedelta("1h")
    starts = valid_gap_starts(holey, gap, context=ctx, max_spacing=pd.Timedelta("25min"))
    last_before, first_after = LINE.index[99], LINE.index[106]   # real readings either side of the hole
    assert len(starts) > 0
    for s in starts:
        # A window that contains readings on BOTH sides of the hole would span it.
        spans_hole = (s - ctx <= last_before) and (s + gap + ctx >= first_after)
        assert not spans_hole


def test_gap_starts_tolerate_single_missed_reading():
    """Positive: one missed reading (a 20-minute spacing) does not block gaps there."""
    one_missing = LINE.drop(LINE.index[100])
    starts = valid_gap_starts(one_missing, pd.Timedelta("30min"), context=pd.Timedelta("1h"))
    assert LINE.index[99] in starts                       # a gap starting right beside it is fine


def test_gap_starts_min_side_readings_is_applied():
    """
    Positive: with readings every 20 min and a 40 min context, each side holds exactly 2 readings,
    so the default minimum (3) allows no gaps and a minimum of 2 allows them.
    """
    sparse = make_series(lambda h: 400 + 5 * h, n=100, step="20min")
    gap, ctx = pd.Timedelta("1h"), pd.Timedelta("40min")
    assert len(valid_gap_starts(sparse, gap, context=ctx)) == 0
    assert len(valid_gap_starts(sparse, gap, context=ctx, min_side_readings=2)) > 0


def test_gap_starts_guarantee_enough_readings_each_side():
    """
    Positive: with a short context and some 20-minute spacings, the spacing rule alone would allow
    gaps with one reading on a side. Every start returned has at least the minimum on both sides,
    counted independently with context_readings (the function fill_gap uses), and can be filled.
    """
    # Every 20 min up to reading 100, then every 10 min. In the 20-minute part a 30-minute window
    # holds only 1 reading. Both orders are checked, so a short side BEFORE the gap and a short
    # side AFTER it are each tested on their own (the other side being in the 10-minute part).
    gap, ctx = pd.Timedelta("30min"), pd.Timedelta("30min")
    for mixed in (LINE.drop(LINE.index[:100:2]), LINE.drop(LINE.index[100::2])):
        starts = valid_gap_starts(mixed, gap, context=ctx, min_side_readings=2)
        assert len(starts) > 0
        for s in starts:
            observed, truth = make_gap(mixed, s, gap)
            before, after = context_readings(observed, truth.index, ctx)
            assert len(before) >= 2 and len(after) >= 2
            fill_gap(observed, truth.index, "cubic", ctx)         # must not raise


def test_evaluate_short_context_does_not_crash():
    """Positive: with a short context, evaluate only uses gaps every method can fill, instead of crashing."""
    one_missing = LINE.drop(LINE.index[100::3])                    # many 20-minute spacings
    r = evaluate(one_missing, ["30min"], n_gaps=200, context=pd.Timedelta("30min"))
    assert len(r) > 0 and set(r["method"]) == {"linear", "cubic", "smoothing"}


def test_gap_starts_min_side_readings_below_two_raises():
    """Negative: fewer than 2 readings per side can never support a cubic spline."""
    with pytest.raises(ValueError, match="min_side_readings"):
        valid_gap_starts(LINE, pd.Timedelta("1h"), min_side_readings=1)


def test_gap_starts_non_positive_length_raises():
    """Negative: a gap must have positive length."""
    with pytest.raises(ValueError, match="positive"):
        valid_gap_starts(LINE, pd.Timedelta(0))


# =============================================================================
# make_gap
# =============================================================================

def test_make_gap_splits_series_exactly():
    """Positive: hidden + observed readings together are exactly the original series."""
    start = LINE.index[50]
    observed, truth = make_gap(LINE, start, pd.Timedelta("1h"))
    assert len(truth) == 6                                 # 6 readings in [start, start + 1 h)
    assert truth.index.min() == start
    # check_freq=False: joining series drops pandas' "frequency" label; the values and times are what matter.
    pd.testing.assert_series_equal(pd.concat([observed, truth]).sort_index(), LINE, check_freq=False)


def test_make_gap_with_no_readings_raises():
    """Negative: a gap that contains no readings cannot be scored."""
    with pytest.raises(ValueError, match="No readings"):
        make_gap(LINE, LINE.index[50] + pd.Timedelta("1min"), pd.Timedelta("5min"))


# =============================================================================
# fill_gap
# =============================================================================

def test_linear_reproduces_a_straight_line_exactly():
    """Positive: linear interpolation of a straight line has zero error."""
    observed, truth = make_gap(LINE, LINE.index[80], pd.Timedelta("3h"))
    estimate = fill_gap(observed, truth.index, "linear")
    np.testing.assert_allclose(estimate, truth, atol=1e-9)


def test_cubic_reproduces_a_cubic_polynomial():
    """Positive: a cubic spline through cubic-polynomial data recovers it (to rounding error)."""
    observed, truth = make_gap(CUBIC, CUBIC.index[80], pd.Timedelta("3h"))
    estimate = fill_gap(observed, truth.index, "cubic")
    np.testing.assert_allclose(estimate, truth, atol=1e-6)


def test_linear_does_not_reproduce_a_curve():
    """Positive (sanity): on curved data, linear interpolation has non-zero error - the test can tell them apart."""
    observed, truth = make_gap(CUBIC, CUBIC.index[80], pd.Timedelta("3h"))
    estimate = fill_gap(observed, truth.index, "linear")
    assert np.max(np.abs(estimate - truth)) > 0.1


def test_fill_only_uses_context_window():
    """
    Positive: a reading just OUTSIDE the context window has no effect on the fill,
    while a reading just INSIDE it does.
    """
    ctx = pd.Timedelta("2h")
    gap_start = CUBIC.index[100]
    observed, truth = make_gap(CUBIC, gap_start, pd.Timedelta("1h"))
    just_outside = gap_start - ctx - pd.Timedelta("10min")   # first reading beyond the window
    just_inside = gap_start - ctx                            # first reading in the window

    changed_outside = observed.copy(); changed_outside[just_outside] += 1000
    changed_inside = observed.copy(); changed_inside[just_inside] += 1000

    # Compared EXACTLY: a spline's sensitivity fades with distance, so a reading 2 h away
    # changes the estimates only slightly (~0.001) - but it must change them, and a
    # reading outside the window must not change them at all.
    base = fill_gap(observed, truth.index, "cubic", context=ctx)
    outside = fill_gap(changed_outside, truth.index, "cubic", context=ctx)
    inside = fill_gap(changed_inside, truth.index, "cubic", context=ctx)
    assert np.array_equal(outside.to_numpy(), base.to_numpy())
    assert not np.array_equal(inside.to_numpy(), base.to_numpy())


# --- smoothing spline -------------------------------------------------------

def test_smoothing_reproduces_a_straight_line():
    """
    Positive: a smoothing spline only penalises curvature, and a straight line has none,
    so it must reproduce a line exactly - whatever the amount of smoothing.
    """
    observed, truth = make_gap(LINE, LINE.index[80], pd.Timedelta("2h"))
    for lam in (None, 0.1, 1000.0):
        estimate = fill_gap(observed, truth.index, "smoothing", lam=lam)
        np.testing.assert_allclose(estimate, truth, atol=1e-6)


def test_smoothing_beats_exact_spline_on_noisy_data():
    """
    Positive: on noisy readings of a smooth curve, the smoothing spline's estimates are
    closer to the TRUE curve than the exact cubic spline's (notes 3.2 / 3.4.14).
    The noise is random but seeded, so the test is repeatable.
    """
    true_fn = lambda h: 450 + 40 * np.sin(h / 4)
    clean = make_series(true_fn)
    rng = np.random.default_rng(0)
    noisy = clean + rng.normal(0, 8, len(clean))           # ~8 ppm noise, like the real CO2 data
    errs = {"cubic": [], "smoothing": []}
    for i in range(30, 170, 10):
        observed, truth = make_gap(noisy, noisy.index[i], pd.Timedelta("1h"))
        for method in errs:
            estimate = fill_gap(observed, truth.index, method)
            errs[method].append(np.mean(np.abs(estimate - clean[truth.index])))
    assert np.mean(errs["smoothing"]) < np.mean(errs["cubic"])


def test_more_smoothing_gives_a_smoother_curve():
    """Positive: increasing lam reduces the curvature (wiggliness) of the reconstruction."""
    rng = np.random.default_rng(1)
    noisy = make_series(lambda h: 450 + 40 * np.sin(h / 4)) + rng.normal(0, 8, 200)
    observed, truth = make_gap(noisy, noisy.index[100], pd.Timedelta("2h"))

    def roughness(lam):
        est = fill_gap(observed, truth.index, "smoothing", lam=lam).to_numpy()
        return np.sum(np.diff(est, 2) ** 2)                 # size of second differences

    assert roughness(10.0) < roughness(0.01)


def test_evaluate_passes_lam_through():
    """Positive: a fixed lam given to evaluate is the one used for the smoothing spline."""
    rng = np.random.default_rng(2)
    noisy = make_series(lambda h: 450 + 40 * np.sin(h / 4)) + rng.normal(0, 8, 200)
    r = evaluate(noisy, ["1h"], methods=["smoothing"], n_gaps=3, seed=0, lam=5.0)
    for _, row in r.iterrows():
        observed, truth = make_gap(noisy, row["gap_start"], pd.Timedelta("1h"))
        estimate = fill_gap(observed, truth.index, "smoothing", lam=5.0)
        assert row["mae"] == pytest.approx(np.mean(np.abs(estimate - truth)))


def test_smoothing_negative_lam_raises():
    """Negative: the amount of smoothing cannot be negative."""
    observed, truth = make_gap(LINE, LINE.index[80], pd.Timedelta("1h"))
    with pytest.raises(ValueError, match="lam"):
        fill_gap(observed, truth.index, "smoothing", lam=-1.0)


def test_smoothing_needs_five_points():
    """Negative: with a tiny context (2 readings each side) the smoothing spline can't be fitted."""
    observed, truth = make_gap(LINE, LINE.index[80], pd.Timedelta("1h"))
    small = pd.Timedelta("25min")                           # 2 readings on each side
    fill_gap(observed, truth.index, "linear", context=small)   # fine for linear
    with pytest.raises(ValueError, match="at least 5"):
        fill_gap(observed, truth.index, "smoothing", context=small)


# --- cubic-spline boundary conditions ----------------------------------------

def test_bc_types_change_the_cubic_spline():
    """
    Positive: different end conditions give different reconstructions of curved data.

    A short context is used on purpose: the end condition acts at the outer edges of the context
    window and its effect shrinks by roughly x0.27 per reading towards the middle, so with the
    default 2 h context (about 12 readings each side) the fills differ by only ~1e-8 ppm.
    """
    observed, truth = make_gap(CUBIC, CUBIC.index[80], pd.Timedelta("2h"))
    short = pd.Timedelta("20min")
    results = {bc: fill_gap(observed, truth.index, "cubic", context=short, bc_type=bc).to_numpy()
               for bc in ("not-a-knot", "natural", "clamped")}
    assert np.abs(results["not-a-knot"] - results["natural"]).max() > 1e-3
    assert np.abs(results["not-a-knot"] - results["clamped"]).max() > 1e-3


def test_natural_spline_reproduces_a_straight_line():
    """Positive: a natural spline (zero end curvature) still reproduces a straight line exactly."""
    observed, truth = make_gap(LINE, LINE.index[80], pd.Timedelta("2h"))
    np.testing.assert_allclose(fill_gap(observed, truth.index, "cubic", bc_type="natural"), truth, atol=1e-9)


def test_unknown_bc_type_raises():
    """Negative: only the listed boundary conditions are accepted."""
    observed, truth = make_gap(LINE, LINE.index[80], pd.Timedelta("1h"))
    with pytest.raises(ValueError, match="bc_type"):
        fill_gap(observed, truth.index, "cubic", bc_type="periodic")


def test_fill_unknown_method_raises():
    """Negative: only "linear", "cubic" and "smoothing" are supported."""
    observed, truth = make_gap(LINE, LINE.index[80], pd.Timedelta("1h"))
    with pytest.raises(ValueError, match="method"):
        fill_gap(observed, truth.index, "quadratic")


def test_fill_too_little_context_raises():
    """Negative: at least 2 readings are needed on each side."""
    observed, truth = make_gap(LINE, LINE.index[1], pd.Timedelta("1h"))   # only 1 reading before
    with pytest.raises(ValueError, match="at least 2"):
        fill_gap(observed, truth.index, "linear")


# =============================================================================
# evaluate
# =============================================================================

def test_evaluate_scores_methods_on_the_same_gaps():
    """Positive: both methods are tested on identical gap positions (a paired comparison)."""
    r = evaluate(CUBIC, ["30min", "1h"], n_gaps=5, seed=1)
    lin = r[r["method"] == "linear"]["gap_start"].tolist()
    cub = r[r["method"] == "cubic"]["gap_start"].tolist()
    assert lin == cub and len(lin) == 10


def test_evaluate_rows_match_their_recorded_gaps():
    """
    Positive: every result row can be reproduced from its recorded gap_start, proving
    each method was really scored on the gap it claims (not just labelled with it).
    Uses a wavy curve so that both methods have non-zero errors.
    """
    wavy = make_series(lambda h: 450 + 30 * np.sin(h / 3))
    gap_length = pd.Timedelta("2h")
    results = evaluate(wavy, [gap_length], n_gaps=5, seed=2)
    for _, row in results.iterrows():
        observed, truth = make_gap(wavy, row["gap_start"], gap_length)
        estimate = fill_gap(observed, truth.index, row["method"])
        assert row["mae"] == pytest.approx(np.mean(np.abs(estimate - truth)))


def test_evaluate_passes_bc_type_through():
    """Positive: the boundary condition given to evaluate is the one used for the cubic spline."""
    r = evaluate(CUBIC, ["2h"], methods=["cubic"], n_gaps=3, seed=0, bc_type="natural")
    for _, row in r.iterrows():
        observed, truth = make_gap(CUBIC, row["gap_start"], pd.Timedelta("2h"))
        estimate = fill_gap(observed, truth.index, "cubic", bc_type="natural")
        assert row["mae"] == pytest.approx(np.mean(np.abs(estimate - truth)))


def test_bias_is_positive_for_linear_on_a_convex_curve():
    """
    Positive: on a curve that bends upwards (convex), a straight line between two points
    always lies ABOVE the curve, so linear interpolation must over-estimate (bias > 0).
    """
    convex = make_series(lambda h: 400 + 2 * (h - 16) ** 2)
    r = evaluate(convex, ["2h"], methods=["linear"], n_gaps=10, seed=0)
    assert (r["bias"] > 0).all()


def test_bias_is_zero_for_exact_reconstruction():
    """Positive: when the reconstruction is exact, the signed error (bias) is zero."""
    r = evaluate(LINE, ["1h"], methods=["linear"], n_gaps=5)
    np.testing.assert_allclose(r["bias"], 0, atol=1e-9)


def test_linear_never_overshoots():
    """
    Positive: linear interpolation can never leave the range of the readings it uses,
    even on noisy data, so its overshoot measures must be zero.
    """
    rng = np.random.default_rng(3)
    noisy = make_series(lambda h: 450 + 40 * np.sin(h / 4)) + rng.normal(0, 8, 200)
    r = evaluate(noisy, ["30min", "2h"], methods=["linear"], n_gaps=10)
    assert (r["frac_outside_range"] == 0).all() and (r["max_overshoot"] == 0).all()


def test_cubic_overshoots_a_sharp_step():
    """
    Positive: around a sharp step (e.g. CO2 jumping when people arrive) an exact cubic spline
    overshoots beyond the surrounding readings, and the overshoot columns detect it.

    The overshoot happens when the step is in the context *next to* the gap (the spline "rings"
    after the jump); a gap that swallows the whole step is just bridged by a smooth ramp.
    The step is at reading 96, so gaps starting a few readings either side of it are kept.
    """
    step = make_series(lambda h: np.where(h < 16, 420.0, 600.0))
    r = evaluate(step, ["1h"], methods=["cubic"], n_gaps=200)
    near_step = r[(r["gap_start"] >= step.index[86]) & (r["gap_start"] <= step.index[100])]
    assert len(near_step) > 0
    assert (near_step["max_overshoot"] > 0).any() and (near_step["frac_outside_range"] > 0).any()


def test_overshoot_counts_both_directions():
    """
    Positive: overshoot is measured below the lowest context reading as well as above the highest.

    Near the step the context spans 420 to 600, and the ringing spline goes both above 600 and
    below 420, so max_overshoot must equal the larger of the two excursions in every row.
    """
    step = make_series(lambda h: np.where(h < 16, 420.0, 600.0))
    r = evaluate(step, ["1h"], methods=["cubic"], n_gaps=200)
    near_step = r[(r["gap_start"] >= step.index[86]) & (r["gap_start"] <= step.index[100])]
    assert (near_step["min_estimate"] < 420 - 1e-6).any()  # some fills dip below the range
    expected = np.maximum.reduce([near_step["max_estimate"] - 600,
                                  420 - near_step["min_estimate"],
                                  np.zeros(len(near_step))])
    np.testing.assert_allclose(near_step["max_overshoot"], expected, atol=1e-9)


def test_min_max_estimate_columns_match_the_fill():
    """Positive: min_estimate / max_estimate are the extremes of the actual reconstruction."""
    rng = np.random.default_rng(4)
    noisy = make_series(lambda h: 450 + 40 * np.sin(h / 4)) + rng.normal(0, 8, 200)
    r = evaluate(noisy, ["2h"], n_gaps=3)
    for _, row in r.iterrows():
        observed, truth = make_gap(noisy, row["gap_start"], pd.Timedelta("2h"))
        est = fill_gap(observed, truth.index, row["method"])
        assert row["min_estimate"] == pytest.approx(est.min())
        assert row["max_estimate"] == pytest.approx(est.max())


def test_evaluate_known_answers():
    """Positive: on a straight line, linear error is zero; on a cubic, spline error is ~zero."""
    r_line = evaluate(LINE, ["1h"], methods=["linear"], n_gaps=5)
    r_cubic = evaluate(CUBIC, ["1h"], methods=["cubic"], n_gaps=5)
    assert r_line["max_abs_error"].max() < 1e-9
    assert r_cubic["max_abs_error"].max() < 1e-6


def test_evaluate_is_reproducible():
    """Positive: the same seed gives the same gaps and errors."""
    a = evaluate(CUBIC, ["1h"], n_gaps=5, seed=3).drop(columns="fill_seconds")
    b = evaluate(CUBIC, ["1h"], n_gaps=5, seed=3).drop(columns="fill_seconds")
    pd.testing.assert_frame_equal(a, b)


def test_evaluate_bad_inputs_raise():
    """Negative: n_gaps below 1, or an unknown method, are rejected."""
    with pytest.raises(ValueError, match="n_gaps"):
        evaluate(LINE, ["1h"], n_gaps=0)
    with pytest.raises(ValueError, match="method"):
        evaluate(LINE, ["1h"], methods=["nearest"])
