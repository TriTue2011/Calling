"""No-account probe for getServerInfo (code 11323).

The real PC client calls getServerInfo before login and updates its
apiType/apiVersion from the response (bundle: `a.type && a.client_version
? (Je.apiType=a.type, Je.apiVersion=a.client_version, ...)`). Our app
sends zpw_ver=695 / zpw_type=30 (bundle config: apiVersion 695,
apiType "embed"===__ZaBUNDLENAME__?31:30, bundle "compact-app-pc"
-> 30; see bao-cao.md 7d); if the server now reports different
values, post-login calls (friends/groups) fail with 602
"zpw_type missing or incorrect".

What it does (and does NOT do):
  - Sends ONE getServerInfo request with a fresh random device id,
    no account, no credentials, no session cookie.
  - Prints ONLY: error_code and the whitelisted config fields
    (type, client_version, app_version) plus the top-level data keys.
    It never prints tokens, cookies, or any secret, and it never
    saves anything to disk.
  - It does NOT log in, poll, or touch any account.

Usage:
  python3 probe_serverinfo.py
"""

import json
import os
import sys
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from zalo_pc_app.crypto import signkey  # noqa: E402
from zalo_pc_app import protocol  # noqa: E402


def main():
    device_id = "probe-" + uuid.uuid4().hex[:16]
    params = {
        "imei": device_id,
        "type": protocol.API_TYPE,
        "client_version": protocol.API_VERSION,
        "computer_name": "probe",
        "sp_mtn": -1,
        "bkt": -1,
    }
    params["signkey"] = signkey("getserverinfo", params)
    url = protocol.build_url(protocol.AUTH_DOMAIN,
                             "/api/login/getServerInfo", params)
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "zalo-pc-qr/1.0")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status, payload = resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8"))
        except Exception:
            payload = {}
        status = e.code
    except Exception as e:  # network / timeout / parse
        print(json.dumps({"outcome": "network_error",
                          "error": str(e)}, indent=2))
        return 3
    data = payload.get("data") if isinstance(payload, dict) else None
    out = {
        "http_status": status,
        "error_code": payload.get("error_code"),
        "error_message": payload.get("error_message", ""),
        "data_keys": sorted(data.keys()) if isinstance(data, dict) else [],
    }
    if isinstance(data, dict):
        for key in ("type", "client_version", "app_version"):
            if key in data:
                out[key] = data[key]
    out["outcome"] = ("ok" if payload.get("error_code") == 0
                      else "server_rejected")
    print(json.dumps(out, indent=2))
    return 0 if out["outcome"] == "ok" else 2


if __name__ == "__main__":
    raise SystemExit(main())
