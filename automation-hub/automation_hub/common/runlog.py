"""Log ke data/logs/<modul>_<tanggal>.log dan ringkasan run."""
import logging
from datetime import date

from .config import data_dir


class RunLog:
    def __init__(self, module, root=None):
        self.module = module
        self.ok, self.skipped, self.warnings = [], [], []
        log_dir = data_dir(root=root) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.path = log_dir / f"{module}_{date.today():%Y%m%d}.log"
        self.logger = logging.getLogger(f"automation_hub.{module}.{id(self)}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        self._handler = logging.FileHandler(self.path, encoding="utf-8")
        self._handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        self.logger.addHandler(self._handler)

    def done(self, msg):
        self.ok.append(msg)
        self.logger.info(msg)

    def skip(self, msg):
        self.skipped.append(msg)
        self.logger.info("SKIP %s", msg)

    def warn(self, msg):
        self.warnings.append(msg)
        self.logger.warning(msg)

    def summary(self):
        text = (f"[{self.module}] berhasil={len(self.ok)} dilewati={len(self.skipped)} "
                f"peringatan={len(self.warnings)}")
        self.logger.info(text)
        self._handler.close()
        self.logger.removeHandler(self._handler)
        return text
