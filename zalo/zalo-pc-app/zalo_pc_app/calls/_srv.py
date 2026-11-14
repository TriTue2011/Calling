"""Cầu nối tới server.py cho các mô-đun luồng cuộc gọi. Nạp muộn để tránh vòng nhập (server nhập calls.*); mọi tham chiếu đi qua thuộc tính của `server`
lúc GỌI, nên test vá `server.STATE`, `server._log_call`, `server._transport_for_call`… vẫn có hiệu lực.

QUAN TRỌNG (lỗi 14/11/2026): container chạy `python3 -m zalo_pc_app.server`, nên mô-đun đang chạy là `__main__`, KHÔNG phải `zalo_pc_app.server`.
`from .. import server` khi đó nạp một BẢN SAO THỨ HAI của server.py (có STATE, bộ đếm call_id, … riêng): nút Kết thúc không thấy cuộc gọi do mã đã tách ghi
(no_live_call), call_id cuộc gọi đi về 1,2,3 (Zalo từ chối -101 vì dùng lại id)… Vì vậy ưu tiên chính mô-đun đang chạy."""
import sys


def srv():
    main = sys.modules.get("__main__")
    spec = getattr(main, "__spec__", None)
    if main is not None and getattr(spec, "name", "") == "zalo_pc_app.server":
        return main
    from .. import server
    return server
