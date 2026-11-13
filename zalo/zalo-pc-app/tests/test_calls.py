"""Unit tests for the server-side call log (zalo_pc_app/call_log.py).

The call log backs the Calls view + rail in the UI: it records every
outgoing call request (sent/error) and end, keeps only the newest 50,
and holds the single live call. It must never contain secrets
(no zpw_sek / zpw_enk / dkey / session values) — only thread ids,
names and statuses.
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from zalo_pc_app import call_log


def test_record_start_fields():
    log = call_log.CallLog()
    e = log.record_start("c1", "Ban A", "20001", "user")
    assert e["call_id"] == "c1"
    assert e["peer"] == "Ban A"
    assert e["thread_id"] == "20001"
    assert e["type"] == "user"
    assert e["status"] == "sent"
    assert isinstance(e["started_at"], (int, float)) and e["started_at"] > 0
    assert e["ended_at"] is None
    assert e["detail"] == ""


def test_snapshot_newest_first_and_active():
    log = call_log.CallLog()
    log.record_start("c1", "Ban A", "20001", "user")
    time.sleep(0.01)
    log.record_start("g1", "Nhom X", "30001", "group")
    snap = log.snapshot()
    assert [c["call_id"] for c in snap["calls"]] == ["g1", "c1"]
    assert snap["active"]["call_id"] == "g1"


def test_second_start_closes_first():
    log = call_log.CallLog()
    log.record_start("c1", "Ban A", "20001", "user")
    log.record_start("c2", "Ban B", "20002", "user")
    snap = log.snapshot()
    by_id = {c["call_id"]: c for c in snap["calls"]}
    assert by_id["c1"]["status"] == "ended"
    assert by_id["c1"]["ended_at"] is not None
    assert by_id["c2"]["status"] == "sent"
    assert snap["active"]["call_id"] == "c2"


def test_record_end_and_unknown_id():
    log = call_log.CallLog()
    log.record_start("c1", "Ban A", "20001", "user")
    assert log.record_end("nope") is None
    e = log.record_end("c1")
    assert e["status"] == "ended" and e["ended_at"] is not None
    assert log.snapshot()["active"] is None
    # Ending an already-ended call is a no-op (returns None);
    # the first ended_at stands.
    first_end = e["ended_at"]
    assert log.record_end("c1") is None
    assert log.snapshot()["calls"][0]["ended_at"] == first_end


def test_record_error():
    log = call_log.CallLog()
    e = log.record_error("c1", "Ban A", "20001", "user", "timeout")
    assert e["status"] == "error"
    assert e["detail"] == "timeout"
    assert log.snapshot()["active"] is None


def test_cap_keeps_newest_50():
    log = call_log.CallLog()
    for i in range(55):
        log.record_start("c%02d" % i, "P", str(i), "user")
    snap = log.snapshot()
    assert len(snap["calls"]) == 50
    assert snap["calls"][0]["call_id"] == "c54"
    assert snap["calls"][-1]["call_id"] == "c05"


def test_no_secrets_in_snapshot():
    log = call_log.CallLog()
    log.record_start("c1", "Ban A", "20001", "user")
    log.record_error("c2", "Nhom X", "30001", "group", "zpw_type 602")
    blob = json.dumps(log.snapshot())
    for secret in ("zpw_sek", "zpw_enk", "zpw_kt", "dkey", "sek-test",
                   "enk-test", "session_key"):
        assert secret not in blob, secret
    allowed = {"call_id", "peer", "thread_id", "type", "status",
               "started_at", "ended_at", "detail", "request_sent",
               "request_detail", "answered_at", "answer_source",
               "diag", "direction"}      # direction: "in"/"out" (khong phai bi mat)
    # "answered_at" (epoch seconds) and "answer_source" ("api" /
    # "media") are not secrets — the 2026-11-08 answered fix adds
    # them to every entry, so the allow-list grows with them.
    # "diag" (2026-11-08 call diagnostics: step1/step2 status,
    # relay addresses, session presence + length) is shapes and
    # counts only — never a session or token value.
    for c in log.snapshot()["calls"]:
        assert set(c) == allowed, set(c)


def main():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:  # noqa: BLE001 - report, keep running
            failed += 1
            print("FAIL %s: %r" % (t.__name__, exc))
    print("%d/%d tests passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
