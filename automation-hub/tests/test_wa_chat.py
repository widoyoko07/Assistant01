import tempfile
import unittest
from pathlib import Path

from automation_hub.common import wa_chat

SAMPLES = Path(__file__).parent / "samples"


class UsExportTest(unittest.TestCase):
    """Export iOS bergaya AS: [MM/DD/YY, H:MM:SS AM/PM], '<image omitted>' diikuti caption."""
    msgs = wa_chat.parse_chat(SAMPLES / "chat_us_ios.txt")

    def test_order_detected_from_file(self):
        lines = (SAMPLES / "chat_us_ios.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(wa_chat.date_order(lines), "mdy")

    def test_count_and_dates(self):
        self.assertEqual(len(self.msgs), 7)
        self.assertEqual(self.msgs[0]["ts"], "2026-10-24T17:33:16+07:00")
        self.assertEqual(self.msgs[-1]["ts"], "2026-10-28T09:10:41+07:00")

    def test_caption_strips_omitted_marker(self):
        m = self.msgs[1]
        self.assertTrue(m["media_omitted"])
        self.assertTrue(m["caption"].startswith("24/10/26 TPE\n- LPS"))
        self.assertNotIn("omitted", m["caption"])

    def test_image_without_caption_is_empty(self):
        self.assertEqual((self.msgs[2]["caption"], self.msgs[2]["media_omitted"]), ("", True))

    def test_blank_line_inside_message_kept(self):
        self.assertIn("Cable Tray\n\nLPS", self.msgs[3]["caption"])

    def test_explicit_order_overrides(self):
        with self.assertRaises(ValueError):
            wa_chat.parse_chat(SAMPLES / "chat_us_ios.txt", order="dmy")


class AndroidTest(unittest.TestCase):
    msgs = wa_chat.parse_chat(SAMPLES / "chat_android.txt")

    def test_count_matches_manual(self):
        self.assertEqual(len(self.msgs), 6)  # 6 stempel waktu di file

    def test_multiline_joined(self):
        m = self.msgs[1]
        self.assertEqual(m["sender"], "Budi Mandor")
        self.assertEqual(m["text"], "TBM pagi\nPekerja 12 orang\nSafety talk selesai")
        self.assertEqual(m["ts"], "2026-10-01T07:12:00+07:00")

    def test_system_messages_flagged_not_dropped(self):
        self.assertTrue(self.msgs[0]["system"])
        self.assertTrue(self.msgs[-1]["system"])
        self.assertEqual(sum(m["system"] for m in self.msgs), 2)

    def test_attachments(self):
        self.assertEqual(self.msgs[2]["attachments"], ["IMG-20261001-WA0003.jpg"])
        self.assertTrue(self.msgs[3]["media_omitted"])
        self.assertEqual(self.msgs[3]["attachments"], [])


class IosTest(unittest.TestCase):
    msgs = wa_chat.parse_chat(SAMPLES / "chat_ios.txt")

    def test_count(self):
        self.assertEqual(len(self.msgs), 6)

    def test_attached_and_invisible(self):
        self.assertEqual(self.msgs[1]["attachments"], ["00000012-PHOTO-2026-10-01-07-13-01.jpg"])
        self.assertEqual(self.msgs[1]["ts"], "2026-10-01T07:13:01+07:00")

    def test_ampm(self):
        self.assertEqual(self.msgs[3]["ts"], "2026-10-01T13:05:10+07:00")
        self.assertEqual(self.msgs[4]["ts"], "2026-10-01T00:30:00+07:00")

    def test_system_ios(self):
        self.assertTrue(self.msgs[5]["system"])
        self.assertEqual(self.msgs[5]["text"], "Andi keluar")


class JsonlTest(unittest.TestCase):
    def test_idempotent_and_overlap_dedupe(self):
        a = wa_chat.parse_chat(SAMPLES / "chat_android.txt")
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "m.jsonl"
            n1 = wa_chat.write_jsonl(a, out)
            first = out.read_text(encoding="utf-8")
            wa_chat.write_jsonl(a, out)
            self.assertEqual(first, out.read_text(encoding="utf-8"))
            self.assertEqual(len(wa_chat.merge_exports(a, a[2:])), n1)


if __name__ == "__main__":
    unittest.main()
