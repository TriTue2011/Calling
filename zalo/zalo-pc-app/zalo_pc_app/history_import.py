"""Nhap lich su da giai ma (history_sync) vao messages.db de hien trong khung chat (13/11/2026).

Cau truc tep sao luu do tren du lieu that: moi tep SQLite `<uid>.db` (hoi thoai 1-1 voi nguoi co UID so thuan) hoac `group_<gid>.db`, bang
ChatContent(SenderId, CliMsgId, GlbMsgId, MsgStatus, MsgType, TimeStamp[ms], TTL, MsgContent, RefCliMsgId, BinNet, LocalPath, SeqId, FLStatus, E2EE).
MsgContent la CHU HIEN THI san ("[Hình ảnh] chu thich", "[File] ten.pdf", "[Link] url", "[Sticker]", "[Tin nhắn thoại]"); link tep/anh that nam trong BinNet
(chua giai) nen tin da phuong tien chi nhap dang chu. MsgType: 0 chu, 3 anh, 6 thoai, 10 sticker, 12 link, 19 video, 20 he thong, 22 tep, 36 rong (bo qua).
App dung ma DAI 19 chu so (noised) nen UID so thuan duoc doi bang POST/GET profile-wpa /api/znoise {fids, gids} (zca-js getNoisedIds, bundle 12390).
Chong trung: cung khoa dedup voi tin ghi truc tiep (msgId + nguoi gui) nen chay lai nhieu lan khong nhan doi, khong de tin da co."""

import collections
import glob
import os
import re
import sqlite3

SYSTEM_TYPES = (20,)
SKIP_EMPTY_TYPES = (36,)
CHUNK = 100
FILE_PREFIX = "[File] "


class ImportError_(RuntimeError):
    pass


def _list_files(run_dir):
    one, grp = {}, {}
    for p in glob.glob(os.path.join(run_dir, "*.db")):
        name = os.path.basename(p)[:-3]
        if name.startswith("group_") and name[6:].isdigit():
            grp[int(name[6:])] = p
        elif name.isdigit():
            one[int(name)] = p
    return one, grp


def _open(path):
    return sqlite3.connect("file:%s?mode=ro" % path, uri=True)


def detect_own_short_uid(one_to_one):
    """UID so thuan cua CHINH MINH: trong tep 1-1 moi tin do hoac la cua nguoi kia (= ten tep) hoac cua minh; lay SenderId khac ten tep xuat hien nhieu nhat."""
    c = collections.Counter()
    for fid, path in one_to_one.items():
        con = _open(path)
        try:
            for (sid, n) in con.execute("SELECT SenderId, COUNT(*) FROM ChatContent GROUP BY SenderId"):
                if sid and sid != fid:
                    c[sid] += n
        finally:
            con.close()
    return c.most_common(1)[0][0] if c else None


def noise_ids(services, fids, gids, domain):
    """{uid_so: ma_dai} va {gid_so: ma_dai} qua znoise (chia lo, nguoi va nhom rieng). Khong co anh xa -> bo khoi ket qua."""
    fmap, gmap = {}, {}
    fids, gids = sorted(set(fids)), sorted(set(gids))
    for i in range(0, len(fids), CHUNK):
        chunk = fids[i:i + CHUNK]
        res = services._get(domain, "/api/znoise", {"fids": chunk, "gids": []}) or {}
        for fid, v in zip(chunk, res.get("fids") or []):
            if v and str(v) not in ("0", ""):
                fmap[fid] = str(v)
    for i in range(0, len(gids), CHUNK):
        chunk = gids[i:i + CHUNK]
        res = services._get(domain, "/api/znoise", {"fids": [], "gids": chunk}) or {}
        for gid, v in zip(chunk, res.get("gids") or []):
            v = str(v or "")
            v = v[1:] if v.startswith("g") else v
            if v and v != "0":
                gmap[gid] = v
    return fmap, gmap


def build_message(row, own_short, own_noised, sender_noised):
    """Mot dong ChatContent -> dict tin (cung dang tin ghi truc tiep) hoac None (bo qua)."""
    sender, cli, glb, status, mtype, ts, ttl, content, ref, binnet, localpath, seq, flstatus, e2ee = row
    text = content if isinstance(content, str) else ""
    if mtype in SKIP_EMPTY_TYPES and not text:
        return None
    if not text.strip():
        return None
    out = own_short is not None and sender == own_short
    mid = str(glb) if isinstance(glb, int) and glb > 0 else ""
    kind = "system" if mtype in SYSTEM_TYPES else "text"
    msg = {"id": mid or ("c%s" % cli), "client_id": str(cli), "sender_id": own_noised if out else sender_noised.get(sender, str(sender)),
           "sender_name": "", "text": text, "time": int(ts // 1000) if isinstance(ts, int) else 0, "kind": kind,
           "file_name": text[len(FILE_PREFIX):] if (mtype == 22 and text.startswith(FILE_PREFIX)) else "",
           "direction": "out" if out else "in", "is_self": bool(out), "imported": True,
           "raw": {"msgId": mid, "cliMsgId": str(cli), "uidFrom": str(sender), "ts": str(ts), "msgType": "backup:%s" % mtype}}
    return msg


def import_run(run_dir, store, services, domain, own_noised, log=print, progress=None, keep_days=0, now=None):
    """Nhap tat ca tep trong run_dir. keep_days > 0: BO QUA tin cu hon moc tu xoa (neu khong tin vua nhap se bi retention xoa roi lan nhap sau
    lai dua vao). Tra ve {"files", "threads", "inserted", "skipped", "old_skipped", "unmapped"}."""
    import time as _time
    cutoff = (float(now if now is not None else _time.time()) - keep_days * 86400) if keep_days else 0
    one, grp = _list_files(run_dir)
    if not one and not grp:
        raise ImportError_("không có tệp .db nào trong %s" % run_dir)
    own_short = detect_own_short_uid(one)
    log("nhap tu %s: %d tep 1-1, %d nhom, uid cua minh=%s" % (run_dir, len(one), len(grp), own_short))
    senders = set(one)
    for path in grp.values():
        con = _open(path)
        try:
            senders.update(r[0] for r in con.execute("SELECT DISTINCT SenderId FROM ChatContent") if r[0] and r[0] != own_short)
        finally:
            con.close()
    fmap, gmap = noise_ids(services, senders, set(grp), domain)
    result = {"files": 0, "threads": 0, "inserted": 0, "skipped": 0, "old_skipped": 0, "unmapped": 0}
    jobs = [("user", fid, p, fmap.get(fid)) for fid, p in sorted(one.items())] + [("group", gid, p, gmap.get(gid)) for gid, p in sorted(grp.items())]
    for i, (ttype, short, path, thread_id) in enumerate(jobs):
        if progress:
            progress("Đang nhập %d/%d…" % (i + 1, len(jobs)))
        if not thread_id:
            result["unmapped"] += 1
            log("bo qua %s %s: khong doi duoc sang ma dai" % (ttype, short))
            continue
        con = _open(path)
        try:
            rows = con.execute("SELECT SenderId,CliMsgId,GlbMsgId,MsgStatus,MsgType,TimeStamp,TTL,MsgContent,RefCliMsgId,BinNet,LocalPath,SeqId,FLStatus,E2EE "
                               "FROM ChatContent ORDER BY TimeStamp").fetchall()
        finally:
            con.close()
        if cutoff:
            fresh = [r for r in rows if not isinstance(r[5], int) or r[5] / 1000.0 >= cutoff]
            result["old_skipped"] += len(rows) - len(fresh)
            rows = fresh
        msgs = [m for m in (build_message(r, own_short, own_noised, fmap) for r in rows) if m]
        ins, skip = store.bulk_record(ttype, thread_id, msgs)
        result["files"] += 1
        result["threads"] += 1 if ins else 0
        result["inserted"] += ins
        result["skipped"] += skip + (len(rows) - len(msgs))
    log("nhap xong: %s" % result)
    return result
