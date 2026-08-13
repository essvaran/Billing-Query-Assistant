import sys
from pathlib import Path

from scripts.bootstrap import ensure_project_root_on_path


def test_ensure_project_root_on_path() -> None:
    project_root = str(Path(__file__).resolve().parents[1])

    sys.path[:] = [entry for entry in sys.path if entry != project_root]

    ensure_project_root_on_path()

    assert project_root in sys.path
