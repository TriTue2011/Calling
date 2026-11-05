# Build image Zalo PC TRÊN SERVER (thay vì chờ GitHub Actions)

Mục đích: sau mỗi lần push code mới, build image ngay trên server rồi chạy
luôn — không chờ CI build xong rồi mới pull về. Đường image cũ
(`docker-compose.yml` + image `ghcr.io/...:test`) vẫn giữ nguyên, thích
dùng đường nào thì dùng đường đó, nhưng đừng chạy hai đường cùng lúc.

## 0. Điều kiện (server đã có sẵn vì đang chạy Portainer)

```bash
docker --version && docker compose version && git --version
```

Ba lệnh đều phải chạy được. Nếu thiếu `docker compose`, cài thêm gói
`docker-compose-plugin` rồi làm tiếp.

## 1. Lần đầu

Dừng stack đang chạy trong Portainer trước để nhường cổng 8080:
Portainer → Stacks → `zalo` → Stop.

Rồi trên server (SSH/terminal):

```bash
mkdir -p ~/calling && cd ~/calling
git clone https://github.com/TriTue2011/Calling.git
cd Calling
git checkout muse/zalo-addon-pivot
cd zalo-pc-app

# Kiểm cú pháp file compose trước (in ra cấu hình đã resolve, không lỗi là được):
docker compose -f docker-compose.build.yml config

# Build + chạy (APP_VERSION để footer hiện đúng commit sha đang chạy):
APP_VERSION=$(git rev-parse HEAD) docker compose -f docker-compose.build.yml up -d --build
```

Kiểm tra:

```bash
docker compose -f docker-compose.build.yml ps
docker logs zalo-zalo-pc-1 --tail 20
```

Mở `http://<địa-chỉ-server>:8080` — cuối trang phải hiện đúng sha vừa build.
Phiên đăng nhập cũ vẫn còn (volume `/opt/zalo` được giữ nguyên) nên không
cần quét lại QR, không cần chown gì thêm. Build lần đầu tải base image
`python:3.12-slim` nên mất vài phút; các lần sau có cache nên nhanh hơn.

## 2. Sau mỗi lần push mới

```bash
cd ~/calling/Calling
git pull
cd zalo-pc-app
APP_VERSION=$(git rev-parse HEAD) docker compose -f docker-compose.build.yml up -d --build
```

Chỉ vậy thôi: `up -d --build` build lại image, tạo lại container, giữ
nguyên volume `/opt/zalo` nên phiên đăng nhập không mất, không quét lại QR.

## 3. Portainer thì sao?

**Dùng lệnh trực tiếp (mục 1–2) cho chắc.** Tài liệu chính thức của
Portainer về "Add a new stack" (docs.portainer.io/user/docker/stacks/add)
không hề nói stack build được từ source — cơ chế cập nhật Git của nó chỉ
là pull lại image (`Re-pull image`). Nên đừng cố bắt stack Portainer build.

Bằng chứng thật (gặp ngày 2026-11-05 khi deploy stack build qua Portainer):

```text
Failed to deploy a stack: compose build operation failed: listing workers
for Build: failed to list workers: Unavailable: connection error: desc =
"error reading server preface: http2: failed reading the frame payload:
http2: frame too large, note that the frame header looked like an
HTTP/1.1 header"
```

Nghĩa là Portainer cố build qua BuildKit nhưng endpoint build trả về
HTTP/1.1 thay vì gRPC HTTP/2 — KHÔNG phải lỗi code app, KHÔNG phải lỗi
cú pháp compose. **Gặp đúng lỗi này tức là đang deploy qua Portainer:
dừng lại, chuyển sang lệnh trực tiếp ở mục 1–2.** (Stack Portainer đang
chạy vẫn hiện dạng «Limited» là bình thường, không phải lỗi.)

Bước dự phòng nếu lệnh trực tiếp cũng lỗi: kiểm tra `docker buildx ls`
xem BuildKit có sẵn không. Nếu build vẫn không được thì đường image cũ
(`docker-compose.yml` + image `ghcr.io/...:test`, xem mục 4) vẫn dùng
được bình thường — build trên server chỉ là đường nhanh hơn, không bắt
buộc.

Có một đường Portainer khác — Images → Build a new image → lấy Dockerfile
từ URL repo GitHub (docs.portainer.io/user/docker/images/build, Method 3) —
nhưng chưa xác minh được với repo/nhánh này, và tài liệu cảnh báo build
trong Portainer không dùng được lệnh `COPY` từ file trên host. Muốn thử
thì thử, còn chắc chắn thì dùng lệnh trực tiếp ở trên.

## 4. Quay lại đường image cũ (nếu cần)

```bash
cd ~/calling/Calling/zalo-pc-app
docker compose -f docker-compose.build.yml down   # KHÔNG thêm -v
```

Rồi trong Portainer start lại stack `zalo` như cũ (nó pull image
`ghcr.io/tritue2011/zalo-pc-app-test:test` về chạy). Volume `/opt/zalo`
không bị đụng tới trong cả hai đường nên phiên đăng nhập vẫn còn.

## Ghi chú

- Một container, một cổng duy nhất 8080 — không còn sidecar Node/zalobot,
  không còn cổng 3000. Home Assistant nối vào API của app ở
  `http://<địa-chỉ-server>:8080`; phiên đăng nhập là QR-PC quét ở 8080.
- Image build ra tên `zalo-pc-app:local`, chỉ nằm trên server, không đẩy
  đi đâu, không đè tag `test` của CI.
- Build chạy native trên server x86_64 nên không cần QEMU.
- Lần build thật đầu tiên là trên server (máy chuẩn bị file này không
  chạy được Docker nên chưa build thử).
