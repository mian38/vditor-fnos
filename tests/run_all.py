#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""统一测试入口：跑完 tests/ 下的全部测试并汇总结果。

用法：
    python3 tests/run_all.py              # 跑核心套件（默认，约 1 分钟）
    python3 tests/run_all.py --all        # 含大文件压力测试（较慢）
    python3 tests/run_all.py --list       # 列出全部用例

约定（务必遵守）：
    本轮新增的测试**必须**放进 tests/ 目录，并在本文件登记，
    不要在仓库根目录或 vditor-fpk/ 下另建 test_*.py —— 散落的测试无法被统一执行，
    也很容易在重构时漏跑。详见 CONTRIBUTING.md「测试」。
"""
import os
import subprocess
import sys
import time

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(TESTS_DIR)

# (文件名, 是否属于核心套件, 说明)
CASES = [
    ("test_version.py",       True,  "版本号一致性（manifest / server.py）"),
    ("test_pkg.py",           True,  "打包输入完整性与产物结构"),
    ("test_security.py",      True,  "纯函数级安全防御（路径穿越、XFF、PBKDF2 等）"),
    ("test_cli.py",           True,  "cmd/ 生命周期脚本语法"),
    ("test_frontend.py",      True,  "前端静态一致性 + 访问层守卫 + 工具栏裁剪防护"),
    ("test_v141_net.py",      True,  "IPv6 双栈、公网访问策略、单分区、渲染模式、绑定隔离"),
    ("test_rawmode_v14.js",   True,  "纯文本模式解耦 / 渲染模式 / 二次确认（vm 驱动真实脚本）"),
    ("test_core.py",          True,  "端到端：拉起真实服务跑完整业务流"),
    ("test_e2e_http.py",      True,  "端到端：按浏览器调用顺序驱动 HTTP 接口"),
    ("test_perf.py",          False, "性能基线"),
    ("test_stress_largefile.py", False, "大文件（4MB/15MB）压力与逐字节校验"),
]

def _node():
    """Node 可执行文件：环境变量 → PATH → node（由 CI 的 setup-node 提供）。"""
    import shutil
    return os.environ.get("VDITOR_NODE") or shutil.which("node") or "node"


NODE = _node()


def _run_one(path):
    t0 = time.time()
    is_js = path.endswith(".js")
    cmd = [NODE, path] if is_js else [sys.executable, path]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           cwd=ROOT, timeout=900)
        out = (p.stdout or "") + (p.stderr or "")
        ok = p.returncode == 0
        # 取末行 RESULT/结果 作为摘要
        summary = ""
        for line in reversed(out.strip().splitlines()):
            if "RESULT" in line or line.startswith("结果"):
                summary = line.strip()
                break
        return ok, summary or ("退出码 %d" % p.returncode), time.time() - t0, out
    except subprocess.TimeoutExpired:
        return False, "超时（>900s）", time.time() - t0, ""
    except Exception as e:                       # noqa: BLE001
        return False, "异常：%s" % e, time.time() - t0, ""


def main():
    argv = sys.argv[1:]
    if "--list" in argv:
        print("用例清单：")
        for name, core, desc in CASES:
            print("  [%s] %-26s %s" % ("核心" if core else "扩展", name, desc))
        return 0

    run_all = "--all" in argv
    cases = [c for c in CASES if run_all or c[1]]

    print("=" * 68)
    print(" Vditor 测试套件（根目录：%s）" % ROOT)
    print(" 模式：%s（%d 个用例）" % ("全部" if run_all else "核心", len(cases)))
    print("=" * 68)

    results = []
    t_all = time.time()
    for name, _core, desc in cases:
        path = os.path.join(TESTS_DIR, name)
        if not os.path.isfile(path):
            print("  SKIP  %-26s 文件不存在" % name)
            results.append((name, None, desc, 0.0))
            continue
        print("  RUN   %-26s %s" % (name, desc))
        ok, summary, dt, _out = _run_one(path)
        print("        %s（%.1fs）" % ("通过" if ok else "失败", dt))
        results.append((name, ok, desc, dt))

    # ---- 汇总 ----
    passed = sum(1 for _n, ok, _d, _t in results if ok is True)
    failed = sum(1 for _n, ok, _d, _t in results if ok is False)
    skipped = sum(1 for _n, ok, _d, _t in results if ok is None)

    print("=" * 68)
    for name, ok, _desc, dt in results:
        mark = "  通过  " if ok else ("  失败  " if ok is False else "  跳过  ")
        print("%s%-26s %6.1fs" % (mark, name, dt))
    print("-" * 68)
    print("合计：通过 %d，失败 %d，跳过 %d，总耗时 %.1fs"
          % (passed, failed, skipped, time.time() - t_all))
    print("=" * 68)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
