"""Offline adoption/campaign contracts; no Docker calls or private material."""

import importlib

import pytest

from scripts.performance.local_container_disposal import Creation, Unconfirmed
from scripts.performance.local_container_sequence import Outcome, Cell
from tests.performance.test_windows_docker_provisioning import setup as provision_setup


def api():
    name = "scripts.performance.windows_adopted_campaign"
    assert importlib.util.find_spec(name) is not None, "adoption/campaign adapter missing"
    return importlib.import_module(name)


def fixture():
    mod = api()
    base, docker, provisioner = provision_setup()
    ids = {}
    for run in ("normal", "interrupted", "fresh"):
        ids[run] = {}
        for role in ("source", "destination"):
            # Existing fake produces fixture metadata only, never a real resource.
            provisioner._owners.clear()
            if docker.network is not None:
                docker.network["Containers"] = {}
            owner = provisioner.create(Creation(run, role), remaining=8)
            ids[run][role] = owner.container_id
            row = docker.containers[owner.container_id]
            row["State"]["Running"] = False
            row.update(Fresh=True, CommandOK=True, EnvironmentOK=True, LabelsOK=True, IsolationOK=True)
    docker.network["Containers"] = {}
    docker.network["LabelsOK"] = True
    docker.calls.clear()
    now = [0.0]

    def command(args, *, timeout):
        if args[0] == "start":
            docker.network["Containers"][args[-1]] = {}
            docker.containers[args[-1]]["Fresh"] = False
        if args[0] == "rm":
            docker.network["Containers"].setdefault(args[-1], {})
        return docker(args, timeout=timeout)

    engine = mod.AdoptedEndpoints(
        command,
        campaign="offline",
        image=provisioner.image,
        specs=provisioner.specs,
        network_id="f" * 64,
        handoff=ids,
        expected_environment=("PATH=/usr/bin:/bin",),
        clock=lambda: now[0],
    )
    return mod, docker, engine, ids, now


def campaign_cells(mod, engine):
    cells = []
    for run in engine.handoff:
        config = engine.config(run, source_sha="a" * 40)
        config[mod.debug.FIELD] = "a" * 64
        config["diagnostic_rate"] = [2, 1]
        cells.append(Cell(run, config, f"/configs/{run}.json", f"/controller/{run}"))
    return cells


def test_adopts_only_exact_fresh_ids_without_creating_or_mounting():
    _, docker, engine, ids, _ = fixture()
    engine.prepare(remaining=50)
    a = engine.create(Creation("normal", "source"), remaining=8)
    b = engine.create(Creation("normal", "destination"), remaining=8)
    assert (a.container_id, b.container_id) == tuple(ids["normal"].values())
    assert all(c[0] in ("inspect", "network", "start") for c in docker.calls)
    assert not any("create" in c or "--mount" in c for c in docker.calls)
    with pytest.raises(Unconfirmed):
        engine.create(Creation("normal", "source"), remaining=8)
    with pytest.raises(Unconfirmed):
        engine.create(Creation("fresh", "source"), remaining=8)


@pytest.mark.parametrize(
    "field,value",
    [
        ("Fresh", False),
        ("CommandOK", False),
        ("EnvironmentOK", False),
        ("LabelsOK", False),
        ("IsolationOK", False),
        ("Image", "sha256:" + "b" * 64),
    ],
)
def test_rejects_mismatch_without_start_or_removal(field, value):
    _, docker, engine, ids, _ = fixture()
    docker.containers[ids["normal"]["source"]][field] = value
    with pytest.raises(Unconfirmed):
        engine.prepare(remaining=50)
    assert not any(c[0] in ("start", "rm") for c in docker.calls)
    assert engine.unresolved_ids


def test_inspection_does_not_emit_env_full_config_or_host_config():
    _, docker, engine, _, _ = fixture()
    engine.prepare(remaining=50)
    templates = [c[c.index("--format") + 1] for c in docker.calls if "--format" in c]
    assert not any("{{json .Config.Env}}" in t or "{{json .Config}}" in t or "{{json .HostConfig}}" in t for t in templates)
    assert any("EnvironmentOK" in t for t in templates)


def test_failed_cleanup_retains_owner_and_blocks_next_pair():
    _, docker, engine, _, _ = fixture()
    engine.prepare(remaining=50)
    owner = engine.create(Creation("normal", "source"), remaining=8)
    docker.fail_remove = True
    with pytest.raises(Unconfirmed):
        engine.remove(owner.container_id, remaining=8)
    assert owner.container_id in engine.owned_ids
    with pytest.raises(Unconfirmed):
        engine.create(Creation("interrupted", "source"), remaining=8)


def test_campaign_three_fresh_pairs_cleanup_and_no_replay():
    mod, docker, engine, _, now = fixture()
    cells = campaign_cells(mod, engine)
    for cell in cells:
        cell.config[mod.debug.FIELD] = "a" * 64
        cell.config["diagnostic_rate"] = [2, 1]
    campaign = mod.Campaign(engine, guard=lambda: None, clock=lambda: now[0])
    seen = []

    def runner(plan):
        seen.extend(o.container_id for o in plan.owners)
        now[0] += 20
        return Outcome("INVALID_PARTIAL", plan.owners) if plan.interrupt else Outcome("PASS_CONTROLLED_FINITE_PAIR_DEBUG_CORRECTNESS")

    result = campaign.run(cells, runner, original_disk_free_bytes=10 * 2**30)
    assert len(result) == 3 and len(set(seen)) == 6
    assert not engine.owned_ids and docker.network is None
    with pytest.raises(Unconfirmed):
        campaign.run(cells, runner, original_disk_free_bytes=10 * 2**30)


def test_campaign_deadline_includes_setup_and_reserves_final_cleanup():
    mod, _, engine, _, now = fixture()
    budget = mod.CampaignBudget(clock=lambda: now[0])
    now[0] = 280
    with pytest.raises(TimeoutError):
        budget.cell()
    assert budget.remaining_cleanup() == 140
    now[0] = 420
    with pytest.raises(TimeoutError):
        budget.remaining_cleanup()


def test_cell_budget_cannot_restart_or_consume_campaign_cleanup_reserve():
    mod, _, _, _, now = fixture()
    budget = mod.CampaignBudget(clock=lambda: now[0])
    cell = budget.cell()
    now[0] = 95
    with pytest.raises(TimeoutError):
        cell.check_work()
    assert cell.remaining_cleanup() == 25
    now[0] = 120
    with pytest.raises(TimeoutError):
        cell.remaining_cleanup()
    now[0] = 119
    with pytest.raises(Unconfirmed):
        budget.remaining_cleanup()


def test_cancel_during_setup_retains_unvalidated_and_cleans_only_validated():
    mod, docker, engine, ids, now = fixture()
    cells = campaign_cells(mod, engine)
    for cell in cells:
        cell.config[mod.debug.FIELD] = "a" * 64
    calls = [0]

    def guard():
        calls[0] += 1
        if calls[0] >= 4:
            raise InterruptedError("fixture cancellation")

    campaign = mod.Campaign(engine, guard=guard, clock=lambda: now[0])
    with pytest.raises(Unconfirmed):
        campaign.run(cells, lambda p: None, original_disk_free_bytes=10 * 2**30)
    assert engine.unresolved_ids
    assert not any(c[0] == "start" for c in docker.calls)
    assert docker.network is not None


def test_wrong_handoff_repeated_id_rejected_before_commands():
    mod, docker, engine, ids, now = fixture()
    ids["fresh"]["source"] = ids["normal"]["source"]
    with pytest.raises(ValueError):
        mod.AdoptedEndpoints(
            docker,
            campaign="offline",
            image=engine.image,
            specs=engine.specs,
            network_id="f" * 64,
            handoff=ids,
            expected_environment=("PATH=/usr/bin:/bin",),
        )
    assert not docker.calls


def test_late_setup_stops_without_starting_and_retains_cleanup_failure():
    mod, docker, engine, ids, now = fixture()
    cells = campaign_cells(mod, engine)
    for cell in cells:
        cell.config[mod.debug.FIELD] = "a" * 64
    original = engine.command

    def late(args, *, timeout):
        result = original(args, timeout=timeout)
        now[0] = 421
        return result

    engine.command = late
    campaign = mod.Campaign(engine, guard=lambda: None, clock=lambda: now[0])
    with pytest.raises(Unconfirmed):
        campaign.run(cells, lambda p: None, original_disk_free_bytes=10 * 2**30)
    assert not any(c[0] == "start" for c in docker.calls)
    assert campaign.cleanup_errors and engine.unresolved_ids


def test_cell_config_must_match_approved_endpoint_mounts_before_adoption():
    mod, docker, engine, _, now = fixture()
    cells = campaign_cells(mod, engine)
    for cell in cells:
        cell.config["source"]["checkout"] = "/unapproved"
    campaign = mod.Campaign(engine, guard=lambda: None, clock=lambda: now[0])
    with pytest.raises(Unconfirmed):
        campaign.run(cells, lambda p: None, original_disk_free_bytes=10 * 2**30)
    assert not any(c[0] in ("start", "rm") for c in docker.calls)


@pytest.mark.parametrize("failure", [InterruptedError, RuntimeError])
def test_runner_failure_disposes_validated_future_pairs_without_replacement(failure):
    mod, docker, engine, _, now = fixture()
    cells = campaign_cells(mod, engine)
    campaign = mod.Campaign(engine, guard=lambda: None, clock=lambda: now[0])

    def runner(plan):
        raise failure("fixture")

    with pytest.raises(Unconfirmed):
        campaign.run(cells, runner, original_disk_free_bytes=10 * 2**30)
    assert len([c for c in docker.calls if c[0] == "start"]) == 2
    assert not engine.owned_ids and docker.network is None
    assert len(campaign.sequence.results) == 1


def test_final_cleanup_recomputes_remaining_cell_budget_after_removal():
    mod, docker, engine, ids, now = fixture()
    cells = campaign_cells(mod, engine)
    original = engine.command
    observed = []
    target = ids["normal"]["source"]

    def command(args, *, timeout):
        if args[0] == "inspect" and args[-1] == target and target in engine.removal_attempts:
            observed.append(timeout)
        result = original(args, timeout=timeout)
        if args[0] == "start":
            now[0] = 117
        if args[0] == "rm" and args[-1] == target:
            now[0] += 2
        return result

    engine.command = command
    campaign = mod.Campaign(engine, guard=lambda: None, clock=lambda: now[0])
    with pytest.raises(Unconfirmed):
        campaign.run(cells, lambda p: None, original_disk_free_bytes=10 * 2**30)
    assert observed and observed[0] <= 1


def test_never_requests_unrestricted_network_inspection_even_at_cleanup():
    mod, docker, engine, _, now = fixture()
    campaign = mod.Campaign(engine, guard=lambda: None, clock=lambda: now[0])

    def runner(plan):
        return Outcome("INVALID_PARTIAL", plan.owners) if plan.interrupt else Outcome("PASS_CONTROLLED_FINITE_PAIR_DEBUG_CORRECTNESS")

    campaign.run(campaign_cells(mod, engine), runner, original_disk_free_bytes=10 * 2**30)
    assert not any("{{json .}}" in c for c in docker.calls)


def test_unexpected_future_pair_network_attachment_blocks_start():
    _, docker, engine, ids, _ = fixture()
    engine.prepare(remaining=50)
    docker.network["Containers"][ids["fresh"]["source"]] = {}
    with pytest.raises(Unconfirmed):
        engine.create(Creation("normal", "source"), remaining=8)
    assert not any(c[0] == "start" for c in docker.calls)


def test_foreign_network_member_rejected_before_any_adoption():
    _, docker, engine, _, _ = fixture()
    docker.network["Containers"]["9" * 64] = {}
    with pytest.raises(Unconfirmed):
        engine.prepare(remaining=50)
    assert not engine.owned_ids and len(engine.unresolved_ids) == 6


def test_current_pair_cleanup_failure_stops_and_does_not_retry():
    mod, docker, engine, ids, now = fixture()
    campaign = mod.Campaign(engine, guard=lambda: None, clock=lambda: now[0])

    def runner(plan):
        docker.fail_remove = True
        return Outcome("PASS_CONTROLLED_FINITE_PAIR_DEBUG_CORRECTNESS")

    with pytest.raises(Unconfirmed):
        campaign.run(campaign_cells(mod, engine), runner, original_disk_free_bytes=10 * 2**30)
    for identity in ids["normal"].values():
        assert len([c for c in docker.calls if c[0] == "rm" and c[-1] == identity]) == 1
    assert len([c for c in docker.calls if c[0] == "start"]) == 2
    assert len(engine.owned_ids) == 6 and not engine.closed
