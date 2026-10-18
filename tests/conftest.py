"""Every test gets its own copy of a freshly seeded catalog (data/catalog.db is never touched by tests).

The seed runs once per session into a template file; each test copies it, which takes milliseconds.
"""
import os
import shutil

import pytest

from src.catalog import db as catalog_db


@pytest.fixture(scope="session")
def _catalog_template(tmp_path_factory):
    path = tmp_path_factory.mktemp("catalog") / "template.db"
    catalog_db.use_path(path)
    catalog_db.ensure()
    return path


@pytest.fixture(autouse=True)
def isolated_catalog(_catalog_template, tmp_path, monkeypatch):
    path = tmp_path / "catalog.db"
    shutil.copyfile(_catalog_template, path)
    for suffix in ("-wal", "-shm"):
        src = str(_catalog_template) + suffix
        if os.path.exists(src):
            shutil.copyfile(src, str(path) + suffix)
    catalog_db.use_path(path)
    monkeypatch.setenv("CATALOG_DB_PATH", str(path))   # inherited by MCP server subprocesses started in a test
    yield path
