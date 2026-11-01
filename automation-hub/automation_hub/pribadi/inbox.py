"""K3c: tulis transaksi ke file inbox TSV di folder OneDrive yang tersinkron di laptop (tanpa Azure).
Kolom: ID, Date, Account, Description, Debit (Spend), Credit (Income), Subcategory, Added By.
Makro Excel (docs/pribadi_inbox_macro.bas) menarik baris baru ke tabel _transaction berdasarkan ID."""
import time
from pathlib import Path

from .sync import entry_id

HEADER = ["ID", "Date", "Account", "Description", "Debit (Spend)", "Credit (Income)", "Subcategory", "Added By"]


def _clean(v):
    return " ".join(str(v).replace("\t", " ").replace("\r", " ").replace("\n", " ").split())


def inbox_row(e):
    spend = e["type"] == "pengeluaran"
    return [entry_id(e), e["date"], e.get("account") or "", e["note"],
            e["amount"] if spend else 0, 0 if spend else e["amount"], e["category"], e["sender"]]


def append_entries(path, entries, retries=3):
    path = Path(path)
    lines = ["\t".join(_clean(c) for c in inbox_row(e)) for e in entries]
    for attempt in range(retries):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            new_file = not path.exists() or path.stat().st_size == 0
            with open(path, "a", encoding="utf-8", newline="") as f:
                if new_file:
                    f.write("\t".join(HEADER) + "\r\n")
                f.write("".join(l + "\r\n" for l in lines))
            return
        except PermissionError:  # file sedang dikunci (sinkron/antivirus): coba lagi
            if attempt == retries - 1:
                raise
            time.sleep(2)
