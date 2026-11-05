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

## 5. Vòng sửa 4 lỗi (2026-11-06) — redeploy + kiểm tra từng lỗi

Vòng này sửa 4 lỗi đã gặp trên server: (1) tin nhắn đến không hiện,
(2) gọi đi kẹt ở bước 2 (11301), (3) đính kèm file không gửi được,
(4) tin nhắn thoại báo lỗi 133 (chỉ nhận MP3). Code đã push lên nhánh
`muse/zalo-addon-pivot`; **bắt buộc rebuild từ source** vì image giờ
cài thêm `ffmpeg` (tin nhắn thoại) — pull image CI cũ sẽ không có
ffmpeg và lỗi 133 vẫn còn.

### Redeploy

```bash
cd ~/calling/Calling
git pull
cd zalo-pc-app
APP_VERSION=$(git rev-parse HEAD) docker compose -f docker-compose.build.yml up -d --build
```

Phiên đăng nhập giữ nguyên (volume `/opt/zalo`), không cần quét lại QR
— trừ trường hợp mục (1) dưới đây báo `sync: no_endpoints`. Kiểm tra
đúng bản mới: cuối trang UI phải hiện sha mới, và log phải có dòng
`[sync-poll]` khi poller chạy.

### (1) Tin nhắn đến — kiểm tra

- Mở `http://<địa-chỉ-server>:8080/api/status`: phải có
  `"sync": "running"`.
  - Nếu là `"sync": "no_endpoints"`: phiên cũ thiếu endpoint poll —
    quét lại QR **một lần** rồi kiểm tra lại (poller tự lấy endpoint
    từ lúc đăng nhập).
- Nhờ một tài khoản khác gửi tin 1-1: tin phải hiện trong thread đang
  mở trong ~5 giây, không cần F5; khi thread không mở phải có badge
  chưa đọc + xem trước tin mới ở danh sách.
- Tin nhóm: hiện với tên người gửi; F5 trong nhóm không trùng tin cũ.
- Nếu không hiện: ghi lại giá trị `"sync"` + các dòng log `[sync-poll]`
  (chỉ số lượng/mã lỗi, không có nội dung tin).

### (2) Gọi đi — kiểm tra

- Bấm gọi từ một dòng liên hệ (dùng tài khoản phụ, không dùng tài
  khoản chính). Dòng trạng thái bước 2 phải đọc:
  `Bước 2 (11301): đã gửi`.
- Nếu vẫn lỗi, dòng bước 2 giờ nêu rõ **tham số còn thiếu + danh sách
  key của phản hồi 11300** — chụp lại dòng đó (không có IP/giá trị
  thật trong đó). Đây là thông tin để sửa tiếp, không phải lỗi hiển
  thị.
- Chưa chứng minh được cuộc gọi thật hoàn tất (nghe/nói 2 chiều) —
  vòng này mới sửa tới bước gửi 11301.

### (3) Đính kèm file — kiểm tra

- File thường (vd. `.m3u`, `.txt`): gửi được, bên kia nhận được file.
- Ảnh `.jpg`/`.png`/`.webp`: gửi dạng ảnh.
- GIF: gửi dạng **file**, không phải ảnh.
- File 0 byte: phải báo lỗi rõ ngay trên UI, không gửi ngầm.
- File >100MB / ảnh >25MB: báo lỗi rõ, không gửi.
- Nếu đính kèm vẫn thất bại dù các trường hợp trên đều báo đúng:
  nghi vấn số 1 là `clientId` — app đang gửi dạng SỐ (epoch-ms, theo
  bản PC), trong khi code Node.js gửi dạng CHUỖI. Ghi lại thông báo lỗi
  trên UI để đối chiếu.

### (4) Tin nhắn thoại — kiểm tra

- Ghi âm ~5 giây rồi gửi: trạng thái phải hiện
  `Đang chuyển sang MP3 rồi gửi…`, sau đó bong bóng thoại hiện và
  bên kia nghe được.
- Nếu báo lỗi, thông báo phải nêu rõ ở bước nào (ghi âm / chuyển MP3 /
  gửi) thay vì lỗi chung chung.
- Lưu ý: ffmpeg chỉ có sau khi rebuild image mới; nếu image cũ thì
  vẫn lỗi 133.

### Câu hỏi còn mở (chưa có đáp án, không chặn redeploy)

- Gọi đi: phản hồi 11300 thật có mang `token`/`sessId`/`srtpKey`
  không (lần lỗi trước dừng ở relay nên chưa thấy); `local_session`
  lấy SSRC từ đâu (không được random mỗi cuộc gọi, cũng không được
  dùng giá trị đã bắt sẵn).
- Đính kèm: `clientId` dạng SỐ có được `sharefile_full` chấp nhận
  không (xem mục (3)).

## Ghi chú

- Một container, một cổng duy nhất 8080 — không còn sidecar Node/zalobot,
  không còn cổng 3000. Home Assistant nối vào API của app ở
  `http://<địa-chỉ-server>:8080`; phiên đăng nhập là QR-PC quét ở 8080.
- Image build ra tên `zalo-pc-app:local`, chỉ nằm trên server, không đẩy
  đi đâu, không đè tag `test` của CI.
- Build chạy native trên server x86_64 nên không cần QEMU.
- Lần build thật đầu tiên là trên server (máy chuẩn bị file này không
  chạy được Docker nên chưa build thử).
