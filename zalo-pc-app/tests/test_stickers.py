"""Nhan dan cho web UI (zalo_pc_app/stickers.py): tim -> lay URL anh -> chuan hoa."""
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import stickers  # noqa: E402

DETAIL = {101: {"id": 101, "cateId": 7, "type": 3, "text": "chao",
                "stickerUrl": "https://s/101.png", "stickerWebpUrl": "https://s/101.webp"},
          102: {"id": 102, "cateId": 7, "type": 3, "text": "", "stickerUrl": "https://s/102.png",
                "stickerWebpUrl": None}}


class FakeSvc:
    service_map = {"sticker": ["https://sticker.example"]}

    def __init__(self):
        self.urls = []
        self.http_post = None

    def _aes(self, raw):
        return raw

    def http_get(self, url, timeout=30):
        self.urls.append(url)
        return 200, {"url": url}

    def _unwrap(self, status, payload, where):
        url = payload["url"]
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        params = __import__("json").loads(q["params"][0]) if "params" in q else {}
        if "/sticker/search" in url:
            assert params["keyword"] == "chao" and params["limit"] <= 24, params
            return [{"type": 3, "cate_id": 7, "sticker_id": 101},
                    {"type": 3, "cate_id": 7, "sticker_id": 102},
                    {"type": 3, "cate_id": 7, "sticker_id": 999}]
        if "/sticker/recommended" in url:
            return {"data": [{"type": 3, "cate_id": 7, "sticker_id": 101}]}
        if "/category/sticker_detail" in url:
            assert params == {"cid": 7}, params
            return list(DETAIL.values())
        if "/sticker/sticker_detail" in url:
            d = DETAIL.get(params["sid"])
            if d is None:
                raise RuntimeError("khong co sticker")
            return d
        raise AssertionError(url)


def test_search_fetches_details_prefers_webp_and_skips_failures():
    svc = FakeSvc()
    items = stickers.Stickers(svc, {"imei": "X"}).search("chao")
    by = {i["id"]: i for i in items}
    assert set(by) == {"101", "102"}, by           # 999 loi -> bo qua, khong lam hong ca danh sach
    assert by["101"]["url"].endswith(".webp") and by["102"]["url"].endswith(".png")
    assert by["101"]["cate_id"] == "7" and by["101"]["type"] == 3


def test_recommended_unwraps_nested_list():
    items = stickers.Stickers(FakeSvc(), {"imei": "X"}).recommended()
    assert [i["id"] for i in items] == ["101"], items


def test_category_uses_inline_details_without_extra_calls():
    svc = FakeSvc()
    items = stickers.Stickers(svc, {"imei": "X"}).category("7")
    assert len(items) == 2 and all(i["url"] for i in items), items
    assert len(svc.urls) == 1, svc.urls


def test_normalize_is_tolerant():
    assert stickers.normalize(None) is None
    assert stickers.normalize({"text": "x"}) is None
    n = stickers.normalize({"sticker_id": 5, "cate_id": 2, "type": 1})
    assert n["id"] == "5" and n["cate_id"] == "2" and n["url"] == ""
    assert stickers._as_list({"data": {"stickers": [1, 2]}}) == [1, 2]
    assert stickers._as_list("x") == []


if __name__ == "__main__":
    for _n, _f in list(globals().items()):
        if _n.startswith("test_") and callable(_f):
            _f()
            print("PASS", _n)
    print("ALL STICKER TESTS PASSED")
