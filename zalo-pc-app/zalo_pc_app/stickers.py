"""Nhan dan (sticker) cho giao dien web — dung API cua zca-js:
searchSticker / getRecommendedStickers / getStickerCategoryDetail (template trong
zca_registry) + sticker_detail (getStickersDetail, goi tung id) de lay URL anh.

Moi ham tra list {id, cate_id, type, text, url}. Hinh dang phan hoi lay theo kieu
du lieu cua zca-js (models/Sticker.ts) nhung CHUA kiem voi may chu that: chuan hoa
khoan dung, thieu thi bo qua tung muc chu khong lam hong ca danh sach.
"""

import threading

from . import zca_api

MAX_DETAIL = 24
_LIST_KEYS = ("stickers", "data", "list", "items", "sticker", "result")


def _as_list(obj, depth=0):
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict) and depth < 3:
        for k in _LIST_KEYS:
            if k in obj:
                got = _as_list(obj[k], depth + 1)
                if got:
                    return got
        for v in obj.values():
            if isinstance(v, list):
                return v
    return []


def normalize(item):
    """StickerDetail / StickerBasic -> {id, cate_id, type, text, url} hoac None."""
    if not isinstance(item, dict):
        return None
    sid = item.get("id", item.get("sticker_id", item.get("stickerId")))
    if sid in (None, ""):
        return None
    url = (item.get("stickerWebpUrl") or item.get("stickerUrl")
           or item.get("stickerSpriteUrl") or item.get("url") or "")
    return {"id": str(sid),
            "cate_id": str(item.get("cateId", item.get("cate_id", ""))),
            "type": item.get("type", 0), "text": item.get("text", ""),
            "url": url}


class Stickers:
    def __init__(self, svc, ctx):
        self.z = zca_api.ZcaApi(svc, ctx)

    def _detail(self, sid):
        got = self.z.raw_call("sticker", "/api/message/sticker/sticker_detail",
                              {"sid": int(sid) if str(sid).isdigit() else sid})
        return normalize(got if isinstance(got, dict) else (_as_list(got) or [None])[0])

    def _with_urls(self, items):
        """Muc chi co id (StickerBasic) -> goi sticker_detail song song de co URL."""
        out = [None] * len(items)
        threads = []

        def work(i, it):
            n = normalize(it)
            if n is None:
                return
            if not n["url"]:
                try:
                    d = self._detail(n["id"])
                    if d:
                        d["cate_id"] = d["cate_id"] or n["cate_id"]
                        n = d
                except Exception:  # noqa: BLE001 - bo qua muc loi
                    return
            out[i] = n

        for i, it in enumerate(items[:MAX_DETAIL]):
            t = threading.Thread(target=work, args=(i, it), daemon=True)
            t.start()
            threads.append(t)
        for t in threads:
            t.join(30)
        return [x for x in out if x and x["url"]]

    def search(self, keyword, limit=24):
        got = self.z.call("searchSticker", {"keyword": keyword,
                                            "limit": min(int(limit), MAX_DETAIL)})
        return self._with_urls(_as_list(got))

    def recommended(self):
        return self._with_urls(_as_list(self.z.call("getRecommendedStickers", {})))

    def category(self, cate_id):
        got = self.z.call("getStickerCategoryDetail", {"cateId": cate_id})
        items = [normalize(x) for x in _as_list(got)]
        return [x for x in items if x and x["url"]]
