"""Nghe may cuoc goi DEN (ta la ben nhan) - tach rieng khoi cuoc goi DI.

Ranh gioi: file nay CHI chua duong nghe may cuoc goi den. Cuoc goi di (ta la ben goi) o `server.py` (`/api/call/request` va
quanh do), khong goi vao day. Loi cuoc goi den sua o day; loi cuoc goi di sua o `server.py`, de khong sua nham.

`sv` la module server dang chay (server.py chay duoi ten `__main__` nen KHONG `import server` o day - se nap ban sao thu hai voi
trang thai rieng). Moi ten toan cuc cua server (STATE, ham tro giup, tu dien trang thai) di qua `sv.`.
"""
import json
import os
import threading
import time


def copy_negotiation_flags(ext, offer):
    """Cờ thương lượng bên gọi khai mà ta chưa có thì lặp lại trong extendData trả lời. Thiếu negoVidQual thì điện thoại hiện «Phiên bản của
    BenBap chưa hỗ trợ tính năng chuyển video» (thấy 12/11 18:54 với lệnh nghe máy kiểu gọn) và không gửi yêu cầu chuyển video."""
    if isinstance(ext, dict) and isinstance(offer, dict):
        for k in ("negoVidQual",):
            if k in offer and k not in ext:
                ext[k] = offer[k]
        # callType: cuoc goi VIDEO den (offer callType 1) thi ban tra loi cung khai 1; truoc day luon 0 (thoai) nen dien thoai goi video khong
        # duoc nhan nhu cuoc video (do 12/11 20:49: offer callType 1, ta tra loi callType 0).
        if str(offer.get("callType")) in ("0", "1"):
            ext["callType"] = int(offer["callType"])
    return ext


def early_p2p(ext, transport, offer, hosts):
    """Khai P2P trong extendData trả lời như engine thật (sP2P 1 + ứng viên của ta) khi điện thoại cũng khai P2P. Trả số ứng viên đã khai (0 = không khai).
    Dùng để thử xem điện thoại có hết báo «Phiên bản chưa hỗ trợ chuyển video» khi ta khai đủ như Zalo PC."""
    cands = [c for c in (offer.get("p2p") or []) if isinstance(c, dict)] if isinstance(offer, dict) and offer.get("sP2P") == 1 else []
    fn = getattr(transport, "local_p2p_candidates", None)
    if not cands or not callable(fn):
        return 0
    mine = fn(hosts)
    if not mine:
        return 0
    transport.set_p2p_candidates(cands)
    ext.update({"p2p": mine, "sP2P": 1})
    return len(mine)


def answer_incoming(sv, sess, body, source="api"):
    """Nghe may mot cuoc goi 1-1 DEN (ta la ben nhan) -> dict {"ok", ...}. Dung chung cho POST /api/call/answer va
    tu nghe may do HA quyet theo quy tac. Loi o buoc bao hieu tra {"ok": False, "error": ...}; nguoi goi tu bat ngoai le khac."""
    # Answer an INCOMING call (we are the callee). zca-js
    # acceptIncomingCall: ringring 11302 (unless the
    # call_event handler already sent it) -> requestVoiceCall
    # 11300 fallback for a fresh allocation (same callId,
    # partner = caller) -> answerVoiceCall 11303 with the
    # allocation's endpoints. The 11301 request step is NOT
    # sent — that is the caller's signal — and no answerack
    # (11304) is sent either: 11304 is the CALLER's signal
    # (zca-js + mock server_call_state). Target resolution
    # mirrors /api/call/answered, but only an "incoming"
    # entry counts.
    raw_id = body.get("call_id", "")
    call_id = sv._coerce_call_id(raw_id)
    # Moc thoi gian mili-giay (tinh tu luc vao ham nay) de xem THU TU: goi tieng dau cua dien thoai toi truoc hay lenh nghe may 11303 toi truoc.
    _t0 = time.monotonic()
    _first = {"ms": None}

    def _ms():
        return int((time.monotonic() - _t0) * 1000)

    def _t(what, extra=""):
        sv._log_call("t call_id=%s %s ms=%d first_media=%s%s" % (call_id, what, _ms(), _first["ms"], (" " + extra) if extra else ""))
    snap = sv.STATE.calls.snapshot()
    live = snap["active"]
    target = None
    if call_id is not None:
        for c in snap["calls"]:
            if (str(c["call_id"]) == str(call_id)
                    and c["status"] == "incoming"):
                target = c
                break
    if target is None and live is not None \
            and live["status"] == "incoming":
        target = live
    if target is None:
        sv._log_call("answer call_id=%s reason=no_incoming_call"
                  % raw_id)
        return {"ok": False, "error": "no_incoming_call"}
    call_id = int(target["call_id"])
    sv._remember_call_devices(call_id, body)
    caller_id = target["thread_id"]
    codec = ((target.get("diag") or {}).get("incoming_codec")
             or sv.media_endpoints.DEFAULT_ZALO_AUDIO_CODEC)
    # Ringring first when the call_event handler has not
    # sent it yet (best-effort, synchronous here: the
    # answer must reach the caller after the ring).
    if not (target.get("diag") or {}).get(
            "incoming_ringring_sent"):
        try:
            transport = sv.make_transport(sess["zpw_sek"])
            sig = sv.signaling_mod.Signaling(
                transport, sess["device_id"], sess["zpw_enk"])
            sig.ringring(caller_id, call_id)
            sv.STATE.calls.record_diag(
                call_id, {"incoming_ringring_sent": True})
        except Exception as e:  # noqa: BLE001 - best-effort
            sv._log_call("ringring call_id=%s ok=False "
                      "error=%s" % (call_id, e))
    try:
        transport = sv.make_transport(sess["zpw_sek"])
        sig = sv.signaling_mod.Signaling(
            transport, sess["device_id"], sess["zpw_enk"])
        # Client that (fork zca-js `acceptIncomingCall`, engine zcall-native): bao chuong 407 -> bat tay UDP lenh 12 -> bao nghe may 11303 voi
        # sessId/relay CUA TIN CUOC GOI DEN; chi goi 11300 khi tin thieu relay. App cu luon goi 11300 truoc roi moi bao nghe may: Co the Zalo coi ta
        # nhu ben vua xin cap phat cho cung callId, roi tu choi 11303 voi inner -101 nen khong ghi nhan nghe may, may Zalo phu van do chuong (GIA THUYET chua kiem chung)
        # (do 12/11, 3 cuoc goi). Bo qua 11300 KHONG het -101 (thu 12/11 07:06), ZALO_PC_INCOMING_SKIP_11300=1 bat cach bo qua (xem ghi chu o _skip_11300).
        _ev_peek = sv._INCOMING_RELAY.get(str(call_id))
        _info_peek = sv._INCOMING_INFO.get(str(call_id)) or {}
        _sess_peek = _info_peek.get("session")
        _like_engine = (os.environ.get("ZALO_PC_INCOMING_CALLEE", "1") != "0"
                        and bool(_ev_peek) and isinstance(_sess_peek, str) and len(_sess_peek) == 154 and _sess_peek.isascii()
                        and bool(_info_peek.get("uid_to")) and bool(_info_peek.get("uid_from")))
        # Bo qua 11300 (nhu client that) la TUY CHON (ZALO_PC_INCOMING_SKIP_11300=1). So do 12/11 chua cho thay cach nao hon: bo qua -> dien thoai gui
        # tieng ve (07:15: 533 goi); goi 11300 -> 06:39 ~1 giay roi im, 10:02 (video) rtcp ve binh thuong, 10:00 (thoai, relay 42.1.81.69) khong ve gi.
        # Thua nhan: cuoc 10:00 co the do relay/mang chu khong phai 11300. Mac dinh giu cach cu cho den khi co them so do.
        _skip_11300 = _like_engine and os.environ.get("ZALO_PC_INCOMING_SKIP_11300", "") == "1"
        if _skip_11300:
            data = {"sessId": _sess_peek, "fromId": _info_peek["uid_to"], "toId": _info_peek["uid_from"]}
            sv._log_call("answer 11300 bo qua call_id=%s (tin cuoc goi den da co relay, nghe may nhu client that)" % call_id)
        else:
            data = sig.request_call(
                caller_id, call_id, codec,
                sv._type_request_for("user"))
        _alloc = sv.media_endpoints. \
            allocation_from_requestcall_data(data)
        # Relay: uu tien relay ben goi viet trong su kien; hong thi
        # quay ve relay cua 11300 moi (hanh vi cu).
        _data_variants = [("11300", data)]
        _ev_relay = sv._INCOMING_RELAY.pop(str(call_id), None)
        if _ev_relay:
            _d_ev = dict(data)
            _d_ev["servers"] = [_ev_relay[0], _ev_relay[1]]
            _d_ev["rtpIP"], _d_ev["rtcpIP"] = _ev_relay
            # Bên NGHE MÁY của engine thật (zcall-native): InitZRTP lệnh 12, sessId = phiên của BÊN GỌI (trong tin cuộc gọi đến), uid của ta
            # (uidTo) và của bên gọi (uidFrom) từ tin; gửi tới đúng relay bên gọi chọn. App cũ gửi lệnh 11 với phiên cấp phát riêng nên relay
            # không nối được với điện thoại (0 gói tiếng về, tự cúp ở 16,7 s). Nhánh dự phòng "11300" giữ cách cũ để vẫn nghe máy được.
            _info = sv._INCOMING_INFO.pop(str(call_id), None) or {}
            _sess = _info.get("session")
            if os.environ.get("ZALO_PC_INCOMING_CALLEE", "1") != "0" and isinstance(_sess, str) and len(_sess) == 154 and _sess.isascii():
                _d_ev["sessId"] = _sess
                if "token" in _d_ev:                      # có khoá token rõ ràng (mock/phản hồi khác) thì cũng phải là phiên bên gọi
                    _d_ev["token"] = _sess
                if _info.get("uid_to"):
                    _d_ev["fromId"] = _info["uid_to"]
                if _info.get("uid_from"):
                    _d_ev["toId"] = _info["uid_from"]
                sv._CALLEE_EVENT.add(str(call_id))
            # Mặc định "event" (như sáng 11/11): relay bên gọi ghi trong sự kiện trước, relay 11300 của mình làm dự phòng. Thử "alloc"
            # (như cuộc gọi đi) lúc 20:18 11/11 KHÔNG đổi gì: vẫn 0 gói tiếng từ điện thoại về, tự cúp ở 16,7 giây. Đặt
            # ZALO_PC_INCOMING_RELAY=alloc để thử cách kia.
            if os.environ.get("ZALO_PC_INCOMING_RELAY", "event").strip().lower() == "alloc":
                _data_variants.append(("event", _d_ev))
            else:
                _data_variants.insert(0, ("event", _d_ev))
        # Hook ma hoa LUON duoc dung (xem cuoc goi di): khoa SRTP lay
        # tu 11300 neu co, neu khong thi khoa ben goi gui kem trong
        # su kien cuoc goi den, neu khong thi RTP tran.
        hooks = {}
        _offer = sv._INCOMING_OFFER.pop(str(call_id), None) or {}
        # Chế độ SRTP theo lời mời của CHÍNH điện thoại gọi (srtpMode 0 = RTP trần; khác 0 = SRTP khoá từ phiên); ZALO_PC_INCOMING_SRTP
        # ép: event (khoá phiên trong tin) | alloc (khoá phiên bot cấp) | off (RTP trần), chỉ để thử.
        _force = os.environ.get("ZALO_PC_INCOMING_SRTP", "").strip().lower()
        _plain = _force == "off" or (not _force and _offer.get("srtpMode") == 0)
        _in_key = _alloc.get("srtp_key")
        _in_src = "alloc.srtp_key" if _in_key is not None else ""
        if _in_key is None:
            _in_key = sv._INCOMING_SRTP.pop(str(call_id), None)
            _in_src = "event" if _in_key is not None else ""
        if _force == "alloc":
            from . import srtp_pure as _sp3
            _in_key, _in_src = _sp3.key_from_session(_alloc.get("session")), "alloc.session(ep)"
        if _plain:
            _in_key, _in_src = None, "plain"
        elif _in_key is None:
            from . import srtp_pure as _srtp_pure
            _in_key = _srtp_pure.key_from_session(
                _alloc.get("session"))
        try:
            from . import pc_media
            hooks, _notes = pc_media.hooks_for_call(_in_key)
            from . import srtp_pure as _sp2
            sv._log_call("answer media hooks call_id=%s srtp=%s opus=%s key_src=%s key=%s alloc_session_key=%s"
                      % (call_id, _notes["srtp"],
                         _notes["opus"][:90], _in_src or "alloc.session", sv._key_fp(_in_key),
                         sv._key_fp(_sp2.key_from_session(_alloc.get("session")))))
        except Exception as exc:  # noqa: BLE001 - optional
            hooks = {}
            sv._log_call("answer media hooks failed call_id=%s: %s"
                      % (call_id, str(exc)[:160]))

        def _on_first_media():
            if _first["ms"] is None:
                _first["ms"] = _ms()
            _t("goi-tieng-dau-tu-dien-thoai")
            sv._mark_answered(call_id, "media", send_ack=False)

        # THU NGHIEM 12/11: bao nghe may 11303 TRUOC khi mo UDP va gui InitZRTP lenh 12. Gia thuyet: Init cua ben nghe may toi relay lam Zalo coi
        # cuoc goi da duoc nghe (dien thoai goi gui answerack ~20 ms TRUOC khi phan hoi 11303 ve toi), nen 11303 den sau bi tu choi -101 va may
        # Zalo phu khong duoc bao «da nghe o thiet bi khac». Neu 11303 gui truoc van -101 thi gia thuyet sai (khong lien quan thu tu UDP).
        # Ban than lenh gui truoc khong co ung vien P2P (relay thuan). ZALO_PC_INCOMING_ANSWER_FIRST=1 bat (mac dinh TAT: 12/11 thu thay 11303 duoc nhan, Zalo phu het chuong, nhung relay khong tra loi Init sau do nen mat tieng).
        _answered_early = False
        _answer_warning = ""
        _early = {"ok": False, "err": ""}

        def _resp_shape(r):
            """Hinh dang phan hoi 11303 (chi ten khoa / do dai, khong gia tri): xem Zalo co tra ve gi cho engine (bundle PC chuyen phan hoi cua
            moi tin hieu nguoc xuong engine native)."""
            if isinstance(r, dict):
                return "dict khoa=%s" % sorted(r.keys())[:12]
            return "%s %s" % (type(r).__name__, ("len=%d" % len(r)) if hasattr(r, "__len__") else "")

        def _early_answer():
            """11303 gui TRUOC phan UDP (relay thuan, khong P2P), dinh dang y het engine that (zalo-for-linux engine-core.js `answer()`): extendData =
            nen native + {numServers 0, select2side 1, supportCallBusy 0}, khoa sap xep, ket thuc "\n" (jsonCpp); codec = hang CODEC chuan co "\n"."""
            try:
                _ext0 = sv.media_endpoints.native_extend_data(_ev_peek[0], _ev_peek[1], False)
                _ext0.update({"numServers": 0, "select2side": 1, "supportCallBusy": 0})
                copy_negotiation_flags(_ext0, _offer)
                if os.environ.get("ZALO_PC_INCOMING_EARLY_P2P", "0") == "1":
                    _tr1 = (sv.media_endpoints.ENDPOINTS.active_record(call_id) or {}).get("transport")
                    _n1 = early_p2p(_ext0, _tr1, _offer, [h.strip() for h in os.environ.get("ZALO_PC_P2P_HOSTS", "").split(",") if h.strip()])
                    _t("p2p-khai-som", "ung_vien_cua_ta=%d" % _n1)
                if _plain:
                    _ext0["srtpMode"] = 0
                _codec0 = str(body.get("codec") or codec)
                if "opus" in _codec0 and "112" in _codec0:
                    _codec0 = sv.media_endpoints.DEFAULT_ZALO_AUDIO_CODEC + "\n"
                sv._log_call("answer early-body call_id=%s codec=%r rtp=%s rtcp=%s session_len=%d session_fp=%s ext_keys=%s ext=%s" % (
                    call_id, _codec0, _ev_peek[0], _ev_peek[1], len(str(_sess_peek)), sv._key_fp(str(_sess_peek).encode()), sorted(_ext0.keys()),
                    json.dumps({k: ("n=%d" % len(v) if isinstance(v, list) else v) for k, v in _ext0.items() if k != "serverAddr"}, sort_keys=True)[:700]))
                _t("11303-kieu-gon-gui")
                _retry = os.environ.get("ZALO_PC_INCOMING_ANSWER_RETRY", "0") == "1"   # THU NGHIEM: -101 thi gui lai dung 1 lan ngay
                for _try in range(2 if _retry else 1):
                    try:
                        _r = sig.answer(caller_id, call_id, 0, _codec0, _ev_peek[1], _ev_peek[0], _sess_peek,
                                        json.dumps(_ext0, separators=(",", ":"), ensure_ascii=False, sort_keys=True) + "\n")
                        break
                    except Exception as _e_try:  # noqa: BLE001
                        if _try == 0 and _retry and "error_code=-101" in str(_e_try):
                            _t("11303-kieu-gon-thu-lai", "sau -101")
                            continue
                        raise
                _t("11303-kieu-gon-tra-loi", "ok")
                _early["ok"] = True
                sv._log_call("answer early call_id=%s ok phan_hoi=%s" % (call_id, _resp_shape(_r)))
            except Exception as _e_early:  # noqa: BLE001 - de lo ket qua
                _early["err"] = str(_e_early)
                _t("11303-kieu-gon-tra-loi", "loi=%s" % str(_e_early)[:40])
                _inner = getattr(_e_early, "inner", None)
                if isinstance(_inner, dict):     # toan bo goi loi Zalo (tru truong session/key/token): xem Zalo noi them gi ngoai error_code
                    sv._log_call("answer early loi-day-du call_id=%s %s" % (call_id, json.dumps(
                        {k: ("<%d ky tu>" % len(v) if (isinstance(v, str) and any(w in k.lower() for w in ("sess", "key", "token"))) else v)
                         for k, v in _inner.items()}, ensure_ascii=False, sort_keys=True)[:700]))
                sv._log_call("answer early call_id=%s FAILED: %s" % (call_id, str(_e_early)[:160]))

        # THU NGHIEM 12/11 (hai che do, mac dinh TAT; ket qua da do):
        #   ZALO_PC_INCOMING_ANSWER_FIRST=1  11303 TRUOC khi mo UDP: Zalo nhan 11303 (het -101, Zalo phu het chuong) NHUNG relay khong tra loi
        #                                    InitZRTP sau do -> mat tieng, ngat o 16,7 giay.
        #   ZALO_PC_INCOMING_ANSWER_PARALLEL=1  11303 va InitZRTP gui CUNG LUC (luong rieng): vi InitZRTP truoc 11303 -> -101, 11303 truoc InitZRTP -> relay
        #                                    im, nen thu xem hai viec dong thoi co duoc chap nhan ca hai khong.
        _early_mode = ""
        if _like_engine:
            if os.environ.get("ZALO_PC_INCOMING_ANSWER_FIRST", "0") == "1":
                _early_mode = "first"
            elif os.environ.get("ZALO_PC_INCOMING_ANSWER_PARALLEL", "0") == "1":
                _early_mode = "parallel"
        _early_thread = None
        # THU NGHIEM 12/11 (mac dinh TAT) ZALO_PC_INCOMING_ANSWER_AFTER_INIT=1: Init di truoc (relay tra loi), nhung 11303 kieu gon gui NGAY SAU KHI GUI Init
        # (khong cho type-02 ~130-240 ms), de thang cuoc dua voi tin «ben nghe da vao relay» gay -101. Cac cuoc 15:31 (nghe may truoc Init) va 15:47 (Init truoc) cho thay
        # chi co Init-truoc moi co tieng, va 11303 chi duoc nhan khi toi may chu truoc su kien relay.
        # THU NGHIEM 12/11 (mac dinh TAT) ZALO_PC_INCOMING_HOLD_MEDIA=1: bo tieng im lang «giu ket noi» 50 goi/giay ma bo truyen tu gui ngay khi chon relay
        # (goi 38 byte dau tien); dien thoai ben goi coi do la «ben nghe da tra loi», xac nhan answer_ack truoc khi 11303 toi may chu (-101). Giu tieng toi khi 11303 co ket qua.
        _hold = _like_engine and not _early_mode and os.environ.get("ZALO_PC_INCOMING_HOLD_MEDIA", "0") == "1"

        def _release_media():
            if not _hold:
                return
            try:
                _tr0 = (sv.media_endpoints.ENDPOINTS.active_record(call_id) or {}).get("transport")
                if _tr0 is not None:
                    _tr0.hold_media = False
                _t("tieng-bat-dau-gui", "da_giu=%s" % (getattr(_tr0, "counters", {}) or {}).get("held_tx", "?"))
            except Exception:  # noqa: BLE001 - khong duoc lam hong viec nghe may
                pass
        _init_mode = _like_engine and not _early_mode and os.environ.get("ZALO_PC_INCOMING_ANSWER_AFTER_INIT", "0") == "1"
        _early_box = {"t": None}

        def _on_init_sent():
            if _early_box["t"] is None and not _early["ok"]:     # nguon «11300» goi lai for_call: chi gui 11303 mot lan
                _t("init-da-gui")
                _early_box["t"] = threading.Thread(target=_early_answer, daemon=True)
                _early_box["t"].start()
        if _early_mode == "first":
            _early_answer()
            _answered_early = _early["ok"]
        elif _early_mode == "parallel":
            _early_thread = threading.Thread(target=_early_answer, daemon=True)
            _early_thread.start()
        endpoints = None
        for _vi, (_vname, _vdata) in enumerate(_data_variants):
            try:
                endpoints = sv.media_endpoints.ENDPOINTS.for_call(
                    call_id=call_id, callee_id=caller_id,
                    call_type="user",
                    codec=body.get("codec") or codec,
                    local_session=_vdata.get("fromId") if _vname == "event" and str(call_id) in sv._CALLEE_EVENT else _alloc.get("local_session"),
                    peer_session=_vdata.get("toId") if _vname == "event" and str(call_id) in sv._CALLEE_EVENT else _alloc.get("peer_session"),
                    requestcall_data=_vdata,
                    on_first_media=_on_first_media,
                    # Hồ sơ extendData như cuộc gọi đi ("native" = engine zcall-native chạy thật với điện thoại). Trước đây đường nghe máy
                    # KHÔNG truyền nên rơi về "pc" cũ (newZrtc 0, platform 3): điện thoại coi ta là bản cũ -> «kết nối không ổn định» và
                    # «phiên bản chưa hỗ trợ chuyển video».
                    extend_profile=sv._extend_profile_for_call(body),
                    # Vai theo nhánh: «event» đúng engine thật (callee, phiên bên gọi) nếu có đủ phiên; «11300» như cũ (caller).
                    is_caller=not (_vname == "event" and str(call_id) in sv._CALLEE_EVENT),
                    on_init_sent=_on_init_sent if _init_mode else None,
                    hold_media=_hold,
                    **hooks)
                sv._log_call("answer relay call_id=%s source=%s"
                          % (call_id, _vname))
                _t("relay-chon-xong", "nguon=%s" % _vname)
                break
            except Exception as _exc:  # noqa: BLE001
                if _vi == len(_data_variants) - 1:
                    raise
                sv._log_call("answer relay call_id=%s source=%s "
                          "failed: %s -> thu nguon ke"
                          % (call_id, _vname, str(_exc)[:120]))
                if _skip_11300 and _data_variants[_vi + 1][0] == "11300":
                    # Du lieu «11300» luc nay chi la ban tong hop tu tin (khong co relay cap phat): xin 11300 THAT roi thu nguon cap phat rieng.
                    _real = sig.request_call(caller_id, call_id, codec, sv._type_request_for("user"))
                    _data_variants[_vi + 1] = ("11300", _real)
                    _alloc = sv.media_endpoints.allocation_from_requestcall_data(_real)
                    sv._log_call("answer call_id=%s da xin 11300 that de thu relay cap phat rieng" % call_id)
        _callee_mode = str(call_id) in sv._CALLEE_EVENT
        sv._CALLEE_EVENT.discard(str(call_id))
        # extendData trả lời: nền «native» + THEO lời mời của chính điện thoại này (máy khác nhau khai khác nhau): srtpMode khớp chế độ thật
        # sự dùng (RTP trần nếu bên gọi xin 0), và các cờ thương lượng bên gọi khai mà ta không có thì lặp lại (negoVidQual).
        _ext_final = endpoints["extend_data"]
        try:
            _ext = json.loads(_ext_final) if isinstance(_ext_final, str) else dict(_ext_final)
            if _plain:
                _ext["srtpMode"] = 0
            copy_negotiation_flags(_ext, _offer)
            # P2P theo đúng điều điện thoại này khai (máy khác nhau khai khác nhau): bên gọi khai sP2P 1 kèm ứng viên thì ta khai ứng viên
            # của mình (địa chỉ máy trên cổng media) + sP2P 1, select2side 1, numServers 0, supportCallBusy 0 như engine zcall-native khi
            # nghe máy, và bắt đầu bind tới từng ứng viên của họ; thiếu thì giữ relay thuần (sP2P 0).
            _tr = (sv.media_endpoints.ENDPOINTS.active_record(call_id) or {}).get("transport")
            _cands = [c for c in (_offer.get("p2p") or []) if isinstance(c, dict)] if _offer.get("sP2P") == 1 else []
            sv._log_call("answer p2p call_id=%s dien_thoai_khai: sP2P=%s ung_vien=%d tpType=%s srtpMode=%s | ta: ZALO_PC_P2P=%s" % (
                call_id, _offer.get("sP2P"), len(_cands), _offer.get("tpType"), _offer.get("srtpMode"), os.environ.get("ZALO_PC_P2P", "1")))
            _lp2p = getattr(_tr, "local_p2p_candidates", None)               # transport cũ/giả không có P2P thì relay thuần
            if _cands and callable(_lp2p) and os.environ.get("ZALO_PC_P2P", "1") != "0":
                _hosts = [h.strip() for h in os.environ.get("ZALO_PC_P2P_HOSTS", "").split(",") if h.strip()]
                _mine = _lp2p(_hosts)
                if _mine:
                    _tr.set_p2p_candidates(_cands)
                    _ext.update({"p2p": _mine, "sP2P": 1, "select2side": 1, "numServers": 0, "supportCallBusy": 0})
            _ext_final = json.dumps(_ext, separators=(",", ":"), ensure_ascii=False)
        except (ValueError, TypeError):
            pass
        sv._log_call("answer offer call_id=%s rtp=%s rtcp=%s plain=%s extend=%s"
                  % (call_id, endpoints["rtp_address"], endpoints["rtcp_address"], _plain, str(_ext_final)[:1500]))
        # 11303 mang sessId cua tin cuoc goi den (= phien media), dung nhu client that. Thu mang phien 11300 cap cho ta (12/11 06:3x) KHONG
        # het -101; NGHI ngo la do goi 11300 truoc khi nghe may (chua kiem chung), xem ghi chu o cho bo qua 11300.
        _answer_session = endpoints["session"]
        # Gan engine media TRUOC khi bao nghe may: neu 11303 bi tu choi (do 12/11: inner -101) thi cau noi loa/mic van phai co, neu khong
        # loa khong bao gio len (gia tri tu dong bat loa chay khi goi dau tien den va chi doi transport).
        sv.engine_seam.SEAM.attach_pc_media(
            sv.media_endpoints.ENDPOINTS.active_record(call_id))
        # Tom tat 11303 de so voi lan khac (chi ten truong, do dai, so sanh — khong ghi gia tri bi mat). Khong bao gio lam hong viec nghe may.
        try:
            _ext_keys = sorted((json.loads(_ext_final) if isinstance(_ext_final, str) else dict(_ext_final)).keys())
        except (ValueError, TypeError):
            _ext_keys = "?"
        sv._log_call("answer body call_id=%s callee_mode=%s caller_is_thread=%s status=0 codec=%r rtp=%s rtcp=%s session_len=%d session_fp=%s ext_len=%d ext_keys=%s"
                  % (call_id, _callee_mode, str(caller_id) == str(target["thread_id"]), endpoints["codec"], endpoints["rtp_address"],
                     endpoints["rtcp_address"], len(str(_answer_session)), sv._key_fp(str(_answer_session).encode()), len(str(_ext_final)),
                     _ext_keys))
        if _early_thread is None:
            _early_thread = _early_box["t"]
        if _early_thread is not None:
            _early_thread.join(timeout=10)
            if _early["ok"]:
                _answered_early = True
            elif "error_code=-101" in _early["err"]:
                _answered_early, _answer_warning = True, "zalo_answer_-101"
        if not _answered_early and os.environ.get("ZALO_PC_INCOMING_ANSWER_EARLY_BODY", "0") == "1" and _like_engine:
            # THU NGHIEM 12/11 (mac dinh TAT): giu thu tu mac dinh (InitZRTP truoc) nhung 11303 mang THAN kieu som (dia chi cua ben goi, session tu tin den,
            # extendData gon). Som thi duoc nhan, muon thi -101: neu van -101 thi nguyen nhan la TRANG THAI may chu sau Init; neu duoc nhan thi do TRUONG trong than muon.
            _early_answer()
            if _early["ok"]:
                _answered_early = True
            elif "error_code=-101" in _early["err"]:
                _answered_early, _answer_warning = True, "zalo_answer_-101"
        if not _answered_early:
            try:
                _t("11303-thuong-gui")
                _resp = sig.answer(caller_id, call_id, 0, endpoints["codec"],
                           endpoints["rtcp_address"],
                           endpoints["rtp_address"],
                           _answer_session,
                           _ext_final)
                sv._log_call("answer call_id=%s 11303 ok phan_hoi=%s" % (call_id, _resp_shape(_resp)))
            except Exception as _e_ans:  # noqa: BLE001
                # Do 12/11 (5 cuoc goi that): sau khi InitZRTP lenh 12 toi relay, Zalo tra inner -101 cho 11303 du am thanh DA noi hai chieu
                # (dien thoai gui answerack va tiep tuc goi). Cuoc goi van chay: bao thanh cong kem canh bao de HA nghe may theo quy tac /
                # AI van chay, thay vi bo cuoc goi. Hau qua da biet: Zalo khong gui «da nghe o thiet bi khac», may Zalo phu van hien cuoc goi.
                # Loi khac (mang, tu choi 114...) van la that bai.
                if "error_code=-101" not in str(_e_ans):
                    raise
                _answer_warning = "zalo_answer_-101"
                sv._log_call("answer call_id=%s 11303 -101 nhung media da noi: tiep tuc cuoc goi (Zalo phu co the van do chuong)" % call_id)
    except Exception as e:  # noqa: BLE001 - loi ro
        try:
            _release_media()
        except NameError:
            pass
        sv._log_call("answer call_id=%s ok=False error=%s"
                  % (call_id, e))
        return {"ok": False, "error": str(e)}
    _release_media()
    entry = sv._mark_answered(call_id, source, send_ack=False)
    if entry is None:
        return {"ok": False, "error": "no_incoming_call"}
    result = {"ok": True, "call_id": call_id,
              "status": entry["status"],
              "answered_at": entry.get("answered_at"),
              "answer_source": entry.get("answer_source", "")}
    if _answer_warning:
        result["warning"] = _answer_warning
    return result
