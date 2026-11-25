import ipaddress
import unittest
from docker_trial import choose_subnet, existing_subnets, validate_stop, validate_same_process, session_count


class SubnetTests(unittest.TestCase):
    def test_cleanup_failure_requires_one_auto_cycle(self):
        self.assertEqual(session_count('auto-network', 1, True), 2)
        for mode, cycles in [('term', 1), ('kill', 1), ('network', 1), ('auto-network', 5)]:
            with self.assertRaises(ValueError):
                session_count(mode, cycles, True)

    def test_bounded_reconnect_cycles(self):
        self.assertEqual(session_count('auto-network', 5), 6)
        self.assertEqual(session_count('auto-network', 1), 2)
        self.assertEqual(session_count('term', 1), 2)
        for mode, cycles in [('auto-network', 0), ('auto-network', 6),
                             ('auto-network', True), ('auto-network', 1.5),
                             ('network', 5), ('term', 2), ('kill', 2)]:
            with self.assertRaises(ValueError):
                session_count(mode, cycles)

    def test_network_change_must_not_restart_connector(self):
        before = {'Id': 'connector-id', 'State': {'Running': True, 'Pid': 123,
                  'StartedAt': 'original-start', 'OOMKilled': False}}
        validate_same_process(before, before)
        for change in ({'Running': False}, {'Pid': 0}, {'Pid': 456},
                       {'StartedAt': 'new-start'}, {'OOMKilled': True}):
            with self.assertRaises(RuntimeError):
                validate_same_process(before, before | {'State': before['State'] | change})
        with self.assertRaises(RuntimeError):
            validate_same_process(before, before | {'Id': 'other-connector'})

    def test_kill_requires_dead_process_without_graceful_marker(self):
        dead = {'Running': False, 'ExitCode': 137, 'OOMKilled': False, 'Pid': 0}
        validate_stop(dead, 137, 'kill', False)
        for change in ({'Running': True}, {'ExitCode': 0}, {'OOMKilled': True}, {'Pid': 123}):
            with self.assertRaises(RuntimeError):
                validate_stop(dead | change, 137, 'kill', False)
        with self.assertRaises(RuntimeError):
            validate_stop(dead, 0, 'kill', False)
        with self.assertRaises(RuntimeError):
            validate_stop(dead, 137, 'kill', True)

    def test_graceful_requires_cleanup_marker(self):
        dead = {'Running': False, 'ExitCode': 0, 'OOMKilled': False, 'Pid': 0}
        validate_stop(dead, 0, 'term', True)
        with self.assertRaises(RuntimeError):
            validate_stop(dead, 0, 'term', False)
        with self.assertRaises(RuntimeError):
            validate_stop(dead, 0, 'unknown', True)

    def test_builtin_networks_without_subnets(self):
        networks = [{'IPAM': {'Config': None}}, {'IPAM': {'Config': []}},
                    {'IPAM': {'Config': [{'Subnet': '10.254.0.0/29'}]}}]
        self.assertEqual(existing_subnets(networks), [ipaddress.ip_network('10.254.0.0/29')])

    def test_skips_existing_networks(self):
        occupied = [ipaddress.ip_network('10.254.0.0/29'), ipaddress.ip_network('172.16.0.0/12')]
        self.assertEqual(str(choose_subnet(occupied)), '10.254.0.8/29')

    def test_fails_closed_when_range_occupied(self):
        with self.assertRaises(RuntimeError):
            choose_subnet([ipaddress.ip_network('10.0.0.0/8')])


if __name__ == '__main__':
    unittest.main()
