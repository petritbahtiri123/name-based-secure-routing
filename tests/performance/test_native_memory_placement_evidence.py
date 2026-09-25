import ast
from pathlib import Path
import pytest


def verifier():
    p = Path("evidence/performance/v2/native-live2048-memory2-8e0b28a2/analyze.py")
    module = ast.parse(p.read_text(encoding="utf-8"))
    namespace = {}
    exec(compile(ast.Module(body=[v for v in module.body if isinstance(v, ast.FunctionDef)], type_ignores=[]), str(p), "exec"), namespace)
    return namespace["verify_placement"]


@pytest.mark.parametrize("tamper", ["workers", "requested_cpus", "none"])
def test_observed_memory_placement_matches_requested(tamper):
    config = {"destination": {"cores": 2, "cpu_pool": [2, 6], "runtime_workers": 2}}
    env = {"linux_environment": {"selected_cpus": [2, 6]}, "runtime_workers": 2}
    if tamper == "workers":
        env["runtime_workers"] = 1
    if tamper == "requested_cpus":
        config["destination"]["cpu_pool"] = [0, 4]
    if tamper == "none":
        verifier()(config, env, "destination")
    else:
        with pytest.raises(AssertionError):
            verifier()(config, env, "destination")
