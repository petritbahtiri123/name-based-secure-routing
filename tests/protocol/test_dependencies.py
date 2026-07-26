from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROTOCOL = ROOT / "nbsr" / "protocol"
FORBIDDEN = {
    "fastapi",
    "jwt",
    "kubernetes",
    "opa",
    "pydantic",
    "uvicorn",
}


def test_protocol_core_has_no_adapter_dependencies() -> None:
    assert PROTOCOL.is_dir()
    violations: list[str] = []
    for path in sorted(PROTOCOL.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.split(".", 1)[0] in FORBIDDEN:
                    violations.append(f"{path.name}: {name}")
    assert violations == []
