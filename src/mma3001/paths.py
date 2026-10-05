"""
Standard folder locations for the project.

Every script, notebook and test should get file locations from here rather
than typing out paths by hand. That way the code works on any computer the
repository is cloned to, not just the one it was written on.

Example:
    >>> from mma3001.paths import RAW_DATA_DIR
    >>> csv_path = RAW_DATA_DIR / "5EnvSensor_MayToDec2024_180kRows.csv"
"""

from pathlib import Path

# This file is at <repo>/src/mma3001/paths.py, so the repo root is three
# levels up: paths.py -> mma3001/ -> src/ -> <repo>.
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
"""Top-level folder of the repository."""

DATA_DIR: Path = PROJECT_ROOT / "data"
"""Folder for all data. Ignored by Git (see ``.gitignore``)."""

RAW_DATA_DIR: Path = DATA_DIR / "raw"
"""Original, unmodified data files exactly as provided (the unzipped CSVs)."""

PROCESSED_DATA_DIR: Path = DATA_DIR / "processed"
"""Data produced by our code, e.g. cleaned tables saved as Parquet."""

REPORTS_DIR: Path = PROJECT_ROOT / "reports"
"""Generated outputs: figures and the pytest HTML test report."""

TEST_FIXTURES_DIR: Path = PROJECT_ROOT / "tests" / "fixtures"
"""Small sample data files, committed to Git, used by the tests."""


def ensure_dirs() -> None:
    """
    Create the data and report folders if they do not already exist.

    The ``data/`` folders are ignored by Git, so a fresh clone of the
    repository will not have them. Call this once before saving any files.

    Returns:
        None
    """
    for folder in (RAW_DATA_DIR, PROCESSED_DATA_DIR, REPORTS_DIR):
        # parents=True also creates data/ if missing; exist_ok=True means
        # no error is raised if the folder is already there.
        folder.mkdir(parents=True, exist_ok=True)
