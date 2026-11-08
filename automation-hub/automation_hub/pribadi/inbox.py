"""K3c: tulis transaksi ke file inbox TSV di folder OneDrive yang tersinkron di laptop (tanpa Azure).
Transaksi (Inbox Transaksi.tsv): ID, Date, Account, Description, Debit (Spend), Credit (Income), Subcategory, Added By.
K9: BBM motor (Inbox BBM.tsv, ID berakhiran 'b') dan bacaan meter listrik (Inbox Listrik.tsv, ID berakhiran 'l').
Makro Excel (docs/pribadi_inbox_macro.bas) menarik baris baru ke tabel masing-masing berdasarkan ID."""
import time
from pathlib import Path

from .sync import entry_id

HEADER = ["ID", "Date", "Account", "Description", "Debit (Spend)", "Credit (Income)", "Subcategory", "Added By"]
HEADER_BBM = ["ID", "TANGGAL", "SUB KATEGORI", "UANG KELUAR", "POSISI KAS", "KETERANGAN", "LITER", "HARSAT", "KM"]
HEADER_LISTRIK = ["ID", "Waktu", "kWH Topup", "kWH Sisa"]


def _clean(v):
    return " ".join(str(v).replace("\t", " ").replace("\r", " ").replace("\n", " ").split())


def inbox_row(e):
    spend = e["type"] == "pengeluaran"
    return [entry_id(e), e["date"], e.get("account") or "", e["note"],
            e["amount"] if spend else 0, 0 if spend else e["amount"], e["category"], e["sender"]]


def bbm_row(e):
    b = e["bbm"]
    return [entry_id(e) + "b", e["date"], e["category"], e["amount"], e.get("account") or "", e["note"], b["liter"], b["harsat"], b["km"]]


def listrik_row(e):
    li = e["listrik"]
    return [entry_id(e) + "l", li["t"].replace("T", " ")[:16], "" if li.get("topup") is None else li["topup"], li["sisa"]]


def _append(path, header, rows, retries=3):
    path = Path(path)
    lines = ["\t".join(_clean(c) for c in row) for row in rows]
    for attempt in range(retries):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            new_file = not path.exists() or path.stat().st_size == 0
            with open(path, "a", encoding="utf-8", newline="") as f:
                if new_file:
                    f.write("\t".join(header) + "\r\n")
                f.write("".join(l + "\r\n" for l in lines))
            return
        except PermissionError:  # file sedang dikunci (sinkron/antivirus): coba lagi
            if attempt == retries - 1:
                raise
            time.sleep(2)


def append_entries(path, entries, bbm_path=None, listrik_path=None):
    """Transaksi ke `path`; entri ber-bbm ke bbm_path dan ber-listrik ke listrik_path (bila diberikan).
    Entri kind=meter hanya bacaan meter, bukan transaksi. Penulisan ulang aman: makro menyaring ID yang sudah ditarik."""
    trx = [inbox_row(e) for e in entries if e.get("kind") != "meter"]
    if trx:
        _append(path, HEADER, trx)
    bbm = [bbm_row(e) for e in entries if e.get("bbm")]
    if bbm and bbm_path:
        _append(bbm_path, HEADER_BBM, bbm)
    lis = [listrik_row(e) for e in entries if e.get("listrik")]
    if lis and listrik_path:
        _append(listrik_path, HEADER_LISTRIK, lis)
