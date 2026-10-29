import unittest
from pathlib import Path
import tempfile

from automation_hub.common import config
from automation_hub.common.runlog import RunLog


class ConfigTest(unittest.TestCase):
    def test_default_config_valid(self):
        self.assertEqual(config.missing_keys(config.load()), [])

    def test_missing_keys_reported(self):
        cfg = {"groups": {}, "drive": {"subcon_inbox": "x"}, "dpr": {"template": "t"}}
        miss = config.missing_keys(cfg)
        self.assertIn("groups", miss)
        self.assertIn("drive.output", miss)
        self.assertIn("dpr.timezone", miss)

    def test_runlog_summary(self):
        with tempfile.TemporaryDirectory() as t:
            log = RunLog("m0", root=Path(t))
            log.done("a"); log.skip("b"); log.warn("c")
            self.assertIn("berhasil=1 dilewati=1 peringatan=1", log.summary())
            self.assertTrue(log.path.exists())


if __name__ == "__main__":
    unittest.main()
