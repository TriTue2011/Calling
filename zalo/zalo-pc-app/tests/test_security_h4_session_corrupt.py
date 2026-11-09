"""H4 — session.json hong khong duoc lam server chet luc khoi dong.

Audit Phan B: session.py load() cu raise JSONDecodeError khi
session.json hong (mat dien giua luc ghi, file cat nua chung) va
AppState.__init__ (server.py:751) goi load() ngay luc khoi tao
STATE o module import — tien trinh chet truoc ca main(), user phai
sua tay file.

Hanh vi moi (pin o day):
  1. session.json chua JSON hong -> load() tra None, khong raise.
  2. File hong duoc doi ten thanh session.json.corrupt, noi dung
     giu nguyen (de doi chieu, khong xoa mat du lieu user).
  3. Server (AppState) khoi dong duoc voi phien trong khi session
     hong — session None, khong crash.
  4. session.json hop le van load binh thuong.
  5. session.json khong ton tai van nhu cu (phien trong, load()
     raise FileNotFoundError nhu truoc; server bao ve bang exists()).

Mock/offline hoan toan: chi dung session GIA (uid/zpw_sek gia),
khong dang nhap that, khong goi that, khong chep noi dung session
that nao vao test.
"""

import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from zalo_pc_app import server as app_server  # noqa: E402
from zalo_pc_app import session as session_mod  # noqa: E402

CORRUPT_BYTES = b'{"uid": "10001", "zpw_sek": "sek-gia", "status": "da_dan'
FAKE_SESSION = {
    "uid": "10001",
    "dkey": "dkey-gia",
    "phonenum": "+84000000000",
    "zpw_sek": "sek-gia",
    "zpw_kt": "kt-gia",
    "zpw_enk": "enk-gia",
    "status": session_mod.STATUS_LOGGED_IN,
}


def _store(tmp):
    return session_mod.SessionStore(os.path.join(tmp, "session.json"))


def test_corrupt_json_load_returns_none():
    """(1) JSON hong -> load() tra None, khong raise."""
    tmp = tempfile.mkdtemp(prefix="zalo-pc-h4-")
    store = _store(tmp)
    with open(store.path, "wb") as f:
        f.write(CORRUPT_BYTES)
    assert store.load() is None


def test_corrupt_file_renamed_with_content_kept():
    """(2) File hong doi ten thanh session.json.corrupt, noi dung
    giu nguyen; session.json goc khong con."""
    tmp = tempfile.mkdtemp(prefix="zalo-pc-h4-")
    store = _store(tmp)
    with open(store.path, "wb") as f:
        f.write(CORRUPT_BYTES)
    assert store.load() is None
    assert not os.path.exists(store.path)
    corrupt_path = store.path + ".corrupt"
    assert os.path.exists(corrupt_path)
    with open(corrupt_path, "rb") as f:
        assert f.read() == CORRUPT_BYTES


def test_server_starts_with_empty_session_on_corrupt():
    """(3) Server khoi dong duoc voi phien trong khi session hong:
    AppState (duong di qua server.py:751) khong raise, session None,
    file hong da duoc doi ten."""
    tmp = tempfile.mkdtemp(prefix="zalo-pc-h4-")
    with open(os.path.join(tmp, "session.json"), "wb") as f:
        f.write(CORRUPT_BYTES)
    state = app_server.AppState(tmp)
    assert state.session is None
    assert not os.path.exists(os.path.join(tmp, "session.json"))
    with open(os.path.join(tmp, "session.json.corrupt"), "rb") as f:
        assert f.read() == CORRUPT_BYTES
    # Trang thai cong khai phai noi "chua dang nhap", khong phai loi
    # crash: public_status doc session None an toan.
    assert state.public_status()["login"] is False


def test_valid_session_still_loads():
    """(4) session.json hop le van load binh thuong."""
    tmp = tempfile.mkdtemp(prefix="zalo-pc-h4-")
    store = _store(tmp)
    sess = session_mod.new_session("dev-1", "testhost")
    sess.update(FAKE_SESSION)
    store.save(sess)
    loaded = store.load()
    assert loaded["uid"] == "10001"
    assert loaded["zpw_sek"] == "sek-gia"
    assert loaded["status"] == session_mod.STATUS_LOGGED_IN
    assert not os.path.exists(store.path + ".corrupt")


def test_missing_session_still_empty():
    """(5) session.json khong ton tai van nhu cu: AppState cho
    phien trong (khong crash, khong tao file rac)."""
    tmp = tempfile.mkdtemp(prefix="zalo-pc-h4-")
    store = _store(tmp)
    assert not store.exists()
    try:
        store.load()
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("load() tren file khong ton tai phai "
                             "raise FileNotFoundError nhu truoc")
    state = app_server.AppState(tmp)
    assert state.session is None
    assert not os.path.exists(store.path + ".corrupt")


def test_valid_json_but_not_a_dict_is_corrupt():
    """JSON hop le nhung khong phai dict (vd list) cung coi la hong:
    khong the dung lam session, doi ten nhu JSON hong."""
    tmp = tempfile.mkdtemp(prefix="zalo-pc-h4-")
    store = _store(tmp)
    with open(store.path, "w", encoding="utf-8") as f:
        f.write('["khong-phai-session"]')
    assert store.load() is None
    with open(store.path + ".corrupt", encoding="utf-8") as f:
        assert f.read() == '["khong-phai-session"]'


if __name__ == "__main__":
    test_corrupt_json_load_returns_none()
    test_corrupt_file_renamed_with_content_kept()
    test_server_starts_with_empty_session_on_corrupt()
    test_valid_session_still_loads()
    test_missing_session_still_empty()
    test_valid_json_but_not_a_dict_is_corrupt()
    print("test_security_h4_session_corrupt: 6 passed")
