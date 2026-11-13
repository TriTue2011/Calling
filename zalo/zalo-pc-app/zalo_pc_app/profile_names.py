"""Ten hien thi cua NGUOI LA (khong co trong danh ba) — 13/11/2026.

Chu may: «Nguoi la nhung cung co ten tuoi chu khong phai chi la day so». Tin nhap tu lich su khong mang `dName`
nen WebUI chi co ma. Tra ho so qua Zalo (getprofiles/v2) theo ma, luu ben (`profile_names.json`, 0600), chay nen,
nho ca ket qua that bai (thu lai sau RETRY_SECONDS) de khong goi Zalo lap lai. Khong ghi ten vao nhat ky.
"""

import json
import os
import threading
import time

FILENAME = "profile_names.json"
RETRY_SECONDS = 6 * 3600
BATCH = 10


def find_name(data, uid):
    """Tim ten hien thi trong phan hoi getprofiles/v2 (changed_profiles / unchanged_profiles ...).

    Khong doan cau truc: quet de quy moi dict co displayName/zaloName; uu tien ho so khop `uid` (theo khoa hoac userId),
    khong khop thi chi nhan khi phan hoi co DUNG MOT ho so (ta chi hoi mot ma moi lan)."""
    uid = str(uid)
    found = []

    def walk(o, key=""):
        if isinstance(o, dict):
            if "displayName" in o or "zaloName" in o:
                found.append((str(key), o))
                return
            for k, v in o.items():
                walk(v, k)
        elif isinstance(o, list):
            for v in o:
                walk(v, key)

    walk(data)

    def nm(d):
        return str(d.get("displayName") or d.get("zaloName") or "").strip()

    for k, d in found:
        if uid in {k, k.split("_")[0], str(d.get("userId") or ""), str(d.get("uid") or "")} and nm(d):
            return nm(d)
    if len(found) == 1:
        return nm(found[0][1])
    return ""


class ProfileNames:
    def __init__(self, path, lookup, on_change=None, now=time.time, pause=0.4):
        self._path = path
        self._lookup = lookup            # lookup(uid) -> ten ("" neu khong co); nem loi neu Zalo/mang loi
        self._on_change = on_change
        self._now = now
        self._pause = pause
        self._lock = threading.Lock()
        self._pending = set()
        self._data = {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict):
                self._data = {str(k): v for k, v in d.items() if isinstance(v, dict)}
        except (OSError, ValueError):
            pass

    def name(self, uid):
        with self._lock:
            return str((self._data.get(str(uid)) or {}).get("name") or "")

    def all_names(self):
        with self._lock:
            return {k: v["name"] for k, v in self._data.items() if v.get("name")}

    def _needs(self, uid):
        e = self._data.get(uid)
        if not e:
            return True
        if e.get("name"):
            return False
        return self._now() - float(e.get("at") or 0) >= RETRY_SECONDS

    def ensure(self, uids):
        """Khong chan: xep hang tra ten cho cac ma chua co (toi da BATCH ma moi lan goi)."""
        with self._lock:
            todo = [u for u in dict.fromkeys(str(x) for x in uids)
                    if u and u != "0" and u not in self._pending and self._needs(u)][:BATCH]
            self._pending.update(todo)
        if todo:
            threading.Thread(target=self._work, args=(todo,), daemon=True).start()

    def _work(self, todo):
        changed = False
        for u in todo:
            name, err = "", ""
            try:
                name = str(self._lookup(u) or "").strip()
            except Exception as e:  # noqa: BLE001 - loi Zalo/mang: nho de thu lai sau
                err = "%s: %s" % (type(e).__name__, str(e)[:80])
            with self._lock:
                self._data[u] = {"name": name, "at": self._now()}
                self._pending.discard(u)
            changed = changed or bool(name)
            print("[profile-names] ...%s %s" % (u[-4:], "ok" if name else ("loi " + err if err else "khong co ten")), flush=True)
            if self._pause:
                time.sleep(self._pause)
        self._save()
        if changed and self._on_change is not None:
            try:
                self._on_change()
            except Exception:  # noqa: BLE001 - bao giao dien that bai khong anh huong gi
                pass

    def _save(self):
        try:
            with self._lock:
                blob = json.dumps(self._data, ensure_ascii=False)
            tmp = self._path + ".tmp"
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(blob)
            os.replace(tmp, self._path)
        except OSError as e:
            print("[profile-names] khong luu duoc: %s" % e, flush=True)
