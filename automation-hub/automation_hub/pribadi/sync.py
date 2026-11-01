"""Kirim antrean ke tujuan (file inbox atau Graph) tanpa baris ganda."""
import hashlib
import json


def entry_id(e):
    key = "|".join(str(e.get(k)) for k in ("ts", "sender", "account", "type", "amount", "category", "note"))
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def sync_queue(send, queue, sent_file):
    """send(entries) menulis ke tujuan, atau melempar error. Entri yang sudah terkirim dicatat idnya di
    sent_file, jadi tidak ada baris ganda bila proses putus sebelum antrean dikosongkan."""
    sent = set(json.loads(sent_file.read_text())) if sent_file.exists() else set()
    entries = queue.all()
    new = [e for e in entries if entry_id(e) not in sent]
    if new:
        send(new)
        sent.update(entry_id(e) for e in new)
        sent_file.write_text(json.dumps(sorted(sent)))
    if entries:
        queue.clear(len(entries))
    return len(new)
