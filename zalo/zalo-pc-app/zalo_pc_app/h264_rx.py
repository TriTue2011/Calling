"""Ghép gói RTP H.264 (RFC 6184) hoặc H.265/HEVC (kiểu đóng gói Zalo) của điện thoại thành khung Annex-B để xem trên WebUI (13/11/2026; H.265 14/11/2026).

Điện thoại gửi hình bằng RTP PT 98 (khung khoá) / 121 (khác), payload H.264 chuẩn: NAL đơn (1..23), STAP-A (24), FU-A (28). Module thuần
(không phụ thuộc mạng) để kiểm thử: `H264Depacketizer.push(payload, marker, seq)` trả (annexb, is_key) khi đủ một khung, ngược lại None.
Mất gói giữa khung thì bỏ khung đó (không ghép bậy) và chờ khung khoá kế tiếp.
"""

START = b"\x00\x00\x00\x01"

# H.265 (log thật 14/11: cuộc gọi video điện thoại gửi HEVC, gói đầu «1c80 00000001 4001» = VPS; H.264 bắt đầu bằng SPS 0x67).
HEVC_PARAM = {32: "vps", 33: "sps", 34: "pps"}


def detect_codec(data):
    """"h265" | "h264" | None (chưa đủ dữ liệu) theo NAL đầu tiên của dãy Annex-B (hoặc NAL trần). Tiêu đề HEVC dài 2 byte: byte đầu (loại<<1) với loại
    32/33/34 (VPS/SPS/PPS) = 0x40/0x42/0x44 và byte hai = 0x01 (lớp 0, tid 0); các byte đó không phải tiêu đề H.264 hợp lệ thường gặp (0x67/0x68/0x65/0x41...)."""
    data = bytes(data)
    i = data.find(b"\x00\x00\x01")
    nal = data[i + 3:] if i >= 0 else data
    if len(nal) < 2:
        return None
    if nal[0] in (0x40, 0x42, 0x44) and nal[1] == 0x01:
        return "h265"
    if nal[0] in (0x26, 0x28, 0x02, 0x4e) and nal[1] == 0x01:           # IDR_W_RADL / IDR_N_LP / TRAIL_R / SEI prefix: mở giữa luồng H.265
        return "h265"
    return "h264"


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


class ReorderBuffer:
    """Xếp lại gói RTP video đến lệch thứ tự (đi qua relay có thể đảo gói) TRƯỚC khi ghép khung: không có nó, mỗi lần đảo gói là mất cả khung và phải chờ khung khoá kế
    (14/11/2026 cuộc video thật: chỉ 147 khung giải mã được trong 100 s, bỏ 302). `push(seq, item)` trả danh sách [(seq, item)] đã SẴN SÀNG theo đúng thứ tự;
    gói đến muộn/trùng bị bỏ; thiếu gói quá `max_hold` gói thì chấp nhận mất và nhảy tiếp (bộ ghép sẽ tự bỏ khung hỏng)."""

    def __init__(self, max_hold=24):
        self.max_hold = max_hold
        self.expected = None
        self.pending = {}
        self.late = 0
        self.lost = 0

    def push(self, seq, item):
        seq &= 0xFFFF
        if self.expected is None:
            self.expected = seq
        ahead = (seq - self.expected) & 0xFFFF
        if ahead >= 0x8000:                     # cũ hơn thứ đang chờ: muộn hoặc trùng
            self.late += 1
            return []
        self.pending[seq] = item
        out = []
        while True:
            while self.expected in self.pending:
                out.append((self.expected, self.pending.pop(self.expected)))
                self.expected = (self.expected + 1) & 0xFFFF
            if len(self.pending) > self.max_hold:       # đợi quá lâu: coi gói thiếu là mất
                nxt = min(self.pending, key=lambda q: (q - self.expected) & 0xFFFF)
                self.lost += (nxt - self.expected) & 0xFFFF
                self.expected = nxt
                continue
            break
        return out


class H264Depacketizer:
    def __init__(self):
        self._nals = []            # các NAL của khung đang ghép
        self._fu = None            # bytearray NAL đang ghép từ FU-A
        self._zraw = None          # bytearray khung Annex-B đang ghép theo kiểu Zalo (header 1c 80/00/40)
        self._last_seq = None
        self._broken = False       # khung hiện tại mất gói: bỏ
        self._need_key = True      # đầu cuộc / sau mất gói: chỉ phát từ khung khoá
        self.sps = self.pps = None
        self.vps = None
        self.codec = None          # "h264" | "h265": nhận biết từ NAL đầu tiên của luồng
        self.stats = {"frames": 0, "key": 0, "dropped": 0, "bad": 0}

    @property
    def need_key(self):
        """Đang chờ khung khoá (đầu cuộc / sau khi mất gói): nên xin điện thoại gửi khung khoá."""
        return self._need_key

    def _end_frame(self):
        nals, broken = self._nals, self._broken
        self._nals, self._fu, self._zraw, self._broken = [], None, None, False
        if broken or not nals:
            if broken:
                self.stats["dropped"] += 1
                self._need_key = True
            return None
        if self.codec is None:
            self.codec = detect_codec(START + nals[0])
        if self.codec == "h265":
            types = [(n[0] >> 1) & 0x3F for n in nals]
            for n, t in zip(nals, types):
                if t == 32:
                    self.vps = n
                elif t == 33:
                    self.sps = n
                elif t == 34:
                    self.pps = n
            is_key = any(16 <= t <= 21 for t in types)                # IRAP: BLA/IDR/CRA
            params = [self.vps, self.sps, self.pps]
            have_params = any(t in (32, 33, 34) for t in types)
        else:
            types = [n[0] & 0x1F for n in nals]
            for n, t in zip(nals, types):
                if t == 7:
                    self.sps = n
                elif t == 8:
                    self.pps = n
            is_key = 5 in types
            params = [self.sps, self.pps]
            have_params = 7 in types
        if self._need_key and not is_key:
            self.stats["dropped"] += 1
            return None
        if is_key:
            self._need_key = False
            if all(params) and not have_params:                      # khung khoá thiếu tập thông số: thêm để bộ giải mã khởi động được
                nals = params + nals
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
