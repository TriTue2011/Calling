"""Webhook tin nhắn mang đủ thông tin ảnh/video/tệp để HA tải về và xử lý (14/11/2026).
Run: python3 tests/test_webhook_media_fields.py"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from zalo_pc_app import webhooks  # noqa: E402


def photo_msg():
    params = json.dumps({"id_in_group": 1, "is_group_layout": 1, "width": 1920, "height": 1080, "group_layout_id": 1794623122212, "total_item_in_group": 3})
    return {"threadId": "3295299208151385728", "type": 1, "senderId": "475796162066271393", "msgId": "8486717320161", "content": "", "kind": "photo",
            "file_url": "https://f65-zpg-r.zdn.vn/5683/b81c.jpg", "file_name": "gui2.jpg", "file_ext": "jpg", "file_size": "125735",
            "raw": {"cliMsgId": "1794623122213", "content": {"href": "https://f65-zpg-r.zdn.vn/5683/b81c.jpg", "thumb": "https://t-f65-zpg-r.zdn.vn/480/5683/b81c.jpg", "params": params}}}


def test_photo_event_carries_file_thumb_size_and_album_position():
    ev = webhooks.build_message_event(photo_msg(), "acc")
    assert ev["kind"] == "photo" and ev["file_url"].endswith("b81c.jpg") and ev["file_name"] == "gui2.jpg" and ev["file_size"] == 125735, ev
    assert ev["thumb_url"].startswith("https://t-f65") and ev["width"] == 1920 and ev["height"] == 1080, ev
    assert ev["album_id"] == 1794623122212 and ev["album_index"] == 1 and ev["album_total"] == 3, ev          # HA biết đây là ảnh thứ mấy trong album


def test_video_event_has_duration_and_size_not_album():
    params = json.dumps({"duration": 5715, "video_height": 720, "fileSize": 1261149, "video_width": 1280})
    ev = webhooks.build_message_event({"threadId": "1", "type": 0, "senderId": "2", "msgId": "3", "content": "🔔 Phát hiện chuyển động!", "kind": "video",
                                       "file_url": "https://fg41.dlfl.vn/a55d/4477", "raw": {"content": {"params": params}}}, "acc")
    assert ev["kind"] == "video" and ev["duration_ms"] == 5715 and ev["width"] == 1280 and ev["height"] == 720, ev
    assert ev["content"] == "🔔 Phát hiện chuyển động!" and "album_id" not in ev, ev                        # chú thích vẫn là content


def test_text_and_broken_params_stay_clean():
    ev = webhooks.build_message_event({"threadId": "1", "type": 0, "senderId": "2", "msgId": "3", "content": "xin chào", "kind": "text"}, "acc")
    for k in ("file_url", "file_name", "file_size", "thumb_url", "width", "album_id", "duration_ms"):
        assert k not in ev, (k, ev)                                    # tin chữ: payload như cũ (tương thích)
    bad = webhooks.build_message_event({"threadId": "1", "type": 0, "senderId": "2", "msgId": "3", "kind": "photo", "file_size": "abc",
                                        "raw": {"content": {"params": "{không phải json"}}}, "acc")
    assert "file_size" not in bad and "width" not in bad, bad          # lỗi dữ liệu không làm hỏng sự kiện


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, str(e)[:300])
    print("ALL WEBHOOK MEDIA TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
