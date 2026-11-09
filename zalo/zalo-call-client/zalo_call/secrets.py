"""Runtime secret injection for a real call.

Secrets are NEVER committed, never logged, and never printed by
this module: errors list secret NAMES only, never values.

Sources (checked in this order; first non-empty value wins):
  1. A secrets file mounted at runtime (default path
     /run/secrets/zalo_call, or ZALO_SECRETS_FILE). The file is
     a KEY=VALUE list, one per line; comments (#) and blank
     lines are ignored. The file should be mounted mode 0600
     (Docker secrets / tmpfs) and is gitignored.
  2. Environment variables (ZALO_P, ZALO_Q, ZALO_SESSION,
     ZALO_SRTP_KEY, ZALO_SRTP_SUITE).

What each secret is (values are NOT in this repo):
  ZALO_P / ZALO_Q    The p/q values from the server JSON that
                     seed the transport key (CoreUtility.p/.q).
  ZALO_SESSION       The mobile socket session token (how the
                     talk socket is authenticated, U5).
  ZALO_SRTP_KEY      SRTP master key material, hex-encoded
                     (30 bytes for AES-CM suites, 28/44 for GCM).
  ZALO_SRTP_SUITE    SRTP suite name (default
                     aes_cm_128_hmac_sha1_80).

A real call must refuse to start when required secrets are
missing: use check_call_ready() (returns the list of missing
NAMES) or require_call_secrets() (raises MissingSecretsError
listing those names). No secret value ever reaches a log line.
"""

import os

from zalo_call.errors import MissingSecretsError

ENV_PREFIX = "ZALO_"
DEFAULT_SECRETS_FILE = "/run/secrets/zalo_call"

# name -> (env var, required for a real call)
_SECRET_SPECS = {
    "p": ("ZALO_P", True),
    "q": ("ZALO_Q", True),
    "session": ("ZALO_SESSION", True),
    "srtp_key": ("ZALO_SRTP_KEY", True),
    "srtp_suite": ("ZALO_SRTP_SUITE", False),
}

DEFAULT_SRTP_SUITE = "aes_cm_128_hmac_sha1_80"


def _read_secrets_file(path: str) -> dict:
    values = {}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    except FileNotFoundError:
        return {}
    return values


def load_secrets(secrets_file: str | None = None) -> dict:
    """Load runtime secrets (names -> values, or missing).

    Values are returned only to the caller in memory; this
    function never logs or prints them. The secrets file wins
    over env vars; env vars fill the gaps.
    """
    path = secrets_file or os.environ.get(
        "ZALO_SECRETS_FILE", DEFAULT_SECRETS_FILE
    )
    file_values = _read_secrets_file(path)
    secrets = {}
    for name, (env_var, _required) in _SECRET_SPECS.items():
        if env_var in file_values and file_values[env_var]:
            secrets[name] = file_values[env_var]
        elif os.environ.get(env_var):
            secrets[name] = os.environ[env_var]
    if "srtp_suite" not in secrets:
        secrets["srtp_suite"] = DEFAULT_SRTP_SUITE
    return secrets


def check_call_ready(secrets: dict | None = None) -> list:
    """Return the list of MISSING required secret names.

    Empty list == ready to attempt a real call (secrets present;
    validity is only proven by the call itself). Names only —
    never values.
    """
    secrets = secrets if secrets is not None else load_secrets()
    return [
        name
        for name, (_env, required) in _SECRET_SPECS.items()
        if required and not secrets.get(name)
    ]


def require_call_secrets(secrets: dict | None = None) -> dict:
    """Return secrets, or raise MissingSecretsError (names only)."""
    secrets = secrets if secrets is not None else load_secrets()
    missing = check_call_ready(secrets)
    if missing:
        raise MissingSecretsError(
            "refusing to start a real call: missing runtime secrets: "
            + ", ".join(missing)
            + " (provide via ZALO_* env vars or a mounted secrets file)"
        )
    return secrets


def srtp_key_bytes(secrets: dict) -> bytes:
    """Decode the hex SRTP key material from loaded secrets."""
    raw = secrets.get("srtp_key", "")
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise MissingSecretsError(
            "ZALO_SRTP_KEY is not valid hex"
        ) from exc
    if not key:
        raise MissingSecretsError("ZALO_SRTP_KEY is empty")
    return key
