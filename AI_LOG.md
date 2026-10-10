# AI Use Log

A running record of how AI tools were used in this project, to support the AI
reflection required by the project brief (Section 7). One entry per working
session.

**AI tool used:** Claude (Anthropic), via the Claude app, with access to the
project folders on my computer.

**Columns:**
- *Task / prompt*: what I asked the AI to do.
- *AI output*: what it produced (files, explanations, suggestions).
- *How I verified it*: tests run, documents checked, reasoning I did myself.
- *What I changed / rejected*: edits I made, suggestions I didn't take, errors found.

---

## 2026-10-05 – Repository set-up

| Task / prompt | AI output | How I verified it | What I changed / rejected |
|---|---|---|---|
| Asked to assist with setting up GitHub repo, given the project brief and Week 1 notes (1.2–1.5, Workshop 1). Needed clarification on how to work best in VSCODE as had only set up Github in Colab Notebooks.| Read the brief and notes; recommended a `src/` package layout, keeping the ~2 GB dataset out of Git, pytest + pdoc, branching, and this log. | Cross checked Claude's suggested practices with content given in notebooks and practical exercises to ensure it made practical sense. Researched common accepted practice for using github and VSCODE with large datasets | Very little was changed/ rejected as it this stage the tasks is just basic code and software setup, no engineering decisions. Did however mandate the addition of an explicit AI log alongside the AI statement at the end. |
| Asked for explanation of how to clone repo into VSCODE specifically | Gave step-by-step set-up instructions. | Followed the steps myself: created the repo, configured Git, cloned it in VS Code. Checked in files to ensurue all included files had been cloned from the repository. | Nothing was changed, this was just a basic step giving assistance and reminders on how to clone a Github repository |
| Asked Claude to create an example code skeleton to structure where I would work and save elements of the project. | Created `pyproject.toml`, `.gitattributes`, project rules in `.gitignore`, `src/mma3001/paths.py` + tests, `data/README.md`, README outline, `CLAUDE.md`, this log. | read each file, ran `pytest`._ | Largely re-wrote the README file and AI declaration |

**Reflection notes:** _TODO (Sam) – anything learned, or anything the AI got wrong or unhelpful._

---

## 2026-10-06 – Data loading, tests and audit notebook (branch `data-audit`)

| Task / prompt | AI output | How I verified it | What I changed / rejected |
|---|---|---|---|
| Asked Claude to create data-loading functions, tests and an audit notebook (on a new `data-audit` branch, which I created). | Created `src/mma3001/io.py` (`load_occupancy`, `load_env`, `load_sensor_locations`), `tests/test_io.py` (21 positive/negative tests), hand-made test fixtures, and `notebooks/01_data_audit.ipynb`. **AI errors found while testing on the real data:** (1) the first `load_env` crashed because Claude assumed every reading has a `value` – the real file has four reading formats; (2) a bug silently dropped the time zone from `createdate`. Both were fixed and a test was added for (2). Claude also deleted `tests/fixtures/.gitkeep` without asking. | ran `pytest` (24 passed); read through io.py; Read through every test individually, questioned and examined all assumptions and properties for which Claude was testing. | Requested Claude not use actual data for the tests as Claude would be unable to know what the expected output should be. Instead created a small known dataset and ran the tests on the known dataset, as to compare to a known output. |
| Asked why all times are converted to Melbourne time with daylight saving. | Explained mixed +10/+11 offsets, Unix timestamps, human-schedule patterns, and DST ambiguity. Flagged that "Melbourne" is an assumption (offsets only show eastern Australia). | Went back through data myself to examine the time formatting, acknowledged it would have made comparison difficult and approved the converted time.| Accepted time formatting change|

## 2026-10-08 – Data audit findings

| Task / prompt | AI output | How I verified it | What I changed / rejected |
|---|---|---|---|
| Asked Claude to add analysis code to notebook to determine when occupancy sensors individually begin and end recording. | Computed first/last record per floor space: 1 occupancy device, 5 spaces; starts are staggered (Nov 2023 ×2, Mar 2024 ×2, May 2024 ×1); the May 2024 space also stops in Dec 2024. Added notebook section A4b (table + per-space records-per-day plot) at my request. | Reviewed the code myself to ensure it functioned as I instructed Claude to write it. Did not ask Claude to do any analysis itself or tell me explicitly when recordings beggining and ended, rather just write code to show when recordings beginning and ended for individual devices. | |
| I noticed temperature and CO₂ were constant for a whole week in the B6 `createdate` plot – physically implausible – and asked what was going on. | Investigated and corrected its earlier explanation: sensors were **re-sending the same old reading** (same time and value) every ~13 minutes. 136,600 of 179,447 uploads (76%) are exact repeats; three of the five env sensors contain only 1–3 genuine readings. Recommended de-duplication in a separate cleaning step. | This step was verification in itself, I questioned AI's portrayal of the data through it's chosen readings, the constant values over timeframes didn't seem physically plausible to me.| After plausbility check, I requested AI keep the misleading cells and graphs in the notebook to show my learning journey. |
| Asked for a time series of when each env sensor transmits, plus a summary table. | Added notebook section B5b: per-sensor table (first/last time, uploads, distinct measurement times, days with uploads) and per-sensor uploads-per-day plot (log scale). Results agree with the repeated-uploads check. | Reviewed Claude's code used to produce the plots, comppared the plots and takeaways against physical reasoning and existing knowledge of the dataset.  | Nothing was required to be changed in this step |

**Reflection notes (6–8 Oct):** _TODO (Sam)_

---

## 2026-10-08 to 10 – Data cleaning (branch `data-cleaning`)

| Task / prompt | AI output | How I verified it | What I changed / rejected |
|---|---|---|---|
| Asked Claude to write the de-duplication logic in a new `src/mma3001/cleaning.py` (I chose for Claude to write it provided a definition of a repeat). | Wrote `flag_repeated_uploads` / `remove_repeated_uploads` with documented assumptions, plus 14 tests in `tests/test_cleaning.py`. Checked on the real data: 136,600 repeats removed, 42,847 uploads kept – matching the audit's count, which was calculated a different way; re-running on cleaned data finds 0 repeats. Deliberately broke four parts of the logic in a scratch copy to confirm a test fails each time. | Examined the results and logic through the process seen in notebook. | Removed the entries Claude had flagged as "near repeats", as I felt they were either repeats or invalid data points. |
| Asked for a cleaning notebook (`notebooks/02_cleaning.ipynb`). | Built three parts: de-duplication before/after and continuous usable periods; sensor error codes (described only, decision left to me), occupancy event regularity and an example conversion to a regular 15-minute series. | Ran every cell on the full data before adding it, and this time checked the actual plotted values (not just the number of points) after the earlier "frozen clock" mistake. |  |

**Reflection notes (8–10 Oct):** _TODO (Sam)_
