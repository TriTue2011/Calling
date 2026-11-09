"""Tests for runtime secret injection.

No real secret values are used: all fixtures are synthetic
placeholders. Tests assert NAMES appear in errors, never values.
"""

import os

import pytest

from zalo_call.errors import MissingSecretsError
from zalo_call.secrets import (
    check_call_ready,
    load_secrets,
    require_call_secrets,
    srtp_key_bytes,
)

FAKE = {
    "ZALO_P": "fake-p",
    "ZALO_Q": "fake-q",
    "ZALO_SESSION": "fake-session",
    "ZALO_SRTP_KEY": "00" * 30,
}


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for var in list(FAKE) + ["ZALO_SRTP_SUITE", "ZALO_SECRETS_FILE"]:
        monkeypatch.delenv(var, raising=False)
    yield


def test_missing_all_reported_by_name(monkeypatch, tmp_path):
    monkeypatch.setenv("ZALO_SECRETS_FILE", str(tmp_path / "nonexistent"))
    missing = check_call_ready()
    assert missing == ["p", "q", "session", "srtp_key"]


def test_env_provides_all(monkeypatch, tmp_path):
    monkeypatch.setenv("ZALO_SECRETS_FILE", str(tmp_path / "nonexistent"))
    for var, val in FAKE.items():
        monkeypatch.setenv(var, val)
    assert check_call_ready() == []
    secrets = require_call_secrets()
    assert secrets["p"] == "fake-p"
    assert secrets["srtp_suite"] == "aes_cm_128_hmac_sha1_80"


def test_secrets_file_provides_values(monkeypatch, tmp_path):
    f = tmp_path / "zalo_call"
    f.write_text(
        "# comment line\n"
        "ZALO_P=file-p\n"
        "ZALO_Q=file-q\n"
        "ZALO_SESSION=file-session\n"
        "ZALO_SRTP_KEY=" + "ab" * 30 + "\n"
    )
    monkeypatch.setenv("ZALO_SECRETS_FILE", str(f))
    assert check_call_ready() == []
    assert load_secrets()["q"] == "file-q"


def test_file_wins_over_env(monkeypatch, tmp_path):
    f = tmp_path / "zalo_call"
    f.write_text(
        "ZALO_P=file-p\nZALO_Q=file-q\n"
        "ZALO_SESSION=file-session\nZALO_SRTP_KEY=" + "cd" * 30 + "\n"
    )
    monkeypatch.setenv("ZALO_SECRETS_FILE", str(f))
    monkeypatch.setenv("ZALO_P", "env-p")
    assert load_secrets()["p"] == "file-p"


def test_require_raises_with_names_only(monkeypatch, tmp_path):
    monkeypatch.setenv("ZALO_SECRETS_FILE", str(tmp_path / "nonexistent"))
    monkeypatch.setenv("ZALO_P", "fake-p")
    with pytest.raises(MissingSecretsError) as exc:
        require_call_secrets()
    msg = str(exc.value)
    assert "q" in msg and "session" in msg and "srtp_key" in msg
    assert "fake-p" not in msg  # no values in the error


def test_srtp_key_hex_decode():
    assert srtp_key_bytes({"srtp_key": "00ff" * 15}) == b"\x00\xff" * 15
    with pytest.raises(MissingSecretsError):
        srtp_key_bytes({"srtp_key": "not-hex!!"})


def test_partial_missing_listed(monkeypatch, tmp_path):
    monkeypatch.setenv("ZALO_SECRETS_FILE", str(tmp_path / "nonexistent"))
    monkeypatch.setenv("ZALO_P", "x")
    monkeypatch.setenv("ZALO_Q", "y")
    assert check_call_ready() == ["session", "srtp_key"]


def test_env_leak_guard(monkeypatch, tmp_path):
    # load_secrets must not print anything; just assert it returns
    # a plain dict with no extra keys.
    monkeypatch.setenv("ZALO_SECRETS_FILE", str(tmp_path / "nonexistent"))
    for var, val in FAKE.items():
        monkeypatch.setenv(var, val)
    secrets = load_secrets()
    assert set(secrets) == {"p", "q", "session", "srtp_key", "srtp_suite"}
