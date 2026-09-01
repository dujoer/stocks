# -*- coding: utf-8 -*-
"""
将本次「中报股东动向」新增/改动文件推送到 GitHub 仓库 dujoer/stocks。
鉴权方式：读取环境变量 GH_PAT（或 GITHUB_TOKEN）作为 Bearer Token，绝不硬编码。
用法：
    set GH_PAT=ghp_xxx
    python quant/_push_q2.py
说明：本脚本仅做 Contents API 的 create/update；每个文件独立提交，失败不阻断其余。
"""
import os, sys, json, base64, urllib.request, urllib.error

REPO = "dujoer/stocks"
BRANCH = "main"
TOKEN = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
API = f"https://api.github.com/repos/{REPO}/contents"

# (本地相对仓库根的路径) — 本次真实改动/新增的文件
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    # 主交付物：全市场中报行业最强榜
    "web/2026-q2-industry-elite.html",
    "quant/build_q2_industry_page.py",
    # 导航挂载点（均已写入生成器，重建不丢）
    "index.html",
    "web/index.html",
    "quant/build_dashboards.py",
    "quant/build_portal.py",
]

def api_req(url, data=None, method="GET"):
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Accept", "application/vnd.github+json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    return urllib.request.urlopen(req, timeout=60)

def get_sha(path):
    try:
        with api_req(f"{API}/{path}?ref={BRANCH}") as r:
            return json.load(r).get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

def push_file(rel):
    local = os.path.join(ROOT, rel)
    if not os.path.exists(local):
        print(f"  跳过(不存在): {rel}")
        return
    with open(local, "rb") as f:
        content = base64.b64encode(f.read()).decode("ascii")
    sha = get_sha(rel)
    body = {
        "message": f"chore: 新增 2026中报 牛散/私募/公募 Q2持仓动向 版块 ({rel})",
        "content": content,
        "branch": BRANCH,
    }
    if sha:
        body["sha"] = sha
    url = f"{API}/{rel}"
    try:
        with api_req(url, data=json.dumps(body).encode("utf-8"), method="PUT") as r:
            ok = json.load(r)
            print(f"  {'更新' if sha else '新建'} 成功: {rel} -> {ok.get('commit',{}).get('html_url','')}")
    except urllib.error.HTTPError as e:
        print(f"  ❌ 失败 {rel}: HTTP {e.code} {e.read().decode('utf-8','replace')[:200]}")

if __name__ == "__main__":
    if not TOKEN:
        print("未检测到 GH_PAT / GITHUB_TOKEN 环境变量，无法推送。")
        print("请先执行： set GH_PAT=你的GitHubPAT  然后再运行本脚本。")
        sys.exit(2)
    print(f"推送到 {REPO}@{BRANCH} ...")
    for rel in FILES:
        push_file(rel)
    print("完成。")
