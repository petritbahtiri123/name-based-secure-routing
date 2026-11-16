import ast
from pathlib import Path

from scripts.ci.check import command_groups


def test_wp4_exporter_vectors_selected_once_with_bounded_check():
    core = next(c for c in command_groups("python-core") if c.name == "python-core")
    assert core.argv.count("tests/test_wp4_exporter_vectors.py") == 1
    source = Path(__file__).resolve().parents[1] / "test_wp4_exporter_vectors.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
             and n.func.value.id == "subprocess" and n.func.attr == "run"]
    assert len(calls) == 1
    call = calls[0]
    assert ast.literal_eval(call.args[0].elts[1]) == "scripts/generate_wp4_exporter_vectors.py"
    assert ast.literal_eval(call.args[0].elts[2]) == "--check"
    assert len(call.args[0].elts) == 3
    kwargs = {k.arg: k.value for k in call.keywords}
    assert ast.literal_eval(kwargs["timeout"]) == 30
