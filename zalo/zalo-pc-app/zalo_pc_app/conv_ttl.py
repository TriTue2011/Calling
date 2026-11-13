"""`ttl` tự xoá của từng cuộc trò chuyện (13/11).

Cuộc trò chuyện bật tự xoá (nhóm AI Camera: 1 ngày) thì Zalo đòi ẢNH gửi vào kèm đúng `ttl` của nó, thiếu thì trả inner 801 và đăng dòng
«Không thể gửi tin nhắn tự xóa do đang dùng phiên bản cũ». Chữ thì Zalo tự áp, không đòi. Đo thật 13/11: gửi ảnh kèm ttl=86400000 vào nhóm -> nhận.

Giá trị lấy từ GET /api/conv/autodelete/getConvers (máy chủ web `tt-convers-wpa.chat.zalo.me`; `convers-wpa.api.zalo.me` trả 404) rồi nhớ lại
`cache_seconds`. Không đọc được -> trả 0 như trước (không chặn việc gửi); lỗi chỉ ghi log một lần mỗi đợt.
"""

import time


class ConvTtl:
    def __init__(self, fetch, cache_seconds=600.0, clock=time.time, log=print):
        """fetch() -> {thread_id(str): ttl_ms(int)} cho các cuộc trò chuyện ĐANG bật tự xoá."""
        self.fetch, self.cache_seconds, self.clock, self.log = fetch, cache_seconds, clock, log
        self._map, self._at, self._failed = {}, None, False

    def get(self, thread_id):
        now = self.clock()
        if self._at is None or now - self._at > self.cache_seconds:
            try:
                self._map = {str(k): int(v) for k, v in (self.fetch() or {}).items()}
                self._failed = False
            except Exception as e:  # noqa: BLE001 - bien he thong: Zalo/mang
                if not self._failed:
                    self.log("[conv-ttl] khong doc duoc cai dat tu xoa: %s: %s" % (type(e).__name__, str(e)[:120]))
                self._failed = True
            # lỗi cũng nhớ mốc để không gọi Zalo mỗi lần gửi, nhưng chỉ 30 giây (chưa đăng nhập lúc khởi động không được khoá cả 10 phút)
            self._at = now - self.cache_seconds + 30 if self._failed else now
        return self._map.get(str(thread_id), 0)

    def forget(self):
        self._at = None
