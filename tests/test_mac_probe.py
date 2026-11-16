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


if __name__ == '__main__':
    unittest.main()
