#!/usr/bin/env python3
"""Cloudflare Pages 直接上传部署（正确流程：assets API 先传文件，再建部署）。
用法: python3 deploy.py [--dir DIR] [--project NAME]
token 从 ~/.config/laowang-opc/cf-token 读取（或 CF_TOKEN 环境变量）。
"""
import base64, hashlib, json, mimetypes, os, sys, urllib.request, urllib.error
from pathlib import Path

try:
    import blake3
except ImportError:
    sys.exit("需要 blake3 库：pip install --break-system-packages blake3")

def wrangler_hash(data: bytes, suffix: str) -> str:
    """与 wrangler 完全一致的 Pages 文件哈希：BLAKE3(base64(内容)+扩展名)前32位"""
    b64 = base64.b64encode(data).decode()
    ext = suffix[1:] if suffix.startswith(".") else suffix
    return blake3.blake3((b64 + ext).encode()).hexdigest()[:32]

BASE = Path(sys.argv[sys.argv.index("--dir")+1] if "--dir" in sys.argv else "~/workspace/laowang-opc").expanduser()
PROJECT = sys.argv[sys.argv.index("--project")+1] if "--project" in sys.argv else "laowang-opc"
TOKEN_FILE = Path.home() / ".config/laowang-opc/cf-token"
EXCLUDE = {"build_reading.py", "deploy.py", "sync_site.sh", ".git", "node_modules", ".DS_Store"}

def token():
    t = os.environ.get("CF_TOKEN")
    return t.strip() if t else TOKEN_FILE.read_text().strip()

def api(method, url, tok, data=None, ctype="application/json"):
    req = urllib.request.Request(url, method=method,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": ctype},
        data=json.dumps(data).encode() if data is not None else None)
    try:
        return json.load(urllib.request.urlopen(req, timeout=60))
    except urllib.error.HTTPError as e:
        body = e.read()[:800].decode(errors="replace")
        raise RuntimeError(f"HTTP {e.code} {url}\n{body}")

def collect():
    files = {}
    for p in sorted(BASE.rglob("*")):
        if not p.is_file(): continue
        rel = p.relative_to(BASE)
        if rel.parts[0] in EXCLUDE or p.name == ".DS_Store": continue
        files["/" + rel.as_posix()] = p
    return files

def main():
    tok = token()
    files = collect()
    items = []  # (web_path, hash, size, data, ctype)
    for web_path, p in files.items():
        data = p.read_bytes()
        h = wrangler_hash(data, p.suffix)
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        if p.suffix == ".html": ctype = "text/html"
        if p.suffix == ".css": ctype = "text/css"
        items.append((web_path, h, len(data), data, ctype))
    print(f"文件 {len(items)} 个，共 {sum(i[2] for i in items)/1024:.1f} KB")

    # account id（从 zone 反查）
    zone = api("GET", "https://api.cloudflare.com/client/v4/zones?name=laowang-opc.com", tok)["result"][0]
    aid = zone["account"]["id"]

    # 1. 取 assets 上传 JWT
    jwt = api("GET",
        f"https://api.cloudflare.com/client/v4/accounts/{aid}/pages/projects/{PROJECT}/upload-token",
        tok)["result"]["jwt"]
    ajwt = {"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"}
    def aapi(method, url, data):
        req = urllib.request.Request(url, method=method, headers=ajwt,
                                     data=json.dumps(data).encode())
        try:
            return json.load(urllib.request.urlopen(req, timeout=120))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code} {url}\n{e.read()[:800].decode(errors='replace')}")

    hashes = [h for _, h, _, _, _ in items]
    # 2. 查缺失
    r = aapi("POST", "https://api.cloudflare.com/client/v4/pages/assets/check-missing",
             {"hashes": hashes})
    res = r.get("result")
    missing = set(res if isinstance(res, list) else res.get("missing", res.get("hashes", [])))
    print(f"需上传 {len(missing)}/{len(hashes)} 个文件")
    # 3. 上传缺失文件
    by_hash = {h: (d, c) for _, h, _, d, c in items}
    batch = [{"key": h, "value": base64.b64encode(by_hash[h][0]).decode(),
              "metadata": {"contentType": by_hash[h][1]}, "base64": True}
             for h in missing]
    for i in range(0, len(batch), 50):
        aapi("POST", "https://api.cloudflare.com/client/v4/pages/assets/upload",
             batch[i:i+50])
        print(f"  已上传 {min(i+50, len(batch))}/{len(batch)}")
    # 4. 注册 hashes
    aapi("POST", "https://api.cloudflare.com/client/v4/pages/assets/upsert-hashes",
         {"hashes": hashes})

    # 5. 建部署（manifest: path -> hash 字符串）
    manifest = {wp: h for wp, h, _, _, _ in items}
    boundary = "----cfpages" + hashlib.md5(os.urandom(8)).hexdigest()
    body = bytearray()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(b'Content-Disposition: form-data; name="manifest"\r\n')
    body.extend(b"Content-Type: application/json\r\n\r\n")
    body.extend(json.dumps(manifest).encode() + b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{aid}/pages/projects/{PROJECT}/deployments",
        data=bytes(body), method="POST",
        headers={"Authorization": f"Bearer {tok}",
                 "Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=120))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}\n{e.read()[:800].decode(errors='replace')}")
    r = resp.get("result", {})
    print("success:", resp.get("success"))
    print("deployment:", r.get("id"))
    print("url:", r.get("url"))
    for e in resp.get("errors", []): print("ERROR:", e)

if __name__ == "__main__":
    main()
