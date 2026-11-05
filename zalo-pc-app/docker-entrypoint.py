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

import os
import pwd
import sys

APP_USER = "app"
DEFAULT_DATA_DIR = "/data"
DEFAULT_COMMAND = ["python3", "-m", "zalo_pc_app.server"]


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
