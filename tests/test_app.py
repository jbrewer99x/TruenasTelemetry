import unittest
from unittest.mock import patch
import app


class GpuProcessTests(unittest.TestCase):
    def test_parses_processes_including_commas_in_name(self):
        output = ("4242, /usr/lib/jellyfin-ffmpeg/ffmpeg, 312\n"
                  "77, python3 train.py --tags a,b, 2048\n")
        self.assertEqual(app.parse_gpu_process_lines(output), [
            {"pid": 4242, "process_name": "/usr/lib/jellyfin-ffmpeg/ffmpeg",
             "used_memory_mib": 312.0},
            {"pid": 77, "process_name": "python3 train.py --tags a,b",
             "used_memory_mib": 2048.0},
        ])

    def test_unavailable_memory_and_junk_lines(self):
        output = "No running processes found\n99, ollama, [N/A]\n"
        self.assertEqual(app.parse_gpu_process_lines(output), [
            {"pid": 99, "process_name": "ollama", "used_memory_mib": None},
        ])

    @patch("app.ssh_command", return_value="")
    def test_no_processes(self, ssh_command):
        self.assertEqual(app.parse_gpu_processes(), {"processes": [], "count": 0})
        self.assertIn("--query-compute-apps", ssh_command.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
