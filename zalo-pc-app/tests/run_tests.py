"""Run all offline tests. Usage: python3 tests/run_tests.py"""

import os
import subprocess
import sys

HERE = os.path.dirname(__file__)
FILES = ["test_aes.py", "test_crypto.py", "test_flow_mock.py",
         "test_logininfo.py", "test_contacts.py", "test_calls.py",
         "test_call_114.py", "test_call_11301.py", "test_call_end.py",
         "test_call_ringing.py", "test_call_answered.py",
         "test_call_states.py", "test_call_diag_11301.py",
         "test_call_local_session.py",
         "test_media_provider.py", "test_udp_transport.py",
         "test_p2p.py",
         "test_app_auth.py",
         "test_contacts_cache_429.py", "test_contacts_stale_swr.py",
         "test_view_decision.py", "test_webhooks.py", "test_chat.py",
         "test_incoming.py",
         "test_sync_start.py",
         "test_sync_cursor.py", "test_message_store.py",
         "test_ctrl_webhooks.py",
         "test_file_ctrl_restart.py", "test_qr_auto_endpoints.py",
         "test_poll_json_error.py",
         "test_file_incoming.py",
         "test_voice_transcode.py", "test_voice_112.py",
         "test_voice_async_114.py",
         "test_photo_silent.py", "test_photo_group.py",
         "test_services.py", "test_server_smoke.py"]

# Node checks: app.js syntax + the vm harness for the End button
# (§7m) — the UI fix cannot be covered by the Python suites.
JS_CHECKS = [["node", "--check", "zalo_pc_app/static/app.js"],
             ["node", "tests/test_app_js_end.js"],
             ["node", "tests/test_app_js_sync.js"],
             ["node", "tests/test_app_js_feedrow.js"],
             ["node", "tests/test_app_js_answered.js"],
             ["node", "tests/test_app_js_attach.js"],
             ["node", "tests/test_app_js_filein.js"]]


def main():
    failed = []
    for name in FILES:
        path = os.path.join(HERE, name)
        print("=== %s ===" % name)
        # -u (unbuffered stdout): test e2e mo poller sync/ctrl la
        # daemon thread in log ra stdout; neu process thoat trong
        # luc mot thread dang in thi interpreter chet voi 'Fatal
        # Python error: _enter_buffered_busy ... at interpreter
        # shutdown' (do BufferedWriter cua stdout). Do 07/11 tren
        # test_chat.py chay rieng: buffered 4/6 lan abort (exit
        # 134), -u 6/6 sach. Test khong can buffer stdout; -u
        # khong doi ket qua assert (redirect_stdout sang StringIO
        # van nhu cu).
        p = subprocess.run([sys.executable, "-u", path],
                           cwd=os.path.join(HERE, ".."))
        if p.returncode != 0:
            failed.append(name)
    for cmd in JS_CHECKS:
        print("=== %s ===" % " ".join(cmd))
        p = subprocess.run(cmd, cwd=os.path.join(HERE, ".."))
        if p.returncode != 0:
            failed.append(" ".join(cmd))
    if failed:
        print("FAILED:", failed)
        return 1
    print("ALL TEST SUITES PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
