# zalobot-embedded — máy chủ Zalo cũ, vendored nguyên vẹn

Nguồn: repo `TriTue2011/has-addons`, thư mục `zalo_bot` (máy chủ zalobot —
Node 20, zca-js 2.1.2), copy verbatim ngày 2026-11-05 (752K, không gồm
`node_modules`). Đã kiểm chứng bằng `diff -r` với nguồn: giống hệt.
`README.md` trong thư mục này vẫn là README gốc của nguồn.

**KHÔNG SỬA file nào trong thư mục này (kể cả README gốc).** Muốn đổi hành
vi thì sửa ở tầng Python (`zalo_pc_app/addon_client.py` gọi API của nó)
hoặc re-vendor từ nguồn. `entrypoint.sh` của nguồn (dành cho Home
Assistant) KHÔNG dùng ở đây — app dùng `docker-entrypoint.py` riêng để khởi
động sidecar với `DATA_DIRECTORY=/data/zalobot`, `PORT=3000`.

Sidecar chạy `node server.js`, nghe loopback `:3000` trong container, publish
`3000:3000` để HA integration nối vào đúng API cũ (132 routes). App UI không
dùng UI của sidecar (`views/`, `public/` đi kèm chỉ để server chạy đúng).
