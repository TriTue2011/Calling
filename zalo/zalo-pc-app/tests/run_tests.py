"""Run all offline tests. Usage: python3 tests/run_tests.py"""

import os
import subprocess
import sys

HERE = os.path.dirname(__file__)
FILES = ["test_docker_entrypoint.py", "test_ffmpeg_log.py", "test_aes.py", "test_srtp_pure.py", "test_video_tx.py", "test_devices_and_media.py", "test_deps.py", "test_audio_rx.py", "test_platform_flag.py", "test_api_type_flag.py", "test_qr_client_kind.py", "test_dead_media_watch.py", "test_image_size.py", "test_call_tags.py", "test_calls_split.py", "test_server_main_module.py", "test_incoming_stale.py", "test_sent_file_copy.py", "test_reaction_store.py", "test_video_caption_send.py", "test_audio_gain.py", "test_webui_referrer.py", "test_merge_placeholder.py", "test_group_call_partners.py", "test_hevc_rx.py", "test_video_dump.py", "test_idle_audio.py", "test_call_window_routes.py", "test_webhook_seed_env.py", "test_noui_mode.py", "test_ingress.py", "test_phone_layout.py", "test_docker_packaging.py", "test_media_no_default_camera.py", "test_webhook_media_fields.py", "test_video_view.py", "test_h264_rx.py", "test_client_kind_urls.py", "test_app_password_change.py", "test_call_media_api.py", "test_zca_api.py", "test_stickers.py", "test_voice2text.py", "test_srtp_mode.py", "test_call_audio.py", "test_crypto.py", "test_flow_mock.py",
         "test_logininfo.py", "test_contacts.py", "test_calls.py",
         "test_call_114.py", "test_call_id_counter.py",
         "test_call_11301.py", "test_call_end.py",
         "test_call_ringing.py", "test_call_answered.py",
         "test_call_states.py", "test_call_diag_11301.py",
         "test_call_local_session.py", "test_codec_zca_js.py",
         "test_call_incoming_zca.py",
         "test_media_provider.py", "test_udp_transport.py",
         "test_p2p.py",
         "test_app_auth.py",
         "test_security_h2_thread_auth.py",
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
         "test_services.py", "test_watch_proxy_security.py",
         "test_server_smoke.py",
         "test_security_h1_fonts.py",
         "test_security_h4_session_corrupt.py",
         "test_security_h5_keepalive.py",
         "test_services_f1d1.py"]

# Node checks: app.js syntax + the vm harness for the End button
# (§7m) — the UI fix cannot be covered by the Python suites.
JS_CHECKS = [["node", "--check", "zalo_pc_app/static/app.js"],
             ["node", "tests/test_app_js_end.js"],
             ["node", "tests/test_app_js_sync.js"],
             ["node", "tests/test_app_js_feedrow.js"],
             ["node", "tests/test_app_js_answered.js"],
             ["node", "tests/test_app_js_attach.js"],
             ["node", "tests/test_app_js_filein.js"],
             ["node", "tests/test_app_js_media_bubbles.js"],
             ["node", "tests/test_app_js_callcard_upgrade.js"],
             ["node", "tests/test_app_js_msg_menu.js"], ["node", "tests/test_app_js_video_caption.js"], ["node", "tests/test_app_js_gain.js"], ["node", "tests/test_app_js_album.js"], ["node", "tests/test_app_js_group_call.js"], ["node", "tests/test_app_js_video_fallback.js"], ["node", "tests/test_app_js_video_window.js"], ["node", "tests/test_call_window_js.js"], ["node", "tests/test_app_js_call_window.js"]]


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
