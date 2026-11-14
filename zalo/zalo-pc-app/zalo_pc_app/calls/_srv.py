"""Cầu nối tới server.py cho các mô-đun luồng cuộc gọi. Nạp muộn để tránh vòng nhập (server nhập calls.*); mọi tham chiếu đi qua thuộc tính của `server`
lúc GỌI, nên test vá `server.STATE`, `server._log_call`, `server._transport_for_call`… vẫn có hiệu lực."""


def srv():
    from .. import server
    return server
