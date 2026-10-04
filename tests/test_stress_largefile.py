#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""test_stress_largefile.py —— 手段 C：大文件复杂 md 压力测试（多种类型）

自行生成 4 类「结构复杂、体积大」的 Markdown，模拟真实极端工况：
  - code        : 大量围栏代码块（最初卡死的根因样本：块级结构密度高）
  - table       : 大表格 + 多级列表 / 标题（结构嵌套）
  - math        : mermaid / katex / 行内公式 / 图表（渲染特性密集）
  - conversation: 对话记录式（标题 + 代码 + 引用 + 列表混杂，最贴近 1.5MB 卡死样本）

每类各生成 4MB / 15MB 两档，共 8 个样本。对每一个样本：
  1) 经真实后端 /api/save 写入、/api/file 读回（逐字节 sha256 校验，防静默损坏）
  2) 经前端统计路径（stripMarkdown + countReaderWords）实测耗时
每轮重新拉起全新服务，连续 5 轮，验证极端工况下保存/读取/统计均稳定且正确。

直接运行：python test_stress_largefile.py [轮数默认=5]
"""
import os, sys, io, re, json, time, socket, tempfile, subprocess, shutil, hashlib
import urllib.request, urllib.error, urllib.parse

# 本文件位于 tests/ 下，仓库根为其上一级目录
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(BASE, "vditor-fpk", "app")
MF = os.path.join(BASE, "vditor-fpk", "manifest")
SRV = os.path.join(APP, "server.py")
PY = sys.executable
# Node 可执行文件：优先用环境变量，其次用 PATH 中的 node，最后才回退到本机 WorkBuddy 运行时。
# 硬编码绝对路径会让他人克隆仓库后无法运行（CI 亦然），故仅作最后兜底。
NODE = (os.environ.get("VDITOR_NODE") or shutil.which("node")
        or r"C:/Users/13379/.workbuddy/binaries/node/versions/22.22.2-3/node.exe")
PERF = os.path.join(BASE, "tools", "perf_frontend_check.js")

def manifest_version():
    with io.open(MF, encoding="utf-8") as f:
        for ln in f:
            if ln.startswith("version="):
                return ln.strip().split("=", 1)[1].strip()
    return ""
MV = manifest_version()

passed = failed = 0
def check(name, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print("  FAIL", name, extra)

# ---------------- 样本生成 ----------------
def gen_code(n_blocks):
    lines = ["# 代码密集压测文档\n",
             "本文档由 `%d` 个代码块组成，用于模拟块级结构密度极高的真实场景。\n" % n_blocks]
    langs = ["python", "js", "json", "bash", "sql", "cpp"]
    for i in range(n_blocks):
        lang = langs[i % len(langs)]
        lines.append("\n## 第 %d 节 功能说明\n" % i)
        lines.append("这是第 %d 段中文叙述，描述该代码块的用途与边界条件，长度足以产生一定体积。\n" % i)
        lines.append("```%s\n" % lang)
        lines.append("def handler_%d(req):\n    # 处理逻辑 %d\n    return process(req, seed=%d)\n" % (i, i, i))
        lines.append("```\n")
    return "".join(lines)

def gen_table(rows):
    lines = ["# 表格密集压测文档\n\n",
             "下表为模拟的数据记录，含多级列表与标题混合。\n\n",
             "| 编号 | 名称 | 数值 | 状态 | 备注 |\n",
             "|------|------|------|------|------|\n"]
    for i in range(rows):
        lines.append("| %d | 项目%d | %.3f | 正常 | 备注说明%d |\n" % (i, i, i * 1.1, i))
    lines.append("\n## 小结\n\n")
    for i in range(rows // 20 + 1):
        lines.append("- 列表项 %d：描述该批次的处理结果，包含一些中文叙述内容。\n" % i)
    return "".join(lines)

def gen_math(blocks):
    lines = ["# 数学与图表密集压测文档\n\n",
             "包含行内公式 $a^2+b^2=c^2$、块级公式与多种图表语法。\n\n"]
    for i in range(blocks):
        lines.append("\n## 主题 %d\n" % i)
        lines.append("行内公式混合文字 $\\alpha_%d + \\beta_%d = \\gamma$。\n" % (i, i))
        lines.append("\n$$\n\\int_0^%d x^2\\,dx = \\frac{%d^3}{3}\n$$\n" % (i + 1, i + 1))
        lines.append("\n```mermaid\nflowchart TD\n  A[开始%d] --> B{判断%d}\n  B -->|是| C[处理]\n  B -->|否| D[跳过]\n```\n" % (i, i))
        lines.append("\n```katex\n\\frac{\\partial f}{\\partial x} = %d\n```\n" % i)
    return "".join(lines)

def gen_conversation(turns):
    lines = ["# 对话记录压测文档\n\n",
             "> 本文档模拟 AI 对话导出的长记录，含大量标题、代码块、引用与列表。\n\n"]
    for i in range(turns):
        lines.append("\n## 2026-01-%02d 用户\n" % ((i % 28) + 1))
        lines.append("这是用户的第 %d 条提问，包含一些背景描述和具体诉求。\n" % i)
        lines.append("\n## 2026-01-%02d 助手\n" % ((i % 28) + 1))
        lines.append("这是助手的回复正文，先给出结论，再展开说明。\n\n")
        lines.append("```json\n{\"turn\": %d, \"ok\": true, \"items\": [%d, %d, %d]}\n```\n" % (i, i, i * 2, i * 3))
        lines.append("\n> 引用：相关参考资料第 %d 条。\n\n" % i)
        lines.append("- 要点一：说明内容 %d\n- 要点二：说明内容 %d\n" % (i, i))
    return "".join(lines)

GENERATORS = {
    "code": lambda: gen_code(900),
    "table": lambda: gen_table(1500),
    "math": lambda: gen_math(400),
    "conversation": lambda: gen_conversation(600),
}

def make_samples(tmp, target_bytes_list):
    """为每个类型生成 target_bytes_list 中各体积的样本文件，返回 [(type,size_label,path,sha)]。"""
    samples = []
    for t, gen in GENERATORS.items():
        base = gen()
        for tb in target_bytes_list:
            # 通过重复 base 达到目标体积
            buf = [base]
            while sum(len(x.encode("utf-8")) for x in buf) < tb:
                buf.append(base)
            text = "".join(buf)
            # 精确裁剪到目标体积附近（避免过大）
            while len(text.encode("utf-8")) > tb and text:
                text = text[:-200]
            path = os.path.join(tmp, "%s_%dMB.md" % (t, tb // (1024 * 1024)))
            with io.open(path, "w", encoding="utf-8") as f:
                f.write(text)
            sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            samples.append((t, "%dMB" % (tb // (1024 * 1024)), path, sha, len(text.encode("utf-8"))))
    return samples

# ---------------- 服务 ----------------
def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); p = s.getsockname()[1]; s.close(); return p

def req(url, method="GET", data=None, cookie=None):
    hdrs = {}
    if cookie: hdrs["Cookie"] = cookie
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        hdrs["Content-Type"] = "application/json; charset=utf-8"
    r = urllib.request.Request(url, data=body, method=method, headers=hdrs)
    try:
        resp = urllib.request.urlopen(r, timeout=120)
        return resp.status, resp.read(), resp.headers.get("Set-Cookie")
    except urllib.error.HTTPError as e:
        return e.code, e.read(), e.headers.get("Set-Cookie")

def run_once(round_no, samples):
    global passed, failed
    port = free_port()
    tmp = tempfile.mkdtemp(prefix="vdss_")
    docdir = os.path.join(tmp, "docs"); uploaddir = os.path.join(tmp, "up")
    os.makedirs(docdir, exist_ok=True); os.makedirs(uploaddir, exist_ok=True)
    env = dict(os.environ)
    env.update({"VDITOR_CONFIG": tmp, "VDITOR_PORT": str(port), "VDITOR_HOST": "127.0.0.1",
                "VDITOR_DOC_DIR": docdir, "VDITOR_DOC_NAME": "我的文档", "VDITOR_UPLOAD_DIR": uploaddir})
    proc = subprocess.Popen([PY, "server.py"], cwd=APP, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    URL = "http://127.0.0.1:%d" % port
    try:
        for _ in range(80):
            try:
                if urllib.request.urlopen(URL + "/index.html", timeout=2).status == 200: break
            except Exception: pass
            if proc.poll() is not None: break
            time.sleep(0.25)
        st, _, ck = req(URL + "/api/setup", method="POST", data={"password": "stress-1234"})
        check("[R%d] 服务就绪+初始化" % round_no, st == 200, st)
        cookie = ck.split(";")[0] if ck else None
        st, d, _ = req(URL + "/api/files", cookie=cookie)
        d = json.loads(d) if d else {}
        rid = (d.get("roots") or [{}])[0].get("id")
        check("[R%d] 获得默认分区 id" % round_no, bool(rid), rid)

        save_ms = []; read_ms = []
        for (t, sz, path, sha, nbytes) in samples:
            with io.open(path, encoding="utf-8") as f:
                content = f.read()
            t0 = time.time()
            st, d, _ = req(URL + "/api/save", method="POST",
                           data={"root": rid, "path": os.path.basename(path), "content": content}, cookie=cookie)
            dt = (time.time() - t0) * 1000
            d = json.loads(d) if d else {}
            check("[R%d] 保存 %s/%s 成功" % (round_no, t, sz), st == 200 and d.get("ok") is True, (st, d))
            if st == 200:
                save_ms.append(dt)
            t0 = time.time()
            st, d, _ = req(URL + "/api/file?root=%s&path=%s" %
                           (urllib.parse.quote(rid), urllib.parse.quote(os.path.basename(path))), cookie=cookie)
            dt = (time.time() - t0) * 1000
            d = json.loads(d) if d else {}
            got = d.get("content", "")
            check("[R%d] 读回 %s/%s 逐字节一致" % (round_no, t, sz),
                  st == 200 and hashlib.sha256(got.encode("utf-8")).hexdigest() == sha,
                  (st, len(got)))
            if st == 200:
                read_ms.append(dt)
        if save_ms:
            print("    · 保存耗时 min/avg/max = %.0f/%.0f/%.0f ms" %
                  (min(save_ms), sum(save_ms)/len(save_ms), max(save_ms)))
            print("    · 读取耗时 min/avg/max = %.0f/%.0f/%.0f ms" %
                  (min(read_ms), sum(read_ms)/len(read_ms), max(read_ms)))

        # 前端统计路径耗时（同一批样本喂给 perf_frontend_check.js）
        sample_paths = [p for (_, _, p, _, _) in samples]
        try:
            out = subprocess.run([NODE, PERF] + sample_paths, capture_output=True, text=True, timeout=300).stdout
            # 解析每个样本的耗时
            for line in out.splitlines():
                if "耗时" in line or "统计" in line:
                    print("    · " + line.strip())
            # 只要脚本返回 ALL OK 即认为前端路径无异常
            ok = "ALL OK" in out
            check("[R%d] 前端统计路径(stripMarkdown/countReaderWords)全部通过" % round_no, ok,
                  ("no ALL OK" if not ok else ""))
        except Exception as e:
            check("[R%d] 前端统计路径执行" % round_no, False, str(e))
    finally:
        try: proc.terminate()
        except Exception: pass
        try: proc.wait(timeout=10)
        except Exception:
            try: proc.kill()
            except Exception: pass
        try: shutil.rmtree(tmp, ignore_errors=True)
        except Exception: pass

def main():
    rounds = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    gen_tmp = tempfile.mkdtemp(prefix="vdgen_")
    samples = make_samples(gen_tmp, [4 * 1024 * 1024, 15 * 1024 * 1024])
    print("生成样本：")
    for (t, sz, path, sha, nbytes) in samples:
        print("  %-13s %-4s %8.2f MB  sha=%s" % (t, sz, nbytes / 1024 / 1024, sha[:10]))
    gstart = time.time()
    for r in range(1, rounds + 1):
        print("======== 手段C 第 %d/%d 轮 ========" % (r, rounds))
        run_once(r, samples)
    dt = time.time() - gstart
    try: shutil.rmtree(gen_tmp, ignore_errors=True)
    except Exception: pass
    print("\nRESULT stress_largefile passed=%d failed=%d rounds=%d time=%.1fs version=%s" %
          (passed, failed, rounds, dt, MV))
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
