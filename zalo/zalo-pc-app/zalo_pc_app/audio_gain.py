"""Tang/giam am luong MIC va LOA cua cuoc goi bang phan mem (PCM16 mono): khong phu thuoc thiet bi (loa R1 khong nghe lenh set_volume).

Muc tinh bang % (100 = giu nguyen). Tang qua 100 thi xen (clip) vao ±32767 de khong tran so.
Mic: ap SAU quyet dinh chan vong (khung bi chan van la im lang). Loa: ap SAU khi EchoGuard do muc tieng ben kia (nguong chan vong khong lech theo nut chinh)."""
import struct

MIN_PERCENT = 0
MAX_PERCENT = 300
DEFAULT_PERCENT = 100
STEP_PERCENT = 10


def clamp_percent(value):
    """Ep ve so nguyen trong [0, 300]. Nem ValueError neu khong phai so."""
    if isinstance(value, bool):
        raise ValueError("muc am luong phai la so")
    try:
        pct = int(round(float(value)))
    except (TypeError, ValueError):
        raise ValueError("muc am luong phai la so") from None
    return max(MIN_PERCENT, min(MAX_PERCENT, pct))


def apply_gain(frame, percent):
    """Nhan tung mau PCM16 little-endian voi percent/100. 100 tra nguyen doi tuong cu; 0 tra khung im lang."""
    if percent == DEFAULT_PERCENT or not frame:
        return frame
    if percent <= 0:
        return bytes(len(frame))
    n = len(frame) // 2
    k = percent / 100.0
    samples = struct.unpack("<%dh" % n, frame[:n * 2])
    out = struct.pack("<%dh" % n, *(max(-32768, min(32767, int(round(s * k)))) for s in samples))
    return out + frame[n * 2:]
