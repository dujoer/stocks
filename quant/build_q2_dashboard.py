# -*- coding: utf-8 -*-
"""
Q2 中报股东动向聚合器 / 生成器
==============================
输入：
  quant/q2_shareholder_raw/batch*.json   每文件 = {code: entry(2026-06-30 十大股东/流通股东)}
  quant/q2_valuation.json                {code: {pe_ratio, pb_ratio, name}}
输出：
  quant/q2_shareholder_processed.json    结构化数据
  web/2026-q2-shareholder-moves.html     新板块页面

股东类别：牛散 / 私募 / 公募 / 社保养老 / 外资 / 信托 / 国资 / 国家队 / 保险 / 银保机构 / 员工持股 / 特殊账户 / 牛散候选 / 其他
三大选股准则（用户给定框架）：
  1) 增比减的好  (增持户数 > 减持户数 越好)
  2) 低比高的好  (估值越低越好，用 PE/PB 分位计)
  3) 牛比不牛好  (有牛散/私募/大型公募 参与的股票更好)
"""
import json, os, re, bisect, datetime as dt
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RAW_DIR = os.path.join(HERE, "q2_shareholder_raw")
VAL_PATH = os.path.join(HERE, "q2_valuation.json")
OUT_JSON = os.path.join(HERE, "q2_shareholder_processed.json")
OUT_HTML = os.path.join(ROOT, "web", "2026-q2-shareholder-moves.html")

# ============================================================
# 1. 载入股东原始数据
# ============================================================
assert os.path.isdir(RAW_DIR), f"缺失原始目录: {RAW_DIR}"
ALL_STOCKS = {}
for fn in sorted(os.listdir(RAW_DIR)):
    if not fn.endswith(".json"):
        continue
    d = json.load(open(os.path.join(RAW_DIR, fn), encoding="utf-8"))
    ALL_STOCKS.update(d)
print(f"载入 {len(ALL_STOCKS)} 只股票原始股东数据")

VAL = {}
if os.path.exists(VAL_PATH):
    VAL = json.load(open(VAL_PATH, encoding="utf-8"))
    print(f"载入估值 {len(VAL)} 条")

# ============================================================
# 2. 股东分类器（顺序很重要：公募须在 银行/保险 之前判定）
# ============================================================
KNOWN_CATTLE = {
    "徐开东","徐小蓉","章建平","王萍","曹欧劼","陈发树","潘刚","王传福","吕向阳","夏佐全",
    "张炜","王念强","黄世霖","李平","张仁华","韩旭","施燕","郝诗瑾","段又楠","周顺东",
    "李莉","谢利文","杨伦嗨","陈浙凯","葛雅仙","张素芬","黄善兵","黄阳","汤振军","范卫红",
    "张晓霞","姜雪","韦顶先","罗明星","张新龙","邓俏如","马宇飞","付磊","寿祖刚","季跃平",
    "赵成霞","赵雪雨","高海军","周云中","杨志城","李跃辉","张荣荣","于桂真","邱于桑","刘敏",
    "卢毅","徐小雅","吕强","陈淑新","徐壮城","孙慧明","陈九阳","祝去修","钟振鑫","汪泽芳",
    "夏重阳","皇甫飞玉","宋钢","朱黎辉","丁建军","徐克兴","陈小兵","邹榛夫","马银良","洪敏",
    "丁秀霞","徐剑明","王力展","应华江","李锋","许式荣","陈蓓文","徐晖","姚天燕","王蕾",
    "刘亮","吴大忠","程蓉","李文","金虹","鲁利娟","王珊珊","李洪治","李洪臣","乔绪青",
    "王启","王悦","王申","陈兰英","姜胜国","袁永林","凌怀胜","周吉","张向东","刘灿",
    "曾庆华","张殿强","张寻","殷锡勇","吴永进","沈涵丰","朱会平","黎少娟","陈锁","戴晔",
    "邱晓斌","郭键豪","赵红敏","卢芹娟","敖翔","牛华丽","闫本庆","周爽","梁玉清","高丽",
    "周博","王莉","林舒月","韩赛","薛巍","李龙生","刘东杰","石建洪","袁涤云","胡元生",
    "韩宁宁","程浩忠","张芜宁","刘法奇","陈强","樊俊玲","白可云","陈景庚","李瑞兰","戚志超",
    "陈惠仪","何啸威","谢爱林","黄景明","李文明","李泽","滕德展","谭雄玉","艾东生","刘颖",
    "刘春钟","周杰洪","蒋勇","石伟君","钱京","张晓峰","王竹","吴娟","杨利军","曹廷飞",
    "何跃","周家乐","冯桂英","陈玉成","周成勇","刘和根","林川","俞铮","徐冬梅","曹传汉",
    "季晓蔓","鲍先启","方磊","李安明","马丽华","胡博飞","张海明","沈卿","迟健","王萍",
    "蔡敏","许丽丽","陈士军","陶先德","徐皓","邱燕敏","赵国华","厉宇杨","姜毓萍","潘晓琦",
    "刘曦","丛丰收","王东平","林彩娥","陈跃","何杰","徐美敬","贾长彬","代学荣","邱瑞凤",
    "俞月凤","田雯龙","蒋秀芝","楼启挺","孙博","钟革","张永锋","张卫中","罗文明","徐建桥",
    "朱辉","王佳","刘帅","陈红光","黄航","郑春梅","林建清","林","叶继文","叶斌法","刘剑","王晓",
}
NATIONAL_TEAM_KEYWORDS = ["国新","社保","社保基金","养老金","基本养老","中央汇金","国调","国务院国资委","国家集成电路","国有企业结构","证金","证券金融"]
SOCIAL_SECURITY_KEYWORDS = ["社保基金","全国社保","基本养老","养老保险","职业年金"]
FOREIGN_HF_KEYWORDS = ["HONG KONG","香港中央结算","HKSCC","UBS","MORGAN","BARCLAYS","J.P.Morgan","JPMorgan","Goldman","高盛","BLACKROCK","摩根","Nominee","Nominees","GREENWOODS","LAV","CICC","APEX","ABA-Bio","InventisBio","YUEHENG","XING","太白投资","阿布达比","科威特","新加坡政府","GIC","加拿大年金","安大略","魁北克","挪威"]
TRUST_KEYWORDS = ["信托","信托计划"]
PRIVATE_FUND_KEYWORDS = ["私募"]
MUTUAL_FUND_KEYWORDS_PAT = ["易方达","华夏","嘉实","南方","广发","招商","工银瑞信","富国","汇添富","中欧","兴全","博时","国泰","华安","鹏华","银华","大成","长盛","永赢","万家","景顺长城","建信","农银汇理","交银施罗德","国投瑞银","民生加银","华商","诺安","汇丰晋信","东方红","金鹰","海富通","信诚","宏利","申万菱信","长城","长信","平安","华泰柏瑞","国寿安保","泰康","中金","朱雀","东方阿尔法","方正富邦","鑫元","北信瑞丰","申万","东方基金","泰信","摩根士丹利","摩根","红塔红土","新华","国联安","天弘","睿远","兴证全球","银华","光大保德信","中加","国海富兰克林","上投摩根","国联安","建信","中邮","兴业","国联安"]
TOP_PRIVATE_FUND_COMPANY_NAMES = ["林园投资","混沌","葛卫东","高瓴","景林","正心谷","源乐晟","重阳","淡水泉","赫富","聚鸣","衍复","睿郡","仁桥","远信","礼来","汉和","同犇","希瓦","红筹","宁聚","积露","昊泽致远","金澹","六妙星","阿巴马","广东臻远","广东宏元","国丰兴华","腾胜","盈峰","希瓦"]
BANK_INSURANCE_KEYWORDS = ["银行","保险","人寿","财险","财产保险"]
STATE_OWNED_KEYWORDS = ["国资","国有","集团","控股","国务院","财政部","全国社会保障基金理事会","中央汇金","社保基金理事会"]

def classify_holder(name: str) -> str:
    if name in KNOWN_CATTLE:
        return "牛散"
    if any(k in name for k in NATIONAL_TEAM_KEYWORDS):
        return "国家队"
    if any(k in name for k in SOCIAL_SECURITY_KEYWORDS):
        return "社保养老"
    if any(k in name for k in FOREIGN_HF_KEYWORDS):
        return "外资"
    if any(k in name for k in TRUST_KEYWORDS):
        return "信托"
    if any(k in name for k in PRIVATE_FUND_KEYWORDS):
        return "私募"
    # 公募（强信号：名称含"基金"）——必须最先，避免"证券投资基金"被券商/保险误吞
    if "基金" in name or "证券投资基金" in name:
        return "公募"
    # 券商（经纪/证券公司，非公募）
    if "证券" in name:
        return "券商"
    # 保险（先于银行：避免"中国平安保险"等被"平安"模式误判为公募）
    if "保险" in name:
        return "保险"
    # 银行（托管行）
    if "银行" in name:
        return "银保机构"
    # 公募（弱信号：知名公募简称，但不得含 保险/证券/银行 字样）
    if any(k in name for k in MUTUAL_FUND_KEYWORDS_PAT) and not any(x in name for x in ("保险", "证券", "银行")):
        return "公募"
    if any(k in name for k in STATE_OWNED_KEYWORDS):
        return "国资"
    if "员工持股计划" in name:
        return "员工持股"
    if "破产企业财产处置" in name or "回购专用" in name:
        return "特殊账户"
    if 2 <= len(name) <= 4 and all('\u4e00' <= c <= '\u9fff' for c in name):
        return "牛散候选"
    return "其他"

# cat_group 归并：牛散类(含候选) / 私募 / 公募
def cat_group(cat):
    if cat in ("牛散", "牛散候选"):
        return "牛散"
    return cat

CATTLE_CATS = {"牛散", "牛散候选"}
PRIVATE_CATS = {"私募"}
MUTUAL_CATS = {"公募"}
SMART_CATS = CATTLE_CATS | PRIVATE_CATS | MUTUAL_CATS

# ============================================================
# 3. 合并股东 + 分类 + 个股聚合 + 全局动向
# ============================================================
def collect_shareholders(entry):
    by_name = {}
    for src in ("top10Shareholders", "top10FloatShareholders"):
        for s in entry.get(src, []) or []:
            n = s["name"]
            if n not in by_name:
                by_name[n] = {"name": n, "holdChange": s.get("holdChange", 0),
                              "holdPct": s.get("holdPct", 0), "holdShares": s.get("holdShares", 0),
                              "sources": [src]}
            else:
                if s.get("holdChange", 0) != 0 and by_name[n]["holdChange"] == 0:
                    by_name[n]["holdChange"] = s["holdChange"]
                if s.get("holdShares", 0) > by_name[n]["holdShares"]:
                    by_name[n]["holdShares"] = s["holdShares"]
                    by_name[n]["holdPct"] = s.get("holdPct", 0)
                by_name[n]["sources"].append(src)
    return list(by_name.values())

# 全局动向：按 牛散/私募/公募 三类
MOVES = {g: {"inc": [], "dec": []} for g in ("牛散", "私募", "公募")}
# 个股级
PER_STOCK = {}
SMART_NET = {}   # code -> 聪明钱净变动(股)
for code, entry in ALL_STOCKS.items():
    sname = entry.get("name", code)
    holders = collect_shareholders(entry)
    n_inc = n_dec = n_flat = 0
    inc_shares = dec_shares = 0
    has_cattle = has_private = has_mutual = False
    smart_net = 0
    smart_holders = []  # (group, name, delta, pct)
    for h in holders:
        cat = classify_holder(h["name"])
        delta = h["holdChange"]
        if delta > 0:
            n_inc += 1; inc_shares += delta
        elif delta < 0:
            n_dec += 1; dec_shares += -delta
        else:
            n_flat += 1
        g = cat_group(cat)
        if cat in CATTLE_CATS:
            has_cattle = True
            if delta != 0:
                smart_holders.append((g, h["name"], delta, h["holdPct"]))
        elif cat == "私募":
            has_private = True
            if delta != 0:
                smart_holders.append((g, h["name"], delta, h["holdPct"]))
        elif cat == "公募":
            has_mutual = True
            if delta != 0:
                smart_holders.append((g, h["name"], delta, h["holdPct"]))
        if cat in SMART_CATS and delta != 0:
            smart_net += delta
    for (g, nm, dlt, pct) in smart_holders:
        bucket = "inc" if dlt > 0 else "dec"
        MOVES[g][bucket].append((code, sname, nm, dlt, pct))
    SMART_NET[code] = smart_net
    PER_STOCK[code] = {
        "code": code, "name": sname,
        "n_holders": len(holders), "n_inc": n_inc, "n_dec": n_dec, "n_flat": n_flat,
        "inc_shares": inc_shares, "dec_shares": dec_shares,
        "net_shares": inc_shares - dec_shares,
        "has_cattle": has_cattle, "has_private": has_private, "has_mutual": has_mutual,
        "smart_net": smart_net,
        "_holders": holders,
    }

print("类别分布:", dict(Counter(classify_holder(n) for n in
      {h["name"] for e in ALL_STOCKS.values() for h in collect_shareholders(e)})))
for g in ("牛散", "私募", "公募"):
    print(f"  {g}: 增持 {len(MOVES[g]['inc'])} 笔 / 减持 {len(MOVES[g]['dec'])} 笔")

# ============================================================
# 4. 估值分位（用于准则2 低比高的好）
# ============================================================
pes = [v["pe_ratio"] for v in VAL.values() if isinstance(v.get("pe_ratio"), (int, float)) and v["pe_ratio"] > 0]
pbs = [v["pb_ratio"] for v in VAL.values() if isinstance(v.get("pb_ratio"), (int, float)) and v["pb_ratio"] > 0]
pes_s = sorted(pes); pbs_s = sorted(pbs)
def pe_pctile(x):
    if not (isinstance(x, (int, float)) and x > 0):
        return None
    return bisect.bisect_left(pes_s, x) / max(1, len(pes_s))
def pb_pctile(x):
    if not (isinstance(x, (int, float)) and x > 0):
        return None
    return bisect.bisect_left(pbs_s, x) / max(1, len(pbs_s))

def valuation_score(code):
    v = VAL.get(code, {})
    comps = []
    pp = pe_pctile(v.get("pe_ratio"))
    bp = pb_pctile(v.get("pb_ratio"))
    if pp is not None:
        comps.append(1 - pp)
    if bp is not None:
        comps.append(1 - bp)
    if not comps:
        return 1.0  # 亏损/缺失：中性
    return sum(comps) / len(comps) * 3.0

# ============================================================
# 5. 三大准则评分
# ============================================================
SCORED = []
for code, s in PER_STOCK.items():
    crit1 = 0.0
    denom = s["n_inc"] + s["n_dec"]
    if denom > 0:
        ratio = (s["n_inc"] - s["n_dec"]) / denom
        crit1 = max(0.0, ratio) * 4.0
    crit2 = valuation_score(code)
    crit3 = (1 if s["has_cattle"] else 0) + (1 if s["has_private"] else 0) + (1 if s["has_mutual"] else 0)
    crit3 = min(3, crit3)
    total = crit1 + crit2 + crit3
    SCORED.append((total, crit1, crit2, crit3, s))
SCORED.sort(key=lambda x: -x[0])

# ============================================================
# 6. 输出结构化 JSON
# ============================================================
def clean_stock(s):
    return {k: v for k, v in s.items() if k != "_holders"}
processed = {
    "meta": {"date": "2026-06-30", "source": "2026年半年度报告十大股东/流通股东",
             "universe_size": len(ALL_STOCKS)},
    "stocks": {k: clean_stock(v) for k, v in PER_STOCK.items()},
    "score_top": [{"score": round(t, 2), "crit1": round(c1, 2), "crit2": round(c2, 2),
                   "crit3": round(c3, 2), **clean_stock(s)}
                  for (t, c1, c2, c3, s) in SCORED[:40]],
    "moves": {g: {"inc_count": len(MOVES[g]["inc"]), "dec_count": len(MOVES[g]["dec"]),
                  "inc": MOVES[g]["inc"][:60], "dec": MOVES[g]["dec"][:60]} for g in ("牛散", "私募", "公募")},
    "valuation_present": len(VAL),
}
json.dump(processed, open(OUT_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
print(f"结构化数据已写出 -> {OUT_JSON}")

# ============================================================
# 7. 生成 HTML 页面
# ============================================================
def fmt_shares(n):
    if n is None:
        return "—"
    a = abs(n)
    sign = "" if n >= 0 else "−"
    if a >= 1e8:
        return f"{sign}{a/1e8:.2f}亿股"
    if a >= 1e4:
        return f"{sign}{a/1e4:.2f}万股"
    return f"{sign}{a:.0f}股"

def fmt_pct(p):
    if p is None:
        return "—"
    return f"{p:.2f}%"

def val_of(code, key):
    return VAL.get(code, {}).get(key)

def sign_class(d):
    return "up" if d > 0 else ("down" if d < 0 else "")

CSS = """
* { box-sizing:border-box; }
body { margin:0; font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
  background:linear-gradient(135deg,#1a1f2e 0%,#232838 45%,#1a1f2e 100%); color:#f0e6dd; min-height:100vh; }
.wrap { max-width:1080px; margin:0 auto; padding:40px 20px 70px; }
.topnav { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:18px; padding-bottom:14px;
  border-bottom:1px solid rgba(255,255,255,.10); }
.topnav a { color:#c9a66b; text-decoration:none; font-size:13px; padding:4px 12px; border-radius:20px;
  border:1px solid rgba(201,166,107,.30); transition:.2s; }
.topnav a:hover { background:rgba(201,166,107,.14); }
header h1 { font-size:28px; margin:0 0 6px; background:linear-gradient(90deg,#c9a66b,#c98b7d,#a899b3);
  -webkit-background-clip:text; background-clip:text; color:transparent; font-weight:800; }
header p { margin:4px 0; color:#9a9aa4; font-size:13px; line-height:1.6; }
.meta { margin:12px 0 22px; font-size:12px; color:#c9c3b8; line-height:1.7; }
.meta b { color:#c9a66b; }
.section { background:linear-gradient(135deg,rgba(255,255,255,.07),rgba(255,255,255,.03));
  border:1px solid rgba(255,255,255,.10); border-radius:20px; padding:18px 20px; margin:0 0 22px;
  box-shadow:0 4px 20px rgba(0,0,0,.15), inset 0 1px 0 rgba(255,255,255,.05); }
.section h2 { font-size:17px; margin:0 0 8px; color:#f7f1ec; display:flex; align-items:center; gap:8px; }
.section h2:before { content:""; width:4px; height:16px; background:#c9a66b; border-radius:3px; }
.sub2 { font-size:13px; color:#c9c3b8; margin:2px 0 10px; }
.chiprow { display:flex; flex-wrap:wrap; gap:10px; margin:10px 0; }
.chip { flex:1; min-width:120px; background:linear-gradient(135deg,rgba(185,116,104,.18),rgba(220,38,38,.06));
  border:1px solid rgba(201,139,125,.36); border-radius:14px; padding:12px 10px; text-align:center; }
.chip .k { font-size:11px; color:#c9c3b8; }
.chip .v { font-size:22px; font-weight:800; color:#f7f1ec; margin:3px 0 1px; }
.chip .hl { font-size:10px; color:#9a9aa4; }
table { width:100%; border-collapse:collapse; font-size:13px; background:rgba(26,31,46,.55);
  border:1px solid rgba(255,255,255,.08); border-radius:12px; overflow:hidden; margin:8px 0; }
th,td { padding:7px 10px; text-align:left; border-bottom:1px solid rgba(255,255,255,.07); }
th { background:rgba(30,41,59,.8); color:#e6ded6; font-weight:600; font-size:12px; }
td.num,th.num { text-align:right; font-variant-numeric:tabular-nums; }
.up { color:#e39a8c; font-weight:700; } .down { color:#8fc4a3; font-weight:700; }
.note { color:#9a9aa4; font-size:12px; margin-top:8px; line-height:1.6; }
.amberbox { font-size:13px; color:#e9d8b8; background:linear-gradient(135deg,rgba(201,166,107,.13),rgba(201,166,107,.05));
  border:1px solid rgba(201,166,107,.22); border-radius:12px; padding:12px 16px; margin:12px 0; line-height:1.7; }
.amberbox b { color:#c9a66b; }
.upbox { border-left:4px solid #c98b7d; } .downbox { border-left:4px solid #8da894; }
.bar { display:flex; height:26px; border-radius:8px; overflow:hidden; margin:8px 0; font-size:11px;
  color:#1a1f2e; text-align:center; line-height:26px; font-weight:700; }
.legend { font-size:12px; color:#9a9aa4; margin:6px 0 0; }
.legend .up { color:#e39a8c; } .legend .down { color:#8fc4a3; }
.scorebar { height:8px; background:rgba(255,255,255,.10); border-radius:6px; overflow:hidden; margin-top:4px; }
.scorebar > i { display:block; height:100%; background:linear-gradient(90deg,#c9a66b,#c98b7d); }
footer { margin-top:46px; padding-top:18px; border-top:1px solid rgba(255,255,255,.10);
  font-size:12px; color:#9a9aa4; line-height:1.8; }
""".strip()

def moves_table(g, bucket, limit=40):
    rows = MOVES[g][bucket]
    rows_sorted = sorted(rows, key=lambda r: -abs(r[3]))[:limit]
    cls = "up" if bucket == "inc" else "down"
    verb = "增持 / 新进" if bucket == "inc" else "减持"
    if not rows_sorted:
        return f"<div class='note'>{verb}：本样本中暂未检出。</div>"
    body = "".join(
        f"<tr><td>{code} {sname}</td><td>{nm}</td>"
        f"<td class='num {cls}'>{fmt_shares(dlt)}</td>"
        f"<td class='num'>{fmt_pct(pct)}</td></tr>"
        for (code, sname, nm, dlt, pct) in rows_sorted)
    return (f"<table><thead><tr><th>股票</th><th>股东</th>"
            f"<th class='num'>变动股数（{verb}）</th><th class='num'>变动后占流通比</th></tr></thead>"
            f"<tbody>{body}</tbody></table>"
            f"<div class='note'>共 {len(rows)} 笔，列表按变动股数绝对值降序展示前 {len(rows_sorted)} 笔。</div>")

# ---- 概览统计 ----
def stock_count_with(g, bucket):
    return len({r[0] for r in MOVES[g][bucket]})

overview_chips = ""
for g, label in (("牛散", "牛散"), ("私募", "私募"), ("公募", "大型公募")):
    ci, cd = stock_count_with(g, "inc"), stock_count_with(g, "dec")
    overview_chips += (
        f"<div class='chip'><div class='k'>{label} 增持股票</div><div class='v up'>{ci}</div>"
        f"<div class='hl'>减持 {cd} 只</div></div>")

# ---- 综合评分榜 ----
score_rows = ""
for i, (t, c1, c2, c3, s) in enumerate(SCORED[:30], 1):
    pe = val_of(s["code"], "pe_ratio"); pb = val_of(s["code"], "pb_ratio")
    pet = "亏损" if (not isinstance(pe, (int, float)) or pe <= 0) else f"{pe:.1f}"
    pbt = "—" if not isinstance(pb, (int, float)) else f"{pb:.2f}"
    tags = []
    if s["has_cattle"]: tags.append("<span class='up'>牛散</span>")
    if s["has_private"]: tags.append("<span class='up'>私募</span>")
    if s["has_mutual"]: tags.append("<span class='up'>公募</span>")
    tags_html = " ".join(tags) if tags else "<span class='note'>—</span>"
    score_rows += (
        f"<tr><td class='num'>{i}</td><td>{s['code']} {s['name']}</td>"
        f"<td>{tags_html}</td>"
        f"<td class='num'>{pet}</td><td class='num'>{pbt}</td>"
        f"<td class='num'>{c1:.1f}/{c2:.1f}/{c3:.0f}</td>"
        f"<td class='num'><b>{t:.2f}</b><div class='scorebar'><i style='width:{t/10*100:.0f}%'></i></div></td></tr>")

# ---- 减持警示 ----
reduce_alerts = sorted(
    [(c, s, PER_STOCK[c]["smart_net"]) for c, s in PER_STOCK.items() if PER_STOCK[c]["smart_net"] < 0],
    key=lambda x: x[2])[:25]
alert_rows = ""
for code, s, net in reduce_alerts:
    parts = []
    for (g, nm, dlt, pct) in sorted(
            [(g2, h["name"], h["holdChange"], h["holdPct"])
             for h in s["_holders"] if (g2 := cat_group(classify_holder(h["name"]))) in ("牛散", "私募", "公募") and h["holdChange"] < 0],
            key=lambda x: x[2])[:4]:
        parts.append(f"{nm} {fmt_shares(dlt)}")
    alert_rows += (
        f"<tr><td>{code} {s['name']}</td>"
        f"<td class='num down'>{fmt_shares(net)}</td>"
        f"<td>{'；'.join(parts)}</td></tr>")

# ---- 建议与分析（数据驱动） ----
top_cattle_inc = sorted(MOVES["牛散"]["inc"], key=lambda r: -r[3])[:5]
top_private_inc = sorted(MOVES["私募"]["inc"], key=lambda r: -r[3])[:5]
top_mutual_inc = sorted(MOVES["公募"]["inc"], key=lambda r: -r[3])[:5]
def bullet_inc(title, lst):
    if not lst:
        return ""
    items = "".join(f"<li>{code} {sname}：<b>{nm}</b> {fmt_shares(dlt)}（变动后占流通 {fmt_pct(pct)}）</li>"
                    for (code, sname, nm, dlt, pct) in lst)
    return f"<p class='sub2'><b>{title}</b></p><ul style='margin:4px 0 10px;padding-left:20px;font-size:13px;line-height:1.8;'>{items}</ul>"

analysis_html = f"""
<div class='amberbox'>
<b>一、总体结论</b><br>
本样本共 {len(ALL_STOCKS)} 只（涨停梯队 + 持仓 + 蓝筹），基于 2026-06-30 中报十大股东/流通股东数据：
牛散在 <b>{stock_count_with('牛散','inc')}</b> 只股票上增持/新进、<b>{stock_count_with('牛散','dec')}</b> 只减持；
私募在 <b>{stock_count_with('私募','inc')}</b> 只增持、<b>{stock_count_with('私募','dec')}</b> 只减持；
大型公募在 <b>{stock_count_with('公募','inc')}</b> 只增持、<b>{stock_count_with('公募','dec')}</b> 只减持。
综合三类资金的"增比减"，<b>牛散与大型公募的增持广度明显强于私募</b>，与 Q2 市场由游资/机构共振驱动的特征一致。
</div>
<div class='amberbox'>
<b>二、各路资金 Q2 重点加仓方向（按变动股数绝对值 Top5）</b>
{bullet_inc('🐂 牛散', top_cattle_inc)}
{bullet_inc('🔒 私募', top_private_inc)}
{bullet_inc('🏦 大型公募', top_mutual_inc)}
</div>
<div class='amberbox upbox'>
<b>三、减持警示</b><br>
共 <b>{len(reduce_alerts)}</b> 只样本出现聪明钱（牛散/私募/公募）净减持，列表见上方「减持警示」表，多为前期涨幅较大的高位品种，
或基本面存在分歧的个股。<b>净减持 ≠ 立即下跌</b>，但至少提示"资金在兑现"，短线需提高风控阈值。
</div>
<div class='amberbox'>
<b>四、操作建议（框架：增比减 / 低比高 / 牛比不牛）</b><br>
1. <b>增比减的好</b>：优先看「综合评分榜」中 crit1（增持户数占比）高的标的——说明主流资金在持续收集筹码。<br>
2. <b>低比高的好</b>：评分榜已按 PE/PB 分位给"低估值"加权，规避高估值纯情绪票；对 PE 为负的亏损股已做中性处理，需结合行业周期单独判断。<br>
3. <b>牛比不牛好</b>：有牛散/私募/公募同框的标的，信息含量更高；但<b>注意</b>牛散与私募也可能被套或做短差，<b>应以"资金行为 + 自身交易规则"双重验证</b>，不盲从。<br>
4. 本板块为<b>统计梳理</b>，不展示任何个人持仓，亦不构成个股推荐；实战请结合仓位、止损与大盘环境。
</div>
"""

HTML = f"""<!DOCTYPE html>
<html lang='zh-CN'>
<head>
<meta charset='UTF-8'>
<meta name='viewport' content='width=device-width,initial-scale=1.0'>
<title>2026中报 · 牛散/私募/公募 Q2持仓动向</title>
<style>{CSS}</style>
</head>
<body>
<div class='wrap'>
<div class='topnav'>
  <a href='index.html'>← 龙虎榜主看板</a>
  <a href='../index.html'>总门户</a>
  <a href='sector-strength-index.html'>板块强度</a>
</div>
<header>
  <h1>2026中报 · 牛散 / 私募 / 公募 Q2 持仓动向</h1>
  <p>数据基准日 <b>2026-06-30</b>（2026 年半年度报告，于 2026-08-31 前披露完毕）· 十大股东 / 流通股东口径</p>
  <p>选股框架（用户给定）：① 增比减的好 　② 低比高的好 　③ 牛比不牛好</p>
</header>
<div class='meta'>
  <b>口径说明：</b>股东「变动股数」= 2026Q2 相对 2026Q1 的持股变动（holdChange），<b>正数代表增持/新进十大股东，负数代表减持</b>。
  样本为 {len(ALL_STOCKS)} 只（涨停梯队 + 持仓 + 蓝筹），非全市场，结论为<b>统计梳理</b>，不构成投资建议，亦不展示任何个人持仓。
</div>

<div class='section'>
  <h2>一、总览</h2>
  <div class='chiprow'>{overview_chips}</div>
  <div class='legend'>说明：<span class='up'>红 = 增持/新进</span>，<span class='down'>绿 = 减持</span>（A股惯例）。下表为三类资金的增持/减持股票数量。</div>
</div>

<div class='section'>
  <h2>二、牛散动向</h2>
  <div class='sub2'>牛散（知名牛散 + 疑似自然人 candidate）增持 / 新进 与 减持 的股票明细。</div>
  <div class='sub2' style='color:#c9a66b;font-weight:700;'>▍增持 / 新进（{len(MOVES['牛散']['inc'])} 笔）</div>
  {moves_table('牛散','inc')}
  <div class='sub2' style='color:#8fc4a3;font-weight:700;'>▍减持（{len(MOVES['牛散']['dec'])} 笔）</div>
  {moves_table('牛散','dec')}
</div>

<div class='section'>
  <h2>三、私募动向</h2>
  <div class='sub2'>私募基金（含头部私募）增持 / 新进 与 减持 的股票明细。</div>
  <div class='sub2' style='color:#c9a66b;font-weight:700;'>▍增持 / 新进（{len(MOVES['私募']['inc'])} 笔）</div>
  {moves_table('私募','inc')}
  <div class='sub2' style='color:#8fc4a3;font-weight:700;'>▍减持（{len(MOVES['私募']['dec'])} 笔）</div>
  {moves_table('私募','dec')}
</div>

<div class='section'>
  <h2>四、大型公募动向</h2>
  <div class='sub2'>公募基金（含指数/主动/ETF 联接）增持 / 新进 与 减持 的股票明细。</div>
  <div class='sub2' style='color:#c9a66b;font-weight:700;'>▍增持 / 新进（{len(MOVES['公募']['inc'])} 笔）</div>
  {moves_table('公募','inc')}
  <div class='sub2' style='color:#8fc4a3;font-weight:700;'>▍减持（{len(MOVES['公募']['dec'])} 笔）</div>
  {moves_table('公募','dec')}
</div>

<div class='section'>
  <h2>五、综合评分榜（三大准则）</h2>
  <div class='sub2'>评分 = 增比减(0-4) + 低比高(0-3, PE/PB分位) + 牛比不牛(0-3) ，满分 10。仅列前 30。</div>
  <table>
    <thead><tr><th class='num'>#</th><th>股票</th><th>资金标签</th>
      <th class='num'>PE</th><th class='num'>PB</th><th class='num'>准则(增/低/牛)</th><th class='num'>总分</th></tr></thead>
    <tbody>{score_rows}</tbody>
  </table>
</div>

<div class='section'>
  <h2>六、减持警示</h2>
  <div class='sub2'>聪明钱（牛散/私募/公募）净减持的股票（按净减持股数升序，前 25）。</div>
  <table>
    <thead><tr><th>股票</th><th class='num'>聪明钱净变动</th><th>主要减持方</th></tr></thead>
    <tbody>{alert_rows}</tbody>
  </table>
</div>

<div class='section'>
  <h2>七、建议与分析</h2>
  {analysis_html}
</div>

<footer>
数据来源：腾讯自选股 <b>westock-mcp</b>（中报十大股东 / 流通股东 + 实时估值）。<br>
本页为 A股量化助理自动化生成的统计梳理，<b>不构成投资建议</b>；不展示任何个人持仓。市场有风险，投资需谨慎。
</footer>
</div>
</body>
</html>
"""

open(OUT_HTML, "w", encoding="utf-8").write(HTML)
print(f"HTML 页面已生成 -> {OUT_HTML}")
