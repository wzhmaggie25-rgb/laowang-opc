#!/usr/bin/env python3
"""备用方案：把静态站打包成单个 Cloudflare Worker（所有文件内联进脚本）。
用于 Pages 服务端故障时的临时/备用托管。仍走 Cloudflare，国内访问不受影响。
用法: python3 deploy_worker.py [--dir DIR] [--worker NAME]
需要有 Workers:Edit 权限的 token（~/.config/laowang-opc/cf-token-workers，或 CF_WORKERS_TOKEN）。
"""
import json, mimetypes, os, sys, urllib.request, urllib.error
from pathlib import Path

BASE = Path(sys.argv[sys.argv.index("--dir")+1] if "--dir" in sys.argv else "~/workspace/laowang-opc").expanduser()
WORKER = sys.argv[sys.argv.index("--worker")+1] if "--worker" in sys.argv else "laowang-site"
TOKEN_FILE = Path.home() / ".config/laowang-opc/cf-token-workers"
EXCLUDE = {"build_reading.py", "deploy.py", "deploy_worker.py", "sync_site.sh", ".git", "node_modules"}

def token():
    t = os.environ.get("CF_WORKERS_TOKEN")
    if t: return t.strip()
    return TOKEN_FILE.read_text().strip()

def api(method, url, tok, data=None, ctype="application/json"):
    req = urllib.request.Request(url, method=method,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": ctype},
        data=data)
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} {url}\n{e.read()[:800].decode(errors='replace')}")

def main():
    tok = token()
    files = {}
    for p in sorted(BASE.rglob("*")):
        if not p.is_file(): continue
        rel = p.relative_to(BASE)
        if rel.parts[0] in EXCLUDE or p.name == ".DS_Store": continue
        ct = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if p.suffix == ".html": ct = "text/html; charset=utf-8"
        if p.suffix == ".css": ct = "text/css; charset=utf-8"
        files["/" + rel.as_posix()] = (ct, p.read_text(encoding="utf-8"))
    print(f"文件 {len(files)} 个")

    # 生成 Worker 脚本（文件内联为 JS 字符串）
    entries = ",\n".join(
        f"  {json.dumps(wp)}: {json.dumps({'ct': ct, 'body': body})}"
        for wp, (ct, body) in files.items())
    script = f"""const FILES = {{
{entries}
}};
export default {{
  async fetch(req) {{
    const u = new URL(req.url);
    let p = u.pathname;
    if (p.endsWith("/")) p += "index.html";
    let f = FILES[p] || FILES[p + "/index.html"] || FILES[p.replace(/\\/$/, "") + "/index.html"];
    if (!f) return new Response("Not Found", {{status: 404}});
    return new Response(f.body, {{headers: {{"content-type": f.ct, "cache-control": "public, max-age=300"}}}});
  }}
}};
"""
    print(f"Worker 脚本 {len(script)/1024:.1f} KB")

    zone = api("GET", "https://api.cloudflare.com/client/v4/zones?name=laowang-opc.com", tok)["result"][0]
    aid = zone["account"]["id"]

    # 上传 Worker（multipart）
    boundary = "----worker" + os.urandom(4).hex()
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="script"; filename="worker.js"\r\n')
    body.extend(b"Content-Type: application/javascript\r\n\r\n")
    body.extend(script.encode() + b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{aid}/workers/scripts/{WORKER}",
        data=bytes(body), method="PUT",
        headers={"Authorization": f"Bearer {tok}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"上传失败 HTTP {e.code}\n{e.read()[:800].decode(errors='replace')}")
    if not resp.get("success"):
        raise RuntimeError(f"上传失败: {resp}")
    print("Worker 已部署:", WORKER)

    # 开 workers.dev 子域名访问
    try:
        api("PATCH",
            f"https://api.cloudflare.com/client/v4/accounts/{aid}/workers/scripts/{WORKER}/subdomain",
            tok, {"enabled": True})
        print("workers.dev 子域名已启用")
    except RuntimeError as e:
        print("子域名启用跳过:", str(e)[:100])

if __name__ == "__main__":
    main()
