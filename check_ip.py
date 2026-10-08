#!/usr/bin/env python3
"""laowang-opc.com 硬指 IP 存活检查。

检查两件事：
1. Cloudflare 权威 DNS：根域与 www 的 A 记录是否仍为 76.223.126.88、且为灰云（proxied=false）。
   —— 用 Cloudflare API 查 zone 记录，不受本机 DNS 劫持影响。
2. 源站可达：https://laowang-opc.com/ 与 https://www.laowang-opc.com/ 是否返回 200。

局限：本机网络走代理，DNS 有劫持（曾返回 198.18.x.x 测试段），因此本脚本
无法验证"国内直连是否被墙"——国内侧仍需用户手机 4G/5G 抽查。本脚本能发现：
配置漂移（有人改了 DNS/开了橙云）、Vercel 换 IP、源站挂掉。

用法: python3 check_ip.py [--json]
退出码: 0=全部正常；1=有异常（DNS 记录漂移或 HTTP 非 200）。
token 从 ~/.config/laowang-opc/cf-token 读取（600 权限文件，不进仓库）。
"""
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

EXPECTED_IP = "76.223.126.88"
DOMAIN = "laowang-opc.com"
TOKEN_FILE = Path.home() / ".config/laowang-opc/cf-token"
API = "https://api.cloudflare.com/client/v4"


def read_token():
    t = os.environ.get("CF_TOKEN")
    if t:
        return t.strip()
    return TOKEN_FILE.read_text().strip()


def api(method, url, tok):
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.load(r)


def check_dns(tok):
    """返回 (ok, details)：权威 A 记录是否符合预期。"""
    zones = api("GET", f"{API}/zones?name={DOMAIN}", tok)["result"]
    if not zones:
        return False, {"error": "zone not found"}
    zid = zones[0]["id"]
    recs = api("GET", f"{API}/zones/{zid}/dns_records?type=A&per_page=50", tok)["result"]
    want = {DOMAIN: None, f"www.{DOMAIN}": None}
    problems = []
    for r in recs:
        if r["name"] in want:
            want[r["name"]] = {"content": r["content"], "proxied": r["proxied"]}
    for name, rec in want.items():
        if rec is None:
            problems.append(f"{name}: 缺少 A 记录")
        elif rec["content"] != EXPECTED_IP:
            problems.append(f"{name}: A 记录变为 {rec['content']}（预期 {EXPECTED_IP}）")
        elif rec["proxied"]:
            problems.append(f"{name}: 被切到橙云（proxied=true），国内访问会走 Cloudflare")
    return (len(problems) == 0), {"records": want, "problems": problems}


def check_http():
    """返回 (ok, details)：双域名 HTTPS 是否 200。"""
    out = {}
    ok = True
    for host in (f"https://{DOMAIN}/", f"https://www.{DOMAIN}/"):
        try:
            p = subprocess.run(
                ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                 "--max-time", "20", host],
                capture_output=True, text=True, timeout=30,
            )
            code = p.stdout.strip()
        except Exception as e:  # noqa: BLE001
            code = f"error: {e}"
        out[host] = code
        if code != "200":
            ok = False
    return ok, out


def main():
    as_json = "--json" in sys.argv
    try:
        tok = read_token()
    except FileNotFoundError:
        print(json.dumps({"ok": False, "error": "cf-token 文件不存在"}))
        return 1
    try:
        dns_ok, dns = check_dns(tok)
    except urllib.error.HTTPError as e:
        dns_ok, dns = False, {"error": f"Cloudflare API HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        dns_ok, dns = False, {"error": str(e)}
    http_ok, http = check_http()
    result = {"ok": dns_ok and http_ok, "expected_ip": EXPECTED_IP,
              "dns_ok": dns_ok, "dns": dns, "http_ok": http_ok, "http": http}
    if as_json or True:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
