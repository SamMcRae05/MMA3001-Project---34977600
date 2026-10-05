"""
Tests for ``mma3001.paths``.

These are deliberately simple: they check the project is installed
correctly and that pytest is set up, before any real code is written.
"""

from mma3001 import paths


def test_project_root_contains_pyproject():
    """Positive test: PROJECT_ROOT should point at the repo's top folder."""
    assert (paths.PROJECT_ROOT / "pyproject.toml").exists()


def test_data_dirs_are_inside_data_folder():
    """Positive test: raw and processed folders sit inside data/."""
    assert paths.RAW_DATA_DIR.parent == paths.DATA_DIR
    assert paths.PROCESSED_DATA_DIR.parent == paths.DATA_DIR


def test_ensure_dirs_creates_folders():
    """Positive test: ensure_dirs() creates the folders and can run twice safely."""
    paths.ensure_dirs()
    paths.ensure_dirs()  # second call must not raise an error
    assert paths.RAW_DATA_DIR.is_dir()
    assert paths.PROCESSED_DATA_DIR.is_dir()
    assert paths.REPORTS_DIR.is_dir()
