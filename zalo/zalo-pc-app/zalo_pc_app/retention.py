"""Tu xoa du lieu cu theo cai dat (13/11/2026) de messages.db / tep tai ve / thu muc dong bo khong phinh mai.

Cai dat luu o <data>/retention.json, DOI TUC THI (khong can khoi dong lai). 0 = khong xoa/khong gioi han:
  messages_days    xoa tin nhan cu hon N ngay                   (mac dinh 365)
  max_per_thread   moi hoi thoai chi giu N tin moi nhat          (mac dinh 20000)
  files_days       xoa tep/anh da tai ve cu hon N ngay           (mac dinh 30)
  sync_days        xoa thu muc dong bo lich su da giai ma > N ngay (mac dinh 7)
Chay moi 6 gio va khi bam «Don ngay». Chi xoa TRONG thu muc du lieu cua app (downloads/, history_sync/<yyyymmdd-hhmmss>/)."""

import json
import os
import re
import shutil
import threading
import time

DEFAULTS = {"messages_days": 365, "max_per_thread": 20000, "files_days": 30, "sync_days": 7}
LIMITS = {"messages_days": (0, 3650), "max_per_thread": (0, 500000), "files_days": (0, 3650), "sync_days": (0, 365)}
RUN_EVERY = 6 * 3600
_RUN_DIR = re.compile(r"^\d{8}-\d{6}$")


class RetentionError(ValueError):
    pass


def _dir_size(path):
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


class Retention:
    def __init__(self, data_dir, store, log=None, clock=time.time):
        self.data_dir = data_dir
        self.store = store
        self.path = os.path.join(data_dir, "retention.json")
        self.log = log or (lambda m: print("[retention] %s" % m, flush=True))
        self.clock = clock
        self.lock = threading.Lock()
        self.last_report = None
        self._stop = threading.Event()
        self._thread = None
        self.apply()

    # ---- cai dat
    def get(self):
        cfg = dict(DEFAULTS)
        try:
            with open(self.path, encoding="utf-8") as f:
                saved = json.load(f)
            for k in DEFAULTS:
                if isinstance(saved.get(k), int) and not isinstance(saved.get(k), bool):
                    lo, hi = LIMITS[k]
                    cfg[k] = max(lo, min(hi, saved[k]))
        except (OSError, ValueError, AttributeError):
            pass
        return cfg

    def update(self, changes):
        """Doi cai dat; gia tri sai -> RetentionError (khong luu gi). Tra ve cai dat moi."""
        if not isinstance(changes, dict):
            raise RetentionError("cài đặt phải là một đối tượng")
        cfg = self.get()
        for k, v in changes.items():
            if k not in DEFAULTS:
                raise RetentionError("không có cài đặt “%s”" % k)
            if isinstance(v, bool) or not isinstance(v, int):
                raise RetentionError("“%s” phải là số nguyên" % k)
            lo, hi = LIMITS[k]
            if not lo <= v <= hi:
                raise RetentionError("“%s” phải trong khoảng %d–%d" % (k, lo, hi))
            cfg[k] = v
        os.makedirs(self.data_dir, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        os.replace(tmp, self.path)
        self.apply()
        return cfg

    def apply(self):
        """Gioi han moi hoi thoai cua kho tin ap dung ngay cho tin ghi moi (0 = khong cat)."""
        self.store.max_per_thread = self.get()["max_per_thread"]

    # ---- so lieu
    def usage(self):
        stats = self.store.stats()
        dl = os.path.join(self.data_dir, "downloads")
        hs = os.path.join(self.data_dir, "history_sync")
        return {"messages": stats["rows"], "threads": stats["threads"], "messages_bytes": stats["db_bytes"],
                "files_bytes": _dir_size(dl) if os.path.isdir(dl) else 0, "sync_bytes": _dir_size(hs) if os.path.isdir(hs) else 0,
                "oldest_ts": stats["oldest_ts"]}

    # ---- don dep
    def run(self):
        cfg = self.get()
        now = self.clock()
        report = {"at": int(now), "messages_deleted": 0, "files_deleted": 0, "sync_dirs_deleted": 0, "freed_bytes": 0}
        with self.lock:
            before = self.usage()
            try:
                report["messages_deleted"] = self.store.prune(cfg["messages_days"], cfg["max_per_thread"], now=now)
            except Exception as e:  # noqa: BLE001 - mot buoc loi khong chan buoc khac
                self.log("don tin nhan loi: %s" % str(e)[:120])
            if cfg["files_days"]:
                report["files_deleted"] = self._clean_files(os.path.join(self.data_dir, "downloads"), now - cfg["files_days"] * 86400)
            if cfg["sync_days"]:
                report["sync_dirs_deleted"] = self._clean_sync(os.path.join(self.data_dir, "history_sync"), now - cfg["sync_days"] * 86400)
            after = self.usage()
        report["freed_bytes"] = max(0, (before["messages_bytes"] + before["files_bytes"] + before["sync_bytes"])
                                    - (after["messages_bytes"] + after["files_bytes"] + after["sync_bytes"]))
        self.last_report = report
        if report["messages_deleted"] or report["files_deleted"] or report["sync_dirs_deleted"]:
            self.log("da don: %d tin, %d tep, %d thu muc dong bo, giai phong %d KB" % (
                report["messages_deleted"], report["files_deleted"], report["sync_dirs_deleted"], report["freed_bytes"] // 1024))
        return report

    @staticmethod
    def _clean_files(root, cutoff):
        """Xoa tep tai ve cu (theo gio sua). Giu registry.json (so dang ky tep) — muc tep bi xoa se bao «tep da bi xoa» khi mo."""
        n = 0
        if not os.path.isdir(root):
            return 0
        for dirpath, _, files in os.walk(root):
            for f in files:
                if f == "registry.json":
                    continue
                p = os.path.join(dirpath, f)
                try:
                    if os.path.getmtime(p) < cutoff:
                        os.remove(p)
                        n += 1
                except OSError:
                    pass
        return n

    @staticmethod
    def _clean_sync(root, cutoff):
        """Xoa thu muc dong bo (ten yyyymmdd-hhmmss) cu; khong dung toi key.pem o goc."""
        n = 0
        if not os.path.isdir(root):
            return 0
        for name in os.listdir(root):
            p = os.path.join(root, name)
            if _RUN_DIR.match(name) and os.path.isdir(p) and not os.path.islink(p):
                try:
                    if os.path.getmtime(p) < cutoff:
                        shutil.rmtree(p)
                        n += 1
                except OSError:
                    pass
        return n

    # ---- nen
    def start(self, first_delay=120):
        if self._thread is not None:
            return

        def loop():
            if self._stop.wait(first_delay):
                return
            while True:
                try:
                    self.run()
                except Exception as e:  # noqa: BLE001
                    self.log("loi: %s" % str(e)[:120])
                if self._stop.wait(RUN_EVERY):
                    return
        self._thread = threading.Thread(target=loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
