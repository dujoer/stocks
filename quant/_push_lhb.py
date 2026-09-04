# -*- coding: utf-8 -*-
"""
将本次「全站 web/ 分层重构」后的全部网页、生成器与数据源推送到 GitHub 仓库 dujoer/stocks。

结构约定（2026-09-04 重构后）：
  - 根 index.html            = 总门户
  - web/<板块>/...           = 各版块按目录分层存放
  - web/docs/DAILY_UPDATE_SOP.html = 操作手册
  - 所有网页均为自包含 HTML（内联 CSS/JS/数据），不依赖外部资源

鉴权方式：读取环境变量 GH_PAT（或 GITHUB_TOKEN）作为 Bearer Token，绝不硬编码。
本地私有 token 文件路径（~/.workbuddy，不在仓库内、不会被上传）：C:/Users/nonoy/.workbuddy/gh_pat.txt
用法：
    set GH_PAT=ghp_xxx
    python quant/_push_lhb.py
说明：本脚本仅做 Contents API 的 create/update；每个文件独立提交，失败不阻断其余。
      强制排除任何含 portfolio / bottom-up / portfolio_analysis 的文件（硬规矩：不对外展示持仓/选股）。
"""
import os, sys, json, base64, glob as _glob, urllib.request, urllib.error

REPO = "dujoer/stocks"
BRANCH = "main"
API = f"https://api.github.com/repos/{REPO}/contents"

# token 仅来自运行时环境 / 本地私有文件，绝不硬编码、绝不以明文写入会被推送的文件。
_LOCAL_TOKEN_FILE = os.path.expanduser("~/.workbuddy/gh_pat.txt")
def _load_token():
    t = os.environ.get("GH_PAT") or os.environ.get("GITHUB_TOKEN")
    if t:
        return t
    try:
        if os.path.exists(_LOCAL_TOKEN_FILE):
            with open(_LOCAL_TOKEN_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return None
TOKEN = _load_token()

# 强制排除名单（路径含以下任一子串即跳过）—— 不对外展示个人持仓 / 选股
EXCLUDE_FRAGMENTS = ("portfolio", "bottom-up", "portfolio_analysis", "_all_store")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# (本地相对仓库根的路径) — 框架 / 生成器 / 门户 / 手册（本次重构真实改动/新增的文件）
FILES = [
    # —— 总门户 + 操作手册 ——
    "index.html",
    "web/docs/DAILY_UPDATE_SOP.html",
    # —— 导航与门户/总览生成器 ——
    "quant/_nav.py",
    "quant/build_dashboards.py",
    "quant/build_portal.py",
    "quant/build_sections.py",
    "quant/_apply_nav.py",
    "quant/_link_check.py",
    "quant/_push_lhb.py",
    "quant/_fix_archive_nav.py",
    # —— 龙虎榜 + 游资 + 当日快照 ——
    "quant/build_lhb_enriched.py",
    "quant/build_sw1_mapping.py",
    "quant/_merge_lhb_subtabs.py",
    "quant/gen_lhb_nextday_backtest.py",
    "quant/build_interactive_sector.py",
    # —— 高管增减持（董监高）——
    "quant/gen_exec.py",
    "quant/build_exec.py",
    "quant/exec_elite_xref.json",
    # —— 板块强度子系统 ——
    "quant/gen_sector_raw.py",
    "quant/run_daily_sector.py",
    "quant/build_sector_strength.py",
    "quant/build_sector_trend.py",
    "quant/build_sector_index.py",
    # —— 大宗交易 ——
    "quant/gen_block.py",
    "quant/build_block.py",
    # —— 个股调研 / 行业最强榜 ——
    "quant/build_research_301110.py",
    "quant/build_research_600838.py",
    "quant/build_q2_industry_page.py",
    # —— 行业知名 Top20 私募/牛散 策划清单 + 5544 只全市场 Q2 中报真实现身佐证 + 机会扫描器 + 股票增持扫描 ——
    "quant/_shareholder/build_top_elite.py",
    "quant/_shareholder/scan_elite_coverage.py",
    "quant/_shareholder/build_stock_accumulation.py",
    "quant/_shareholder/elite_coverage.json",
    "quant/_shareholder/_quotes_elite.json",
    "quant/_shareholder/_elite_codes.json",
    # —— 重构/自检辅助脚本（记录本次分层过程，便于复现）——
    "quant/_cleanup_flat.py",
    "quant/_verify_dupes.py",
    "quant/_fix_psy_paths.py",
]

# 自动纳入「带日期/版块」的页面与数据源，保证每一页都带统一导航、且数据可复现。
# 与 FILES 去重；EXCLUDE_FRAGMENTS 仍生效（不推送持仓/选股类文件）。
_AUTO_PATTERNS = [
    # 所有分层网页（递归）
    "web/**/*.html",
    # 龙虎榜 / 行情 / 涨停 / 大盘 当日与历史快照
    "quant/lhb/2026-*.json",
    "quant/quotes/2026-*.json",
    "quant/board_hot/2026-*.json",
    "quant/limitup/2026-*.json",
    "quant/market_overview/2026-*.json",
    "quant/exec_chg/2026-*.json",
    "quant/lhb_detail/*.json",
    # 板块强度
    "quant/sector_industry_2026*.json",
    "quant/sector_concept_2026*.json",
    "quant/sector_strength_data_2026*.json",
    "quant/sector_daily/2026-*.json",
    "quant/sector_trend.json",
    # 大宗交易
    "quant/block_chg/2026-*.json",
    "quant/quotes/block_2026-*.json",
    # 龙虎榜富集 / 次日回测 / 要闻 / 申万映射
    "quant/lhb_enriched_*.json",
    "quant/lhb_nextday_backtest/2026-*.json",
    "quant/sw2_chg_live.json",
    "quant/sw1_detail.json",
    "quant/news.json",
    # 心理雷达构建脚本（仍在 market-trend/，输出到 web/psychology/）
    "market-trend/*.py",
]
_AUTO_ADDED = []
for _pat in _AUTO_PATTERNS:
    for _p in sorted(_glob.glob(os.path.join(ROOT, _pat), recursive=True)):
        _rel = os.path.relpath(_p, ROOT).replace(os.sep, "/")
        if _rel not in FILES:
            FILES.append(_rel)
            _AUTO_ADDED.append(_rel)
if _AUTO_ADDED:
    print(f"[auto] 纳入 {len(_AUTO_ADDED)} 个带日期/版块页面与数据源以确保结构一致")

def api_req(url, data=None, method="GET"):
    import time as _time
    last = None
    for _attempt in range(4):
        try:
            req = urllib.request.Request(url, data=data, method=method)
            req.add_header("Authorization", f"Bearer {TOKEN}")
            req.add_header("Accept", "application/vnd.github+json")
            if data is not None:
                req.add_header("Content-Type", "application/json")
            return urllib.request.urlopen(req, timeout=120)
        except (urllib.error.HTTPError,) as e:
            if e.code == 404:
                raise
            last = e
            _time.sleep(2 + _attempt * 2)
        except Exception as e:  # 瞬时网络错误（IncompleteRead / 连接重置等）重试
            last = e
            _time.sleep(2 + _attempt * 2)
    raise last

def get_sha(path):
    try:
        with api_req(f"{API}/{path}?ref={BRANCH}") as r:
            return json.load(r).get("sha")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise

def push_file(rel):
    if any(frag in rel for frag in EXCLUDE_FRAGMENTS):
        print(f"  ⛔ 跳过(命中排除名单): {rel}")
        return
    local = os.path.join(ROOT, rel)
    if not os.path.exists(local):
        print(f"  跳过(不存在): {rel}")
        return
    with open(local, "rb") as f:
        content = base64.b64encode(f.read()).decode("ascii")
    sha = get_sha(rel)
    body = {
        "message": f"refactor: 全站 web/ 分层重构 + 统一导航与门户（{rel})",
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
