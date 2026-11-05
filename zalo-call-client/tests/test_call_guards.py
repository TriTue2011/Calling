"""Tests for the real-call secret guard in make_call + 401 dispatcher.

make_call refuses to run without runtime secrets by default
(require_secrets=True). The 401 dispatcher must produce the same
bytes as the per-mode builders.
"""

import pytest

from zalo_call.client import ClientConfig, ZaloCallClient
from zalo_call.errors import MissingSecretsError
from zalo_call.signaling import (
    build_401,
    build_401_mode1,
    build_401_mode2,
)


def test_make_call_refuses_without_secrets(monkeypatch, tmp_path):
    monkeypatch.setenv("ZALO_SECRETS_FILE", str(tmp_path / "nonexistent"))
    for var in ("ZALO_P", "ZALO_Q", "ZALO_SESSION", "ZALO_SRTP_KEY"):
        monkeypatch.delenv(var, raising=False)
    client = ZaloCallClient(ClientConfig("127.0.0.1", 1))
    with pytest.raises(MissingSecretsError):
        client.make_call("thread-1")


def test_make_call_allowed_when_secrets_present(monkeypatch):
    # Provide secrets via config (no socket needed: make_call's
    # send path is stubbed by monkeypatching send_message).
    secrets = {
        "p": "x",
        "q": "y",
        "session": "z",
        "srtp_key": "00" * 30,
        "srtp_suite": "aes_cm_128_hmac_sha1_80",
    }
    client = ZaloCallClient(
        ClientConfig("127.0.0.1", 1, secrets=secrets)
    )
    sent = []
    client.send_message = lambda msg, scheme="gcm": sent.append(msg)
    seq, msg = client.make_call("thread-1")
    assert sent and msg.opcode == 401
    assert seq == 1


def test_make_call_opt_out_for_offline_tests():
    client = ZaloCallClient(
        ClientConfig("127.0.0.1", 1, require_secrets=False)
    )
    client.send_message = lambda msg, scheme="gcm": None
    seq, msg = client.make_call("thread-1")
    assert msg.opcode == 401 and seq == 1


def test_build_401_dispatcher_matches_mode_builders():
    params1, h1 = build_401(
        1, i=1, i5=2, str2="t", i9=3, str3="a", str4="b"
    )
    params1b, h1b = build_401_mode1(
        i=1, i5=2, str2="t", i9=3, str3="a", str4="b", mode=1
    )
    assert (params1, h1) == (params1b, h1b)
    params3, _ = build_401(3, str2="t")
    params3b, _ = build_401_mode1(str2="t", mode=3)
    assert params3 == params3b
    params2, _ = build_401(2, first_str="f", i5=9, str2="s")
    params2b, _ = build_401_mode2(first_str="f", i5=9, str2="s", mode=2)
    assert params2 == params2b


def test_build_401_unknown_mode():
    with pytest.raises(ValueError):
        build_401(9)
