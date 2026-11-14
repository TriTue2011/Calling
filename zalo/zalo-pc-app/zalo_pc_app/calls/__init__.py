"""Luồng cuộc gọi tách theo trục (14/11/2026): video.py (hình, báo camera, thoại→video), …; danh tính web/pc ở identity_*.py.

Mỗi mô-đun chỉ chứa việc của MỘT trục; việc dùng chung (STATE, nhật ký, tìm transport) vẫn ở server.py và được gọi qua `srv()` (nạp muộn, nên test vá `server.X` vẫn có tác dụng)."""
