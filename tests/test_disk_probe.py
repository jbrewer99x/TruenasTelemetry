import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch
import disk_probe


class DiskProbeTests(unittest.TestCase):
    def sense(self, asc, ascq, descriptor=False):
        data = bytearray(18)
        data[0] = 0x72 if descriptor else 0x70
        if descriptor:
            data[2:4] = bytes([asc, ascq])
        else:
            data[7] = 10
            data[12:14] = bytes([asc, ascq])
        return bytes(data)

    def test_sas_states_both_formats(self):
        for descriptor in (False, True):
            for asc, ascq, expected in [(0, 0, 'active'), (0x5e, 2, 'standby'),
                    (0x5e, 4, 'standby'), (0x5e, 1, 'idle'),
                    (0x5e, 9, 'low_power'), (0x5e, 0, 'low_power'),
                    (0x20, 0, 'unknown')]:
                self.assertEqual(disk_probe.scsi_state(self.sense(asc, ascq, descriptor)), expected)
        self.assertEqual(disk_probe.scsi_state(b''), 'unknown')
        self.assertEqual(disk_probe.scsi_state(b'\x70' * 4), 'unknown')

    def metadata(self, path):
        return 'ATA' if path.name == 'vendor' else '1'

    @patch('disk_probe.read')
    @patch('disk_probe.run')
    def test_sata_standby_never_reads_temperature(self, run, read):
        read.side_effect = self.metadata
        run.return_value = subprocess.CompletedProcess([], 0, b'drive state is: standby', b'')
        result = disk_probe.probe(Path('/sys/block/sda'))
        self.assertTrue(result['spun_down'])
        run.assert_called_once_with(['hdparm', '-C', '/dev/sda'])

    @patch('disk_probe.read', return_value='1')
    @patch('disk_probe.run')
    def test_sas_standby_only_requests_sense(self, run, read):
        run.return_value = subprocess.CompletedProcess([], 0, self.sense(0x5e, 2), b'')
        result = disk_probe.probe(Path('/sys/block/sdb'))
        self.assertTrue(result['spun_down'])
        run.assert_called_once_with(['sg_requests', '--raw', '/dev/sdb'])

    @patch('disk_probe.read', return_value='1')
    @patch('disk_probe.run')
    def test_sas_active_reads_temperature(self, run, read):
        run.side_effect = [
            subprocess.CompletedProcess([], 0, self.sense(0, 0), b''),
            subprocess.CompletedProcess([], 0, b'Current temperature = 31 C', b'')]
        result = disk_probe.probe(Path('/sys/block/sdb'))
        self.assertEqual(result['power_state'], 'active')
        self.assertFalse(result['spun_down'])
        self.assertEqual(result['temperature_c'], 31)
        self.assertEqual(run.call_args_list[0].args[0],
                         ['sg_requests', '--raw', '/dev/sdb'])

    @patch('disk_probe.subprocess.run')
    def test_subprocess_timeout_retained(self, run):
        disk_probe.run(['sg_requests', '--raw', '/dev/sdb'])
        self.assertEqual(run.call_args.kwargs['timeout'], 5)

    @patch('disk_probe.read')
    @patch('disk_probe.run')
    def test_failed_ata_probe_not_misreported_as_sleep(self, run, read):
        read.side_effect = self.metadata
        run.return_value = subprocess.CompletedProcess([], 1, b'drive state is: sleeping', b'error')
        result = disk_probe.probe(Path('/sys/block/sda'))
        self.assertIn('exit 1', result['error'])
        self.assertIn('error', result['error'])
        self.assertIsNone(result['spun_down'])
        self.assertEqual(result['power_state'], 'unknown')
        self.assertEqual(run.call_count, 1)

    @patch('disk_probe.read')
    @patch('disk_probe.run')
    def test_ata_temperature_has_no_wake_guard_and_explicit_type(self, run, read):
        read.side_effect = self.metadata
        run.side_effect = [subprocess.CompletedProcess([], 0, b'drive state is: active/idle', b''),
                           subprocess.CompletedProcess([], 0, b'{"temperature":{"current":32}}', b'')]
        result = disk_probe.probe(Path('/sys/block/sda'))
        self.assertFalse(result['spun_down'])
        self.assertEqual(result['temperature_c'], 32)
        self.assertEqual(run.call_args.args[0], ['smartctl', '-d', 'ata', '-n', 'standby,3,5', '-A', '-j', '/dev/sda'])

    @patch('disk_probe.read')
    @patch('disk_probe.run')
    def test_unknown_ata_preserves_diagnostics_without_temperature_read(self, run, read):
        read.side_effect = self.metadata
        run.return_value = subprocess.CompletedProcess(
            [], 1, b'drive state is: unknown', b'SG_IO: unsupported')
        result = disk_probe.probe(Path('/sys/block/sdab'))
        self.assertIn('SG_IO: unsupported', result['error'])
        self.assertIsNone(result['spun_down'])
        self.assertIsNone(result['temperature_c'])
        self.assertEqual(run.call_count, 1)

    @patch('disk_probe.read')
    @patch('disk_probe.run')
    def test_unknown_ata_guarded_fallback(self, run, read):
        import json
        read.side_effect = self.metadata
        for code, payload, state, temperature in [
            (0, {'ata_smart_attributes': {'table': []}, 'temperature': {'current': 31}}, 'active', 31),
            (3, {'smartctl': {'messages': [{'string': 'Device is in STANDBY mode, exit(3)'}]}}, 'standby', None),
            (3, {'smartctl': {'messages': [{'string': 'Device is in STANDBY_Y mode, exit(3)'}]}}, 'low_power', None),
            (5, {'smartctl': {'messages': [{'string': 'CHECK POWER MODE not implemented'}]}}, 'unknown', None),
            (3, {}, 'unknown', None),
        ]:
            run.reset_mock()
            run.side_effect = [subprocess.CompletedProcess([], 0, b'drive state is: unknown', b''),
                              subprocess.CompletedProcess([], code, json.dumps(payload).encode(), b'')]
            result = disk_probe.probe(Path('/sys/block/sdab'))
            self.assertEqual(result['power_state'], state)
            self.assertEqual(result['temperature_c'], temperature)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args.args[0], ['smartctl', '-d', 'ata', '-n', 'standby,3,5', '-A', '-j', '/dev/sdab'])

    @patch('disk_probe.read', return_value='1')
    @patch('disk_probe.run', side_effect=subprocess.TimeoutExpired('sg_requests', 5))
    def test_timeout_is_per_disk_unknown(self, run, read):
        self.assertEqual(disk_probe.probe(Path('/sys/block/sdc'))['power_state'], 'unknown')


if __name__ == '__main__':
    unittest.main()
