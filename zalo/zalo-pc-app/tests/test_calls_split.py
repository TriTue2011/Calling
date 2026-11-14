"""Cấu trúc tách luồng cuộc gọi (14/11/2026): calls/{video,voice,incoming,outgoing}.py + identity_{web,pc,mobile}.py.

Kiểm: (1) không còn tên chưa định nghĩa sau khi chuyển mã (lỗi hay gặp nhất khi tách: tên cấp mô-đun còn sót, nhập tương đối cục bộ);
(2) alias trong server.py trỏ đúng hàm ở mô-đun trục; (3) các trục KHÔNG nhập lẫn nhau (video không nhập voice/incoming/outgoing…): mọi liên hệ đi qua `srv()`.
Run: python3 tests/test_calls_split.py"""
import ast
import glob
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
PKG = os.path.join(HERE, "..", "zalo_pc_app")
from zalo_pc_app import server  # noqa: E402

import builtins
def check(path):
    t = ast.parse(open(path).read())
    mod = set(dir(builtins))
    for n in t.body:
        if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)): mod.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            for a in n.names: mod.add((a.asname or a.name).split(".")[0])
        else:
            for x in ast.walk(n):
                if isinstance(x, ast.Name) and isinstance(x.ctx, ast.Store): mod.add(x.id)
                if isinstance(x, (ast.Import, ast.ImportFrom)):
                    for a in x.names: mod.add((a.asname or a.name).split(".")[0])
    bad = set()
    def stored(fn):
        S = set()
        for x in ast.walk(fn):
            if isinstance(x, ast.arg): S.add(x.arg)
            if isinstance(x, ast.Name) and isinstance(x.ctx, (ast.Store, ast.Del)): S.add(x.id)
            if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)): S.add(x.name)
            if isinstance(x, ast.ExceptHandler) and x.name: S.add(x.name)
            if isinstance(x, (ast.Import, ast.ImportFrom)):
                for a in x.names: S.add((a.asname or a.name).split(".")[0])
        return S
    def visit(node, scope):
        for ch in ast.iter_child_nodes(node):
            if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                visit(ch, scope | stored(ch))
            else:
                if isinstance(ch, ast.Name) and isinstance(ch.ctx, ast.Load) and ch.id not in scope: bad.add((ch.id, ch.lineno))
                visit(ch, scope)
    visit(t, mod | set())
    return sorted(bad, key=lambda x: x[1])


AXES = ("video", "voice", "incoming", "outgoing")


def test_no_undefined_names_anywhere():
    bad = {}
    for p in sorted([os.path.join(PKG, "server.py")] + glob.glob(os.path.join(PKG, "calls", "*.py"))):         # chỉ các tệp có mã được chuyển
        b = [x for x in check(p) if x[0] != "__file__"]
        if b:
            bad[os.path.relpath(p, PKG)] = b[:8]
    assert not bad, bad


def test_server_aliases_point_at_axis_modules():
    assert server._start_video.__module__.endswith("calls.video") and server._stop_video.__module__.endswith("calls.video")
    assert server._start_mic.__module__.endswith("calls.voice") and server._watch_dead_media.__module__.endswith("calls.voice")
    assert server._answer_incoming.__module__.endswith("calls.incoming") and server._reject_signals.__module__.endswith("calls.incoming")
    assert server._arm_ring_timer.__module__.endswith("calls.outgoing") and server._send_answerack_async.__module__.endswith("calls.outgoing")
    assert server.VIDEO_SENDERS is server.video_calls.VIDEO_SENDERS and server.AUDIO_SENDERS is server.voice_calls.AUDIO_SENDERS
    mro = [c.__name__ for c in server.AppState.__mro__]
    assert "IncomingCalls" in mro and "OutgoingCalls" in [c.__name__ for c in server.Handler.__mro__]


def test_axes_do_not_import_each_other():
    for ax in AXES:
        tree = ast.parse(open(os.path.join(PKG, "calls", ax + ".py"), encoding="utf-8").read())
        for n in ast.walk(tree):
            mods = []
            if isinstance(n, ast.ImportFrom):
                mods = [(n.module or "")] + [a.name for a in n.names]
            elif isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            for m in mods:
                for other in AXES:
                    if other != ax and m.split(".")[-1] == other:
                        raise AssertionError("%s.py nhập %s: các trục chỉ liên hệ qua srv()" % (ax, other))
                assert m.split(".")[-1] != "server", (ax, "nhập server trực tiếp: dùng srv()")


def test_axis_modules_hold_only_their_axis():
    names = {ax: {n.name for n in ast.parse(open(os.path.join(PKG, "calls", ax + ".py"), encoding="utf-8").read()).body
                  if isinstance(n, (ast.FunctionDef, ast.ClassDef))} for ax in AXES}
    assert {"_start_video", "_send_a2v_async"} <= names["video"] and "_start_mic" not in names["video"]
    assert {"_start_mic", "_start_speaker", "_watch_dead_media"} <= names["voice"] and "_start_video" not in names["voice"]
    assert {"_answer_incoming", "IncomingCalls"} <= names["incoming"] and "_arm_ring_timer" not in names["incoming"]
    assert {"_arm_ring_timer", "OutgoingCalls"} <= names["outgoing"] and "_answer_incoming" not in names["outgoing"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, type(e).__name__, e)
    print("ALL CALLS SPLIT TESTS PASSED" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)
