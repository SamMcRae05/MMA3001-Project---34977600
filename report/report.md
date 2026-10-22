# MMA3001 Project Report – Reconstructing Gaps in Building CO₂ Sensor Data

> **Status: working draft.** The numbered sections follow the brief's required report structure and
> are for Sam to write. The **Decisions and assumptions log** at the end records the choices made so far,
> who made them, and where the evidence is, so they can be written up and justified later.

## 1. Engineering problem
_TODO (Sam)_

## 2. Inputs, outputs and data
_TODO (Sam)_

## 3. Computational approach
_TODO (Sam)_

## 4. Validation method and results
_TODO (Sam)_

## 5. Comparison and optimisation
_TODO (Sam)_

## 6. Limitations and lessons learned
_TODO (Sam)_

## 7. AI-use reflection
_TODO (Sam) – see `AI_LOG.md` for the session-by-session record._

## 8. References
_TODO (Sam)_

---

## Decisions and assumptions log

**Who decided:** *Sam* = Sam's decision; *Sam (on AI suggestion)* = proposed by Claude and accepted
by Sam; *Default (open)* = a starting setting that may change after exploring the development data.

### A. Data source and handling

| # | Decision / assumption | Who | Evidence / where |
|---|---|---|---|
| A1 | Dataset: MMA3001 Dataset 2 (Monash Smart Infrastructure). Raw data is not stored in the repository (≈2 GB; Monash-owned). | Sam (on AI suggestion) | `data/README.md` |
| A2 | File names say "May to Dec 2024", but the data actually spans May 2023 – Apr 2026. The file names are not used as evidence of the time period. | Found in audit | `01_data_audit.ipynb` A3, B4 |
| A3 | All times are converted to `Australia/Melbourne` time, with daylight saving handled. **Assumption:** the buildings are in Melbourne (the UTC offsets only show an eastern-Australian time zone). | Sam (on AI suggestion) | `src/mma3001/io.py` (`LOCAL_TZ`) |
| A4 | The occupancy sensor location IDs are unreliable (spreadsheet labelled "Incorrect Data"; edStem thread #121: not synced at MSI's cloud level, no correction available). Environmental and occupancy data therefore cannot be paired by room. | Sam (from edStem #121) | `01_data_audit.ipynb` Part C |
| A5 | Readings are taken **at face value** as the true values. Results describe how well each method recovers what the sensor would have recorded, not the true room CO₂ (sensor measurement error is not included). | Sam | – |

### B. Cleaning

| # | Decision / assumption | Who | Evidence / where |
|---|---|---|---|
| B1 | **Exact repeated uploads removed.** An upload identical to an earlier upload from the same sensor (same measurement time and values for every variable) is a re-sent copy, not a new measurement. 136,600 of 179,447 uploads (76.1%) removed; the earliest-arriving copy is kept. | Sam (on AI suggestion) | `src/mma3001/cleaning.py`; `02_cleaning.ipynb` 1.1 |
| B2 | **Near-repeats removed: one upload per sensor per measurement time.** A sensor cannot take two different sets of readings at the same instant, and the later copies contained missing (NaN) values. 4 further uploads removed (42,843 kept). | **Sam** | `cleaning.py` (`match="time"`); `02_cleaning.ipynb` 1.7–1.8 |
| B3 | Three of the five environmental sensors (…0227, …0241, …0777) contain only 1–3 genuine readings and are effectively unusable. | Found in cleaning | `02_cleaning.ipynb` 1.1 |
| B4 | Sensor error codes occur only on formaldehyde (~16% of its readings). No rule applied, because formaldehyde is not used in this project. | Sam | `02_cleaning.ipynb` Part 2 |
| B5 | Missing values / missing times are dropped when the series is prepared. | Default | `gapfill.prepare_series` |

### C. Problem definition

| # | Decision / assumption | Who | Evidence / where |
|---|---|---|---|
| C1 | **Question (comparative)**, in Sam's wording (`gapfill.py` docstring): *"Can missing values in CO₂ readings be reasonably reliably reconstructed using interpolation, and how does reconstruction error grow with gap length when comparing linear interpolation and cubic spline methods?"* A smoothing spline has since been added as a third method (C6). No pass/fail accuracy threshold is used. | **Sam** | `src/mma3001/gapfill.py` |
| C2 | Variable: **CO₂** (ppm) only. | **Sam** | – |
| C3 | Sensor **6012002000869** (spreadsheet: building 60, room G.38, "Compactus_upper"), period **29 Feb – 14 Jun 2024**: its longest continuous run (13,800 readings, ~105 days). | Sam (on AI suggestion) | `02_cleaning.ipynb` 1.5 |
| C4 | Readings are normally 10 min apart; ~10% of spacings are 20 min (one missed reading); the largest is 30 min. | Data property | `02_cleaning.ipynb` 1.4 |
| C5 | Methods: **linear interpolation** (baseline) vs **cubic spline** (`scipy.interpolate.CubicSpline`, default "not-a-knot" end conditions). | **Sam** | `src/mma3001/gapfill.py` (`fill_gap`) |
| C6 | **Smoothing spline added** (`scipy.interpolate.make_smoothing_spline`, as used in notes 3.2 and 3.4). Reason: notes 3.4.16 recommend a smoothing spline *"when the observations contain noise and exact interpolation is not justified"*, and the CO₂ readings are noisy (whole-number ppm, ~8 ppm change between readings). Linear and cubic are both exact interpolators. | **Sam** (after comparing the design against notes 3.4.16) | `fill_gap(method="smoothing")` |
| C7 | Cubic spline is **not presumed better**: 3.4.16 recommends it when smooth first/second derivatives matter, which gap-filling does not require. It is included to test whether smoothness helps. | Sam (on AI suggestion) | notes 3.4.16 |

### D. Experiment and validation design

| # | Decision / assumption | Who | Evidence / where |
|---|---|---|---|
| D1 | **Two-part, time-ordered split** (no training set: interpolation does not learn parameters from data). Development = first 75% of the period (to 18 May 2024), used to explore and fix all choices; test = last 25% (19 May – 14 Jun 2024), run **once** at the end. Based on MMA3001 notes 5.5.5 and 5.6.6. | Sam (on AI suggestion; Sam raised the question) | `gapfill.split_dev_test` |
| D2 | 1-day **buffer** between development and test, so no gap or its context draws on both parts (notes 5.6.7). | Sam (on AI suggestion) | `split_dev_test(buffer=...)` |
| D3 | **Artificial gaps:** real readings are hidden and kept as the truth, then reconstructed and compared. | Sam (on AI suggestion) | `make_gap`, `evaluate` |
| D4 | Original timestamps kept; **no resampling** to an exact 10-min grid (resampling is itself interpolation and would add error before the experiment). | Sam (on AI suggestion) | `gapfill.py` module docstring |
| D5 | Gaps are only placed where no spacing exceeds **25 min** (`max_spacing`), i.e. single missed readings are tolerated, **and** where at least **3 readings** fall within the context on each side (`MIN_SIDE_READINGS`; the cubic spline needs 2 per side, the smoothing spline 5 in total). The second rule was added after a 30 min context crashed the experiment; it does not change any result with the 2 h context. | Default (open); 3-reading rule: Sam | `valid_gap_starts`; tests `test_gap_starts_*` |
| D6 | Each fill uses real readings within **2 h** each side of the gap (`context`). The spline's behaviour depends on this, so it should be explored on development data. | Default (open) | `fill_gap` |
| D7 | Gap lengths tested: 10 min, 30 min, 1 h, 2 h, 4 h, 8 h, 24 h; up to **200 random gaps per length**; fixed random seed for reproducibility. | Default (open) | `evaluate` |
| D8 | Both methods are scored on **exactly the same gaps** (paired comparison). | Sam (on AI suggestion) | `evaluate`; test `test_evaluate_rows_match_their_recorded_gaps` |
| D9 | Metrics per gap: mean absolute error, root-mean-square error and maximum absolute error (ppm), plus time to fill (s). Added later: **bias** (mean of estimate − truth; positive = over-estimates), **overshoot** (`frac_outside_range`, `max_overshoot`: how far estimates go above the highest or below the lowest context reading, a physical-plausibility check from notes 3.4.16) and the lowest/highest estimate. | Sam (on AI suggestion) | `evaluate`; tests `test_bias_*`, `test_cubic_overshoots_a_sharp_step`, `test_overshoot_counts_both_directions` |
| D10 | Smoothing amount `lam` fixed at **0.1** (time in hours), chosen on development data from the values searched in `03_gap_filling.ipynb` 7.3 (None/GCV, 0.001, 0.01, 0.1, 1, 10). To be confirmed by rerunning sections 5–8 with `LAM = 0.1` before the test (notes 3.4.14: choose smoothing by measured error, not appearance). Reason and criterion: Sam to write (see D-R below for the AI's version). | **Sam** (pending rerun) | `03_gap_filling.ipynb` 7.3 |
| D11 | Inside the fitting functions, time is measured in **hours** since the first context reading. Linear/cubic results don't depend on the unit; the smoothing spline's automatic smoothing does, and hours are well scaled. | Sam (on AI suggestion) | `fill_gap` |
| D12 | Cubic-spline boundary condition is a setting, `bc_type`: "not-a-knot" (default), "natural" or "clamped" (notes 3.4.16). The condition acts at the outer edges of the context window, not at the gap, and its effect fades quickly inwards; in a test on a smooth curve the three choices differed by only ~1e-8 ppm with the 2 h context, but ~0.1 ppm with a 20 min context. So it matters mainly when the context is short. To be checked on development data. | Default (open) | `fill_gap(bc_type=...)`, `evaluate(bc_type=...)` |

### D-R. Reasoning for the final settings – AI draft, for comparison only

> **Written by Claude (AI), not Sam.** Sam asked for this so he can compare it with his own reasoning,
> which will replace it. It explains the AI's suggested values and how it would defend them. All figures are
> **development-data** results from `03_gap_filling.ipynb` (seed 0, 200 gaps per length), with automatic
> smoothing (`LAM = None`) unless stated. They must be rechecked after the rerun with `LAM = 0.1`.

| Setting | Suggested | Reasoning | Likely challenge, and a defence |
|---|---|---|---|
| `LAM` (D10) | 0.1 (Sam's choice) | In 7.3, 0.1 gave the lowest MAE of all values tried at 2 h gaps (11.3 ppm vs 12.2 for GCV), was within 0.1 ppm of the best at 30 min (8.4 vs 8.3), and beat GCV clearly at 8 h (22.9 vs 27.1). Larger values (1, 10) were better still at 8 h but worse at short gaps. So 0.1 is a compromise across gap lengths, rather than the best value for any one. | *"Why not a different λ per gap length?"* In practice you know a gap's length before filling it, so this would be possible. But it adds a tuned setting per length, fitted to only 200 gaps each, which raises the risk of overfitting to the development data. One value is simpler and was not far from the best at any length tested. *"Why not GCV, which needs no choice?"* GCV picks λ for each gap by how well the curve predicts the context readings, not the hidden gap. Here it smoothed too little for long gaps (27.1 vs 22.9 ppm at 8 h). *"Even at 0.1, smoothing does not beat linear for 2 h+ gaps."* True (11.3 vs 11.3 at 2 h, 22.9 vs 18.0 at 8 h), and this is a finding to report, not hide. |
| `CONTEXT` (D6) | 2 h | In 7.1, 1, 2 and 4 h gave nearly identical MAE for every method (e.g. 8 h gaps, cubic 88.9/84.5/83.4, linear 18.0/18.0/18.9, smoothing 27.5/27.1/27.3 ppm). 2 h gives about 12 readings per side, well above the minimum of 3, and keeps the spline's ends far enough from the gap that the end condition has no effect. Readings from many hours away are unlikely to tell you much about CO2 now. | *"Was context tuned?"* It was tested, and it made no meaningful difference, so the middle value was kept rather than picking the lowest number (which would be chasing noise). *"The contexts were compared on different gaps."* Yes: context changes which gap positions qualify (7.1 note). Linear shows only small differences across contexts, even though it only uses the nearest reading on each side, which suggests the different gap sets matter little. |
| `BC_TYPE` (D12) | not-a-knot | With a 2 h context, all three end conditions gave identical MAE to two decimal places (7.2). With a 1 h context the differences were under 1 ppm (8 h: 88.9/89.7/90.0). The condition acts at the outer context readings, and its effect fades by about ×0.27 per reading inwards (tested in `test_bc_types_change_the_cubic_spline`). Not-a-knot is SciPy's default and assumes nothing about slope or curvature at the ends. | *"Did you consider boundary conditions?"* Yes, as notes 3.4.16 ask. They were tested and found to be irrelevant at this context length, and the reason is understood. That is a stronger result than ignoring them. |
| `MAX_SPACING` (D5) | 25 min | Not tuned: it follows from the data. Development spacings are 10 min (9,109), 20 min, i.e. one missed reading (1,140), and 30 min (1). 25 min keeps gaps where the sensor missed one reading but excludes longer outages, so the "truth" inside every artificial gap consists of real readings at normal spacing. | *"This excludes some data."* Only the windows around the rare longer outages. Allowing them would mean scoring against an artificial gap that already contains a real gap. |
| `MIN_SIDE_READINGS` (D5) | 3 | The smallest number that lets every method fill every allowed gap (cubic needs 2 per side, smoothing 5 in total). It is a requirement of the methods, not a tuned value. It changes no result at the 2 h context. | – |
| `GAP_LENGTHS` (D7) | 10 min – 24 h (7 lengths) | From one missed reading up to a full daily cycle, roughly doubling each step, so the growth of error with gap length (the project question) can be seen on a log scale. 24 h spans a whole daily cycle, so it shows what happens when the gap hides an entire day's pattern that no method can see from the readings either side. | *"Why stop at 24 h?"* By 24 h every method's error is several times the sensor's reading-to-reading change (about 8 ppm). Longer gaps would only confirm the trend. Optionally add 12 h to fill the 8→24 h jump. |
| `N_GAPS`, `SEED` (D7) | 200, 0 | 200 gaps per length gives a stable mean; the fixed seed makes every result reproducible. Fixed before the test and not changed afterwards. | *"Is 200 enough?"* Check on development data by rerunning with another seed: if the same method wins at each gap length, the conclusions don't depend on which gaps were drawn. *(To do.)* |
| `PLAUSIBLE_MIN` | 400 ppm | Indoor CO2 should not fall clearly below outdoor air (about 420 ppm in 2024 – **Sam to find a citable source**). 400 leaves a margin for sensor error. Used only to report plausibility; it does not change any fill. | *"The threshold is arbitrary."* It is a judgement, stated openly. The underlying numbers (lowest estimate, % of gaps outside the context range) are reported too, so a reader can apply their own threshold. |

**Criterion for "reasonably reliable"** – to be decided before the test. One defensible version: a method is
reasonably reliable for a gap length if its mean error on test data is comparable to the sensor's own
reading-to-reading change (about 8 ppm median, 24 ppm 95th percentile, 10 min apart) **and** it produces no
physically implausible values. On development data that would currently favour linear interpolation, and
smoothing at λ = 0.1, for gaps up to a few hours, and no method for 24 h gaps.

**General defence of the process:** every setting was fixed using development data only (D1). Where a
setting made no measurable difference (context, end condition), the standard or middle value was kept
rather than the numerically lowest, to avoid tuning to noise. Where it did matter (λ), the search range,
the values tried and the trade-off are all reported. The test data is used once, with these settings, and
its results are reported as they are.

### E. Software environment

Python 3.10.5; numpy 2.2.6; pandas 2.3.3; scipy 1.15.3; matplotlib 3.10.9; pytest 9.1.1; pdoc 16.0.0.
Full dependency list in `pyproject.toml`. Tests: `pytest` (90 tests at the time of writing).
