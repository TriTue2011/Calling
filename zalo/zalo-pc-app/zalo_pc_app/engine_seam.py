"""Media-engine seam (phase 2 integration point).

This module does NOT implement audio. The parallel mobile-Linux agent
owns the native media engine (SRTP via libsrtp2, Opus, PCM streaming
for HA/R1). This file is the contract between the app service and that
engine, so neither side re-implements the other.

What signaling gives the engine (from the voicecall handshake):
  rtcp_address, rtp_address  relay addresses from the 416/request step
  session                    call session token from signaling
  extend_data                opaque relay/session blob (subCommand=3)
  codec                      codec list string from requestcall
  call_id, peer_id           call identity

What the engine must provide back:
  attach(call)   -> object with:
      .start()            begin media (relay connect + SRTP + Opus)
      .stop()             end media
      .pcm_out_frames()   iterator/generator of bytes: PCM 16 kHz mono
                          16-bit LE (the format HA/R1 consume)
      .send_pcm(bytes)    push microphone PCM frames into the call
  status() -> {"attached": bool, "detail": str}

Until an engine is attached, the call screen can signal (dial, answer,
end) but cannot carry voice; /api/engine/status reports that plainly
instead of pretending audio works.
"""


class EngineNotAttached(Exception):
    pass


class MediaEngineSeam:
    """Placeholder seam. Replace `engine` with the real engine object
    (see contract above) when the parallel agent's engine lands."""

    def __init__(self):
        self.engine = None

    def attach(self, engine):
        self.engine = engine

    def status(self):
        if self.engine is None:
            return {"attached": False,
                    "detail": "Chua co engine tieng (giai doan 2). "
                              "Goi di van signaling duoc, chua co tieng."}
        try:
            return {"attached": True, "detail": str(self.engine.status())}
        except Exception as exc:  # noqa: BLE001 - seam must not crash UI
            return {"attached": False, "detail": "engine error: %s" % exc}

    def start_call_media(self, call_info):
        if self.engine is None:
            raise EngineNotAttached(
                "no media engine attached (phase 2); signaling only")
        return self.engine.attach(call_info)


    def attach_pc_media(self, record):
        """Attach a `PcMediaEngine` for a transport started by
        `media_endpoints` (phase 2, stage 2). `record` is the
        memory-only dict from `MediaEndpoints.active_record`
        ({"transport", ...}). Best-effort: returns True when the
        engine is attached and its PCM callback registered, False
        otherwise — never raises, so a media failure cannot break
        signaling. The transport keeps running (handshake /
        relay) even when this returns False; voice just stays
        unwired until hooks are available."""
        if not record or record.get("transport") is None:
            return False
        try:
            from . import pc_media
            engine = pc_media.PcMediaEngine(record["transport"])
            engine.attach({"call_id": record.get("call_id"),
                           "callee_id": record.get("callee_id"),
                           "codec": record.get("codec")})
            engine.start()
            self.engine = engine
            return True
        except Exception:  # noqa: BLE001 - media must not break calls
            return False

    def stop_media(self):
        """Stop the attached media engine, if any. Best-effort,
        never raises. Detaches the engine so /api/engine/status
        reports "no engine" again after the call ends."""
        engine = self.engine
        self.engine = None
        if engine is not None:
            try:
                engine.stop()
            except Exception:  # noqa: BLE001 - stop is best-effort
                pass


SEAM = MediaEngineSeam()
