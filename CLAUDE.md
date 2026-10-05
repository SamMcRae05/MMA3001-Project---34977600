# CLAUDE.md – project context for the AI assistant

This file is read by Claude at the start of each working session so that
code stays consistent across sessions. It is also a useful summary for any
human contributor.

## Project
- MMA3001 (Numerical Methods & Machine Learning) individual project, Monash 2026. Worth 25%.
- Dataset: Monash Smart Infrastructure occupancy + environmental sensor data (Dataset 2).
- Specific question: _TODO – to be decided by Sam._
- Assessed on: documentation, validation, baseline comparison, performance/optimisation,
  reproducibility, and AI-use reflection. See the brief for the rubric.

## Working agreement
- Sam makes all engineering decisions (question, method, validation) and all Git commits.
- Claude edits files but never commits, pushes, or rewrites Git history.
- Claude's shell cannot delete files by default: only run read-only Git commands, with
  `git --no-optional-locks ...`, so no `.git/index.lock` file is left behind.
- Explain changes so Sam understands them – he will be questioned on the code without AI.
- At the end of each session, draft an `AI_LOG.md` entry; Sam completes the
  "how I verified" and "what I changed" columns.

## Code conventions
- All reusable code lives in `src/mma3001/` as modules. Notebooks only import and present.
- Google-style docstrings on every module, function and class (Args / Returns / Raises).
- Inline comments explain *why*, not *what*.
- Get file locations from `mma3001.paths`; never hard-code absolute paths.
- Every new function gets at least one positive and one negative pytest test in `tests/`.
  Use `pytest.approx` / `np.isclose` for floating-point comparisons.
- Never commit data. Raw data lives in `data/raw/` (git-ignored) and is never modified;
  derived data goes to `data/processed/` as Parquet.
- Keep `README.md` and `docs/` in sync with the code (regenerate docs with pdoc).

## Environment
- Sam's machine: Windows, VS Code, Python virtual environment in `.venv/`.
- Install: `pip install -e ".[dev]"`. Run tests: `pytest`.
