import subprocess

import pytest


def sysfs(tmp_path, *, device=False):
    net = tmp_path / 'sys/class/net/eth0'
    net.mkdir(parents=True)
    for name, value in {'type': '1', 'mtu': '1500', 'operstate': 'up', 'carrier': '1', 'speed': '10000'}.items():
        (net / name).write_text(value)
    (net / 'statistics').mkdir()
    for name in ('rx_bytes', 'tx_bytes', 'rx_packets', 'tx_packets', 'rx_dropped', 'tx_dropped', 'rx_errors', 'tx_errors'):
        (net / 'statistics' / name).write_text('0')
    (net / 'queues/rx-0').mkdir(parents=True)
    (net / 'queues/tx-0').mkdir()
    if device:
        (net / 'device/msi_irqs').mkdir(parents=True)
        (net / 'device/msi_irqs/31').touch()
        irq = tmp_path / 'proc/irq/31'
        irq.mkdir(parents=True)
        (irq / 'smp_affinity_list').write_text('2-3')
    return tmp_path / 'sys', tmp_path / 'proc'


def runner(argv):
    return dict(argv=argv, status='MEASURED', returncode=0, stdout='fixture', stderr='')


@pytest.mark.parametrize('name', ['', '../eth0', '/eth0', 'eth0/../../', 'eth0;id', 'eth0\n'])
def test_interface_name_is_not_a_path_or_shell_expression(tmp_path, name):
    from scripts.performance.linux_network_inventory import collect_network
    with pytest.raises(ValueError):
        collect_network(name, sys_root=tmp_path, proc_root=tmp_path, runner=runner)


def test_virtual_interface_never_becomes_physical_hardware_proof(tmp_path):
    from scripts.performance.linux_network_inventory import collect_network
    sys, proc = sysfs(tmp_path)
    result = collect_network('eth0', sys_root=sys, proc_root=proc, runner=runner)
    assert result['device_classification'] == 'NO_DEVICE_BACKING_REPORTED'
    assert result['external_hardware'] == 'NOT_PROVEN'
    assert result['hardware_ceiling'] == 'NOT_PROVEN'
    assert result['statistics']['rx_bytes']['value'] == 0


def test_device_backing_and_irq_are_observations_not_bare_metal_attestation(tmp_path):
    from scripts.performance.linux_network_inventory import collect_network
    sys, proc = sysfs(tmp_path, device=True)
    result = collect_network('eth0', sys_root=sys, proc_root=proc, runner=runner)
    assert result['device_classification'] == 'DEVICE_BACKING_REPORTED'
    assert result['irq_affinity']['31']['value'] == '2-3'
    assert result['external_hardware'] == 'NOT_PROVEN'
    assert result['dedicated_data_path'] == 'NOT_PROVEN'
    assert all(command['argv'][0] in ('ethtool', 'systemd-detect-virt') for command in result['commands'])


def test_missing_and_malformed_counters_are_not_zero_or_saturation(tmp_path):
    from scripts.performance.linux_network_inventory import collect_network
    sys, proc = sysfs(tmp_path)
    (sys / 'class/net/eth0/statistics/rx_bytes').write_text('-1')
    (sys / 'class/net/eth0/statistics/tx_bytes').unlink()
    result = collect_network('eth0', sys_root=sys, proc_root=proc, runner=runner)
    assert result['statistics']['rx_bytes']['status'] == 'INVALID'
    assert result['statistics']['tx_bytes']['status'] == 'UNAVAILABLE'
    assert result['statistics']['tx_bytes']['value'] is None


@pytest.mark.parametrize('failure,status', [(FileNotFoundError(), 'TOOL_UNAVAILABLE'),
    (PermissionError(), 'ADMIN_REQUIRED'), (subprocess.TimeoutExpired('ethtool', 5), 'TIMED_OUT')])
def test_tool_failures_remain_explicit(monkeypatch, failure, status):
    from scripts.performance import linux_network_inventory as inventory
    def fail(*a, **k):
        raise failure
    monkeypatch.setattr(inventory.subprocess, 'run', fail)
    assert inventory.run_command(['ethtool', '-i', 'eth0'])['status'] == status


@pytest.mark.parametrize('returncode', [0, 1])
def test_read_only_command_does_not_use_shell_or_hide_partial_permission_error(monkeypatch, returncode):
    from scripts.performance import linux_network_inventory as inventory
    seen = []
    def run(argv, **kwargs):
        assert kwargs.get('shell', False) is False
        assert kwargs['timeout'] == 5
        seen.append(argv)
        return subprocess.CompletedProcess(argv, returncode, 'partial link settings', 'Operation not permitted')
    monkeypatch.setattr(inventory.subprocess, 'run', run)
    result = inventory.run_command(['ethtool', '-x', 'eth0'])
    assert result['status'] == 'ADMIN_REQUIRED'
    assert result['stdout'] == 'partial link settings'
    assert seen == [['ethtool', '-x', 'eth0']]
