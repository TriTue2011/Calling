#!/usr/bin/env python3
"""Entrypoint: fix the data-dir ownership, then drop to user `app`.

The container starts as root so it can chown a host-path volume
(e.g. /opt/zalo:/data, owned by root on the host) to app:app. The
server itself never runs as root: after the chown we drop all
privileges (setgroups/setgid/setuid) and exec the command.

Only the data directory itself is chowned (not recursively) and only
when its ownership differs. session.json keeps mode 0600 (the server
enforces it on save). Named volumes keep working: Docker already
copies the image's /data ownership, so the chown is a no-op there.

If the entrypoint itself runs as a non-root user (e.g. --user), or
the app user is missing, it just execs the command as-is. A failed
chown (e.g. read-only mount) only warns; the server then fails
loudly with a clear error if it cannot write.

Pure stdlib on purpose: python:3.12-slim has no guaranteed `su` or
`setpriv`, so the privilege drop is done with os.setgid/os.setuid.
"""

import json
import os
import pwd
import secrets
import sys

APP_USER = "app"
DEFAULT_DATA_DIR = "/data"
DEFAULT_COMMAND = ["python3", "-m", "zalo_pc_app.server"]
# Add-on Home Assistant: Supervisor ghi tuy chon cua nguoi dung o day (chay Docker thuong thi khong co).
ADDON_OPTIONS_FILE = "/data/options.json"
LOGIN_INFO_NAME = "THONG-TIN-DANG-NHAP.txt"
_PW_PREFIX = "Mat khau: "


def _apply_addon_options(env=None, options_path=ADDON_OPTIONS_FILE, data_dir=None):
    """Chay duoi add-on HA: doi tuy chon (username, password) thanh bien moi truong cua app.

    Khong co options.json = chay Docker thuong: khong dong vao gi. Bo trong password thi tu sinh
    mot mat khau, giu lai trong THONG-TIN-DANG-NHAP.txt (0600) cua thu muc du lieu va in ra log,
    de khoi dong lai khong doi. Bien moi truong da dat san thang tuy chon. Tra ve mat khau vua
    sinh/doc lai tu tep (de in log), hoac None."""
    env = os.environ if env is None else env
    try:
        with open(options_path, encoding="utf-8") as fh:
            opts = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(opts, dict):
        return None
    user = str(opts.get("username") or "").strip() or "admin"
    password = str(opts.get("password") or "")
    shown = None
    if not password:
        data_dir = data_dir or env.get("ZALO_PC_DATA_DIR", DEFAULT_DATA_DIR)
        info = os.path.join(data_dir, LOGIN_INFO_NAME)
        try:
            with open(info, encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith(_PW_PREFIX):
                        password = line[len(_PW_PREFIX):].strip()
        except OSError:
            pass
        if not password:
            password = secrets.token_urlsafe(12)
            try:
                os.makedirs(data_dir, exist_ok=True)
                fd = os.open(info, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write("Ten dang nhap: %s\n%s%s\n" % (user, _PW_PREFIX, password))
            except OSError as e:
                print("entrypoint: cannot save %s: %s" % (info, e), file=sys.stderr)
        shown = password
    env.setdefault("ZALO_PC_APP_USER", user)
    env.setdefault("ZALO_PC_APP_PASSWORD", password)
    return shown


def _fix_data_dir():
    data_dir = os.environ.get("ZALO_PC_DATA_DIR", DEFAULT_DATA_DIR)
    try:
        os.makedirs(data_dir, exist_ok=True)
    except OSError as e:
        print("entrypoint: cannot create %s: %s" % (data_dir, e),
              file=sys.stderr)
        return
    if os.getuid() != 0:
        return  # not root: nothing we can (or need to) fix
    try:
        pw = pwd.getpwnam(APP_USER)
    except KeyError:
        print("entrypoint: user %r missing, running as root" % APP_USER,
              file=sys.stderr)
        return
    try:
        st = os.stat(data_dir)
        if st.st_uid != pw.pw_uid or st.st_gid != pw.pw_gid:
            os.chown(data_dir, pw.pw_uid, pw.pw_gid)
    except OSError as e:
        # Warn and continue; the server fails loudly if it cannot write.
        print("entrypoint: cannot chown %s: %s" % (data_dir, e),
              file=sys.stderr)


def _drop_privileges():
    """Drop to user app (only when running as root and user exists)."""
    if os.getuid() != 0:
        return
    try:
        pw = pwd.getpwnam(APP_USER)
    except KeyError:
        return
    os.setgroups([])  # drop supplementary groups
    os.setgid(pw.pw_gid)
    os.setuid(pw.pw_uid)
    os.environ["USER"] = APP_USER
    os.environ["HOME"] = pw.pw_dir


def main():
    generated = _apply_addon_options()
    if generated:
        print("Add-on Zalo Calling: dang nhap WebUI = %s / %s (mat khau tu sinh; doi duoc trong WebUI "
              "hoac dat o tuy chon add-on)" % (os.environ.get("ZALO_PC_APP_USER"), generated),
              flush=True)
    _fix_data_dir()
    _drop_privileges()
    cmd = sys.argv[1:] or DEFAULT_COMMAND
    # The server module lives under /app in the image; run from there
    # when it exists so `python3 -m zalo_pc_app.server` resolves.
    if os.path.isdir("/app/zalo_pc_app"):
        os.chdir("/app")
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
