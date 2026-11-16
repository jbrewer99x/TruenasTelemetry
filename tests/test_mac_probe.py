import unittest
import mac_probe


class MacProbeTests(unittest.TestCase):
    def test_cpu_usage_average_and_per_cpu(self):
        before = [(100, 1000), (0, 1000)]
        after = [(150, 1100), (100, 1100)]
        usage = mac_probe.cpu_usage(before, after)
        self.assertEqual(usage['per_cpu_percent'], [50.0, 100.0])
        self.assertEqual(usage['average_percent'], 75.0)

    def test_cpu_usage_handles_counter_wrap(self):
        top = (1 << 32) - 10
        usage = mac_probe.cpu_usage([(top, top)], [(10, 30)])
        self.assertEqual(usage['per_cpu_percent'], [50.0])

    def test_cpu_usage_idle_interval(self):
        usage = mac_probe.cpu_usage([(5, 5)], [(5, 5)])
        self.assertEqual(usage['average_percent'], 0.0)

    def test_core_types_three_levels(self):
        cpus = [{'logical-cpu-id': 0, 'cluster-type': b'E\0'},
                {'logical-cpu-id': 1, 'cluster-type': b'M\0'},
                {'logical-cpu-id': 2, 'cluster-type': b'P\0'}]
        clusters = [{'name': 'Super', 'cores': 1}, {'name': 'Performance', 'cores': 1},
                    {'name': 'Efficiency', 'cores': 1}]
        self.assertEqual(mac_probe.core_types(cpus, clusters), ['E', 'P', 'S'])

    def test_core_types_two_levels(self):
        cpus = [{'logical-cpu-id': 1, 'cluster-type': b'P\0'},
                {'logical-cpu-id': 0, 'cluster-type': b'E\0'}]
        clusters = [{'name': 'Performance', 'cores': 1}, {'name': 'Efficiency', 'cores': 1}]
        self.assertEqual(mac_probe.core_types(cpus, clusters), ['E', 'P'])

    def test_core_types_mismatch_is_empty(self):
        cpus = [{'logical-cpu-id': 0, 'cluster-type': b'E\0'}]
        self.assertEqual(mac_probe.core_types(cpus, []), [])
        self.assertEqual(mac_probe.core_types([], []), [])

    def test_disk_rates(self):
        before = {'disk0': {'model': 'SSD', 'read_bytes': 1000, 'write_bytes': 0}}
        after = {'disk0': {'model': 'SSD', 'read_bytes': 3000, 'write_bytes': 4000},
                 'disk9': {'model': 'New', 'read_bytes': 5, 'write_bytes': 5}}
        rates = mac_probe.disk_rates(before, after, 2.0)
        self.assertEqual(rates, {'disk0': {'model': 'SSD', 'read_bps': 1000.0,
                                           'write_bps': 2000.0}})

    def test_temperature_summary_groups_and_skips_calibration(self):
        readings = [('PMU tdie1', 40.0), ('PMU2 tdie2', 50.0), ('PMU tcal', 51.8),
                    ('PMU tdev1', 30.0), ('NAND CH0 temp', 35.0), ('PMU tdie3', -1.0)]
        groups = {g['label']: g for g in mac_probe.temperature_summary(readings)}
        self.assertEqual(set(groups), {'SoC die', 'SoC package', 'SSD'})
        self.assertEqual(groups['SoC die']['average_c'], 45.0)
        self.assertEqual(groups['SoC die']['maximum_c'], 50.0)
        self.assertEqual(groups['SoC die']['sensors'], 2)

    def test_gpu_stats_picks_accelerator_with_statistics(self):
        accelerators = [{'IOClass': 'Other'},
                        {'model': 'Apple M6', 'gpu-core-count': 12,
                         'PerformanceStatistics': {'Device Utilization %': 20,
                                                   'In use system memory': 1024}}]
        stats = mac_probe.gpu_stats(accelerators)
        self.assertEqual(stats['device_util'], 20)
        self.assertEqual(stats['memory_in_use_bytes'], 1024)
        self.assertIsNone(mac_probe.gpu_stats([]))

    def test_average_gpu(self):
        merged = mac_probe.average_gpu({'device_util': 10}, {'device_util': 30, 'model': 'M'})
        self.assertEqual(merged, {'device_util': 20.0, 'model': 'M'})
        self.assertEqual(mac_probe.average_gpu(None, {'device_util': 5}), {'device_util': 5})

    def test_memory_summary_from_vm_stat(self):
        text = ('Mach Virtual Memory Statistics: (page size of 16384 bytes)\n'
                'Pages free:                     75092.\n'
                'Pages wired down:                 100.\n'
                'Pages purgeable:                   10.\n'
                '"Translation faults":       374654103.\n'
                'File-backed pages:                 40.\n'
                'Anonymous pages:                  210.\n'
                'Pages occupied by compressor:      50.\n')
        page_size, pages = mac_probe.parse_vm_stat(text)
        self.assertEqual(page_size, 16384)
        self.assertEqual(pages['Translation faults'], 374654103)
        memory = mac_probe.memory_summary(page_size, pages, 1000 * 16384)
        self.assertEqual(memory['app_bytes'], 200 * 16384)
        self.assertEqual(memory['used_bytes'], 350 * 16384)
        self.assertEqual(memory['used_percent'], 35.0)
        self.assertEqual(memory['cached_bytes'], 50 * 16384)

    def test_parse_swap_used(self):
        self.assertEqual(mac_probe.parse_swap_used(
            'total = 2048.00M  used = 1.50G  free = 0.50G  (encrypted)'), 1610612736)
        self.assertEqual(mac_probe.parse_swap_used(
            'total = 0.00M  used = 0.00M  free = 0.00M  (encrypted)'), 0)
        self.assertIsNone(mac_probe.parse_swap_used(''))


if __name__ == '__main__':
    unittest.main()
