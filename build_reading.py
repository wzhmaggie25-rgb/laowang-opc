#!/usr/bin/env python3
"""把最新一期《老王的阅读杂志》转成公开版目录页（标题+中文摘要+原文链接，不含全文翻译）。
用法: python3 build_reading.py [--all]
  默认只处理最新一期；--all 处理全部历史期数。
输出: reading/index.html（最新一期）+ reading/YYYY-MM-DD.html（各期归档）
"""
import re, sys, html as ihtml
from pathlib import Path
from datetime import date

BASE = Path(__file__).parent
DIGEST_FILES = Path.home() / "workspace/goals/daily-subscription-reading-digest/files"
READING = BASE / "reading"

def parse_issue(path: Path):
    raw = path.read_text(encoding="utf-8")
    m = re.search(r"第(\d+)期-(\d{4})(\d{2})(\d{2})", path.name)
    n, y, mo, d = m.groups()
    day = f"{y}-{mo}-{d}"

    # 文章: div.srcname + article[id]
    articles = {}   # anchor_id -> dict
    order = []      # [(srcname, anchor_id)]
    cur_src = ""
    for mm in re.finditer(r'<div class="srcname">(.*?)</div>|<article id="([^"]+)">(.*?)</article>', raw, re.S):
        if mm.group(1) is not None:
            cur_src = ihtml.unescape(re.sub(r"<[^>]+>", "", mm.group(1))).strip()
        else:
            aid, body = mm.group(2), mm.group(3)
            t = re.search(r'<h3><a href="([^"]+)"[^>]*>(.*?)</a></h3>', body, re.S)
            meta = re.search(r'<div class="art-meta">(.*?)</div>', body, re.S)
            summ = re.search(r'<div class="summary">.*?<p>(.*?)</p>', body, re.S)
            if not t:
                continue
            url = t.group(1)
            title = ihtml.unescape(re.sub(r"<[^>]+>", "", t.group(2))).strip()
            meta_txt = ihtml.unescape(re.sub(r"<[^>]+>", "", meta.group(1))).strip() if meta else ""
            summ_txt = ihtml.unescape(re.sub(r"<[^>]+>", "", summ.group(1))).strip() if summ else ""
            articles[aid] = dict(title=title, url=url, meta=meta_txt, summary=summ_txt, src=cur_src)
            order.append((cur_src, aid))

    # 今日推荐
    recs = []
    rm = re.search(r'<section class="recs">(.*?)</section>', raw, re.S)
    if rm:
        for r in re.finditer(r'<div class="rec">\s*<a href="#([^"]+)">(.*?)</a>\s*<p>(.*?)</p>', rm.group(1), re.S):
            aid, rtitle, rnote = r.group(1), r.group(2).strip(), r.group(3).strip()
            art = articles.get(aid, {})
            recs.append(dict(
                title=ihtml.unescape(rtitle),
                note=ihtml.unescape(re.sub(r"<[^>]+>", "", rnote)).strip(),
                url=art.get("url", "#"),
                src=art.get("src", ""),
            ))

    # X 每日速览
    tweets = []
    xm = re.search(r'<section class="xsec">(.*?)</section>', raw, re.S)
    if xm:
        seg = xm.group(1)
        xnote = re.search(r'<p class="xnote">(.*?)</p>', seg, re.S)
        xnote_txt = ihtml.unescape(re.sub(r"<[^>]+>", "", xnote.group(1))).strip() if xnote else ""
        cur_person, cur_handle = "", ""
        for t in re.finditer(
            r'<div class="xperson">(.*?)<span class="xhandle">(.*?)</span></div>|'
            r'<div class="xtweet">\s*<p class="xzh">(.*?)</p>\s*<p class="xen">(.*?)</p>\s*'
            r'<div class="xmeta">(.*?)\s*·\s*<a href="([^"]+)"', seg, re.S):
            if t.group(1) is not None:
                cur_person = ihtml.unescape(t.group(1)).strip()
                cur_handle = ihtml.unescape(t.group(2)).strip()
            else:
                zh = ihtml.unescape(re.sub(r"<[^>]+>", "", t.group(3))).strip()
                tm = ihtml.unescape(re.sub(r"<[^>]+>", "", t.group(5))).strip()
                url = t.group(6)
                tweets.append(dict(person=cur_person, handle=cur_handle, zh=zh, time=tm, url=url))
    else:
        xnote_txt = ""

    return dict(day=day, n=n, recs=recs, articles=articles, order=order,
                tweets=tweets, xnote=xnote_txt)

def esc(s): return ihtml.escape(s, quote=True)

def render(iss, all_days):
    day, n = iss["day"], iss["n"]
    parts = ["""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>每日阅读 · {day} · 老王</title>
<meta name="description" content="老王的阅读杂志公开目录（{day}）：14 个英文信源中文摘要与今日推荐，全文版在私密阅读站。">
<link rel="stylesheet" href="/styles.css">
</head>
<body>
<nav><div class="wrap">
<a class="brand" href="/">老王</a>
<a class="nav-link" href="/#products">产品</a>
<a class="nav-link" href="/reading/">每日阅读</a>
<a class="nav-link" href="/#about">关于我</a>
</div></nav>
<div class="wrap">
<header class="hero" style="padding-bottom:16px">
<h1>每日阅读 · 公开目录</h1>
<p class="tagline">14 个英文订阅源每天的中文目录：<strong>标题 + 中文摘要 + 原文链接</strong>。<br>全文翻译版在私密阅读站，<a href="/#contact">加微信获取阅读权限</a>。</p>
</header>
<section>
<h2>{day}（第 {n} 期）</h2>
<p class="sub">每天早上更新 · 摘要免费看，全文私密阅读</p>
""".format(day=day, n=n)]

    if iss["recs"]:
        parts.append('<h2 style="margin-top:8px">今日推荐</h2><p class="sub">今天最值得读的几篇</p>')
        for r in iss["recs"]:
            parts.append(
                f'<div class="pick"><div class="pick-label">今日推荐{r["src"] and " · "+esc(r["src"])}</div>'
                f'<h4><a href="{esc(r["url"])}" target="_blank" rel="noopener">{esc(r["title"])}</a></h4>'
                f'<p>{esc(r["note"])}</p></div>')

    # 按来源分组的文章目录
    parts.append('<h2 style="margin-top:28px">全部文章目录</h2><p class="sub">按来源分组 · 点标题读英文原文</p>')
    last_src = None
    for src, aid in iss["order"]:
        a = iss["articles"][aid]
        if src != last_src:
            if last_src is not None:
                parts.append('</div>')
            parts.append(f'<div class="day-block"><h3>{esc(src or "未分类")}</h3>')
            last_src = src
        summ_html = f'<div style="font-size:14px;color:#666;margin-top:4px">{esc(a["summary"])}</div>' if a["summary"] else ""
        parts.append(
            f'<div class="article"><a href="{esc(a["url"])}" target="_blank" rel="noopener">{esc(a["title"])}</a>{summ_html}</div>')
    if last_src is not None:
        parts.append('</div>')

    if iss["tweets"]:
        parts.append('<h2 style="margin-top:28px">X 每日速览</h2>'
                     f'<p class="sub">{esc(iss["xnote"])}</p>')
        for t in iss["tweets"][:30]:
            parts.append(
                f'<div class="article"><span class="src">{esc(t["person"])}</span>'
                f'<a href="{esc(t["url"])}" target="_blank" rel="noopener">{esc(t["zh"])}</a>'
                f'<div style="font-size:13px;color:#999">{esc(t["time"])}</div></div>')

    if len(all_days) > 1:
        parts.append('<h2 style="margin-top:28px">往期目录</h2><p class="sub">过往每天的公开目录</p>')
        for d2 in all_days:
            if d2 == day:
                continue
            parts.append(f'<div class="article"><a href="/reading/{d2}.html">{d2}</a></div>')

    parts.append("""</section>
</div>
<footer><div class="wrap">
<span>© 2026 老王 · laowang-opc.com</span>
<span><a href="/">返回首页</a></span>
</div></footer>
</body></html>""")
    return "\n".join(parts)

def main():
    files = sorted(DIGEST_FILES.glob("老王的阅读杂志-第*期-*.html"))
    if not files:
        print("no issues found"); return
    targets = files if "--all" in sys.argv else files[-1:]
    READING.mkdir(parents=True, exist_ok=True)
    days = []
    for f in sorted(files):
        m = re.search(r"(\d{4})(\d{2})(\d{2})", f.name)
        days.append(f"{m.group(1)}-{m.group(2)}-{m.group(3)}")
    for f in targets:
        iss = parse_issue(f)
        out = READING / f'{iss["day"]}.html'
        out.write_text(render(iss, days), encoding="utf-8")
        print("wrote", out, f'articles={len(iss["order"])} recs={len(iss["recs"])} tweets={len(iss["tweets"])}')
    # index.html 指向最新一期
    latest = targets[-1]
    m = re.search(r"(\d{4})(\d{2})(\d{2})", latest.name)
    latest_day = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    (READING / "index.html").write_text(
        (READING / f"{latest_day}.html").read_text(encoding="utf-8"), encoding="utf-8")
    print("index.html ->", latest_day)

if __name__ == "__main__":
    main()
