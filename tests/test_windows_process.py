"""Windows-only real process identity tests; no external processes touched."""
import os
import subprocess
import sys
import unittest


@unittest.skipUnless(os.name == "nt", "Windows process identity")
class WindowsOwnership(unittest.TestCase):
    def test_live_process_and_fake_identity_do_not_kill_external(self):
        import platform_process as pp
        command = [
            sys.executable, "-c", "import time; time.sleep(40)",
            "--alias", "identity-test", "--port", "18119"
        ]
        process = subprocess.Popen(command, creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
        try:
            meta = pp.capture(process.pid, command)
            self.assertTrue(pp.is_owned(meta))
            invalid = {**meta, "created_at": meta["created_at"] - 50}
            self.assertFalse(pp.is_owned(invalid))
            self.assertFalse(pp.terminate_owned(invalid))
            self.assertIsNone(process.poll(), "Unowned process must remain alive")
            invalid_args = {**meta, "argv": command[:-1] + ["18000"]}
            self.assertFalse(pp.terminate_owned(invalid_args))
            self.assertIsNone(process.poll())
            self.assertTrue(pp.terminate_owned(meta))
            process.wait(timeout=10)
            self.assertFalse(pp.is_owned(meta))
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=10)

    def test_bad_metadata_fails_closed(self):
        import platform_process as pp
        for data in ({}, {"pid": 0}, {"pid": "bad"}, None):
            self.assertFalse(pp.is_owned(data))
            self.assertFalse(pp.terminate_owned(data))


if __name__ == "__main__":
    unittest.main()
