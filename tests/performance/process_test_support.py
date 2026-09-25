"""Test fixture readiness, outside the unchanged timeout being exercised."""
import time


def wait_ready(path, *, alive=lambda: True):
    deadline = time.monotonic() + 5
    while not path.exists():
        if not alive() or time.monotonic() >= deadline:
            raise AssertionError("test child did not publish readiness")
        time.sleep(0.005)


def prepare_durable_child(monkeypatch, ready):
    from scripts.performance import durable_memory
    original = durable_memory.spawn_owned

    def spawn(command, **options):
        child = original([*command, "--ready-file", str(ready)], **options)
        try:
            wait_ready(ready, alive=lambda: child.poll() is None)
        except BaseException:
            try:
                durable_memory._terminate_process_tree(child)
            finally:
                job = getattr(child, "nbsr_job", None)
                if job is not None:
                    job.close()
            raise
        return child

    monkeypatch.setattr(durable_memory, "spawn_owned", spawn)
