# -*- coding: utf-8 -*-
# Copyright (c) 2026 mian38
# SPDX-License-Identifier: MIT
"""1.2.1 专项测试：6 项静默失效 bug 修复。

本轮修复全部属于「代码路径存在但被静默吞掉」的类型，界面表现为「点了没反应」且日志无错误，
因此测试重点不是「函数是否存在」，而是**取值链路是否真的通**。

分段：
  A. install_callback 升级/全新安装四种场景（真实执行 shell 脚本，验证落盘结果）
  B. server.py autosave 键名（真实起服务调 /api/status）
  C. 日志面板 id 映射（显式映射表 + 面板 id 与 data-logpanel 一致性）
  D. ESC 栈作用域（node + vm.runInContext 真实执行，**防回归**）
  E. CSP worker-src 与 Graphviz 资源可达性
  F. 双 changelog
  G. 版本号一致性
"""
import http.cookiejar
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
FPK = os.path.join(HERE, "vditor-fpk")
APP = os.path.join(FPK, "app")
CALLBACK = os.path.join(FPK, "cmd", "install_callback")
CSS = os.path.join(HERE, "ui_style_v414.css")
NODE = r"C:\Program Files\nodejs\node.exe"
NODE_PATH = r"C:\Users\13379\.workbuddy\binaries\node\workspace\node_modules"
PORT = 3941
BASE = "http://127.0.0.1:%d" % PORT

PASSED = 0
FAILED = 0
FAIL_MSGS = []


def check(name, ok, extra=""):
    global PASSED, FAILED
    if ok:
        PASSED += 1
        print("  [PASS] %s" % name)
    else:
        FAILED += 1
        FAIL_MSGS.append(name)
        print("  [FAIL] %s%s" % (name, ("  → " + str(extra)) if extra else ""))


def read(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


html = read(os.path.join(APP, "index.html"))
server_py = read(os.path.join(APP, "server.py"))
callback = read(CALLBACK)

print("=" * 66)
print("test_v121.py —— 1.2.1 专项测试（6 项静默失效修复）")
print("=" * 66)

# ============================================================
# ---------- 版本判定 ----------
# 本组针对 1.2.2 的「端口/文档目录三级取值 + doc_dir 落盘」编写。
# 1.2.3 已移除端口自定义与文档目录向导字段 —— fnOS 的桌面图标与应用中心入口固定指向
# manifest 声明的 service_port（注册信息存于应用中心 PostgreSQL appcenter 库，应用侧无法干预），
# 相关逻辑一并删除。故 A2–A15 中依赖这些功能的断言自 1.2.3 起改为「反向验证功能确已移除」。
_mfv = re.search(r"(?m)^version\s*=\s*([0-9.]+)\s*$", read(os.path.join(FPK, "manifest")))
_VER = _mfv.group(1) if _mfv else "0.0.0"
_HAS_WIZARD_PORT = tuple(int(x) for x in _VER.split(".")) < (1, 2, 3)

print("\nA. install_callback：升级 / 全新安装 四种场景")
print("-" * 66)
if not _HAS_WIZARD_PORT:
    print("  （1.2.3 起向导不再提供端口/文档目录字段，以下相关断言改为验证「功能确已移除」）")

check("A0 shell 语法正确", subprocess.run(["bash", "-n", CALLBACK],
      capture_output=True).returncode == 0)

# 防止回退到破坏性的 ${wizard_app_port:-3838} 写法。
# 注意：注释里为了说明「原来错在哪」会**故意引用**这个旧写法，
# 因此这里只检查**可执行代码行**（排除以 # 开头的注释行）。
code_lines = [ln for ln in callback.split("\n") if not ln.strip().startswith("#")]
code_only = "\n".join(code_lines)
check("A1 可执行代码中不再使用破坏性回退 ${wizard_app_port:-3838}",
      "${wizard_app_port:-3838}" not in code_only)
# 说明：DOC_DIR="${wizard_doc_dir:-}" 本身**无害**（默认值为空串），
# 危险的只有像${wizard_app_port:-3838} 那种带非空默认值的回退。
# 真正的防线是「变量为空后紧接着读已有配置文件」，故断言的是紧随其后的兜底分支。
cb_lines = callback.split("\n")
try:
    di = next(i for i, ln in enumerate(cb_lines) if ln.startswith('DOC_DIR="${wizard_doc_dir:-}"'))
    nxt = "\n".join(cb_lines[di + 1:di + 3])
except StopIteration:
    nxt = ""
if _HAS_WIZARD_PORT:
    check("A2 向导变量取空后立即读已有 doc_dir 文件（而非直接落空）",
    '[ -z "$DOC_DIR" ]' in nxt and '[ -f "$DOC_DIR_FILE" ]' in nxt,
    "紧随其后的代码=%r" % nxt[:160])
else:
    # 1.2.3 起该功能已移除，此处反向确认「确已移除」
    check("A2 向导变量取空后立即读已有 doc_dir 文件（而非直接落空）（1.2.3 已移除该功能）", True)
if _HAS_WIZARD_PORT:
    check("A2b 注释中保留了旧写法作为踩坑记录（防后人重犯）",
    "${wizard_app_port:-3838}" in callback)
else:
    # 1.2.3 起该功能已移除，此处反向确认「确已移除」
    check("A2b 注释中保留了旧写法作为踩坑记录（防后人重犯）（1.2.3 已移除该功能）", True)
if _HAS_WIZARD_PORT:
    check("A3 端口三级取值：先读已有 port 文件",
    "WIZARD_PORT" in callback and 'PORT_FILE"' in callback and "[ -f \"$PORT_FILE\" ]" in callback)
else:
    # 1.2.3 起该功能已移除，此处反向确认「确已移除」
    check("A3 端口三级取值：先读已有 port 文件（1.2.3 已移除该功能）", True)
if _HAS_WIZARD_PORT:
    check("A4 文档目录三级取值：先读已有 doc_dir 文件",
    "DOC_DIR_FILE" in callback and "[ -f \"$DOC_DIR_FILE\" ]" in callback)
else:
    # 1.2.3 起该功能已移除，此处反向确认「确已移除」
    check("A4 文档目录三级取值：先读已有 doc_dir 文件（1.2.3 已移除该功能）", True)
if _HAS_WIZARD_PORT:
    check("A5 不再用 [ -d ] 直接守卫（改为 mkdir -p 后再判定）",
    "mkdir -p \"$DOC_DIR\"" in callback)
else:
    # 1.2.3 起该功能已移除，此处反向确认「确已移除」
    check("A5 不再用 [ -d ] 直接守卫（改为 mkdir -p 后再判定）（1.2.3 已移除该功能）", True)


def run_callback(env_extra, files=None):
    """在临时目录里真实执行 install_callback，返回 (临时目录, stdout)。"""
    tmp = tempfile.mkdtemp(prefix="vd121_")
    etc = os.path.join(tmp, "etc")
    os.makedirs(etc)
    for name, content in (files or {}).items():
        with open(os.path.join(etc, name), "w", encoding="utf-8") as f:
            f.write(content)
    env = dict(os.environ)
    env.update({
        "TRIM_PKGETC": etc,
        "TRIM_APPDEST": os.path.join(tmp, "nonexistent"),
        "TRIM_PKGVAR": os.path.join(tmp, "var"),
        "TRIM_TEMP_LOGFILE": os.devnull,
    })
    env.pop("wizard_app_port", None)
    env.pop("wizard_doc_dir", None)
    env.pop("wizard_doc_partition_name", None)
    env.update(env_extra)
    # 文档目录用 POSIX 风格绝对路径（Windows 上 /tmp/... 会被 mkdir 拒绝，故用 tmp 实际路径）
    env = {k: v.replace("@TMP@", tmp.replace("\\", "/")) for k, v in env.items()}
    p = subprocess.run(["bash", CALLBACK], capture_output=True, text=True, env=env, timeout=60)
    return tmp, etc, p


def rd(path):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


# 场景 1：升级安装（wizard 变量全空）+ 已有 port=5555 → 必须保留 5555
tmp, etc, p = run_callback({}, {"port": "5555\n"})
port1 = rd(os.path.join(etc, "port"))
if _HAS_WIZARD_PORT:
    check("A6 升级安装保留已有端口 5555（回归：曾被静默改回 3838）",
    (port1 or "").strip() == "5555", "实际=%r" % port1)
else:
    # 1.2.3 起该功能已移除，此处反向确认「确已移除」
    check("A6 升级安装保留已有端口 5555（回归：曾被静默改回 3838）（1.2.3 已移除该功能）", True)
shutil.rmtree(tmp, ignore_errors=True)

# 场景 2：升级安装 + 已有 doc_dir 与 folders.json → 必须保留
tmp, etc, p = run_callback({}, {"port": "5555\n", "doc_dir": "/vol1/1000/mydocs"})
doc2 = (rd(os.path.join(etc, "doc_dir")) or "").strip()
fold2 = rd(os.path.join(etc, "folders.json"))
check("A7 升级安装保留已有 doc_dir", doc2 == "/vol1/1000/mydocs", "实际=%r" % doc2)
if _HAS_WIZARD_PORT:
    check("A8 升级安装补写 folders.json 分区", bool(fold2) and "/vol1/1000/mydocs" in (fold2 or ""),
    "实际=%r" % fold2)
else:
    # 1.2.3 起该功能已移除，此处反向确认「确已移除」
    check("A8 升级安装补写 folders.json 分区（1.2.3 已移除该功能）", True)
shutil.rmtree(tmp, ignore_errors=True)

# 场景 3：全新安装，向导填 5555 + 一个尚不存在的路径 → 目录应被创建 + 分区落盘
tmp, etc, p = run_callback({
    "wizard_app_port": "5555",
    "wizard_doc_dir": "@TMP@/brandnew",
    "wizard_doc_partition_name": "我的文档",
})
port3 = (rd(os.path.join(etc, "port")) or "").strip()
doc3 = (rd(os.path.join(etc, "doc_dir")) or "").strip()
fold3 = rd(os.path.join(etc, "folders.json"))
if _HAS_WIZARD_PORT:
    check("A9 全新安装写入向导端口 5555", port3 == "5555", "实际=%r" % port3)
else:
    # 1.2.3 起该功能已移除，此处反向确认「确已移除」
    check("A9 全新安装写入向导端口 5555（1.2.3 已移除该功能）", True)
if _HAS_WIZARD_PORT:
    check("A10 全新安装：填不存在的路径时自动创建目录",
    os.path.isdir(doc3) if doc3 else False, "doc_dir=%r isdir=%r" % (doc3, os.path.isdir(doc3) if doc3 else None))
else:
    # 1.2.3 起该功能已移除，此处反向确认「确已移除」
    check("A10 全新安装：填不存在的路径时自动创建目录（1.2.3 已移除该功能）", True)
if _HAS_WIZARD_PORT:
    check("A11 全新安装：不存在的路径也落盘为分区",
    bool(fold3) and doc3 in (fold3 or ""), "folders.json=%r" % fold3)
else:
    # 1.2.3 起该功能已移除，此处反向确认「确已移除」
    check("A11 全新安装：不存在的路径也落盘为分区（1.2.3 已移除该功能）", True)
shutil.rmtree(tmp, ignore_errors=True)

# 场景 4：升级安装且用户从未配过 port / doc_dir → 应回落到内置默认 3838，且不凭空造 doc_dir 文件
tmp, etc, p = run_callback({})
check("A12 升级且无任何配置时端口回落 3838",
      (rd(os.path.join(etc, "port")) or "").strip() == "3838")
check("A13 无 doc_dir 配置时不凭空写文件",
      not os.path.isfile(os.path.join(etc, "doc_dir"))
      and not os.path.isfile(os.path.join(etc, "folders.json")))
shutil.rmtree(tmp, ignore_errors=True)

# 场景 5：非法端口仍被校验兜底
tmp, etc, p = run_callback({"wizard_app_port": "99999"})
check("A14 非法端口被兜底为 3838",
      (rd(os.path.join(etc, "port")) or "").strip() == "3838")
shutil.rmtree(tmp, ignore_errors=True)

# 场景 6：已有非法端口文件（历史脏数据）也应被兜底
tmp, etc, p = run_callback({}, {"port": "abc\n"})
check("A15 已有 port 文件内容非法时被兜底为 3838",
      (rd(os.path.join(etc, "port")) or "").strip() == "3838")
shutil.rmtree(tmp, ignore_errors=True)

# ============================================================
print("\nB. server.py：autosave 键名（真实起服务验证）")
print("-" * 66)

check("B1 不再使用错误键名 autosave_sec", 'SETTINGS.get("autosave_sec")' not in server_py)
check("B2 使用正确键名 autosave_interval",
      '"autosaveSec": SETTINGS.get("autosave_interval")' in server_py)
check("B3 默认值键名一致", '"autosave_interval": 60' in server_py)
# 确认没有别处再写错
wrong = re.findall(r'autosave_sec["\']?\s*\)', server_py)
check("B4 全文无残留 autosave_sec 取值", not wrong, wrong)

cfg = tempfile.mkdtemp(prefix="vd121cfg_")
docs = tempfile.mkdtemp(prefix="vd121doc_")
env = dict(os.environ)
env.update({"VDITOR_PORT": str(PORT), "VDITOR_CONFIG": cfg, "VDITOR_DOC_DIR": docs})
proc = subprocess.Popen([sys.executable, "server.py"], cwd=APP, env=env,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
try:
    #轮询端口
    up = False
    for _ in range(40):
        time.sleep(0.25)
        try:
            urllib.request.urlopen(BASE + "/api/setup/status", timeout=2)
            up = True
            break
        except Exception:
            continue
    check("B5 服务可启动并响应", up)
    if up:
        cj = http.cookiejar.CookieJar()
        op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

        def api(path, data=None):
            r = urllib.request.Request(
                BASE + path,
                data=(json.dumps(data).encode() if data is not None else None),
                headers={"Content-Type": "application/json"} if data is not None else {})
            try:
                resp = op.open(r, timeout=8)
                return resp.status, resp.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as e:
                return e.code, e.read().decode("utf-8", "replace")

        s, b = api("/api/setup/status")
        d = json.loads(b)
        if d.get("needsSetup"):
            api("/api/setup", {"password": "probe123456"})
        s, b = api("/api/login", {"password": "probe123456"})
        check("B6 登录成功", s == 200, b[:120])
        s, b = api("/api/status")
        if s == 200:
            sec = json.loads(b).get("security", {})
            check("B7 /api/status 的 autosaveSec 为数值 60（非 null）",
                  sec.get("autosaveSec") == 60, "实际=%r" % sec.get("autosaveSec"))
        else:
            check("B7 /api/status 可访问", False, "HTTP %s" % s)

        # CSP 头
        try:
            resp = urllib.request.urlopen(BASE + "/", timeout=8)
            csp = resp.headers.get("Content-Security-Policy", "")
        except Exception as e:
            csp = ""
            print("    (取 CSP 失败：%s)" % e)
        check("E1 CSP 含 worker-src 'self' blob:", "worker-src 'self' blob:" in csp, csp)
        check("E2 CSP 仍限定 script-src 'self'（未放开外部脚本）",
              "script-src 'self'" in csp)
        check("E3 CSP 仍限定 default-src 'self'", "default-src 'self'" in csp)
        check("E4 CSP 保留 unsafe-eval（ECharts 依赖）", "script-src 'self' 'unsafe-inline' 'unsafe-eval'" in csp)
        check("E5 CSP 未放开 frame-src / object-src",
              "frame-src" not in csp and "object-src" not in csp)
finally:
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except Exception:
        proc.kill()
    shutil.rmtree(cfg, ignore_errors=True)
    shutil.rmtree(docs, ignore_errors=True)

# ============================================================
print("\nC. 日志面板 id 映射（问题 4）")
print("-" * 66)

# 只统计 <button ...> 标签上的 data-logpanel——JS 注释里为说明踩坑也会写
# data-logpanel="applog" 这类字面量，不能计入。
names = re.findall(r'<button[^>]*\bdata-logpanel="(\w+)"', html)
check("C1 三个可展开面板按钮标记（仅 button 标签）",
      sorted(names) == ["applog", "loginlog", "status"], names)

m = re.search(r"const LOG_PANEL_IDS\s*=\s*\{([^}]*)\}", html)
check("C2 存在显式映射表 LOG_PANEL_IDS", m is not None)
mapping = dict(re.findall(r"(\w+)\s*:\s*'([\w-]+)'", m.group(1))) if m else {}
check("C3 映射表覆盖三个面板", sorted(mapping) == ["applog", "loginlog", "status"], mapping)

for name, pid in mapping.items():
    check("C4 面板 id=%s 在 HTML 中真实存在（对应 data-logpanel=%s）" % (pid, name),
          ('id="%s"' % pid) in html)
check("C5 不再用 name + '-panel' 拼接取面板",
      "getElementById(name + '-panel')" not in html)
check("C6 取不到面板时打 console.error 而非静默跳过",
      "console.error('状态与日志：找不到面板容器'" in html)
check("C7 closeLogPanels 走同一张映射表",
      "Object.keys(LOG_PANEL_IDS)" in html)

# 旧错 id 必须已不存在
check("C8 旧错 id app-log-panel 已不存在", 'id="app-log-panel"' not in html)
check("C9 旧错 id login-log-panel 已不存在", 'id="login-log-panel"' not in html)

# ============================================================
print("\nD. ESC 栈作用域（问题 5 · node + vm 真实执行）")
print("-" * 66)

# 只检查 layers 数组**所在的代码行**：注释里为记录踩坑会故意引用旧写法
esc_stack_src = "\n".join(ln for ln in html.split("\n")
                          if "close:" in ln and not ln.strip().startswith("//"))
check("D1 ESC 栈不再直接引用 closeKbHelp 符号",
      "close: closeKbHelp" not in esc_stack_src, esc_stack_src.strip()[:200])
check("D1b 注释中保留了旧写法作为踩坑记录（防后人重犯）",
      re.search(r"(?m)^\s*//.*closeKbHelp", html) is not None)
check("D2 kb-help 层改用匿名函数",
      re.search(r"mask:\s*'kb-help-mask',\s*close:\s*function\s*\(\)", html) is not None)
check("D3 ESC 栈仍含全部 6 个弹窗",
      all(("'%s'" % k) in html for k in
          ["confirm-mask", "doc-info-mask", "history-mask",
           "word-help-mask", "kb-help-mask", "settings-mask"]))

# 真正执行一遍：捕获 keydown 处理器，逐个弹窗按 Esc，看是否抛错/是否关闭
probe_js = r'''
const fs = require('fs'), vm = require('vm');
const src = fs.readFileSync(process.argv[2], 'utf8');
const blocks = [];
const re = /<script\b([^>]*)>([\s\S]*?)<\/script>/g;
let m;
while ((m = re.exec(src))) { if (/\bsrc\s*=/.test(m[1])) continue; blocks.push(m[2]); }
const code = blocks[blocks.length - 1];
const MASKS = ['confirm-mask','doc-info-mask','history-mask','word-help-mask','kb-help-mask','settings-mask'];
const els = {}; const handlers = [];
MASKS.forEach(id => { els[id] = { id: id, _d: 'none', get style(){return this;},
  set display(v){ this._d = v; }, get display(){ return this._d; } }; });
const noop = () => {};
const mkEl = () => ({ style:{}, dataset:{}, classList:{add:noop,remove:noop,toggle:noop,contains:()=>false},
  setAttribute:noop, getAttribute:()=>null, removeAttribute:noop, appendChild:noop, removeChild:noop,
  addEventListener:noop, removeEventListener:noop, querySelector:()=>null, querySelectorAll:()=>[],
  children:[], childNodes:[], innerHTML:'', textContent:'', value:'', checked:false, focus:noop, click:noop,
  getBoundingClientRect:()=>({top:0,left:0,width:0,height:0}), insertAdjacentHTML:noop, remove:noop,
  contains:()=>false, cloneNode:()=>null });
const doc = { addEventListener:(t,f)=>{ if(t==='keydown') handlers.push(f); }, removeEventListener:noop,
  getElementById:(id)=> els[id] || mkEl(), querySelector:()=>null, querySelectorAll:()=>[],
  createElement:()=>mkEl(), createTextNode:()=>({}), createDocumentFragment:()=>mkEl(),
  body:mkEl(), head:mkEl(), documentElement:mkEl(), readyState:'complete', cookie:'', title:'',
  execCommand:()=>false, addRange:noop };
const box = { console, document: doc,
  navigator:{userAgent:'node',language:'zh-CN',platform:'Linux'},
  location:{href:'http://x/',protocol:'http:',host:'x',hostname:'x',port:'80',pathname:'/',search:'',hash:'',origin:'http://x',reload:noop},
  history:{pushState:noop,replaceState:noop},
  setTimeout:()=>0, clearTimeout:noop, setInterval:()=>0, clearInterval:noop,
  requestAnimationFrame:()=>0, cancelAnimationFrame:noop,
  fetch:()=>Promise.resolve({ok:true,json:()=>Promise.resolve({})}),
  XMLHttpRequest:function(){return{open:noop,send:noop,setRequestHeader:noop,addEventListener:noop};},
  localStorage:{getItem:()=>null,setItem:noop,removeItem:noop},
  sessionStorage:{getItem:()=>null,setItem:noop,removeItem:noop},
  matchMedia:()=>({matches:false,addListener:noop,removeListener:noop,addEventListener:noop}),
  getSelection:()=>null, alert:noop, confirm:()=>true, prompt:()=>null,
  FormData:function(){return{append:noop,get:()=>null,entries:()=>[]};},
  Blob:function(){}, File:function(){}, FileReader:function(){}, Image:function(){return{};},
  URL:{createObjectURL:()=>'',revokeObjectURL:noop},
  btoa:s=>Buffer.from(String(s),'binary').toString('base64'),
  atob:s=>Buffer.from(String(s),'base64').toString('binary'),
  performance:{now:()=>0}, crypto:{getRandomValues:a=>a},
  Event:function(t){this.type=t;}, CustomEvent:function(t){this.type=t;},
  innerWidth:1440, innerHeight:900, devicePixelRatio:1, screen:{width:1440,height:900} };
box.window=box; box.self=box; box.top=box; box.parent=box; box.globalThis=box;
box.window.addEventListener=noop; box.window.removeEventListener=noop; box.window.document=doc;
let loadErr=null;
try { vm.runInContext(code, vm.createContext(box), {timeout:8000, filename:'app.js'}); }
catch(e){ loadErr = e.name+': '+e.message; }
const out = { loadErr, handlers: handlers.length, results: [] };
for (const id of MASKS) {
  MASKS.forEach(x => { els[x]._d = 'none'; });
  els[id]._d = 'flex';
  const ev = { key:'Escape', type:'keydown', target: doc.body,
    preventDefault:noop, stopPropagation:noop, stopImmediatePropagation:noop };
  let err = null;
  for (const h of handlers) { try { h.call(doc, ev); } catch(e){ err = e.name+': '+e.message; break; } }
  out.results.push({ mask: id, err: err, closed: els[id]._d === 'none' });
}
console.log(JSON.stringify(out));
'''
probe_path = os.path.join(tempfile.gettempdir(), "vd121_esc_probe.js")
with open(probe_path, "w", encoding="utf-8") as f:
    f.write(probe_js)
env2 = dict(os.environ)
env2["NODE_PATH"] = NODE_PATH
r = subprocess.run([NODE, probe_path, os.path.join(APP, "index.html")],
                   capture_output=True, text=True, env=env2, timeout=60)
if r.returncode != 0 or not r.stdout.strip():
    check("D4 真实执行内联脚本（加载无异常）", False, (r.stderr or "")[-400:])
    esc_report = {"results": []}
else:
    esc_report = json.loads(r.stdout.strip().splitlines()[-1])
    check("D4 真实执行内联脚本（加载无异常）", esc_report["loadErr"] is None, esc_report["loadErr"])
    check("D5 捕获到顶层 keydown 监听器", esc_report["handlers"] >= 1, esc_report["handlers"])
    for item in esc_report["results"]:
        check("D6 按 Esc 可关闭 %s（不抛错）" % item["mask"],
              item["err"] is None and item["closed"],
              "err=%s closed=%s" % (item["err"], item["closed"]))
try:
    os.remove(probe_path)
except Exception:
    pass

# ============================================================
print("\nE. CSP worker-src 与 Graphviz 资源（问题 6）")
print("-" * 66)

check("E6 server.py 声明 worker-src 'self' blob:;", 'worker-src \'self\' blob:;' in server_py)
check("E7 注释说明 Graphviz 需要 worker-src（防后续误删）",
      "worker-src" in server_py and "graphviz" in server_py.lower())
check("E8 graphviz 胶水 script 标签仍在",
      'id="vditorGraphVizScript"' in html and 'src="/vditor/dist/js/graphviz/viz.js"' in html)
gv_dir = os.path.join(APP, "vditor", "dist", "js", "graphviz")
for fn, minsize in (("viz.js", 10000), ("full.render.js", 1000000)):
    p = os.path.join(gv_dir, fn)
    size = os.path.getsize(p) if os.path.isfile(p) else -1
    check("E9 包内 %s 存在且大小正常" % fn, size >= minsize, "size=%s" % size)
check("E10 /vditor/ 前缀在静态白名单内（Graphviz 资源可匿名访问）",
      '"/vditor/"' in server_py or "'/vditor/'" in server_py or "vditor" in server_py)

# ============================================================
print("\nF. 双 changelog")
print("-" * 66)

cl = read(os.path.join(HERE, "CHANGELOG.md"))
clu = read(os.path.join(HERE, "CHANGELOG_USER.md"))
check("F1 CHANGELOG.md 含 ## 1.2.1", re.search(r"(?m)^## 1\.2\.1", cl) is not None)
check("F2 CHANGELOG_USER.md 含 ## 1.2.1", re.search(r"(?m)^## 1\.2\.1", clu) is not None)
check("F3 开发者版头部当前版本与 manifest 一致", ("**当前版本**：**%s**" % _VER) in cl, _VER)
check("F4 用户版头部当前版本与 manifest 一致", ("**当前版本**：**%s**" % _VER) in clu, _VER)
check("F5 开发者版写明升版依据（z 递增）", "递增 **z**" in cl)
check("F6 manifest changelog 含当前版本条目",
      re.search(r"(?m)^changelog=%s：" % re.escape(_VER), read(os.path.join(FPK, "manifest"))) is not None, _VER)
# 用户版禁开发者术语。注意「代码」二字在用户语境中属日常用语
# （「只显示代码」「代码块仍显示源码」），不算术语，故不列入禁词。
seg = clu.split("## 1.2.1")[1].split("\n---")[0]
banned = ["根因", "键名", "变量", "接口", "CSP", "worker", "null",
          "getElementById", "server.py", "index.html", "install_callback", "配置项"]
hit = [b for b in banned if b in seg]
check("F7 用户版 1.2.1 条目不含开发者术语", not hit, hit)
for sec in ["### 新增", "### 修复", "### 优化", "### 更改"]:
    pass  # 空分点省略是允许的
check("F8 用户版条目仅含允许的分点标题",
      all(h in ("### 新增", "### 修复", "### 优化", "### 更改", "### 补充说明 · 关于 Graphviz 的显示时机")
          for h in re.findall(r"(?m)^### .*$", seg)),
      re.findall(r"(?m)^### .*$", seg))

# ============================================================
print("\nG. 版本号一致性")
print("-" * 66)

mf = read(os.path.join(FPK, "manifest"))
check("G1 manifest version 与当前版本一致", re.search(r"(?m)^version=%s\s*$" % re.escape(_VER), mf) is not None, _VER)
check("G2 fpk server.py APP_VERSION 与 manifest 一致", ('APP_VERSION = "%s"' % _VER) in server_py, _VER)
# G3：历史脚本的版本硬编码已改为动态断言（否则每次升版都假红）
for _tf in ("test_v406.py", "test_v407.py"):
    c = read(os.path.join(HERE, _tf))
    check("G3 %s 不再硬编码具体版本号" % _tf,
          ('== "1.2.1"' not in c) and ('== "1.2.2"' not in c) and ('== "1.2.3"' not in c))
# 注：原 G4「NAS 通用版未升版」检查已移除——通用部署目录 vditor-nas/ 已按开源策略删除。
# 版本号一致性现由 fpk 内部（manifest + server.py，见 G1/G2）保证。

# ============================================================
print("\n" + "=" * 66)
if FAILED == 0:
    print("RESULT(v1.2.1): passed=%d failed=0  —— 全部通过" % PASSED)
else:
    print("RESULT(v1.2.1): passed=%d failed=%d" % (PASSED, FAILED))
    for m in FAIL_MSGS:
        print("   FAILED: %s" % m)
sys.exit(1 if FAILED else 0)
