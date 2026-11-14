"""Dòng xem trước của danh sách hội thoại không bao giờ trống với tin không phải chữ (14/11/2026: ảnh thật «AI Camera — Bạn: » và «Zalo» trống).
Chạy: python3 tests/test_conv_preview.py"""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import message_store  # noqa: E402


def _msg(mid, sender, text, ts, kind, **kw):
    return dict({"id": mid, "sender_id": sender, "text": text, "time": ts, "kind": kind, "sender_name": "A", "raw": {"msgId": mid}}, **kw)


def test_non_text_last_message_always_has_a_label():
    st = message_store.MessageStore(os.path.join(tempfile.mkdtemp(), "m.db"))
    st.set_account("ME")
    now = time.time()
    cases = {"photo": "[Ảnh]", "voice": "[Tin nhắn thoại]", "video": "[Video]", "sticker": "[Nhãn dán]", "link": "[Liên kết]",
             "location": "[Tin đính kèm]", "loai_la_chua_biet": "[Tin đính kèm]"}          # loại chưa biết: nhãn chung, không cần liệt kê hết
    for i, (kind, _) in enumerate(cases.items()):
        st.record("user", "T%d" % i, _msg(str(i), "T%d" % i, "", now - i, kind))
    rows = {r["thread_id"]: r["last_text"] for r in st.threads()}
    for i, (kind, want) in enumerate(cases.items()):
        assert rows["T%d" % i] == want, (kind, rows["T%d" % i])
    # chữ thật luôn thắng nhãn; tệp có tên thì hiện tên
    st.record("user", "TX", _msg("x", "TX", "xin chào", now, "text"))
    st.record("user", "TF", _msg("f", "TF", "", now, "file", file_name="bao-cao.pdf"))
    rows = {r["thread_id"]: r["last_text"] for r in st.threads()}
    assert rows["TX"] == "xin chào" and rows["TF"] == "[Tệp] bao-cao.pdf", rows
    # tin chữ rỗng (không phải kind lạ) thì để trống như cũ
    st.record("user", "TE", _msg("e", "TE", "", now, "text"))
    assert {r["thread_id"]: r["last_text"] for r in st.threads()}["TE"] == ""


if __name__ == "__main__":
    test_non_text_last_message_always_has_a_label()
    print("PASS test_non_text_last_message_always_has_a_label")
    print("ALL CONV PREVIEW TESTS PASSED")
