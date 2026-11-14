#!/usr/bin/env python3
"""Phân tích tệp zalo_pc_app/audio_dump (diag/echo-*.bin): độ trễ loa→mic, mức VỌNG còn lại trong tiếng mic gửi sang bên kia, và ghi 2 tệp WAV đã căn giờ.

Dùng: python3 tools/echo_analyze.py <echo-....bin> [--wav ra_thu_muc]
Số in ra:
  tre_ms       độ trễ loa→mic tìm bằng GCC-PHAT (đỉnh rõ = đường vọng có thật)
  doi_chieu    đỉnh / trung vị của tương quan (≥ 8: tin được)
  vong_%       tỷ lệ công suất mic GIẢI THÍCH được bằng tiếng loa trễ (bộ lọc ngắn thích nghi bình phương tối thiểu, theo từng đoạn 2 s có tiếng loa);
               ≈ phần tiếng bên kia bị gửi NGƯỢC lại. 0% = sạch, vài chục % = vọng nặng. Người nhà nói chen làm số này THẤP đi (không phải vọng) nên đọc cùng mic_rms.
  erle_db      -10·log10(1 - vong) : mức bộ khử đã/chưa làm được trên đoạn đó (không phải mức vọng trước khi khử)
Chỉ dùng numpy."""
import struct
import sys
import wave

import numpy as np

RATE = 16000
FRAME = 640                 # byte mỗi khung (20 ms PCM16 mono 16 kHz)
SAMPLES = FRAME // 2        # = 320 mẫu
REC = struct.Struct("<Bd")


def load(path):
    """-> (far, near) mảng float32 căn theo giờ đơn điệu (cùng độ dài, cùng gốc thời gian)."""
    raw = open(path, "rb").read()
    step = REC.size + FRAME
    recs = [(raw[i], REC.unpack_from(raw, i)[1], np.frombuffer(raw[i + REC.size:i + step], dtype="<i2").astype(np.float32))
            for i in range(0, len(raw) - step + 1, step)]
    if not recs:
        raise SystemExit("tệp rỗng")
    t0 = min(t for _, t, _ in recs)
    end = max(t for _, t, _ in recs) - t0 + 0.02
    n = int(end * RATE) + SAMPLES
    out = {0: np.zeros(n, np.float32), 1: np.zeros(n, np.float32)}
    for kind, t, pcm in recs:
        a = int(round((t - t0) * RATE))
        out[kind][a:a + SAMPLES] = pcm[:max(0, n - a)] if a + SAMPLES > n else pcm
    return out[0], out[1]


def gcc_phat(near, far, max_s=1.5):
    m = 1 << int(np.ceil(np.log2(near.size + far.size)))
    c = np.conj(np.fft.rfft(far, m)) * np.fft.rfft(near, m)       # đỉnh ở k = trễ (mic trễ hơn loa k mẫu)
    r = np.fft.irfft(c / (np.abs(c) + 1e-9), m)
    lim = int(max_s * RATE)
    seg = r[:lim]
    k = int(np.argmax(seg))
    return k, float(seg[k] / (np.median(np.abs(seg)) + 1e-9))


def echo_fraction(near, far, delay, taps=512):
    """Tỷ lệ công suất near giải thích bằng far trễ `delay` mẫu qua bộ lọc FIR `taps` tap (bình phương tối thiểu miền tần số trên cả đoạn)."""
    n = min(near.size, far.size - delay) if delay >= 0 else near.size
    if n < RATE:
        return 0.0
    d = near[delay:delay + n]
    x = far[:n]
    # hồi quy FIR bằng FFT chia khối đơn giản: dùng bình phương tối thiểu trên ma trận Toeplitz giảm bớt (taps nhỏ)
    L = min(n - taps, RATE * 4)
    if L <= taps:
        return 0.0
    idx = np.arange(taps)[None, :] + np.arange(L)[:, None]
    X = x[idx[:, ::-1]]
    y = d[taps - 1:taps - 1 + L]
    w, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ w
    py = float(np.mean(y * y)) + 1e-9
    return float(max(0.0, 1.0 - np.mean(res * res) / py))


def analyze(far, near):
    k, conf = gcc_phat(near, far)
    rows = []
    seg = RATE * 2
    for a in range(0, min(far.size, near.size) - seg, seg):
        f, d = far[a:a + seg], near[a:a + seg]
        frms = float(np.sqrt(np.mean(f * f)))
        if frms < 30.0:                                      # loa im: không có vọng để đo
            continue
        fa = far[max(0, a - k):a + seg - k] if a - k >= 0 else None
        if fa is None or fa.size != seg:
            continue
        frac = echo_fraction(d, np.concatenate([np.zeros(0, np.float32), fa]), 0)
        rows.append((a / RATE, frms, float(np.sqrt(np.mean(d * d))), frac))
    return k, conf, rows


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    far, near = load(argv[0])
    k, conf, rows = analyze(far, near)
    print("thời lượng %.1fs | tre_ms=%d | doi_chieu=%.1f %s" % (far.size / RATE, round(k * 1000 / RATE), conf, "(tin được)" if conf >= 8 else "(KHÔNG rõ đường vọng)"))
    print("  giây    far_rms  mic_rms  vong_%  erle_db")
    for t, fr, mr, frac in rows:
        print("  %5.1f   %6.0f  %7.0f  %5.0f   %6.1f" % (t, fr, mr, frac * 100, -10 * np.log10(max(1e-3, 1 - frac))))
    if rows:
        print("TRUNG BÌNH vọng còn lại: %.0f%% công suất mic (%d đoạn có tiếng loa)" % (100 * np.mean([r[3] for r in rows]), len(rows)))
    if "--wav" in argv:
        out = argv[argv.index("--wav") + 1]
        for name, v in (("far", far), ("mic", near)):
            with wave.open("%s/%s.wav" % (out, name), "wb") as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE)
                w.writeframes(np.clip(v, -32768, 32767).astype("<i2").tobytes())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
