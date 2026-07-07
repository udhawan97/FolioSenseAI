"""Source-mode behavior of app.paths.

In a normal checkout the app is not frozen, so resources and writable data both
resolve to the repo root and the app keeps reading ./static, ./templates and
writing ./database and ./.env exactly as before packaging was added.
"""

from pathlib import Path

from app import paths


REPO_ROOT = Path(__file__).resolve().parent.parent


def test_not_frozen_in_source_checkout():
    assert paths.is_frozen() is False


def test_resource_dir_is_repo_root():
    assert paths.resource_dir() == REPO_ROOT


def test_data_dir_is_repo_root():
    assert paths.data_dir() == REPO_ROOT


def test_bundled_resources_resolve_from_resource_dir():
    assert (paths.resource_dir() / "static").is_dir()
    assert (paths.resource_dir() / "templates" / "index.html").is_file()
