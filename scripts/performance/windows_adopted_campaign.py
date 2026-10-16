"""Offline-tested adoption of exact manually provisioned endpoints; no provisioning.

The caller supplies a reviewed handoff, public expected configuration and a bounded
DockerCommand. Construction is inert. Invoking Campaign.run needs separate live
trial authority. These local observations are not authenticated remote receipts.
"""

import json
import hashlib
import re
import stat
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath, PurePosixPath
import math
import time

from scripts.performance import native_debug_correctness as debug
from scripts.performance.local_container_disposal import Container, Creation, Unconfirmed
from scripts.performance.local_container_sequence import Sequence, _plans
from scripts.performance.windows_docker_provisioning import DockerProvisioner, _id, _name


@dataclass(frozen=True)
class MountMapping:
    """Exact trusted local controller/observed-source binding, with record identity."""

    controller: str
    observed: str
    record_sha256: str


def _windows_path(value):
    if type(value) is not str or not re.fullmatch(r"[A-Z]:\\[^/]+", value) or any(c in value[3:] for c in ':<>"|?*,~\x00\n\r'):
        raise ValueError("canonical local Windows drive path required")
    parts = value[3:].split("\\")
    if any(
        not p or p in (".", "..") or p.rstrip(" .") != p or re.fullmatch(r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", p)
        for p in parts
    ):
        raise ValueError("ambiguous Windows source path")
    return PureWindowsPath(value)


def validate_mapping(mapping):
    if (
        type(mapping) is not MountMapping
        or type(mapping.record_sha256) is not str
        or not re.fullmatch("[0-9a-f]{64}", mapping.record_sha256)
    ):
        raise ValueError("exact recorded mount mapping required")
    _windows_path(mapping.controller)
    from scripts.performance.windows_docker_provisioning import _path

    if type(mapping.observed) is not str:
        raise ValueError("observed source must be exact text")
    if mapping.observed.startswith("/"):
        if mapping.observed.startswith("//"):
            raise ValueError("ambiguous POSIX source root")
        _path(mapping.observed)
    else:
        _windows_path(mapping.observed)
    path = Path(mapping.controller)
    for entry in (path, *path.parents):
        info = entry.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError("source links/reparse points forbidden")
    if str(path.resolve(strict=True)) != mapping.controller:
        raise ValueError("source spelling/case/alias differs from materialized path")
    return path


def load_mount_mappings(wire, expected_sha256):
    """Parse a separately pinned PUBLIC mapping record; never infer an alias."""
    if (
        type(wire) is not bytes
        or len(wire) > 65536
        or type(expected_sha256) is not str
        or not re.fullmatch("[0-9a-f]{64}", expected_sha256)
        or hashlib.sha256(wire).hexdigest() != expected_sha256
    ):
        raise ValueError("mapping record digest mismatch")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate mapping field")
            result[key] = value
        return result

    value = json.loads(wire, object_pairs_hook=unique)
    if (
        type(value) is not dict
        or set(value) != {"schema", "bindings"}
        or value["schema"] != "nbsr-local-mount-mapping-v1"
        or type(value["bindings"]) is not list
        or not 1 <= len(value["bindings"]) <= 14
    ):
        raise ValueError("exact bounded mapping record required")
    mappings = []
    for row in value["bindings"]:
        if type(row) is not dict or set(row) != {"controller", "observed"}:
            raise ValueError("exact mapping row required")
        mapping = MountMapping(row["controller"], row["observed"], expected_sha256)
        validate_mapping(mapping)
        mappings.append(mapping)
    if len({m.controller for m in mappings}) != len(mappings):
        raise ValueError("duplicate mapped controller")
    return tuple(mappings)


class CampaignBudget:
    """One monotonic 420s deadline; 25s reserved for final campaign cleanup."""

    def __init__(self, *, clock=time.monotonic):
        self.clock = clock
        self.started = self.previous = clock()
        self.invalid = False
        if type(self.started) not in (int, float) or not math.isfinite(self.started):
            raise ValueError("invalid campaign clock")

    def now(self):
        value = self.clock()
        if self.invalid or type(value) not in (int, float) or not math.isfinite(value) or value < self.previous:
            self.invalid = True
            raise Unconfirmed("campaign clock uncertainty; ownership retained")
        self.previous = value
        return value

    def remaining_cleanup(self):
        value = self.started + 420 - self.now()
        if value <= 0:
            raise TimeoutError("campaign cleanup deadline")
        return value

    def check_work(self):
        if self.remaining_cleanup() <= 25:
            raise TimeoutError("campaign final cleanup reserve")

    def cell(self):
        if self.remaining_cleanup() < 145:
            raise TimeoutError("insufficient campaign time for fresh cell and final cleanup")
        return _CellBudget(self)


class _CellBudget:
    def __init__(self, campaign):
        self.campaign = campaign
        self.clock = campaign.now
        self.started = campaign.now()

    def check_work(self):
        self.campaign.check_work()
        if self.clock() >= self.started + 95:
            raise TimeoutError("cell work deadline")

    def remaining_cleanup(self):
        value = min(self.started + 120 - self.clock(), self.campaign.remaining_cleanup() - 25)
        if value <= 0:
            raise TimeoutError("cell cleanup deadline")
        return value


def _equal(expression, value):
    # Compare inside the Docker template; never emit environment/command values.
    return "(eq (json " + expression + ") " + json.dumps(json.dumps(value, sort_keys=True, separators=(",", ":"))) + ")"


class AdoptedEndpoints(DockerProvisioner):
    """Six exact stopped endpoint IDs, consumed once as three fresh pairs.

    Only validated owners are eligible for start/removal. Rejected or unobserved IDs
    remain unresolved and prevent successful campaign cleanup. No create/key-mount
    operation is implemented. Inherited provisioning create is overridden entirely.
    """

    def __init__(
        self,
        command,
        *,
        campaign,
        image,
        specs,
        network_id,
        handoff,
        expected_environment,
        inherited_labels=None,
        mount_mappings=(),
        clock=time.monotonic,
    ):
        labels = {} if inherited_labels is None else inherited_labels
        if type(labels) is not dict or any(
            type(k) is not str or type(v) is not str or not k or k.lower().startswith("nbsr.") or any(c in k + v for c in "\x00\n\r")
            for k, v in labels.items()
        ):
            raise ValueError("exact inherited labels cannot supply task ownership labels")
        self.inherited_labels = dict(labels)
        if type(mount_mappings) is not tuple:
            raise ValueError("immutable explicit mapping inventory required")
        self.mount_mappings = {}
        for mapping in mount_mappings:
            validate_mapping(mapping)
            if mapping.controller in self.mount_mappings:
                raise ValueError("duplicate controller mapping")
            self.mount_mappings[mapping.controller] = mapping
        super().__init__(command, campaign=campaign, image=image, specs=specs, clock=clock)
        sources = {
            getattr(s, field)
            for s in self.specs.values()
            for field in s.__dataclass_fields__
            if field not in ("address", "checkout_target")
        }
        if self.mount_mappings and set(self.mount_mappings) != sources:
            raise ValueError("complete exact mapping inventory required")
        observed = [m.observed for m in self.mount_mappings.values()]
        if observed and len({v.startswith("/") for v in observed}) != 1:
            raise ValueError("mixed observed source namespaces are ambiguous")
        observed_paths = [PurePosixPath(v) if v.startswith("/") else PureWindowsPath(v) for v in observed]
        if len(set(observed_paths)) != len(observed_paths):
            raise ValueError("ambiguous observed source mapping")
        if observed:

            def observed_path(value):
                mapped = self.mount_mappings[value].observed
                return PurePosixPath(mapped) if mapped.startswith("/") else PureWindowsPath(mapped)

            inputs = [
                observed_path(getattr(spec, field))
                for spec in self.specs.values()
                for field in ("checkout_source", "binaries_source", "manifest_source", "ca_source", "certificate_source", "key_source")
            ]
            outputs = [observed_path(spec.evidence_source) for spec in self.specs.values()]
            if any(a == b or a in b.parents or b in a.parents for a in outputs for b in inputs) or any(
                a == b or a in b.parents or b in a.parents for a, b in [(outputs[0], outputs[1])]
            ):
                raise ValueError("observed output overlaps inputs or other output")
        self.network = _id(network_id)
        if type(handoff) is not dict or len(handoff) != 3:
            raise ValueError("exact three-run handoff required")
        self.handoff = {}
        identities = set()
        for run, pair in handoff.items():
            _name(run)
            if type(pair) is not dict or set(pair) != {"source", "destination"}:
                raise ValueError("exact role pair required")
            self.handoff[run] = {}
            for role in ("source", "destination"):
                identity = _id(pair[role])
                if identity in identities or identity == self.network:
                    raise ValueError("fresh distinct endpoint IDs required")
                identities.add(identity)
                self.handoff[run][role] = identity
        if (
            type(expected_environment) is not tuple
            or not expected_environment
            or any(type(v) is not str or "\x00" in v or "=" not in v for v in expected_environment)
        ):
            raise ValueError("explicit reviewed public image environment required")
        self.environment = expected_environment
        self.unresolved_ids = set(identities)
        self.prepared = self.preparing = False
        self.issued = set()
        self.removal_attempts = set()
        self._run_index = 0
        self._fresh_required = False
        self.work_check = lambda: None
        self._closing_network = False

    def _labels(self, owner):
        return {**self.inherited_labels, **super()._labels(owner)}

    def _source_path(self, value):
        mapping = self.mount_mappings.get(value)
        if mapping is not None:
            validate_mapping(mapping)
            return _windows_path(value)
        return super()._source_path(value)

    def _mounts(self, role):
        mounts = super()._mounts(role)
        for mount in mounts:
            mapping = self.mount_mappings.get(mount["Source"])
            if mapping is not None:
                validate_mapping(mapping)
                mount["Source"] = mapping.observed
        return mounts

    def _inspect(self, call, owner):
        host = (
            "NetworkMode PidMode IpcMode UTSMode Privileged ReadonlyRootfs CapDrop CapAdd "
            "SecurityOpt PortBindings Devices Binds VolumesFrom PidsLimit NanoCpus Memory MemorySwap Init"
        ).split()
        fields = [
            '"Id":{{json .Id}}',
            '"Image":{{json .Image}}',
            '"User":{{json .Config.User}}',
            '"Mounts":{{json .Mounts}}',
            '"Networks":{{json .NetworkSettings.Networks}}',
            '"State":{"Running":{{json .State.Running}},"OOMKilled":{{json .State.OOMKilled}}}',
            '"HostConfig":{' + ",".join('"' + k + '":{{json .HostConfig.' + k + "}}" for k in host) + "}",
            '"LabelsOK":{{' + _equal(".Config.Labels", self._labels(owner)) + "}}",
            '"EnvironmentOK":{{' + _equal(".Config.Env", list(self.environment)) + "}}",
            '"CommandOK":{{and '
            + _equal(".Config.Entrypoint", ["python3"])
            + " "
            + _equal(".Config.Cmd", ["-B", "-c", "import time; time.sleep(3600)"])
            + "}}",
            '"Fresh":{{and (eq .State.Status "created") (eq .RestartCount 0)}}',
            '"IsolationOK":{{and (not .HostConfig.AutoRemove) '
            '(eq .HostConfig.RestartPolicy.Name "no") (not .HostConfig.PublishAllPorts) '
            "(not .HostConfig.DeviceRequests) (not .HostConfig.ExtraHosts) "
            "(not .HostConfig.Links) (not .HostConfig.GroupAdd) (not .HostConfig.Tmpfs)}}",
        ]
        template = "{" + ",".join(fields) + "}"

        def inspect(args):
            if owner.container_id not in self.removal_attempts:
                self.work_check()
            result = call([*args[: args.index("--format") + 1], template, owner.container_id])
            if result.code == 0:
                row = json.loads(result.stdout)
                if any(row.get(k) is not True for k in ("LabelsOK", "EnvironmentOK", "CommandOK", "IsolationOK")) or (
                    self._fresh_required and (row.get("Fresh") is not True or row.get("State", {}).get("Running") is not False)
                ):
                    raise Unconfirmed("endpoint public configuration or freshness mismatch")
                row["Labels"] = self._labels(owner)
                from scripts.performance.windows_docker_provisioning import CommandResult

                result = CommandResult(0, json.dumps(row), "")
            return result

        return super()._inspect(inspect, owner)

    def _network_row(self, call):
        # Do not request unrestricted inspect output, options or arbitrary labels.
        template = (
            '{"Id":{{json .Id}},"Name":{{json .Name}},"Driver":{{json .Driver}},'
            '"Internal":{{json .Internal}},"EnableIPv6":{{json .EnableIPv6}},'
            '"IPAM":{"Config":{{json .IPAM.Config}}},"Containers":{{json .Containers}},'
            '"LabelsOK":{{' + _equal(".Labels", {"nbsr.campaign": self.campaign}) + "}}}"
        )

        def inspect(args):
            if not self._closing_network:
                self.work_check()
            result = call([*args[: args.index("--format") + 1], template, self.network])
            row = json.loads(self._success(result))
            if row.get("LabelsOK") is not True:
                raise Unconfirmed("network ownership label mismatch")
            row["Labels"] = {"nbsr.campaign": self.campaign}
            from scripts.performance.windows_docker_provisioning import CommandResult

            return CommandResult(0, json.dumps(row), "")

        row = super()._network_row(inspect)
        if not set(row["Containers"]).issubset(self.issued):
            raise Unconfirmed("unexpected unissued endpoint attached to network")
        return row

    def prepare(self, *, remaining):
        if self.preparing or self.prepared or self.uncertain:
            raise Unconfirmed("handoff is single-use")
        self.preparing = True
        try:
            with self._operation(remaining) as call:
                self._network_row(call)
                self._fresh_required = True
                for run, pair in self.handoff.items():
                    for role, identity in pair.items():
                        owner = Container(run, role, identity, True)
                        if self._inspect(call, owner) is None:
                            raise Unconfirmed("handed-off endpoint absent")
                        self._owners[identity] = owner
                        self.unresolved_ids.remove(identity)
                self.prepared = True
        except BaseException:
            self.uncertain = True
            raise
        finally:
            self._fresh_required = False

    def create(self, request, *, remaining):
        if (
            not self.prepared
            or self.uncertain
            or self.closed
            or type(request) is not Creation
            or request.run not in self.handoff
            or request.role not in ("source", "destination")
        ):
            raise Unconfirmed("unprepared or mismatched adoption")
        runs = list(self.handoff)
        run_index = runs.index(request.run)
        if run_index != self._run_index:
            if run_index != self._run_index + 1 or any(
                identity not in self._absent for identity in self.handoff[runs[self._run_index]].values()
            ):
                raise Unconfirmed("previous pair not confirmed absent or run out of order")
            self._run_index = run_index
        identity = self.handoff[request.run][request.role]
        if identity in self.issued or identity in self._absent:
            raise Unconfirmed("endpoint adoption replay")
        owner = self._owners[identity]
        self.issued.add(identity)  # A failed start may have acted; never reissue it.
        try:
            with self._operation(remaining) as call:
                self._network_row(call)
                self._fresh_required = True
                if self._inspect(call, owner) is None:
                    raise Unconfirmed("endpoint disappeared before adoption")
                self._fresh_required = False
                self._success(call(["start", identity]))
                row = self._inspect(call, owner)
                if row is None or row["State"]["Running"] is not True:
                    raise Unconfirmed("adopted endpoint not running")
                return owner
        except BaseException:
            self.uncertain = True
            raise
        finally:
            self._fresh_required = False

    def remove(self, identity, *, remaining):
        self.removal_attempts.add(identity)
        return super().remove(identity, remaining=remaining)

    def close_network(self, *, remaining):
        if self.unresolved_ids:
            raise Unconfirmed("handoff IDs remain unresolved")
        self._closing_network = True
        try:
            if self.owned_ids or self.closed:
                raise Unconfirmed("network still owned or already closed")
            with self._operation(remaining) as call:
                if self._network_row(call)["Containers"]:
                    raise Unconfirmed("network still has endpoints")
                self._success(call(["network", "rm", self.network]))
                result = call(["network", "inspect", "--format", "{{json .Id}}", self.network])
                if (
                    result.code != 1
                    or result.stdout.strip()
                    or result.stderr.strip() != "Error response from daemon: network " + self.network + " not found"
                ):
                    raise Unconfirmed("network absence unconfirmed")
                self.closed = True
        finally:
            self._closing_network = False


class _BudgetedAdoption:
    def __init__(self, engine, budget, guard):
        self.engine, self.budget, self.guard = engine, budget, guard
        self.current = self.run = None

    def budget_for(self, run):
        if self.run != run or self.current is None:
            raise Unconfirmed("no current adopted cell")
        return self.current

    def create(self, request):
        self.guard()
        if self.run != request.run:
            self.current = self.budget.cell()
            self.run = request.run
        self.current.check_work()
        owner = self.engine.create(request, remaining=self.current.remaining_cleanup() - 25)
        self.current.check_work()
        return owner

    def remove(self, identity):
        return self.engine.remove(identity, remaining=self.current.remaining_cleanup())

    def observe(self, probe):
        cleanup = probe.container.container_id in self.engine.removal_attempts
        if not cleanup:
            self.guard()
            self.current.check_work()
        result = self.engine.observe(probe, remaining=self.current.remaining_cleanup() - (0 if cleanup else 25))
        self.current.remaining_cleanup()
        return result


class Campaign:
    """One serialized campaign; callbacks must honor supplied command deadlines.

    Use WindowsWorkload with this object's budget_for and check_work callbacks. All
    Docker commands retain the existing Windows Job supervision. No hard guarantee
    is made for arbitrary injected callbacks that ignore deadlines.
    """

    def __init__(self, engine, *, guard, clock=time.monotonic):
        self.engine, self.guard, self.clock = engine, guard, clock
        self.started = False
        self.budget = self.adapter = self.sequence = None
        self.cleanup_errors = []

    def check_work(self):
        self.guard()
        self.budget.check_work()

    def budget_for(self, run):
        return self.adapter.budget_for(run)

    def run(self, cells, runner, *, original_disk_free_bytes):
        if self.started:
            raise Unconfirmed("campaign replay")
        self.started = True
        self.budget = CampaignBudget(clock=self.clock)
        self.engine.clock = self.budget.now
        self.adapter = _BudgetedAdoption(self.engine, self.budget, self.check_work)
        self.sequence = Sequence(self.adapter)
        self.engine.work_check = self.check_work
        primary = None
        results = None
        try:
            _plans(cells, original_disk_free_bytes)
            if [c.run for c in cells] != list(self.engine.handoff):
                raise Unconfirmed("cell and handoff order mismatch")
            for cell in cells:
                if cell.config.get(debug.FIELD) is None:
                    raise Unconfirmed("adopted campaign requires explicit debug provenance")
                expected = self.engine.config(cell.run, source_sha=cell.config["source_sha"])
                expected[debug.FIELD] = cell.config[debug.FIELD]
                expected["diagnostic_rate"] = [2, 1]
                if cell.config != expected:
                    raise Unconfirmed("cell differs from approved endpoint configuration")
            self.check_work()
            self.engine.prepare(remaining=self.budget.remaining_cleanup() - 25)
            self.check_work()

            def checked(plan):
                self.check_work()
                self.budget_for(plan.run).check_work()
                result = runner(plan)
                self.budget_for(plan.run).check_work()
                return result

            results = self.sequence.run(cells, checked, original_disk_free_bytes=original_disk_free_bytes)
        except BaseException as exc:
            primary = exc
        finally:
            from scripts.performance.local_container_disposal import Probe

            for owner in self.engine.retained_owners:
                if owner.container_id in self.engine.removal_attempts:
                    continue  # Failed automatic disposal is retained, not silently retried.
                try:
                    remaining = self.budget.remaining_cleanup()
                    if owner.container_id in self.engine.issued:
                        remaining = min(remaining, self.budget_for(owner.run).remaining_cleanup())
                    self.engine.remove(owner.container_id, remaining=remaining)
                    remaining = self.budget.remaining_cleanup()
                    if owner.container_id in self.engine.issued:
                        remaining = min(remaining, self.budget_for(owner.run).remaining_cleanup())
                    self.engine.observe(Probe(owner), remaining=remaining)
                except BaseException as exc:
                    self.cleanup_errors.append((owner.container_id, type(exc).__name__))
            try:
                self.engine.close_network(remaining=self.budget.remaining_cleanup())
                self.budget.remaining_cleanup()
            except BaseException as exc:
                self.cleanup_errors.append(("network", type(exc).__name__))
        if primary is not None or self.cleanup_errors:
            raise Unconfirmed("campaign incomplete; inspect results, unresolved IDs and retained owners") from primary
        return results
