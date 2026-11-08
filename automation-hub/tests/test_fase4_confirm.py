import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from automation_hub.common import config
from automation_hub.pribadi.entries import Ctx, Queue, handle_message

TZ = ZoneInfo("Asia/Jakarta")
TS = int(datetime(2026, 11, 8, 9, 0, tzinfo=TZ).timestamp())
CFG = config.load()
PR = CFG["pribadi"]
CATS, ACC = CFG["categories"], CFG["accounts"]


class Env:
    def __init__(self, limit=None):
        self.q = Queue(Path(tempfile.mkdtemp()) / "queue.jsonl")
        self.ctx = Ctx({**PR, **({"confirm_over": limit} if limit is not None else {})}, None)

    def send(self, text, ts=TS, sender=1):
        return handle_message(text, ts, sender, CATS, self.q, ACC, None, None, self.ctx)


class ConfirmTest(unittest.TestCase):
    def test_config_limit_is_5jt(self):
        self.assertEqual(PR["confirm_over"], 5000000)

    def test_small_and_exact_limit_pass_through(self):
        e = Env()
        self.assertIn("Tercatat", e.send("cash kopi 18rb"))
        self.assertIn("Tercatat", e.send("jago bayar vendor 5jt"))
        self.assertEqual(len(e.q.all()), 2)

    def test_big_is_held_then_ya_records_with_original_date(self):
        e = Env()
        out = e.send("kemarin jago servis mobil 6jt")
        self.assertIn("Nominal besar", out)
        self.assertEqual(e.q.all(), [])
        out = e.send("ya", ts=TS + 60)
        self.assertIn("Tercatat 2026-11-07", out)
        (x,) = e.q.all()
        self.assertEqual(x["amount"], 6000000)
        e.send("ya", ts=TS + 90)
        self.assertEqual(len(e.q.all()), 1)

    def test_batal_drops(self):
        e = Env()
        e.send("jago servis mobil 6jt")
        self.assertIn("Dibatalkan", e.send("batal", ts=TS + 5))
        self.assertEqual(e.q.all(), [])
        self.assertNotIn("Tercatat", e.send("ya", ts=TS + 10))
        self.assertEqual(e.q.all(), [])

    def test_expired(self):
        e = Env()
        e.send("jago servis mobil 6jt")
        self.assertIn("kedaluwarsa", e.send("ya", ts=TS + 601))
        self.assertEqual(e.q.all(), [])

    def test_other_message_replaces_pending(self):
        e = Env()
        e.send("jago servis mobil 6jt")
        self.assertIn("Tercatat", e.send("cash parkir 5rb", ts=TS + 5))
        e.send("ya", ts=TS + 10)
        self.assertEqual([x["amount"] for x in e.q.all()], [5000])

    def test_only_same_sender_confirms(self):
        e = Env()
        e.send("jago servis mobil 6jt", sender=1)
        e.send("ya", ts=TS + 5, sender=2)
        self.assertEqual(e.q.all(), [])
        self.assertIn("Tercatat", e.send("ya", ts=TS + 6, sender=1))

    def test_transfer_exempt(self):
        e = Env()
        out = e.send("jago ke cash pindah kas 10jt")
        self.assertNotIn("Nominal besar", out)
        self.assertEqual(len(e.q.all()), 2)

    def test_multiline_all_held_together(self):
        e = Env()
        out = e.send("cash parkir 5rb\njago servis mobil 6jt")
        self.assertIn("Nominal besar", out)
        self.assertIn("1 baris lain", out)
        self.assertEqual(e.q.all(), [])
        out = e.send("ya", ts=TS + 5)
        self.assertIn("Tercatat 2 dari 2", out)

    def test_cek_not_held_and_disabled(self):
        e = Env()
        self.assertIn("SIMULASI", e.send("/cek jago servis mobil 6jt"))
        self.assertEqual(e.ctx.pending, {})
        off = Env(limit=0)
        self.assertIn("Tercatat", off.send("jago servis mobil 6jt"))


if __name__ == "__main__":
    unittest.main()
