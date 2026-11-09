"""CLI for zalo_call.

Real call mode requires a mobile socket session + p/q values, which
this package deliberately does NOT supply (see README). The CLI
therefore offers only:
  --help        usage
  --self-check  offline verification: Req build + checksum + GCM
                round-trip + Opus round-trip (if libopus present)
                + SRTP round-trip (if libsrtp2 present).
                Exits 0 when every offline check passes.
  --check-call-ready
                report whether the runtime secrets for a real call
                are present (names only, never values). Exits 0
                when ready, 2 when secrets are missing.
"""

import argparse
import sys

from zalo_call.req import Message
from zalo_call.secrets import check_call_ready
from zalo_call.transport import gcm_decrypt, gcm_encrypt


def self_check() -> int:
    failures = []

    # 1. Req build/parse + checksum.
    msg = Message(
        version=2,
        need_ack=1,
        msg_type=1,
        seq_id=42,
        src_id=7,
        src_type=1,
        opcode=401,
        sub_cmd=0,
        params=b"\x01\x02\x03",
    )
    try:
        parsed = Message.parse(msg.build())
        assert parsed.opcode == 401 and parsed.seq_id == 42
        assert parsed.params == b"\x01\x02\x03"
        print("PASS req build/parse + checksum")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"req: {exc}")
        print(f"FAIL req: {exc}")

    # 2. GCM round-trip with a test key.
    key = bytes(range(32))
    try:
        frame = gcm_encrypt(key, 2, b"hello")
        wire_type = frame[4]
        inner, plain = gcm_decrypt(key, wire_type, frame[5:])
        assert inner == 2 and plain == b"hello"
        print("PASS gcm round-trip")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"gcm: {exc}")
        print(f"FAIL gcm: {exc}")

    # 3. Opus round-trip (skipped, not failed, when libopus is absent).
    try:
        from zalo_call.audio import OpusCodec

        codec = OpusCodec()
        pcm = b"\x00\x10" * 960
        decoded = codec.decode(codec.encode(pcm))
        assert len(decoded) == 1920
        codec.close()
        print("PASS opus round-trip")
    except Exception as exc:  # noqa: BLE001
        if "libopus" in str(exc) or "OpusUnavailable" in type(exc).__name__:
            print("SKIP opus (libopus not present)")
        else:
            failures.append(f"opus: {exc}")
            print(f"FAIL opus: {exc}")

    # 4. SRTP round-trip with a test key (skipped when libsrtp2
    #    is absent; the Dockerfile installs libsrtp2-1).
    try:
        import struct

        from zalo_call.srtp import SrtpSession

        key = bytes(range(30))
        with SrtpSession(key) as sess:
            rtp = struct.pack(">BBHII", 0x80, 111, 1, 960, 7) + b"opus"
            assert sess.unprotect(sess.protect(rtp)) == rtp
        print("PASS srtp round-trip (aes_cm_128_hmac_sha1_80)")
    except Exception as exc:  # noqa: BLE001
        if "libsrtp" in str(exc) or "SrtpUnavailable" in type(exc).__name__:
            print("SKIP srtp (libsrtp2 not present)")
        else:
            failures.append(f"srtp: {exc}")
            print(f"FAIL srtp: {exc}")

    if failures:
        print(f"self-check FAILED: {len(failures)} failure(s)")
        return 1
    print("self-check OK (offline checks only; no real call attempted)")
    return 0


def check_ready() -> int:
    missing = check_call_ready()
    if missing:
        print("not ready for a real call; missing secrets: " + ", ".join(missing))
        print("(names only — provide via ZALO_* env vars or a mounted secrets file)")
        return 2
    print("ready for a real call (secrets present; validity unproven until a call)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m zalo_call",
        description=(
            "Zalo voice-call signaling client (signaling complete per "
            "disassembly spec; real session + p/q still TODO). "
            "There is no real-call mode: a mobile socket session and "
            "p/q values are required and must be supplied by the "
            "outer layer, never by this CLI."
        ),
    )
    parser.add_argument(
        "--self-check",
        action="store_true",
        help="run offline verification checks and exit",
    )
    parser.add_argument(
        "--check-call-ready",
        action="store_true",
        help="report whether runtime secrets for a real call are present",
    )
    args = parser.parse_args(argv)
    if args.self_check:
        return self_check()
    if args.check_call_ready:
        return check_ready()
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
