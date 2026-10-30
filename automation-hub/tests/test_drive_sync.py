import unittest
from unittest import mock

from automation_hub.proyek import drive_sync as D


class ListRemoteTest(unittest.TestCase):
    def test_parse_path_with_pipe_free_size(self):
        out = "H:\\x\\A & B.zip|123\nH:\\x\\C.zip|45\n\nnoise\n"
        with mock.patch.object(D, "_ps", return_value=out):
            self.assertEqual(D.list_remote("H:\\x"), [("H:\\x\\A & B.zip", 123), ("H:\\x\\C.zip", 45)])

    def test_sync_needs_config(self):
        self.assertEqual(D.sync({"drive": {}}, root=None, log=mock.Mock()), [])


if __name__ == "__main__":
    unittest.main()
