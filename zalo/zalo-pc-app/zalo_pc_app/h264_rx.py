"""Ghép gói RTP H.264 (RFC 6184) của điện thoại thành khung Annex-B để xem trên WebUI (13/11/2026).

Điện thoại gửi hình bằng RTP PT 98 (khung khoá) / 121 (khác), payload H.264 chuẩn: NAL đơn (1..23), STAP-A (24), FU-A (28). Module thuần
(không phụ thuộc mạng) để kiểm thử: `H264Depacketizer.push(payload, marker, seq)` trả (annexb, is_key) khi đủ một khung, ngược lại None.
Mất gói giữa khung thì bỏ khung đó (không ghép bậy) và chờ khung khoá kế tiếp.
"""

START = b"\x00\x00\x00\x01"


def split_annexb(data):
    """Tách dãy Annex-B (mã bắt đầu 3 hoặc 4 byte) thành danh sách NAL (không kèm mã bắt đầu)."""
    data = bytes(data)
    pos, starts, i = [], [], 0
    while True:
        j = data.find(b"\x00\x00\x01", i)
        if j < 0:
            break
        starts.append(j + 3)
        pos.append(j)
        i = j + 3
    out = []
    for k, st in enumerate(starts):
        end = pos[k + 1] if k + 1 < len(pos) else len(data)
        nal = data[st:end].rstrip(b"\x00") if k + 1 < len(pos) else data[st:end]
        if nal:
            out.append(nal)
    return out


def rtp_payload(rtp):
    """Phần payload của gói RTP đã giải mã (bỏ tiêu đề cố định, CSRC, phần mở rộng); None nếu gói hỏng."""
    if len(rtp) < 12 or rtp[0] >> 6 != 2:
        return None
    n = 12 + 4 * (rtp[0] & 0x0F)
    if rtp[0] & 0x10:
        if len(rtp) < n + 4:
            return None
        n += 4 + 4 * int.from_bytes(rtp[n + 2:n + 4], "big")
    if rtp[0] & 0x20 and len(rtp) > n:                 # padding cuối
        pad = rtp[-1]
        return bytes(rtp[n:len(rtp) - pad]) if 0 < pad < len(rtp) - n else None
    return bytes(rtp[n:]) if len(rtp) > n else None


class H264Depacketizer:
    def __init__(self):
        self._nals = []            # các NAL của khung đang ghép
        self._fu = None            # bytearray NAL đang ghép từ FU-A
        self._zraw = None          # bytearray khung Annex-B đang ghép theo kiểu Zalo (header 1c 80/00/40)
        self._last_seq = None
        self._broken = False       # khung hiện tại mất gói: bỏ
        self._need_key = True      # đầu cuộc / sau mất gói: chỉ phát từ khung khoá
        self.sps = self.pps = None
        self.stats = {"frames": 0, "key": 0, "dropped": 0, "bad": 0}

    def _end_frame(self):
        nals, broken = self._nals, self._broken
        self._nals, self._fu, self._zraw, self._broken = [], None, None, False
        if broken or not nals:
            if broken:
                self.stats["dropped"] += 1
                self._need_key = True
            return None
        types = [n[0] & 0x1F for n in nals]
        for n, t in zip(nals, types):
            if t == 7:
                self.sps = n
            elif t == 8:
                self.pps = n
        is_key = 5 in types
        if self._need_key and not is_key:
            self.stats["dropped"] += 1
            return None
        if is_key:
            self._need_key = False
            if self.sps and self.pps and 7 not in types:      # khung khoá thiếu SPS/PPS: thêm để bộ giải mã khởi động được
                nals = [self.sps, self.pps] + nals
        self.stats["frames"] += 1
        self.stats["key"] += 1 if is_key else 0
        return b"".join(START + n for n in nals), is_key

    def push(self, payload, marker, seq):
        if not payload:
            return None
        if self._last_seq is not None and seq != (self._last_seq + 1) & 0xFFFF:
            self._broken = True
            self._fu = None
            self._zraw = None
        self._last_seq = seq
        t = payload[0] & 0x1F
        if payload[:4] == START or payload[:3] == b"\x00\x00\x01":
            # Kiểu Zalo (zcall-native packetizeFrame): khung vừa một gói thì gửi NGUYÊN dạng Annex-B (bắt đầu bằng mã 00 00 00 01), không phải NAL RFC 6184.
            self._nals.extend(split_annexb(payload))
        elif t == 28 and len(payload) >= 2 and (payload[1] & 0x1F) == 0:
            # Khung lớn cắt mảnh với header 2 byte «1c 80» (đầu) / «1c 00» (giữa) / «1c 40» (cuối) — byte thứ hai KHÔNG mang loại NAL (khác FU-A RFC 6184).
            flag = payload[1]
            if flag & 0x80:
                self._zraw = bytearray(payload[2:])
            elif self._zraw is not None:
                self._zraw += payload[2:]
            else:
                self._broken = True
            if flag & 0x40 and self._zraw is not None:
                self._nals.extend(split_annexb(self._zraw))
                self._zraw = None
        elif 1 <= t <= 23:
            self._nals.append(bytes(payload))
        elif t == 24:                                          # STAP-A: [2 byte độ dài][NAL]...
            i = 1
            while i + 2 <= len(payload):
                n = int.from_bytes(payload[i:i + 2], "big")
                i += 2
                if n == 0 or i + n > len(payload):
                    self.stats["bad"] += 1
                    self._broken = True
                    break
                self._nals.append(bytes(payload[i:i + n]))
                i += n
        elif t == 28 and len(payload) >= 2:                    # FU-A
            fu_h = payload[1]
            if fu_h & 0x80:
                self._fu = bytearray([(payload[0] & 0xE0) | (fu_h & 0x1F)])
                self._fu += payload[2:]
            elif self._fu is not None:
                self._fu += payload[2:]
            else:
                self._broken = True                            # giữa/cuối FU mà chưa thấy đầu
            if fu_h & 0x40 and self._fu is not None:
                self._nals.append(bytes(self._fu))
                self._fu = None
        else:
            self.stats["bad"] += 1
        return self._end_frame() if marker else None
