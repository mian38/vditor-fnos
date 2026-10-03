#!/usr/bin/env python3
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
# test_v411.py —— 验证 v4.0.11 的“卸载清理由设置控制”机制
# 1) server.py：DEFAULT_SETTINGS 含 clear_on_uninstall；_apply_settings 接受布尔、拒绝非布尔；导出含该键
# 2) uninstall_callback：读 @appconf/settings.json 的 clear_on_uninstall 决定删/留
import os, json, sys, shutil, subprocess, tempfile, importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.join(HERE, "vditor-fpk")
SCRIPT = os.path.join(PKG, "cmd", "uninstall_callback").replace("\\", "/")
SERVER = os.path.join(PKG, "app", "server.py").replace("\\", "/")

ok = 0
fail = 0
def check(name, cond, extra=""):
    global ok, fail
    if cond:
        ok += 1
        print("  PASS", name)
    else:
        fail += 1
        print("  FAIL", name, extra)

# ---------- 1) server.py 设置项（直接调用真实代码路径）----------
def load_server_module():
    spec = importlib.util.spec_from_file_location("vditor_server_411", SERVER)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

print("[1] server.py clear_on_uninstall 设置项")
try:
    srv = load_server_module()
    Handler = srv.Handler
    check("DEFAULT_SETTINGS 含 clear_on_uninstall", "clear_on_uninstall" in srv.DEFAULT_SETTINGS)
    # ⚠️ 注释里的假设「_apply_settings 不依赖 self」在 1.1.4 审计后已不成立：
    # 该方法内部会调用 self._apply_int_setting(...) 校验三个整型字段，
    # 传 None 作 self 会抛 AttributeError: 'NoneType' object has no attribute
    # '_apply_int_setting'（1.1.4 之前无此间接依赖，故该测试一直通过）。
    # 这里传一个最小 stub：_apply_settings 用到的 self 仅限这一个方法。
    class _StubSelf:
        _apply_int_setting = Handler._apply_int_setting
    stub = _StubSelf()
    changed, errs = Handler._apply_settings(stub, {"clear_on_uninstall": False})
    check("接受 False 且无错误", (not errs) and (srv.SETTINGS.get("clear_on_uninstall") is False), str(errs))
    changed, errs = Handler._apply_settings(stub, {"clear_on_uninstall": True})
    check("接受 True 且无错误", (not errs) and (srv.SETTINGS.get("clear_on_uninstall") is True), str(errs))
    changed, errs = Handler._apply_settings(stub, {"clear_on_uninstall": "yes"})
    check("非布尔被拒绝", any("布尔" in e for e in errs), str(errs))
    # 导出：用假 self 捕获 _send 的 body，验证导出的 settings 含 clear_on_uninstall
    class FakeSelf:
        def _send(self, code, body, headers=None):
            self.code = code
            self.body = body
    fake = FakeSelf()
    Handler._api_settings_export(fake)
    exp = json.loads(fake.body.decode())
    check("导出 settings 含 clear_on_uninstall", "clear_on_uninstall" in exp.get("settings", {}), str(exp.get("settings")))
except Exception as e:
    check("server 模块可加载并调用", False, repr(e))

# ---------- 2) uninstall_callback 行为 ----------
def run_uninstall(etc_dir, var_dir, settings_obj):
    os.makedirs(etc_dir, exist_ok=True)
    with open(os.path.join(etc_dir, "settings.json"), "w", encoding="utf-8") as f:
        json.dump(settings_obj, f)
    env = dict(os.environ)
    env["TRIM_PKGETC"] = etc_dir.replace("\\", "/")
    env["TRIM_PKGVAR"] = var_dir.replace("\\", "/")
    env["TRIM_TEMP_LOGFILE"] = os.path.join(var_dir, "uninstall.log").replace("\\", "/")
    return subprocess.run(["bash", SCRIPT], env=env, capture_output=True, text=True)

def make_tree(etc, var):
    os.makedirs(etc, exist_ok=True)
    os.makedirs(var, exist_ok=True)
    with open(os.path.join(etc, "pwhash"), "w") as f: f.write("x")
    with open(os.path.join(etc, "folders.json"), "w") as f: f.write("[]")
    docroot = os.path.join(var, "docs")
    os.makedirs(docroot, exist_ok=True)
    with open(os.path.join(docroot, "note.md"), "w") as f: f.write("hi")
    versions = os.path.join(docroot, ".vditor_versions")
    os.makedirs(versions, exist_ok=True)
    with open(os.path.join(versions, "note.2020.md"), "w") as f: f.write("old")
    os.makedirs(os.path.join(var, "uploads"), exist_ok=True)
    with open(os.path.join(var, "uploads", "a.bin"), "w") as f: f.write("b")

print("[2] uninstall_callback 读设置决定删/留")
base = tempfile.mkdtemp(prefix="v411_")
try:
    # 2a) 关闭（默认保留）
    etc1 = os.path.join(base, "etc_keep"); var1 = os.path.join(base, "var_keep")
    make_tree(etc1, var1)
    r1 = run_uninstall(etc1, var1, {"clear_on_uninstall": False})
    check("keep: 脚本成功退出", r1.returncode == 0, r1.stderr)
    check("keep: pwhash 保留", os.path.isfile(os.path.join(etc1, "pwhash")))
    check("keep: 文档保留", os.path.isfile(os.path.join(var1, "docs", "note.md")))
    check("keep: 历史版本保留", os.path.isdir(os.path.join(var1, "docs", ".vditor_versions")))
    check("keep: 上传保留", os.path.isfile(os.path.join(var1, "uploads", "a.bin")))

    # 2b) 开启（彻底清除）
    etc2 = os.path.join(base, "etc_clear"); var2 = os.path.join(base, "var_clear")
    make_tree(etc2, var2)
    r2 = run_uninstall(etc2, var2, {"clear_on_uninstall": True})
    check("clear: 脚本成功退出", r2.returncode == 0, r2.stderr)
    check("clear: pwhash 已删", not os.path.isfile(os.path.join(etc2, "pwhash")))
    # clear 分支执行 rm -rf "$ETC"/*，etc 应用配置被整体清空（含 settings.json 本身）
    check("clear: etc 配置已整体清空", sorted(os.listdir(etc2)) == [], os.listdir(etc2))
    check("clear: 文档保留", os.path.isfile(os.path.join(var2, "docs", "note.md")))
    check("clear: 历史版本已删", not os.path.isdir(os.path.join(var2, "docs", ".vditor_versions")))
    check("clear: 上传已删", not os.path.isfile(os.path.join(var2, "uploads", "a.bin")))

    # 2c) 设置文件缺键 → 默认保留
    etc3 = os.path.join(base, "etc_nodef"); var3 = os.path.join(base, "var_nodef")
    make_tree(etc3, var3)
    r3 = run_uninstall(etc3, var3, {})  # 无 clear_on_uninstall 键
    check("缺键: 默认保留 pwhash", os.path.isfile(os.path.join(etc3, "pwhash")))
finally:
    shutil.rmtree(base, ignore_errors=True)

print()
print("RESULT v411: %d passed, %d failed" % (ok, fail))
sys.exit(1 if fail else 0)
