import os, sys, json, time, tempfile, subprocess, threading, urllib.request, urllib.error, urllib.parse, shutil, http.server
BASE = "C:/Users/13379/WorkBuddy/2026-10-01-14-38-51"
APP = os.path.join(BASE, "vditor-nas")
PYEX = sys.executable
tmp = tempfile.mkdtemp(prefix="vdtest2_")
docs = os.path.join(tmp, "docs"); os.makedirs(docs, exist_ok=True)
port = 9173
env = dict(os.environ)
env.update({"VDITOR_CONFIG": tmp, "VDITOR_PORT": str(port), "VDITOR_HOST": "127.0.0.1",
            "VDITOR_DOC_DIR": docs, "VDITOR_DOC_NAME": "docs",
            "VDITOR_UPLOAD_DIR": os.path.join(tmp, "uploads")})
img_dir = os.path.join(tmp, "imgsrv"); os.makedirs(img_dir, exist_ok=True)
png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154789c6360000002000154a24f600000000049454e44ae426082")
open(os.path.join(img_dir, "t.png"), "wb").write(png)
img_port = 9174
httpd = http.server.ThreadingHTTPServer(("127.0.0.1", img_port), http.server.SimpleHTTPRequestHandler)
httpd.directory = img_dir
threading.Thread(target=httpd.serve_forever, daemon=True).start()
proc = subprocess.Popen([PYEX, "server.py"], cwd=APP, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2.5)
URL = "http://127.0.0.1:%d" % port
passed = 0; failed = 0
def req(method, path, body=None, cookie=None):
    headers = {"Content-Type": "application/json"}
    if cookie: headers["Cookie"] = cookie
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(URL + path, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(r, timeout=5)
        return resp.status, json.loads(resp.read().decode() or "{}"), resp.headers.get("Set-Cookie")
    except urllib.error.HTTPError as e:
        try: return e.code, json.loads(e.read().decode() or "{}"), None
        except Exception: return e.code, {}, None
def check(name, cond, extra=""):
    global passed, failed
    if cond: passed += 1; print("  PASS", name)
    else: failed += 1; print("  FAIL", name, extra)
st, d, ck = req("POST", "/api/setup", {"password": "secret123"}); check("setup ok", st == 200 and d.get("ok")); cookie = ck
st, d, _ = req("GET", "/api/settings", cookie=cookie); check("settings has image_bed_url", st == 200 and "image_bed_url" in d.get("settings", {}))
st, d, _ = req("GET", "/api/folders", cookie=cookie); roots = d.get("roots", [])
check("folders lists system root docs", st == 200 and any(r["name"] == "docs" for r in roots))
doc_path = next(r["path"] for r in roots if r["name"] == "docs")
st, d, _ = req("POST", "/api/folders", {"action": "remove", "path": doc_path}, cookie=cookie)
check("hide system root", st == 200 and not any(r["path"] == doc_path for r in d.get("roots", [])))
check("excluded recorded", doc_path in d.get("excluded", []))
st, d, _ = req("POST", "/api/folders", {"action": "restore", "path": doc_path}, cookie=cookie)
check("restore system root", st == 200 and any(r["path"] == doc_path for r in d.get("roots", [])) and doc_path not in d.get("excluded", []))
req("POST", "/api/new", {"root": "docs", "path": "d.md"}, cookie=cookie)
req("POST", "/api/save", {"root": "docs", "path": "d.md", "content": "line1\nline2"}, cookie=cookie)
req("POST", "/api/save", {"root": "docs", "path": "d.md", "content": "line1\nline2\nline3"}, cookie=cookie)
st, d, _ = req("GET", "/api/versions?root=docs&path=" + urllib.parse.quote("d.md"), cookie=cookie)
vers = d.get("versions", [])
check("versions >= 2", st == 200 and len(vers) >= 2)
if len(vers) >= 2:
    newest = vers[0]["ts"]
    st, d, _ = req("GET", "/api/version/diff?root=docs&path=" + urllib.parse.quote("d.md") + "&ts=" + str(newest), cookie=cookie)
    check("diff returns lines", st == 200 and isinstance(d.get("diff"), list) and d.get("added", 0) >= 1, str(d))
img_url = "http://127.0.0.1:%d/t.png" % img_port
st, d, _ = req("POST", "/api/link-to-img", {"url": img_url}, cookie=cookie)
check("link-to-img ok", st == 200 and d.get("code") == 0 and d.get("data", {}).get("url", "").startswith("/uploads/"), str(d))
st, d, _ = req("POST", "/api/link-to-img", {"url": "not-a-url"}, cookie=cookie)
check("link-to-img invalid rejected", st == 400 or (d.get("code") == 1), str((st, d)))
st, d, _ = req("POST", "/api/settings", {"image_bed_url": "https://example.com/upload"}, cookie=cookie)
check("set image_bed_url", st == 200 and d["settings"]["image_bed_url"] == "https://example.com/upload")
httpd.shutdown(); proc.terminate()
try: proc.wait(timeout=5)
except Exception: proc.kill()
shutil.rmtree(tmp, ignore_errors=True)
print("\nRESULT: passed=%d failed=%d" % (passed, failed))
sys.exit(1 if failed else 0)
