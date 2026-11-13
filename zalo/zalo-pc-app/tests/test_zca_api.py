"""Bo goi chung API zca-js (zalo_pc_app/zca_api.py + zca_registry.json).

Khong cham mang that: Services gia ghi lai URL/params. Kiem: danh muc du 333,
template goi dung duong dan + params giai ra duoc, POST dung form, API nguy hiem can
confirm, raw can params, manual bao ly do, domain thieu thi loi ro (khong doan).
"""
import json
import os
import sys
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import zca_api  # noqa: E402


class FakeSvc:
    def __init__(self, service_map=None):
        self.service_map = service_map if service_map is not None \
            else {"friend": ["https://friend.example"], "group": ["https://g.example"]}
        self.calls = []
        self.http_post = self._post

    def _aes(self, raw):
        return "ENC(" + raw + ")"

    def http_get(self, url, timeout=30):
        self.calls.append(("GET", url, None))
        return 200, {"error_code": 0}

    def _post(self, url, form, timeout=30):
        self.calls.append(("POST", url, form))
        return 200, {"error_code": 0}

    def _unwrap(self, status, payload, where):
        return {"where": where, "payload": payload}


def _params_of(url_or_form):
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url_or_form).query
                              if "?" in url_or_form else url_or_form)
    enc = urllib.parse.unquote(q["params"][0])
    assert enc.startswith("ENC(") and enc.endswith(")"), enc
    return json.loads(enc[4:-1])


def test_registry_has_all_333_and_modes_are_known():
    cat = zca_api.catalog()
    assert cat["total"] == 333, cat["total"]
    assert {a["mode"] for a in cat["apis"]} <= {"template", "raw", "manual"}
    names = [a["name"] for a in cat["apis"]]
    assert len(set(names)) == 333
    for a in cat["apis"]:
        assert a["summary"], a["name"]
        if a["mode"] == "manual":
            assert a["reason"], a["name"]


def test_template_get_builds_encrypted_params_and_url():
    svc = FakeSvc()
    api = zca_api.ZcaApi(svc, {"imei": "IMEI-1"})
    r = api.call("getFriendRequestStatus", {"friendId": "123"})
    kind, url, _ = svc.calls[0]
    assert kind == "GET" and url.startswith("https://tt-friend-wpa.chat.zalo.me/api/friend/reqstatus?"), url
    assert "zpw_ver=" in url and "zpw_type=" in url, url
    assert _params_of(url) == {"fid": "123", "imei": "IMEI-1"}, _params_of(url)
    assert r["where"].startswith("GET /api/friend/reqstatus"), r


def test_snake_case_alias_and_missing_required_field():
    svc = FakeSvc()
    api = zca_api.ZcaApi(svc, {"imei": "X"})
    try:
        api.call("get_friend_request_status", {})
    except zca_api.ZcaError as e:
        assert "friendId" in str(e), e
    else:
        raise AssertionError("thieu truong bat buoc phai bao loi")


def test_post_uses_form_body():
    reg = zca_api.registry()
    posts = [e for e in reg.values() if e["mode"] == "template"
             and e.get("method") == "POST" and e.get("service") in ("friend", "group")
             and not e["danger"] and not any(a.get("required") for a in e.get("args", []))]
    assert posts, "can it nhat mot API POST template khong can tham so"
    e = posts[0]
    svc = FakeSvc()
    zca_api.ZcaApi(svc, {"imei": "X"}).call(e["name"], {})
    kind, url, form = svc.calls[0]
    assert kind == "POST" and form.startswith("params="), (kind, form)
    assert "params=" not in url, url


def test_dangerous_api_needs_confirm():
    reg = zca_api.registry()
    e = next(x for x in reg.values() if x["danger"] and x["mode"] == "template"
             and x.get("service") in ("friend", "group")
             and not any(a.get("required") for a in x.get("args", [])))
    svc = FakeSvc()
    api = zca_api.ZcaApi(svc, {"imei": "X"})
    try:
        api.call(e["name"], {})
    except zca_api.ZcaError as err:
        assert "confirm" in str(err), err
    else:
        raise AssertionError("API nguy hiem khong co confirm phai bi chan")
    assert svc.calls == [], "khong duoc gui khi chua confirm"
    api.call(e["name"], {"confirm": True})
    assert len(svc.calls) == 1


def test_raw_mode_needs_params_and_passes_them_verbatim():
    reg = zca_api.registry()
    e = next(x for x in reg.values() if x["mode"] == "raw" and not x["danger"]
             and x.get("service") in ("friend", "group", "chat"))
    svc = FakeSvc({e["service"]: ["https://x.example"]})
    api = zca_api.ZcaApi(svc, {})
    try:
        api.call(e["name"], {})
    except zca_api.ZcaError as err:
        assert "params" in str(err)
    else:
        raise AssertionError("raw khong co params phai bao loi")
    api.call(e["name"], {"params": {"a": 1, "b": "x"}})
    assert _params_of(svc.calls[0][1] if svc.calls[0][0] == "GET" else svc.calls[0][2]) \
        == {"a": 1, "b": "x"}


def test_manual_and_missing_domain_are_explicit_not_guessed():
    api = zca_api.ZcaApi(FakeSvc(), {})
    try:
        api.call("getContext", {})
    except zca_api.ZcaManual as m:
        assert m.reason, m
    else:
        raise AssertionError("manual phai bao ly do")
    # Dich vu khong co domain PC va khong co trong services map -> loi ro, khong doan.
    e = next(x for x in zca_api.registry().values() if x["mode"] == "template"
             and x.get("service") not in zca_api.ZcaApi._PC_DOMAINS
             and not x.get("fixed_domain") and not x["danger"]
             and not any(a.get("required") for a in x.get("args", [])))
    svc = FakeSvc(service_map={})
    try:
        zca_api.ZcaApi(svc, {"imei": "X"}).call(e["name"], {})
    except zca_api.ZcaManual as m:
        assert "services map" in m.reason, m.reason
    else:
        raise AssertionError("thieu domain phai bao loi, khong doan")
    assert svc.calls == []


def test_pc_domain_wins_over_unresolvable_session_map():
    svc = FakeSvc(service_map={"sticker": ["https://tt-sticker-wpa.zalo.me"]})
    zca_api.ZcaApi(svc, {"imei": "X"}).raw_call(
        "sticker", "/api/message/sticker/sticker_detail", {"sid": 1})
    assert svc.calls[0][1].startswith("https://sticker-wpa.zalo.me/"), svc.calls[0][1]


def test_unknown_api_raises_keyerror():
    try:
        zca_api.ZcaApi(FakeSvc(), {}).call("khongCoApiNay", {})
    except KeyError:
        pass
    else:
        raise AssertionError


if __name__ == "__main__":
    for _n, _f in list(globals().items()):
        if _n.startswith("test_") and callable(_f):
            _f()
            print("PASS", _n)
    print("ALL ZCA API TESTS PASSED")
