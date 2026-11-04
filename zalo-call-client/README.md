# Zalo voice-call signaling client

Pure-Python implementation of the Zalo VoIP signaling protocol,
reverse-engineered from static analysis of the Zalo Android app
(libznetwork) and packet captures. **This is a signaling client
only — it does not make a real call yet.** The pieces that are
still missing for a real call are listed explicitly below; nothing
here pretends otherwise.

## What is implemented (verified by offline tests)

- **Wire framing**: `[u32 L][u8 wire_type][payload]`, `L = bytes after
  the u32`, with an incremental `FrameReader` (OOM cap, malformed
  frames rejected).
- **Req/Comm/Ret messages**: 23/36/27-byte headers, little-endian,
  strict `dataSize` checks. Req checksum confirmed two-way:
  `sum(needAck, msgType, seqId, srcId, srcType, opcode as signed
  halfword, subCmd) XOR 0x6ce7daa0`. Comm/Ret checksum uses the Req
  formula as a placeholder (their extended checksum is not yet
  mapped — TODO).
- **Params XOR layer**: two-stage XOR with the E2E srcId and the
  total message length; skipped for handshake subCmds 0xa1/0xa3 and
  for version != 2; NULL key passes through unchanged.
- **Transport schemes**: plaintext (wire <= 2), AES-GCM-256
  (wire 3..4, 12-byte nonce, 16-byte tag, old-key retry for
  wire <= 4), ProvV21 ECDH+GCM (wire >= 5, trailing A/B 32-byte
  fields), CBCXor+MD5 fallback frame layout (GCM tried first).
- **Key management**: `KeySet` mirroring the native model — k1
  verbatim, transport key = Base64Decode(k2), old-key rotation,
  auth key-set name = peer `host:port`, XOR key defaulting to k1
  (a working hypothesis, NOT runtime-confirmed).
- **Signaling**: opcodes 401/402/405/407/408/409/411/413/416/417/425/
  427/432/440/441 with the dex-derived params layouts, plus a
  1-1 call state machine (IDLE → DIALING → RINGING → ACTIVE →
  ENDED) that never crashes on unknown opcodes.
- **Client**: TCP socket (+ optional HTTP CONNECT proxy), sender
  thread, reader thread → state machine + callback + inbound queue,
  auto-incrementing seq ids, handshake frames, Prov handshake,
  `make_call(thread_id, tts_text)`.
- **Media packet header**: ZRTP relay packet header (type 03/04,
  0x90, flag, per-call byte, 1-byte wrapping seq, big-endian
  timestamp +960 per 20 ms frame).
- **Opus codec**: real encode/decode via ctypes `libopus.so`
  (VOIP, 48 kHz, mono, 20 ms frames). No opuslib needed.
- **Abstract audio I/O**: `MicSource`/`SpeakerSink` interfaces with
  file, silent, null, and TTS-backed implementations; `AudioPipeline`
  wires mic → Opus → protect → network and back.

## What is NOT done (TODO, blocking a real call)

1. **p/q values** (`CoreUtility.p` / `.q`): the server JSON values
   that seed the transport key. No real values are in this repo and
   none may be committed.
2. **Mobile socket session**: how the talk socket is authenticated
   (U5). The client takes a host/port and assumes a session.
3. **Prov key derivation**: the shared-secret → GCM key KDF is not
   documented in the disassembly; it is an injectable hook that
   raises `NotImplementedError` by default.
4. **Prov A/B field identities**: the two trailing 32-byte fields
   are caller-supplied parameters, not interpreted here.
5. **First Prov message content** (U4): caller-supplied; not invented.
6. **CBCXor construction**: exact cipher + which header bytes feed
   the MD5 are not documented; the frame layout is implemented
   with an injectable cipher hook (default: raise).
7. **SRTP**: `SrtpSession` raises `SrtpUnavailable` by design.
   Media payloads are opaque until a portable x86 SRTP library is
   wired in. Test-only identity protect/unprotect functions are
   never real SRTP.
8. **401 field semantics**: which field carries the thread id, and
   the meaning of 401 modes 1/2/3, are unconfirmed. `make_call`
   maps thread_id to the first string field of a mode-1 401 and
   logs that mapping as UNCONFIRMED.
9. **Real-world test**: no test against a real server has been run.
   All tests are offline. Any future real test must use a secondary
   account only, never a primary account.

## Layout

```
zalo_call/
  errors.py        exception hierarchy
  params.py        LE int / length-prefixed string / blob codecs
  req.py           Req/Comm/Ret build + parse + checksum
  xor_params.py    params XOR layer
  keyset.py        KeySet (k1/k2/transport/old/xor-key/prov map)
  transport.py     framing + plaintext/GCM/Prov/CBC schemes
  signaling.py     opcode layouts + call state machine
  client.py        TCP client, threads, handshake, call API
  audio.py         audio I/O, Opus codec, SRTP stub, media packets
  __main__.py      CLI: --help / --self-check (offline only)
tests/             offline pytest suite (no network, no accounts)
Dockerfile         python:3.12-slim + ffmpeg + libopus0
```

## Usage

```python
from zalo_call.client import ClientConfig, ZaloCallClient
from zalo_call.keyset import KeySet

# All session/key material is injected by the caller, never read
# from files or environment by this package.
cfg = ClientConfig(
    talk_host="...", talk_port=0,  # supplied by the outer layer
    keyset=KeySet(k1="...", k2="..."),
    src_id=0,
)
client = ZaloCallClient(cfg, on_message=lambda msg, ev: print(ev))
client.connect()
client.perform_handshake()  # 0xa1 then 0xa3 plaintext frames
seq, msg = client.make_call(thread_id="...", tts_text="...")
```

## Test

```bash
python -m pytest -q
```

All tests are offline (socketpair, in-memory keys, synthetic
vectors). A green suite means the wire format is self-consistent
with the disassembly spec — it does NOT mean a real call works.

## Security

No credentials, keys, tokens, sessions, or account identifiers are
stored in this repository. The package never reads secrets from
files or environment variables; the caller injects them at runtime.
