"""Selection contract: SQLite prototype is distinct from memory-only conformance."""
import sys

from scripts.ci.check import command_groups


def test_sqlite_history_explicit_selection_and_lint():
    commands = command_groups("python-core")
    selected = next(item for item in commands if item.name == "inclusion-persistence-sqlite-local")
    assert selected.cwd == "."
    assert selected.argv == (
        sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
        "tests/federation/test_local_history_sqlite.py",
        "tests/federation/test_inclusion_persistence.py",
    )
    lint = next(item for item in commands if item.name == "inclusion-persistence-sqlite-lint")
    assert lint.argv == (
        sys.executable, "-m", "ruff", "check", "--no-cache",
        "scripts/local_history_sqlite.py", "tests/federation/test_local_history_sqlite.py",
        "tests/ci/test_sqlite_history_selection.py",
    )
