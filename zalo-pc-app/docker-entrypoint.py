#!/usr/bin/env python3
"""Entrypoint: fix the data-dir ownership, prepare the embedded
zalobot sidecar, then drop to user `app` and run the Python server.

The container starts as root so it can chown a host-path volume
(e.g. /opt/zalo:/data, owned by root on the host) to app:app. The
server itself never runs as root: after the chown we drop all
privileges (setgroups/setgid/setuid) and exec the command.

PIVOT addon-embedded (2026-11-05): the same container also runs the
zalobot server (Node, zca-js) as a sidecar on loopback :3000, in
/app/zalobot-embedded (vendored, never modified). The sidecar is
started BEFORE the privilege drop, as a background child that drops
to user `app` itself and restarts node on crash (`while True; sleep
2`), then the parent drops to app and execs the Python server as
PID 1 — exactly as before. The sidecar therefore runs as `app` (not
root) and writes only under /data/zalobot.

Secrets (same self-generate-and-keep pattern as the zalobot
entrypoint.sh): SESSION_SECRET, ZALO_SERVER_ADMIN_PASSWORD and
ZALO_SERVER_API_KEY come from the environment when set; otherwise
they are read from persisted 0600 files under /data/zalobot
(.session_secret / .admin_password / .api_key) or generated once and
kept there. The generated values are exported into the environment
BEFORE the exec, so the Python sidecar client (which reads the same
env) can log in to the sidecar even when the user never set a
password. ZALO_SERVER_ADMIN_USERNAME defaults to "admin".
ZALO_COOKIE_SECURE is left unset (loopback is plain HTTP) and
ZALO_DEV_ENDPOINTS is left unset (dev endpoints stay 404).
Secret VALUES are never printed — only which file was (re)used.

Caveat (documented, not hidden): the sidecar child is supervised by
a forked helper, not by PID 1 — `docker stop` signals PID 1 (the
Python server) only, so the sidecar is stopped by the runtime's
SIGKILL after the stop timeout instead of receiving SIGTERM (its
group-history flush-on-SIGTERM path does not run on stop). Pending
history writes flush every ~100 ms anyway, so at most a fraction of
a second of buffered group history can be lost on stop.
"""

import os
import pwd
import secrets
import subprocess
import sys
import time

APP_USER = "app"
DEFAULT_DATA_DIR = "/data"
ZALOBOT_DIRNAME = "zalobot"
SIDECAR_DIR = "/app/zalobot-embedded"
DEFAULT_COMMAND = ["python3", "-m", "zalo_pc_app.server"]

# (env var, persisted file, generator) — same pattern as the
# zalobot entrypoint.sh: generate once, keep in the data dir.
_SECRETS = (
    ("SESSION_SECRET", ".session_secret",
     lambda: secrets.token_hex(32)),
    ("ZALO_SERVER_ADMIN_PASSWORD", ".admin_password",
     lambda: secrets.token_urlsafe(12)),
    ("ZALO_SERVER_API_KEY", ".api_key",
     lambda: secrets.token_hex(32)),
)


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


def _chown_app(path):
    """Chown one directory to app:app (root only, best-effort)."""
    if os.getuid() != 0:
        return
    try:
        pw = pwd.getpwnam(APP_USER)
    except KeyError:
        return
    try:
        st = os.stat(path)
        if st.st_uid != pw.pw_uid or st.st_gid != pw.pw_gid:
            os.chown(path, pw.pw_uid, pw.pw_gid)
    except OSError as e:
        print("entrypoint: cannot chown %s: %s" % (path, e),
              file=sys.stderr)


def _read_secret_file(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            value = f.read().strip()
        return value or None
    except OSError:
        return None


def _write_secret_file(path, value):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(value + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _prepare_zalobot():
    """Prepare /data/zalobot + sidecar env. Returns the env dict for
    the sidecar (a copy of os.environ, updated), or None when the
    sidecar tree is missing (run without a sidecar, warn loudly)."""
    data_dir = os.environ.get("ZALO_PC_DATA_DIR", DEFAULT_DATA_DIR)
    zalo_dir = os.path.join(data_dir, ZALOBOT_DIRNAME)
    try:
        os.makedirs(zalo_dir, exist_ok=True)
    except OSError as e:
        print("entrypoint: cannot create %s: %s" % (zalo_dir, e),
              file=sys.stderr)
        return None
    _chown_app(zalo_dir)
    # Staging dir for uploads the sidecar downloads over loopback.
    tmp_dir = os.path.join(data_dir, "tmp")
    try:
        os.makedirs(tmp_dir, exist_ok=True)
    except OSError:
        pass
    _chown_app(tmp_dir)
    if not os.path.isfile(os.path.join(SIDECAR_DIR, "server.js")):
        print("entrypoint: WARNING: sidecar missing (%s/server.js "
              "not found) — running without the addon sidecar"
              % SIDECAR_DIR, file=sys.stderr)
        return None
    env = dict(os.environ)
    env.setdefault("ZALO_SERVER_ADMIN_USERNAME", "admin")
    env["DATA_DIRECTORY"] = zalo_dir
    env["PORT"] = "3000"
    generated = []
    for var, filename, make in _SECRETS:
        value = (env.get(var) or "").strip()
        path = os.path.join(zalo_dir, filename)
        if value:
            # Env wins; it is NOT written to disk (only
            # self-generated secrets are persisted, like the
            # zalobot entrypoint.sh).
            env[var] = value
            continue
        value = _read_secret_file(path)
        if value:
            env[var] = value
            print("entrypoint: dung %s da luu tai %s"
                  % (var, path), flush=True)
            continue
        value = make()
        try:
            _write_secret_file(path, value)
        except OSError as e:
            print("entrypoint: cannot persist %s: %s"
                  % (filename, e), file=sys.stderr)
        env[var] = value
        generated.append(var)
        print("entrypoint: tu sinh %s, da luu tai %s (0600)"
              % (var, path), flush=True)
    if "ZALO_SERVER_ADMIN_PASSWORD" in generated:
        # Same discoverability as the zalobot entrypoint.sh: the
        # generated admin password is written to a 0600 file in the
        # data dir (only when it was generated on THIS run — never
        # when the user set it in env).
        info = os.path.join(zalo_dir, "THONG-TIN-DANG-NHAP.txt")
        try:
            with open(info, "w", encoding="utf-8") as f:
                f.write("THONG TIN DANG NHAP ZALO BOT (sidecar)\n")
                f.write("=====================================\n\n")
                f.write("Dia chi : http://<dia-chi-may-chu>:3000\n")
                f.write("Tai khoan: %s\n"
                        % env.get("ZALO_SERVER_ADMIN_USERNAME",
                                  "admin"))
                f.write("Mat khau : %s\n"
                        % env["ZALO_SERVER_ADMIN_PASSWORD"])
                f.write("\nMat khau nay do entrypoint tu sinh vi "
                        "chua dat ZALO_SERVER_ADMIN_PASSWORD.\n")
                f.write("Dang nhap xong nen doi mat khau, hoac dien "
                        "san o compose.\n")
            os.chmod(info, 0o600)
        except OSError as e:
            print("entrypoint: cannot write %s: %s" % (info, e),
                  file=sys.stderr)
    # Export the resolved secrets to THIS process so the Python
    # server (exec'd below) inherits them — that is how the addon
    # client logs in to the sidecar.
    for var, _filename, _make in _SECRETS:
        os.environ[var] = env[var]
    os.environ["ZALO_SERVER_ADMIN_USERNAME"] = env[
        "ZALO_SERVER_ADMIN_USERNAME"]
    return env


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


def _start_sidecar(env):
    """Fork a supervisor child that runs `node server.js` (cwd
    zalobot-embedded) as user `app`, restarting it on crash with a
    2 s pause. Returns the child pid (or None when forking is
    impossible — the server still starts, without a sidecar)."""
    try:
        pid = os.fork()
    except OSError as e:
        print("entrypoint: cannot fork sidecar: %s" % e,
              file=sys.stderr)
        return None
    if pid != 0:
        print("entrypoint: sidecar supervisor started (pid %d)" % pid,
              flush=True)
        return pid
    # Child: never return to the parent's flow.
    try:
        os.setsid()
        _drop_privileges()
        os.chdir(SIDECAR_DIR)
        while True:
            try:
                subprocess.run(["node", "server.js"], env=env)
            except Exception as e:  # noqa: BLE001 - restart loop
                print("entrypoint: sidecar start failed: %s" % e,
                      file=sys.stderr, flush=True)
            print("entrypoint: sidecar exited, restarting in 2s",
                  flush=True)
            time.sleep(2)
    finally:
        os._exit(1)


def main():
    _fix_data_dir()
    env = _prepare_zalobot()
    if env is not None:
        _start_sidecar(env)
    _drop_privileges()
    cmd = sys.argv[1:] or DEFAULT_COMMAND
    # The server module lives under /app in the image; run from there
    # when it exists so `python3 -m zalo_pc_app.server` resolves.
    if os.path.isdir("/app/zalo_pc_app"):
        os.chdir("/app")
    os.execvp(cmd[0], cmd)


if __name__ == "__main__":
    main()
