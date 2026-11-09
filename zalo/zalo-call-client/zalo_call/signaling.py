"""Signaling opcodes, params builders/parsers, and the call state machine.

Opcode layouts are from giai-ma-packet.md §5 (dex analysis).
Notation: g4 = int 4-byte LE, h2+s = string with 2-byte LE length,
b1 = 1 byte, h2+[B = blob with 2-byte LE length.

Known 1-1 call opcodes:
    401 voiceRequestCall      mode 1/3: b1(mode) b1(4) g4 g4 h2+s g4 h2+s h2+s
                              mode 2:   b1(mode) b1(len) s g4 h2+s
    402 voiceRequestAnswer    g4 b1 g4 h2+s x5
    405 cancelCall            params not decoded (opaque)
    407 voiceCallRinging      g4 g4 g4 g4 h2+s
    408 voiceAnswerACK        g4 g4 g4
    409 voiceEndCall          g4 b1 g4 h2+s h2+s h2+s g4
    411 voiceHoldCall         params not decoded (opaque)
    413 voiceResumeCall       params not decoded (opaque)
    416 ZRTP variant          g4 g4 (h2+blob) x7 g4 ; h = 3/2 by flag
    417 change ZRTP           g4 g4 g4 h2 h2 h2
    419 change ZRTP ACK       g4 g4 h2 h2 h2
    425 requestPreCall        g4 g4
    427 answerPreCall         g4 g4 h2+s
    432 sendCoreDataToPartner g4 g4 g4 h2+s
    440 calleeRequestNewServer g4 g4 g4 h2+s
    441 callerAnswerNewServer g4 g4 g4 h2+s

TODO (runtime confirmation): the semantic roles of the individual
fields (which int/string carries the thread id, the call id, etc.)
and the mode 1/2/3 meaning of 401 are NOT confirmed. Builders take
explicit fields; the make_call service maps thread_id to the first
string field of a mode-1 401 and logs that mapping as UNCONFIRMED.
"""

from enum import IntEnum

from zalo_call.params import ParamsReader, ParamsWriter


class Opcode(IntEnum):
    REQUEST_CALL = 401
    REQUEST_ANSWER = 402
    CANCEL = 405
    RINGING = 407
    ANSWER_ACK = 408
    END_CALL = 409
    HOLD = 411
    RESUME = 413
    ZRTP_CALL = 416
    CHANGE_ZRTP = 417
    CHANGE_ZRTP_ACK = 419
    PRE_CALL = 425
    PRE_CALL_ANSWER = 427
    CORE_DATA = 432
    CALLEE_NEW_SERVER = 440
    CALLER_NEW_SERVER = 441


# ---------------------------------------------------------------- builders

def build_401_mode1(
    i: int = 0,
    i5: int = 0,
    str2: str = "",
    i9: int = 0,
    str3: str = "",
    str4: str = "",
    mode: int = 1,
    param_byte: int = 0,
) -> tuple[bytes, int]:
    """401 mode 1/3 params. Returns (params, header_h_byte)."""
    w = ParamsWriter()
    w.byte(mode).byte(4).i32(i).i32(i5).string(str2).i32(i9).string(
        str3
    ).string(str4)
    return w.build(), param_byte


def build_401_mode2(
    first_str: str = "",
    i5: int = 0,
    str2: str = "",
    mode: int = 2,
    param_byte: int = 0,
) -> tuple[bytes, int]:
    """401 mode 2 params (first string uses a raw 1-byte length)."""
    w = ParamsWriter()
    w.byte(mode).string1(first_str).i32(i5).string(str2)
    return w.build(), param_byte


# ---------------------------------------------------------------- 401 modes

# 401 mode summary (layouts from giai-ma-packet.md §5; SEMANTICS
# UNCONFIRMED — which field carries the thread id / call id, and
# what distinguishes modes 1/2/3, must be confirmed against a real
# handshake; see README TODO). Use build_401() to select a mode;
# the mode-1 thread_id mapping in client.make_call (thread_id ->
# str2, the first string field) is a documented guess.
MODE_401_MODE1 = "mode 1/3: b1(mode) b1(4) g4 g4 h2+s g4 h2+s h2+s"
MODE_401_MODE2 = "mode 2: b1(mode) b1(len) s g4 h2+s"


def build_401(mode: int, **kwargs) -> tuple[bytes, int]:
    """Build 401 params for the given mode (1/2/3).

    Mode 1 and 3 share the mode-1 layout; mode 2 uses its own
    layout. Keyword arguments are forwarded to the mode builder
    (mode 1: i, i5, str2, i9, str3, str4, param_byte; mode 2:
    first_str, i5, str2, param_byte).
    """
    if mode in (1, 3):
        return build_401_mode1(mode=mode, **kwargs)
    if mode == 2:
        return build_401_mode2(mode=mode, **kwargs)
    raise ValueError(f"unknown 401 mode: {mode}")


def build_402(
    i1: int = 0,
    b: int = 0,
    i2: int = 0,
    strings: tuple[str, str, str, str, str] = ("", "", "", "", ""),
) -> bytes:
    w = ParamsWriter()
    w.i32(i1).byte(b).i32(i2)
    for s in strings:
        w.string(s)
    return w.build()


def build_407(
    i1: int = 0, i2: int = 0, i3: int = 0, i4: int = 0, s: str = ""
) -> bytes:
    w = ParamsWriter()
    w.i32(i1).i32(i2).i32(i3).i32(i4).string(s)
    return w.build()


def build_408(i1: int = 0, i2: int = 0, i3: int = 0) -> bytes:
    w = ParamsWriter()
    w.i32(i1).i32(i2).i32(i3)
    return w.build()


def build_409(
    i1: int = 0,
    b: int = 0,
    i2: int = 0,
    s1: str = "",
    s2: str = "",
    s3: str = "",
    i3: int = 0,
) -> bytes:
    w = ParamsWriter()
    w.i32(i1).byte(b).i32(i2).string(s1).string(s2).string(s3).i32(i3)
    return w.build()


def build_416(
    i1: int = 0,
    i2: int = 0,
    blobs: tuple[bytes, ...] = (),
    i3: int = 0,
    flag: bool = False,
) -> tuple[bytes, int]:
    """416 ZRTP variant. blobs should be 7 binary blobs; h = 3/2."""
    if len(blobs) != 7:
        raise ValueError(f"416 needs exactly 7 blobs, got {len(blobs)}")
    w = ParamsWriter()
    w.i32(i1).i32(i2)
    for blob in blobs:
        w.blob(blob)
    w.i32(i3)
    return w.build(), 3 if flag else 2


def build_425(i1: int = 0, i2: int = 0) -> bytes:
    w = ParamsWriter()
    w.i32(i1).i32(i2)
    return w.build()


def build_427(i1: int = 0, i2: int = 0, s: str = "") -> bytes:
    w = ParamsWriter()
    w.i32(i1).i32(i2).string(s)
    return w.build()


def build_432(i1: int = 0, i2: int = 0, i3: int = 0, s: str = "") -> bytes:
    w = ParamsWriter()
    w.i32(i1).i32(i2).i32(i3).string(s)
    return w.build()


def build_440_441(i1: int = 0, i2: int = 0, i3: int = 0, s: str = "") -> bytes:
    w = ParamsWriter()
    w.i32(i1).i32(i2).i32(i3).string(s)
    return w.build()


# ---------------------------------------------------------------- parsers

def parse_402(data: bytes) -> dict:
    r = ParamsReader(data)
    out = {"i1": r.i32(), "b": r.byte(), "i2": r.i32()}
    out["strings"] = tuple(r.string() for _ in range(5))
    return out


def parse_407(data: bytes) -> dict:
    r = ParamsReader(data)
    return {
        "i1": r.i32(),
        "i2": r.i32(),
        "i3": r.i32(),
        "i4": r.i32(),
        "s": r.string(),
    }


def parse_408(data: bytes) -> dict:
    r = ParamsReader(data)
    return {"i1": r.i32(), "i2": r.i32(), "i3": r.i32()}


def parse_409(data: bytes) -> dict:
    r = ParamsReader(data)
    return {
        "i1": r.i32(),
        "b": r.byte(),
        "i2": r.i32(),
        "s1": r.string(),
        "s2": r.string(),
        "s3": r.string(),
        "i3": r.i32(),
    }


def parse_425(data: bytes) -> dict:
    r = ParamsReader(data)
    return {"i1": r.i32(), "i2": r.i32()}


def parse_427(data: bytes) -> dict:
    r = ParamsReader(data)
    return {"i1": r.i32(), "i2": r.i32(), "s": r.string()}


def parse_432(data: bytes) -> dict:
    r = ParamsReader(data)
    return {"i1": r.i32(), "i2": r.i32(), "i3": r.i32(), "s": r.string()}


def parse_416(data: bytes) -> dict:
    r = ParamsReader(data)
    out = {"i1": r.i32(), "i2": r.i32()}
    out["blobs"] = tuple(r.blob() for _ in range(7))
    out["i3"] = r.i32()
    return out


_PARSERS = {
    Opcode.REQUEST_ANSWER: parse_402,
    Opcode.RINGING: parse_407,
    Opcode.ANSWER_ACK: parse_408,
    Opcode.END_CALL: parse_409,
    Opcode.ZRTP_CALL: parse_416,
    Opcode.PRE_CALL: parse_425,
    Opcode.PRE_CALL_ANSWER: parse_427,
    Opcode.CORE_DATA: parse_432,
}


def parse_params(opcode: int, data: bytes) -> dict | bytes:
    """Parse known params layouts; unknown opcodes return raw bytes."""
    fn = _PARSERS.get(opcode)
    if fn is None:
        return data
    return fn(data)


# ---------------------------------------------------------------- state machine

IDLE = "idle"
DIALING = "dialing"
RINGING_STATE = "ringing"
ACTIVE = "active"
ENDED = "ended"


class CallStateMachine:
    """1-1 call state machine (caller side + incoming-call events).

    Incoming messages are dispatched by opcode; unknown opcodes are
    reported as ('unknown', opcode) events and otherwise ignored
    (never crash the reader thread).
    """

    def __init__(self) -> None:
        self.state = IDLE
        self.last_zrtp: dict | None = None
        self.last_core_data: dict | None = None
        self.last_relay_request: dict | None = None
        self.events: list[tuple] = []

    def _emit(self, *event) -> None:
        self.events.append(event)

    def sent(self, opcode: int) -> None:
        if opcode == Opcode.REQUEST_CALL:
            self.state = DIALING
            self._emit("dialing")
        elif opcode == Opcode.END_CALL:
            self.state = ENDED
            self._emit("ended", "local")
        elif opcode == Opcode.CANCEL:
            self.state = ENDED
            self._emit("ended", "cancelled")

    def received(self, message) -> tuple | None:
        """Feed one parsed Message; returns the emitted event."""
        opcode = message.opcode
        if opcode == Opcode.RINGING:
            self.state = RINGING_STATE
            event = ("ringing", parse_params(opcode, message.params))
        elif opcode == Opcode.REQUEST_ANSWER:
            self.state = ACTIVE
            event = ("answered", parse_params(opcode, message.params))
        elif opcode == Opcode.ANSWER_ACK:
            event = ("answer_ack", parse_params(opcode, message.params))
        elif opcode == Opcode.END_CALL:
            self.state = ENDED
            event = ("ended", "remote", parse_params(opcode, message.params))
        elif opcode == Opcode.CANCEL:
            self.state = ENDED
            event = ("ended", "cancelled-remote")
        elif opcode == Opcode.ZRTP_CALL:
            self.last_zrtp = parse_params(opcode, message.params)
            event = ("zrtp", self.last_zrtp)
        elif opcode == Opcode.CORE_DATA:
            self.last_core_data = parse_params(opcode, message.params)
            event = ("core_data", self.last_core_data)
        elif opcode in (Opcode.CALLEE_NEW_SERVER, Opcode.CALLER_NEW_SERVER):
            self.last_relay_request = parse_params(opcode, message.params)
            event = ("new_server", opcode, self.last_relay_request)
        elif opcode == Opcode.PRE_CALL:
            event = ("pre_call", parse_params(opcode, message.params))
        elif opcode == Opcode.PRE_CALL_ANSWER:
            event = ("pre_call_answer", parse_params(opcode, message.params))
        else:
            event = ("unknown", opcode)
        self._emit(*event)
        return event
