"""K3: tulis antrean ke Tabel Excel di OneDrive pribadi lewat Microsoft Graph (stdlib saja).

Perintah:
  python -m automation_hub.pribadi.graph login    # sekali: login lewat kode perangkat
  python -m automation_hub.pribadi.graph doctor   # uji di file salinan: tambah 1 baris, baca balik, hapus
Butuh .env: MS_CLIENT_ID=<Application (client) ID dari Entra>. Panduan: docs/pribadi_graph_setup.md
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date

from ..common import config

AUTH = "https://login.microsoftonline.com/consumers/oauth2/v2.0/"
GRAPH = "https://graph.microsoft.com/v1.0"
SCOPE = "Files.ReadWrite offline_access"
EPOCH = date(1899, 12, 30)  # nol tanggal seri Excel

# urutan kolom tabel _transaction; None = kolom rumus, dibiarkan kosong agar Excel mengisinya
COLUMNS = ["Date", "Account", "Description", "Debit (Spend)", "Credit (Income)", "Income/(Expense)",
           "Subcategory", "Month", "Year", "Category", "Category Type"]


def excel_serial(iso_date):
    return (date.fromisoformat(iso_date) - EPOCH).days


def row_values(e):
    """Satu entri antrean -> satu baris tabel. Hanya kolom kuning yang diisi."""
    spend = e["type"] == "pengeluaran"
    return [excel_serial(e["date"]), e["account"], e["note"],
            e["amount"] if spend else 0, 0 if spend else e["amount"], None,
            e["category"], None, None, None, None]


class GraphError(Exception):
    pass


def _post_form(url, fields):
    data = urllib.parse.urlencode(fields).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data), timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}")


class Graph:
    def __init__(self, client_id, token_file, http=None):
        self.client_id = client_id
        self.token_file = token_file
        self._http = http or self._urlopen
        self._access = None
        self._exp = 0

    # ---- login ----
    def login(self, say=print):
        dc = _post_form(AUTH + "devicecode", {"client_id": self.client_id, "scope": SCOPE})
        if "device_code" not in dc:
            raise GraphError(f"login gagal: {dc.get('error_description', dc)}")
        say(dc["message"])
        end = time.time() + dc["expires_in"]
        while time.time() < end:
            time.sleep(dc.get("interval", 5))
            tok = _post_form(AUTH + "token", {"client_id": self.client_id, "device_code": dc["device_code"],
                                              "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
            if "access_token" in tok:
                self._save(tok)
                return
            if tok.get("error") != "authorization_pending":
                raise GraphError(f"login gagal: {tok.get('error_description', tok)}")
        raise GraphError("login kedaluwarsa, ulangi")

    def _save(self, tok):
        self._access, self._exp = tok["access_token"], time.time() + int(tok["expires_in"]) - 60
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        self.token_file.write_text(json.dumps({"refresh_token": tok["refresh_token"]}), encoding="utf-8")

    def token(self):
        if self._access and time.time() < self._exp:
            return self._access
        if not self.token_file.exists():
            raise GraphError("belum login: jalankan 'python -m automation_hub.pribadi.graph login'")
        rt = json.loads(self.token_file.read_text(encoding="utf-8"))["refresh_token"]
        tok = _post_form(AUTH + "token", {"client_id": self.client_id, "grant_type": "refresh_token",
                                          "refresh_token": rt, "scope": SCOPE})
        if "access_token" not in tok:
            raise GraphError(f"token ditolak, login ulang: {tok.get('error_description', tok)}")
        self._save(tok)
        return self._access

    # ---- panggilan Graph ----
    def _urlopen(self, method, url, headers, body):
        req = urllib.request.Request(url, body, headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                return r.status, json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read()
            return e.code, json.loads(raw) if raw else {}

    def call(self, method, path, body=None, retries=3):
        url = path if path.startswith("http") else GRAPH + path
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(retries):
            status, out = self._http(method, url, {"Authorization": "Bearer " + self.token(),
                                                   "Content-Type": "application/json"}, data)
            if status in (423, 429, 500, 502, 503, 504) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)  # file terkunci / throttle: coba lagi
                continue
            if status >= 400:
                raise GraphError(f"{method} {path} -> {status}: {out.get('error', {}).get('message', out)}")
            return out

    def _table(self, drive_path, table):
        return f"/me/drive/root:/{urllib.parse.quote(drive_path)}:/workbook/tables/{urllib.parse.quote(table)}"

    def add_rows(self, drive_path, table, rows):
        """Tambah baris ke akhir tabel dalam satu panggilan; kembalikan indeks baris pertama yang baru."""
        out = self.call("POST", self._table(drive_path, table) + "/rows/add", {"values": rows})
        return out.get("index")

    def get_row(self, drive_path, table, index):
        return self.call("GET", self._table(drive_path, table) + f"/rows/itemAt(index={index})")["values"][0]

    def delete_row(self, drive_path, table, index):
        self.call("DELETE", self._table(drive_path, table) + f"/rows/itemAt(index={index})")


def from_env():
    from .bot import load_env
    load_env()
    cid = os.environ.get("MS_CLIENT_ID")
    if not cid:
        raise GraphError("MS_CLIENT_ID belum diisi di .env")
    cfg = config.load().get("pribadi", {})
    base = config.data_dir() / "07_pribadi"
    return Graph(cid, base / "token.json"), cfg, base


def doctor():
    g, cfg, _ = from_env()
    path, table = cfg["onedrive_path"], cfg["table"]
    print(f"Uji di: {path} / tabel {table}")
    test = {"date": date.today().isoformat(), "type": "pengeluaran", "account": "Cash",
            "note": "TES BOT (akan dihapus)", "amount": 1000, "category": "Rumah Tangga"}
    idx = g.add_rows(path, table, [row_values(test)])
    row = g.get_row(path, table, idx)
    print("Baris terbaca balik:")
    for name, val in zip(COLUMNS, row):
        print(f"  {name:18} {val!r}")
    ok = row[5] == -1000 and row[9] not in ("", None)
    g.delete_row(path, table, idx)
    print("Baris tes dihapus.")
    print("HASIL: rumus ikut terisi, siap dipakai." if ok else
          "HASIL: kolom rumus TIDAK terisi otomatis, perlu cara lain. Kabari saya.")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "login":
        from_env()[0].login()
        print("Login berhasil.")
    elif cmd == "doctor":
        doctor()
    else:
        print(__doc__)
