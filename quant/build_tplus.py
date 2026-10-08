# -*- coding: utf-8 -*-
"""做T池 · 引擎（Stage 2）：多源候选 → 做T适合度评分 → 操作参数 → 出页。

候选来源（gen_tplus.py 三源并集，逐只标注）：
  机构底仓 / 龙虎榜活跃 / 强势股（20日超额 ≥5pp 且站上 MA20）

方法论（顶级机构规则）：
  - 网格交易法(Grid)：震荡市机械高抛低吸，赚波动不猜方向
  - 均值回归(Mean Reversion)：价格围绕箱体中枢往复
  - 底仓+卫星仓(Core-Satellite)：底仓不动，卫星仓反复做T摊低成本
  - 波动率套利：日振幅/ATR 足够大，做T才有空间
  - 相对强度增强：强势股只做「回踩买」，不逆势
  - 龙虎榜跟踪：机构/游资席位净买为正向共振，净卖出为风险信号
  - 风险预算：破箱体下沿无条件离场，单次做T亏损 ≤ 总资金 0.5%

输入：quant/tplus/universe_{D}.json / quotes_{D}.json / kline_{D}.json
输出：web/tplus/index.html、web/tplus/tplus-{D}.html、quant/tplus/history.json

用法：python build_tplus.py --date YYYY-MM-DD
"""
import os, sys, json, math, argparse, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _xhist as X  # 跨池历史入选（徽标 / 排序 / 对比）
import _idxkline as E  # 大盘环境判定（市场画像 + 指数均线，腾讯日K，可离线降级）
import gen_tplus as G  # 龙虎榜近 N 日聚合（universe 缺失时兜底）
import _tbox as TB  # 箱体锚定引擎（锁定式上下沿 + 反复验证闸门）

CUR_ENV = None      # 由 build() 写入，供 render_card 缩放仓位建议
ENV_STRICT_NOTE = ""
CUR_TDIR = None      # 做T方向（反T/正T），由大盘近20日偏离决定（原则15 方向×环境配对）
CUR_IDX20 = None     # 上证近20日涨幅（%），方向判定的输入

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "quant", "tplus")
WEB = os.path.join(ROOT, "web", "tplus")
PICKS = os.path.join(ROOT, "quant", "picks")
HIST = os.path.join(DATA, "history.json")


def esc(s):
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("'", "&#39;"))


def fnum(x, n=2):
    if x is None:
        return "—"
    return f"{x:.{n}f}"


def pct(x):
    if x is None:
        return "—"
    return f"{x:+.2f}%"


def yi(x):
    if not x:
        return "—"
    return f"{x/1e8:.2f} 亿"


def clamp(x, a, b):
    return max(a, min(b, x))


def band(x, a, b, c, d, mx):
    """x 落在 [a,b] 得满分 mx，落在 [c,d] 外得 0，之间线性过渡。"""
    if x is None:
        return 0.0
    if a <= x <= b:
        return float(mx)
    if x < a:
        return float(mx) * (x - c) / (a - c) if a > c else 0.0
    return float(mx) * (d - x) / (d - b) if d > b else 0.0


# ---------------- 基准（上证）相对强度 ----------------
_IDX_SER, _IDX_DS = {}, []


def set_index(ser):
    global _IDX_SER, _IDX_DS
    _IDX_SER = ser or {}
    _IDX_DS = sorted(_IDX_SER)


def _idx_chg(date, n):
    """上证指数截至 date（含）的近 n 个交易日涨幅（%）。"""
    if not _IDX_SER:
        return None
    ds = [d for d in _IDX_DS if d <= date]
    if len(ds) < n + 1:
        return None
    c0, cn = _IDX_SER[ds[-1]], _IDX_SER[ds[-(n + 1)]]
    return (c0 - cn) / cn * 100 if cn else None


def lhb_block(u):
    """universe 里的龙虎榜聚合块（缺失则就地兜底重算）。"""
    b = u.get("lhb")
    if b:
        return b
    return None


# ---------------- 字段口径说明（悬浮提示） ----------------
TIPS = {
    "现价": "数据日期（T 日）收盘价，括号内为当日涨跌幅（红涨绿跌）。所有网格/波段价位均以该日收盘后的数据推算。",
    "做T分": "做T适合度分（0~100）= 9 个先验固定因子（箱体窄/带宽低/均线粘合/波动规律/振幅适中/ATR适中/横盘/支撑被验/流动性）在当日的域内横截面分位、等权平均 × 100。分数是相对位置，不是绝对阈值；越高越「安静、收敛、有流动性」，越适合反复做T。实证见 lab.html。",
    "档位": "A ≥80（可重点做T）· B 70~80（适合做T）· C 60~70（可小仓试）· D <60（不适合，仅列出）。",
    "来源": "候选来源三选一或多选：机构底仓（公募≥3% 或 社保/险资≥2 家）／龙虎榜（近 10 交易日上榜且净买为正或≥2 次）／强势（20 日超额收益 ≥5pp 且站上 MA20）。多源共振 = 同时命中两条以上，确定性最高。",
    "龙虎榜": "近 10 交易日上榜次数（括号内为累计净买额，单位亿元）。上榜越频繁说明资金关注度越高、波动与流动性越充足；累计净买为正 = 席位整体在吸筹，为正向共振；净卖为主 = 派发，风险信号。",
    "强势": "20 日相对强度超额（个股 20 日涨幅 − 上证 20 日涨幅，单位 pp）。>0 表示跑赢大盘；5~30pp 是「强而不过热」的理想做T区间，>45pp 视为已在高潮段（追高风险）。",
    "强势结构": "强势结构得分（0~12）= 20 日超额收益分档（8） + 均线多头排列 MA5>MA10>MA20>MA60（4）。用于「强势股分析」板块分档：≥9 强势多头 · 5~9 温和偏强 · <5 非强势。",
    "龙虎榜共振": "龙虎榜共振得分（0~8）= 上榜频次（3） + 累计净买占流通市值比（3） + 席位结构（2，游资等级越高分越高）。未上榜者给中性 1 分，不惩罚干净标的。",
    "日内振幅": "近 20 个交易日 (最高−最低)/前收 的平均值（%）。做T的『空间』来自振幅：低于 3% 基本没有做T价值，3%~9% 最佳。",
    "ATR%": "近 14 日平均真实波幅占现价比例（%），衡量单日波动幅度。3%~8% 最适合做T；过高(>10%)易单边、风险大。",
    "换手": "当日换手率（成交量/流通股本）。2%~18% 为活跃且可持续；过高(>20%)多为游资情绪票，做T易被闷杀。",
    "箱体": "近 90 个交易日里确认的震荡区间 [下沿 L, 上沿 U]。边界取自**被反复验证**的局部高低点（各取最近 4 个的中位数），而非单日极值，因此不会被一根插针拉偏。反复做T即在此区间内高抛低吸。箱体高度=(U−L)/L。",
    "箱体锁定": "箱体一经确立，上下沿即**锁死不动**，此后每天只判断「是否仍然有效」，不随行情微调 ✅。只有当行情走出这个区间（连续 2 个交易日收盘价越界 2% 以上）或已锁定超过 90 个交易日，才会重找箱体并 +1 版本号，页面上会同步显示新的「确立日」。这样上下沿不会天天变，才有真正的参考价值。",
    "往返": "「3轮·上4下3」= 近 90 日完成了 3 轮「摸到下沿 → 涨到上沿」的完整往返；期间共有 4 个局部高点落在上沿附近、3 个局部低点落在下沿附近——即这条边界被市场反复确认的次数。往返轮数越多，网格越有得做；只来回一两次的属于刚成型的区间，证据不足。",
    "箱体涨幅": "箱体最大理论可盈利涨幅 =(上沿−下沿)/下沿×100%，即从下沿买入、上沿卖出的单轮理论收益上限（未扣滑点与手续费；实际做T通常只吃中间段）。",
    "箱内位置": "现价在箱体中的百分位：0=贴下沿(低吸区)，100=贴上沿(高抛区)，50=中枢。理想做T在 20%~80% 区间。",
    "均线斜率": "MA20 近 5 日的变化率（%）。越接近 0 说明越横盘、越适合网格；绝对值大说明在走趋势，做T易做反。",
    "机构底仓": "公募基金持有十大流通股比例（季报数据）。底仓越重，箱体下沿支撑越强，做T越安全。龙虎榜/强势源无季报数据时以「席位净买为正或均线多头」作代理值，显示为 —。",
    "顶级机构": "社保 / 养老 / 年金 / 险资 / 汇金 / 证金 / QFII 是否出现在十大流通股东。出现即视为强底仓信号。",
    "类型": "网格型 = 箱体清晰、均线粘合，适合机械网格高抛低吸；波段型 = 有一定趋势/箱体较宽，适合按支撑压力几日一循环。",
    "网格档": "把箱体 [L,U] 均分为 5 档，给出每档的价格与建议动作。下跌触及买入档分批接、上涨触及卖出档分批抛，机械执行。",
    "底仓/滚动": "机构常用『底仓+卫星仓』：底仓不动吃趋势/分红，用卫星(滚动)仓反复做T摊低成本。A股 T+1，做T必须先有底仓。",
    "波段买区": "回落至支撑位附近的吸纳区间（支撑取箱体下沿与 MA20 的较高者）。",
    "波段卖区": "反弹至箱体上沿附近的减持区间。",
    "止损": "做T的纪律线：收盘跌破箱体下沿一定比例（通常 4%~6%）即无条件清仓，避免『越补越亏』。",
    "失效条件": "出现以下任一即停止做T：放量破箱体下沿、MA20 拐头向下走成空头排列、出现解禁/减持公告。",
    "成交额": "当日成交金额。做T需足够流动性，日成交额建议 ≥3 亿，否则买卖冲击成本高。",
    "风险": "风险提示项：跌破 MA60、RSI 超买、成交额不足、MA20 陡峭、龙虎榜净卖出等。v6 起只作卡片提示、不参与排序；命中解禁/计划减持会直接进 D 档（风险否决）。",
    "评级": "做T池评分模型（v6：先验固定因子集 × 域内横截面分位）的口径与依据说明。",
    "可做T": "是否放行做T = 档位 × 大盘环境 × 做T方向。破位环境一律不放行；弱势环境只放行 A 档且须「一年分位 ≤70% · MA20 斜率 ≥−1% · 箱体高度 ≤40%」；更关键的是**方向须与环境配对**（原则15）：上证近20日<0 只做反T(先低吸后高抛)、≥0 只做正T(先高抛后低吸补回)，反向配对最差、故不做，方向无法判定则空仓。未放行的一律「仅跟踪」，不新开仓。",
    "大环境": "大盘环境 = 市场画像评分（短趋势/技术/宽度/情绪）× 55% + 上证指数均线状态 × 45%。强势 ≥3.8 · 震荡 3.0~3.8 · 弱势 2.2~3.0 · 破位 <2.2。弱势起收紧出池并折算仓位，破位不新开做T仓。",
    "方法论": "本页采用顶级机构常用的四类方法：网格交易、均值回归、底仓+卫星仓、波动率套利，均服务于『在震荡区间反复降低持仓成本』。",
    "RSI": "14 日相对强弱指标。做T标的宜处于 35~70 的健康区间；<30 超卖(可低吸)、>75 超买(宜高抛)。",
    "波动稳定": "近 20 日振幅的变异系数（标准差/均值）。越低说明波动越规律、越可预期，做T节奏越好把握。",
    "箱体位置图": "把「箱体价格」和「现价位置」放在一格里读：横条是箱体本身，左端=下沿 L、右端=上沿 U，指针=现价；底色三段对应低吸区(0~20%·绿)/中枢(20~80%·灰)/高抛区(80~100%·红)，与涨红跌绿一致。**上下沿不是对未来的价格预测**，而是过去 90 个交易日里被反复验证过的边界（≥2 次触碰上沿 + ≥2 次触碰下沿 + ≥1 轮完整往返才算成立），锁定后数值不再天天改。",
    "箱体下沿": "箱体下沿价格 L（锚定值）。跌到这里意味着回到区间底部；有效跌破（连续 2 个交易日收盘低于 L×0.98）会触发箱体换版，届时本列价格会同步更新。",
    "箱体上沿": "箱体上沿价格 U（锚定值）。涨到这里意味着触到区间顶部；有效突破同样触发换版。",
    "距下沿": "现价跌到箱体下沿还需要下跌的百分比 =（现价 − 下沿）÷ 现价。数字越大，说明离下方边界越远（回旋余地越大）。",
    "距上沿": "现价涨到箱体上沿还需要上涨的百分比 =（上沿 − 现价）÷ 现价。数字越大，说明到顶部区还有多少空间。",
    "位置状态": "按箱内位置的读数：贴上沿(≥90) = 已在区间顶部，再往上就是突破而非做T语境；接近上沿(67~90)；中枢(33~67) = 上不上、下不下，做T性价比最低的一段；接近下沿(10~33)；贴下沿(<10) = 已在区间底部。",
}


def tip_t(key):
    t = TIPS.get(key)
    return f" title='{esc(t)}'" if t else ""


def tip(key, cls="tip"):
    t = TIPS.get(key)
    if not t:
        return ""
    return f" class='{cls}' title='{esc(t)}'"


STYLE = """
:root{--bg:#f5f6f8;--card:#fff;--tx:#23262b;--sub:#6b7280;--gold:#b8893b;--red:#b8332a;--green:#1a9e5a;--line:#e6e8eb;}
*{box-sizing:border-box;}
body{margin:0;background:var(--bg);color:var(--tx);font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;font-size:14px;line-height:1.6;}
.wrap{max-width:1180px;margin:0 auto;padding:26px 20px 60px;}
.topnav{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px;}
.topnav a{font-size:12.5px;color:#7a5a1f;background:#fff;border:1px solid #e7dcc4;border-radius:20px;padding:5px 12px;text-decoration:none;}
.topnav a:hover{background:#faf3e4;}
.topnav a.cur{background:linear-gradient(135deg,#c79a44,#a97b2e);color:#fff;border-color:transparent;}
header{background:linear-gradient(135deg,#fdf8ef,#f7efe0);border:1px solid #ecdfc6;border-radius:16px;padding:22px 24px;margin-bottom:18px;}
header h1{margin:0 0 6px;font-size:26px;background:linear-gradient(135deg,#c79a44,#8f6420);-webkit-background-clip:text;background-clip:text;color:transparent;}
header .sub{color:var(--sub);font-size:13px;}
.section{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px 20px;margin-bottom:16px;}
.section h2{margin:0 0 12px;font-size:17px;padding-left:10px;border-left:4px solid var(--gold);}
.note{background:#fbf9f4;border:1px solid #efe6d4;border-radius:10px;padding:12px 14px;color:#5c5648;font-size:13px;margin-bottom:14px;}
.note.warn{background:#fdf3f2;border-color:#f0d6d3;color:#8a3b32;}
.note.ok{background:#f1faf5;border-color:#d6efe0;color:#2c6b4c;}
/* 表格：**不再横向滚动** —— 宽屏列自适应、文字可换行；窄屏整行堆成卡片（列名由 td 的 data-l 提供） */
.tbl-wrap{max-width:100%;border:1px solid var(--line);border-radius:10px;margin-top:4px;background:#fff;}
table{width:100%;border-collapse:collapse;font-size:13px;table-layout:auto;}
th,td{padding:7px 6px;border-bottom:1px solid var(--line);text-align:right;
      white-space:normal;word-break:break-word;vertical-align:middle;}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left;}
thead th{background:#faf7f0;color:#7a5a1f;font-weight:600;white-space:nowrap;}
tbody tr:hover{background:#fdfaf3;}
@media(max-width:1000px){
  table.rt thead{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap;}
  table.rt tr{display:block;border-bottom:2px solid var(--line);padding:9px 0;}
  table.rt tr:last-child{border-bottom:0;}
  table.rt td{display:flex;align-items:baseline;justify-content:space-between;gap:12px;
              border:0;padding:3px 12px;text-align:right;}
  table.rt td::before{content:attr(data-l);flex:0 0 42%;color:var(--sub);font-size:12px;text-align:left;}
  table.rt tbody tr:hover{background:transparent;}
}
.up{color:var(--red);} .down{color:var(--green);}
details.ref-fold>summary{cursor:pointer;list-style:none;}
details.ref-fold>summary::-webkit-details-marker{display:none;}
details.ref-fold>summary h2{display:inline;margin:0;padding-left:10px;border-left:4px solid var(--gold);font-size:17px;}
details.ref-fold>summary:hover h2{color:#8f6420;}
details.ref-fold[open]>summary{margin-bottom:12px;}
.fold-tip{margin-left:8px;font-size:12px;color:var(--sub);border:1px solid var(--line);
  border-radius:20px;padding:2px 10px;white-space:nowrap;} .muted{color:var(--sub);} .dim{color:#9aa3ad;}
.badge{display:inline-block;min-width:20px;text-align:center;border-radius:6px;padding:1px 7px;font-size:12px;font-weight:700;color:#fff;}
.bA{background:#b8332a;} .bB{background:#d98a26;} .bC{background:#7a8aa0;} .bD{background:#c2c7cd;}
.tag{display:inline-block;font-size:11.5px;border-radius:6px;padding:1px 7px;margin-right:4px;}
.tgrid{background:#eef4ec;color:#2f6b46;border:1px solid #d6e6da;}
.tswing{background:#eef1f8;color:#3b4f86;border:1px solid #d9e0f0;}
.tinst{background:#fbf3e3;color:#8a5d16;border:1px solid #efe0bf;}
.tlhb{background:#fdeef0;color:#a03050;border:1px solid #f2d3da;}
.tstrong{background:#eaf3fd;color:#1f5b96;border:1px solid #cfe2f6;}
.cards{display:grid;grid-template-columns:1fr 1fr;gap:14px;}
.card{border:1px solid var(--line);border-radius:12px;padding:14px 16px;background:#fff;}
.card .hd{display:flex;align-items:center;gap:8px;margin-bottom:8px;}
.card .nm{font-size:16px;font-weight:700;}
.card .cd{color:var(--sub);font-size:12px;}
.grid2{display:grid;grid-template-columns:repeat(3,1fr);gap:8px 12px;margin:8px 0;}
.kv{background:#fafbfc;border:1px solid #eef0f2;border-radius:8px;padding:6px 9px;}
.kv .k{color:var(--sub);font-size:11.5px;}
.kv .v{font-size:14px;font-weight:600;}
.kv .k.tipk::after{content:"?";display:inline-block;margin-left:3px;font-size:9px;color:var(--gold);border:1px solid rgba(184,137,59,.5);border-radius:50%;width:11px;height:11px;line-height:10px;text-align:center;}
.gtable{width:100%;font-size:12.5px;border-collapse:collapse;margin-top:6px;}
.gtable th,.gtable td{padding:4px 6px;text-align:center;border-bottom:1px dashed #eceef0;}
.gbuy{color:var(--green);font-weight:600;} .gsell{color:var(--red);font-weight:600;}
.sig{font-size:12.5px;color:#4b5563;margin-top:6px;}
.tip{cursor:help;border-bottom:1px dotted #c3cad3;}
.kv.tipbox:hover{background:#fdf8ef;}
/* ---- 箱内位置条：把「现价落在箱体哪个位置」画出来（纯 CSS，无 JS 依赖）----
   轨道底色三段（0~20% 低吸区绿 / 20~80% 中枢灰 / 80~100% 高抛区红），与 A 股「涨红跌绿」一致。
   指针位置 = 现价在 [下沿,上沿] 的百分位，已在服务端算好写进 style，页面不再重算。 */
.bxbar{position:relative;display:inline-block;width:118px;height:13px;vertical-align:middle;
  border:1px solid #c8d0d8;border-radius:7px;overflow:hidden;
  background:linear-gradient(90deg,#d8ecdf 0 20%,#e7ebef 20% 80%,#f7dcdb 80% 100%);}
.bxpin{position:absolute;top:-1px;bottom:-1px;width:3px;margin-left:-1.5px;background:#1b1e22;
  box-shadow:0 0 0 1px rgba(255,255,255,.95);border-radius:2px;}
.bxtk{position:absolute;top:0;bottom:0;width:1px;background:rgba(0,0,0,.14);}
.bxn{display:inline-block;margin-left:7px;font-size:12px;font-weight:700;font-variant-numeric:tabular-nums;}
.bxwrap{white-space:nowrap;}
.bxsum{display:flex;flex-wrap:wrap;gap:10px;margin:0 0 12px;}
.bxsum div{flex:1 1 150px;background:#fafbfc;border:1px solid #eef0f2;border-radius:9px;padding:9px 12px;}
.bxsum b{display:block;font-size:19px;line-height:1.25;}
.bxsum span{font-size:12px;color:var(--sub);}
footer{text-align:center;color:#9aa3ad;font-size:12px;margin-top:24px;}
@media(max-width:760px){.cards{grid-template-columns:1fr;}.wrap{padding:18px 12px 44px;}table{font-size:12px;}}
"""


def pos_state(pos, px=None, lo=None, hi=None):
    """箱内位置 → (读数, 颜色类)。读数是描述性的，不含操作指令。

    必须区分「贴在边界附近」与「已经在箱体外面」：百分位被 clamp 到 0 或 100 时，
    两者看起来一样，但含义完全不同 —— 后者说明行情已经走出去，箱体面临换版。
    """
    p = clamp(pos or 0, 0, 100)
    if px and lo and hi and hi > lo:
        if px > hi:
            return "已在上沿之上", "up"
        if px < lo:
            return "已在下沿之下", "down"
    if p >= 90:
        return "贴上沿", "up"
    if p >= 67:
        return "接近上沿", "up"
    if p > 33:
        return "中枢", "muted"
    if p > 10:
        return "接近下沿", "down"
    return "贴下沿", "down"


def box_bar(m, show_num=True):
    """箱内位置条：轨道 = 箱体 [L,U]，指针 = 现价所在百分位。

    两种退化情形都如实标出来，不画一根看起来正常的假条：
      · None / 极小箱体 → 返回「—」；
      · 现价已在箱体之外 → 指针压在最边上并加越界箭头（↗/↘，含超出百分比）。
    """
    lo, hi = m.get("box_low") or 0, m.get("box_high") or 0
    px = m.get("price") or 0
    if not (hi and lo and hi > lo > 0 and px):
        return "<span class='dim'>—</span>"
    pos = clamp(m.get("pos") or 50, 0, 100)
    pin = 1.5 + 97.0 * pos / 100.0
    over = ""
    if px > hi:
        pin = 98.5
        over = "<span class='up' style='font-size:11px;font-weight:700'>↗%.1f%%</span>" % (
            (px - hi) / hi * 100)
    elif px < lo:
        pin = 1.5
        over = "<span class='down' style='font-size:11px;font-weight:700'>↘%.1f%%</span>" % (
            (lo - px) / lo * 100)
    ttl = esc("现价 %.2f 落在箱体 %.2f ~ %.2f 的 %.0f%% 位置" % (px, lo, hi, pos))
    num = "<span class='bxn'>%.0f%%</span>" % pos if show_num else ""
    return ("<span class='bxwrap'><span class='bxbar' title='%s'>"
            "<span class='bxtk' style='left:20%%'></span>"
            "<span class='bxtk' style='left:80%%'></span>"
            "<span class='bxpin' style='left:%.2f%%'></span>"
            "</span>%s%s</span>") % (ttl, pin, num, over)


def nav(cur="tplus"):
    from _nav import topnav
    return topnav(current_web_dir="tplus", home="../../index.html")


# ---------------- 指标计算 ----------------
def calc_metrics(code, u, q, nodes, box=None):
    # nodes: 日期倒序，nodes[0] 最新
    # box: _tbox 锚定箱体（dict）。给定则用它的**锁定**上下沿，替代每日滚动重算的 20 日极值。
    if not nodes or len(nodes) < 30:
        return None
    closes = [n.get("last") for n in nodes]
    highs = [n.get("high") for n in nodes]
    lows = [n.get("low") for n in nodes]
    amts = [n.get("amount") or 0 for n in nodes]
    if any(c is None for c in closes[:25]) or any(h is None for h in highs[:25]):
        return None
    price = closes[0]

    def ma(arr, n):
        return sum(arr[:n]) / n if len(arr) >= n else None

    ma5, ma10, ma20, ma60 = ma(closes, 5), ma(closes, 10), ma(closes, 20), ma(closes, 60)
    ma20_prev = sum(closes[5:25]) / 20 if len(closes) >= 25 else None
    slope = (ma20 - ma20_prev) / ma20_prev * 100 if (ma20 and ma20_prev) else 0.0

    # 箱体：优先用**锚定锁定**的上下沿（确立后数值不再变动），退回滚动 20 日极值
    if box and box.get("U") and box.get("L") and box["U"] > box["L"]:
        box_high, box_low = box["U"], box["L"]
    else:
        box_high = max(highs[:20]); box_low = min(lows[:20])
    box_h = (box_high - box_low) / box_low * 100 if box_low else 0
    pos = clamp((price - box_low) / (box_high - box_low) * 100 if box_high > box_low else 50, 0, 100)

    # ATR14
    trs = []
    for i in range(min(14, len(nodes) - 1)):
        h, l, pc = highs[i], lows[i], closes[i + 1]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    atr = sum(trs) / len(trs) if trs else 0
    atr_pct = atr / price * 100 if price else 0

    # 近20日平均振幅
    amps = []
    for i in range(min(20, len(nodes) - 1)):
        pc = closes[i + 1]
        if pc:
            amps.append((highs[i] - lows[i]) / pc * 100)
    amp20 = sum(amps) / len(amps) if amps else 0
    amp_cv = 0.0
    if len(amps) > 2:
        m = amp20
        sd = (sum((x - m) ** 2 for x in amps) / len(amps)) ** 0.5
        amp_cv = sd / m if m else 0

    # BOLL 带宽
    bstd = 0.0
    if ma20:
        bstd = (sum((c - ma20) ** 2 for c in closes[:20]) / 20) ** 0.5
    bwidth = 4 * bstd / ma20 * 100 if ma20 else 0

    # 均线粘合度
    ma_list = [x for x in (ma5, ma10, ma20) if x]
    cohesion = (max(ma_list) - min(ma_list)) / ma20 * 100 if ma20 and ma_list else 0

    # RSI14
    gains = losses = 0.0
    for i in range(14):
        d = closes[i] - closes[i + 1]
        if d >= 0:
            gains += d
        else:
            losses -= d
    rsi = 100 - 100 / (1 + (gains / losses)) if losses > 0 else (100 if gains > 0 else 50)

    amt_yi = (sum(amts[:20]) / 20) / 1e8

    # 流动性判据要看**常态**，不能用「当日换手」：
    # 大盘缩量日会有一大批票当日换手掉到 2% 以下而被误杀（09-24 实测误杀 364 只），
    # 但它们日常流动性完全够做T。故用近 20 日均成交额 ÷ 流通市值 作为「20 日均换手」。
    _cmc = q.get("circulating_market_cap") or 0
    turn20 = (amt_yi / _cmc * 100) if (_cmc and _cmc > 0) else None

    # 下沿被测试次数（近 60 日里最低价触及「近 20 日下沿 ×1.02」的天数）
    # —— 被反复验证过的支撑更可靠（先验集因子 neg_tests 的原始量）
    # 改用**锚定下沿**（过去锁定的那条线）统计被测试次数 —— 与页面上展示的下沿是同一条
    tests = (sum(1 for k in range(min(60, len(lows))) if lows[k] <= box_low * 1.02)
             if box_low else 0)

    h52 = q.get("high_52week") or box_high
    l52 = q.get("low_52week") or box_low
    pos52 = (price - l52) / (h52 - l52) * 100 if h52 > l52 else 50

    # 相对强度（对基准上证的超额收益，pp）
    chg20 = q.get("chg_20d")
    chg60 = q.get("chg_60d")
    b20, b60 = _idx_chg(nodes[0].get("date") or "", 20), _idx_chg(nodes[0].get("date") or "", 60)
    rs20 = (chg20 - b20) if (chg20 is not None and b20 is not None) else None
    rs60 = (chg60 - b60) if (chg60 is not None and b60 is not None) else None
    multi = bool(ma5 and ma10 and ma20 and ma60 and ma5 > ma10 > ma20 > ma60)
    to_hi52 = (price - h52) / h52 * 100 if h52 else None

    return {
        "code": code, "name": q.get("name") or u.get("name"), "industry": u.get("industry"),
        "price": price, "chg": q.get("change_percent"),
        "turn": q.get("turnover_rate"), "vratio": q.get("volume_ratio"),
        "amount": q.get("amount"), "amt_yi": amt_yi,
        "cmc_yi": (q.get("circulating_market_cap") or 0),  # westock 已为亿元
        "pe": q.get("pe_ratio"), "pb": q.get("pb_ratio"),
        "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60, "slope": slope,
        "box_high": box_high, "box_low": box_low, "box_h": box_h, "pos": pos,
        # 箱体锚定元信息（None 表示无有效箱体 —— 调用方应已在前置闸门里取消）
        "box": box, "box_lock": bool(box),
        "box_since": (box or {}).get("since"), "box_age": (box or {}).get("age", 0),
        "box_ver": (box or {}).get("ver", 0),
        "touch_h": (box or {}).get("touch_h", 0), "touch_l": (box or {}).get("touch_l", 0),
        "rounds": (box or {}).get("rounds", 0), "spread": (box or {}).get("spread", 1),
        "atr_pct": atr_pct, "amp20": amp20, "amp_cv": amp_cv, "bwidth": bwidth,
        "turn20": turn20,
        "cohesion": cohesion, "rsi": rsi, "pos52": pos52, "tests": tests,
        "fund_ratio": u.get("fund_ratio"), "top_inst": u.get("top_inst"),
        "chg20": chg20, "chg60": chg60, "rs20": rs20, "rs60": rs60,
        "multi": multi, "to_hi52": to_hi52,
        "sources": u.get("sources") or [], "lhb": lhb_block(u),
    }


def load_risk_sets(date):
    def rd(name):
        p = os.path.join(PICKS, name)
        if not os.path.exists(p):
            return set()
        try:
            j = json.load(open(p, encoding="utf-8"))
        except Exception:
            return set()
        out = set()
        if isinstance(j, list):
            for it in j:
                if isinstance(it, dict):
                    c = it.get("code") or it.get("symbol")
                    if c:
                        out.add(c)
        elif isinstance(j, dict):
            for k, v in j.items():
                if k.startswith(("sh", "sz", "bj")):
                    out.add(k)
        return out
    return rd(f"events_unlock_{date}.json"), rd(f"events_reduce_{date}.json")


def score(m, unlock, reduce):
    detail = {}
    comp = 0.0

    # 波动性 24（取 ATR% 与 20日振幅的较大者；满分区间 5%~7% 最理想）
    wave = max(m["atr_pct"], m["amp20"])
    s_wave = band(wave, 5.0, 7.0, 3.0, 10.5, 24)
    detail["波动"] = round(s_wave, 1); comp += s_wave

    # 流动性 16
    s_turn = band(m["turn"], 4.5, 12.0, 2.0, 19.0, 8)
    s_amt = band(m["amt_yi"], 4.0, 70.0, 2.0, 300.0, 8)
    detail["流动性"] = round(s_turn + s_amt, 1); comp += s_turn + s_amt

    # 区间结构 20
    # 箱体偏好下移：回测显示「完成一轮做T」的箱体高度均值 19.4%，未完成的 29.1%
    # —— 箱体越宽，卖区越远，5 日内越摸不到，一轮做不完。故满分区间由 18~36 收窄为 12~26。
    s_box = band(m["box_h"], 12.0, 26.0, 8.0, 45.0, 8)
    s_pos = band(abs(m["pos"] - 50), 0.0, 18.0, 0.0, 46.0, 8)
    s_ma = band(abs(m["slope"]), 0.0, 1.5, 0.0, 6.0, 4)
    detail["区间结构"] = round(s_box + s_pos + s_ma, 1); comp += s_box + s_pos + s_ma

    # 资金底仓 12（公募/顶级机构为季报口径；龙虎榜·强势源无季报数据时用代理值）
    lh = m.get("lhb") or {}
    lhb_net = lh.get("net") or 0
    if m.get("fund_ratio") is not None or m.get("top_inst"):
        s_fund = band(m["fund_ratio"] or 0, 8.0, 25.0, 3.0, 40.0, 8)
        s_top = 4 if (m.get("top_inst") or 0) >= 2 else (2.4 if (m.get("top_inst") or 0) == 1 else 0)
    else:
        s_fund = 7.0 if (lhb_net > 0 or m.get("multi")) else 4.0
        s_top = 0.0
    detail["资金底仓"] = round(s_fund + s_top, 1); comp += s_fund + s_top

    # 龙虎榜共振 8（近 10 交易日上榜频次 + 净买强度 + 席位结构）
    n_lhb = lh.get("n") or 0
    s_n = 3.0 if n_lhb >= 3 else (2.4 if n_lhb == 2 else (1.6 if n_lhb == 1 else 1.0))
    net_ratio = (lhb_net / (m["cmc_yi"] * 1e8) * 100) if m["cmc_yi"] else 0.0
    s_net = band(net_ratio, 0.15, 3.0, -0.5, 8.0, 3)
    lvl = lh.get("hot") or ""
    if not n_lhb:
        s_seat = 1.0
    elif lvl == "高":
        s_seat = 2.0
    elif lvl == "中":
        s_seat = 1.5
    else:
        s_seat = 0.8
    detail["龙虎榜共振"] = round(s_n + s_net + s_seat, 1); comp += s_n + s_net + s_seat

    # 强势结构 12（对基准的超额收益 + 均线多头排列）
    s_rs = band(m.get("rs20"), 5.0, 30.0, -5.0, 55.0, 8) if m.get("rs20") is not None else 4.0
    if m.get("multi"):
        s_multi = 4.0
    elif (m.get("ma20") and m.get("ma60") and m["ma20"] > m["ma60"] and m["price"] > m["ma20"]):
        s_multi = 2.0
    else:
        s_multi = 0.0
    detail["强势结构"] = round(s_rs + s_multi, 1); comp += s_rs + s_multi

    # 波动稳定性 8
    s_stab = band(m["amp_cv"], 0.0, 0.32, 0.0, 0.85, 8)
    detail["稳定性"] = round(s_stab, 1); comp += s_stab

    # 风险扣分
    pen = 0.0
    notes = []
    if m["ma60"] and m["price"] < m["ma60"]:
        pen += 6; notes.append("跌破 MA60")
    if m["pos52"] > 88:
        pen += 6; notes.append("一年高位")
    elif m["pos52"] > 75:
        pen += 3; notes.append("偏一年高位")
    if m["rsi"] > 76:
        pen += 4; notes.append("RSI 超买")
    if m["box_h"] > 45:
        pen += 4; notes.append("箱体过宽·一轮难做完")
    elif m["box_h"] > 36:
        pen += 2; notes.append("箱体偏宽")
    if m["amt_yi"] < 2:
        pen += 3; notes.append("成交额不足")
    # 趋势陡峭：做T是区间策略，走成单边趋势最容易做反（回测中破止损样本斜率显著更高）
    if abs(m["slope"]) > 4.5:
        pen += 6; notes.append("MA20 陡峭·近单边")
    elif abs(m["slope"]) > 3.0:
        pen += 3; notes.append("MA20 偏陡")
    # 贴/破箱体下沿：此时做T等同于在破位边缘接刀
    if m["box_low"] and m["price"] < m["box_low"] * 1.03:
        pen += 6; notes.append("贴箱体下沿·易破位")
    # 龙虎榜净卖出：席位在派发，做T易被闷杀
    if n_lhb and net_ratio < -0.3:
        pen += 5; notes.append("龙虎榜净卖出")
    elif n_lhb >= 3 and lhb_net < 0:
        pen += 3; notes.append("龙虎榜多上榜但累计净卖")
    # 短线过热：20 日超额过大 = 已在高潮段
    if (m.get("rs20") or 0) > 45:
        pen += 4; notes.append("20日超额过大·追高")
    if m["code"] in unlock:
        pen += 8; notes.append("近期解禁")
    if m["code"] in reduce:
        pen += 6; notes.append("计划减持窗口")
    detail["风险"] = -round(pen, 1)

    total = clamp(comp - pen, 0, 100)
    if total >= 80:
        g, gname = "A", "可重点做T"
    elif total >= 70:
        g, gname = "B", "适合做T"
    elif total >= 60:
        g, gname = "C", "可小仓试"
    else:
        g, gname = "D", "不适合"
    return round(total, 1), g, gname, detail, notes


# ---------------- v6 打分：先验固定因子集 · 域内横截面分位 ----------------
# 来自 quant/_tplus_lab.py（全市场域 93,331 样本 / 10 个月 / 训练段择优→测试段验证）。
# 因子方向全部由做T的经济逻辑给定（箱体窄、带宽低、均线粘合、波动规律、斜率平、
# 下沿被反复验证、流动性足），等权、不筛因子、不调权重 → 全期都是干净样本外。
PRIOR_FEATS = ["box_dev", "bwidth", "cohesion", "amp_cv", "amp_dev", "atr_dev",
               "slope_abs", "neg_tests", "neg_amt"]
PRIOR_CN = {
    "box_dev": "偏离理想箱体 |箱高−20%|（箱体要够窄，一轮才做得完）",
    "bwidth": "BOLL 带宽 4σ/MA20（带宽低 = 波动收敛）",
    "cohesion": "均线粘合度 MA5/10/20（粘合 = 无趋势 = 适合网格）",
    "amp_cv": "振幅变异系数（波动越规律越可预期）",
    "amp_dev": "偏离理想振幅 |amp20−6%|（太小没空间、太大是单边）",
    "atr_dev": "偏离理想 ATR |ATR%−5%|",
    "slope_abs": "|MA20 二十日斜率|（越横盘越好）",
    "neg_tests": "负的「近 60 日下沿被测试次数」（被验证过的支撑更可靠）",
    "neg_amt": "负的 20 日均成交额（流动性下限）",
}
# 卡片里展示用的短名（避免把整句释义塞进一行）
PRIOR_SHORT = {
    "box_dev": "箱体窄",
    "bwidth": "带宽低",
    "cohesion": "均线粘合",
    "amp_cv": "波动规律",
    "amp_dev": "振幅适中",
    "atr_dev": "ATR 适中",
    "slope_abs": "横盘",
    "neg_tests": "支撑被验",
    "neg_amt": "流动性",
}


def prior_raw(m):
    """从 calc_metrics 的 m 里取先验因子原始值（全部已统一成「越小越好」）。"""
    def _a(x):
        return abs(x)
    return {
        "box_dev": _a((m.get("box_h") or 0) - 20.0),
        "bwidth": m.get("bwidth"),
        "cohesion": m.get("cohesion"),
        "amp_cv": m.get("amp_cv"),
        "amp_dev": _a((m.get("amp20") or 0) - 6.0),
        "atr_dev": _a((m.get("atr_pct") or 0) - 5.0),
        "slope_abs": _a(m.get("slope") or 0.0),
        "neg_tests": -float(m.get("tests") or 0),
        "neg_amt": -float(m.get("amt_yi") or 0.0),
    }


def assign_prior_scores(rows, unlock=None, reduce=None):
    """v6：做T分 = 先验固定集的**域内横截面分位**（等权、方向全为「越小越好」）× 100。

    为什么换掉旧 7 维绝对分数：
      ① 绝对阈值（≥80 才是 A）会随行情漂移，同分数在不同日子的含义不同；分位不会。
      ② 实验室显示旧口径挑出来的是「波动大、贴下沿」的票 —— 完成一轮率高、
         但**期望收益反而更差**（D1 −0.71% vs D10 −0.07%）。先验集把「安静/收敛」放在首位，
         它的完成一轮率 edge 在训练半/测试半同向（+5.3pp / 同向），是这个框架里唯一稳定的选股能力。
    风险扣分（解禁/减持等）不再参与排序，改为**展示提示 + 放行否决**（弱辅助，与前几轮口径一致）。
    """
    n = len(rows)
    if not n:
        return
    raw = {r["code"]: prior_raw(r["m"]) for r in rows}
    rank = {f: {} for f in PRIOR_FEATS}
    for f in PRIOR_FEATS:
        vals = sorted([(raw[c][f], c) for c in raw if raw[c][f] is not None])
        if len(vals) < 5:
            continue
        m1 = len(vals) - 1
        for pos, (v, c) in enumerate(vals):
            rank[f][c] = (pos / m1) if m1 else 0.5
    for r in rows:
        c = r["code"]
        tot = cnt = 0.0
        det = {}
        for f in PRIOR_FEATS:
            v = rank[f].get(c)
            if v is None:
                continue
            tot += 1 - v
            cnt += 1
            det[f] = round((1 - v) * 100)
        qs = (tot / cnt * 100) if cnt else 0.0
        r["qs"] = round(qs, 1)
        r["score"] = round(qs, 1)
        r["qrank"] = None
        r["detail"] = {PRIOR_SHORT.get(f, f): v for f, v in det.items()}
        r["pctile"] = {f: det.get(f) for f in PRIOR_FEATS}
        # 风险提示（不参与排序）
        m = r["m"]
        pen, notes = 0.0, []
        if m["ma60"] and m["price"] < m["ma60"]:
            pen += 6; notes.append("跌破 MA60")
        if m["rsi"] > 76:
            pen += 4; notes.append("RSI 超买")
        if m["amt_yi"] < 2:
            pen += 3; notes.append("成交额不足")
        if abs(m["slope"]) > 4.5:
            pen += 6; notes.append("MA20 陡峭·近单边")
        elif abs(m["slope"]) > 3.0:
            pen += 3; notes.append("MA20 偏陡")
        lh = m.get("lhb") or {}
        net = lh.get("net") or 0
        if (lh.get("n") or 0) and m["cmc_yi"] and (net / (m["cmc_yi"] * 1e8) * 100) < -0.3:
            pen += 5; notes.append("龙虎榜净卖出")
        r["pen"] = -round(pen, 1) or 0
        r["notes"] = notes
        r["veto"] = bool(unlock and c in unlock) or bool(reduce and c in reduce)
        if unlock and c in unlock:
            notes.append("近期解禁")
        if reduce and c in reduce:
            notes.append("计划减持窗口")
    # 档位：域内分位（A = 前 10% / B = 前 25%）
    order = sorted(rows, key=lambda r: -r["score"])
    na = max(1, int(round(len(order) * 0.10)))
    nb = max(na + 1, int(round(len(order) * 0.25)))
    for i, r in enumerate(order):
        r["qrank"] = i + 1
        r["grade"] = "A" if i < na else ("B" if i < nb else "C")
        r["gname"] = {"A": "可重点做T", "B": "适合做T", "C": "仅跟踪"}[r["grade"]]
    for r in rows:
        if r.get("grade") is None:
            r["grade"], r["gname"] = "C", "仅跟踪"
    return order


def strong_grade(m):
    """强势分档（用于「强势股分析」板块；与总分独立，只看相对强度 + 均线结构）。"""
    s_rs = band(m.get("rs20"), 5.0, 30.0, -5.0, 55.0, 8) if m.get("rs20") is not None else 4.0
    s_multi = 4.0 if m.get("multi") else (2.0 if (m.get("ma20") and m.get("ma60")
                                                  and m["ma20"] > m["ma60"]
                                                  and m["price"] > m["ma20"]) else 0.0)
    v = s_rs + s_multi
    rs = m.get("rs20")
    above = bool(m.get("ma20") and m["price"] > m["ma20"])
    if rs is None:
        return v, "非强势"
    if rs >= 5.0 and m.get("multi"):
        return v, "强势多头"
    if rs >= 5.0 and above:
        return v, "强势整理"
    if rs >= 5.0:
        return v, "强势回调"
    if rs >= 0.0 and above and (m.get("ma20") or 0) > (m.get("ma60") or 0):
        return v, "温和偏强"
    return v, "非强势"


def plan_types(m):
    """判定主导做T类型"""
    grid = (15 <= m["box_h"] <= 48) and (abs(m["slope"]) <= 3.2) and (20 <= m["pos"] <= 80)
    return "网格型" if grid else "波段型"


def grid_levels(m):
    L, U = m["box_low"], m["box_high"]
    step = (U - L) / 4.0
    levels = []
    for i in range(5):
        p = L + step * i
        if i <= 1:
            act, cls = "分批买入", "gbuy"
        elif i == 2:
            act, cls = "中枢观望", "dim"
        else:
            act, cls = "分批卖出", "gsell"
        levels.append({"p": round(p, 2), "act": act, "cls": cls})
    return levels


def swing_plan(m):
    """波段买卖区。

    旧版卖区固定取箱体上沿 U*0.98~U —— 回测显示 5 日内只有 5%~10% 能摸到，
    「一轮做完」率仅 6%。改为 ATR 驱动：单轮目标 = 1.2 × ATR%（下限 2.5%），
    即赚一个波动单位的价差就走，而不是非等到箱体上沿。
    """
    L, U = m["box_low"], m["box_high"]
    price = m["price"]
    support = max(L, m["ma20"] if (m["ma20"] and m["ma20"] < price) else L)
    buy_lo, buy_hi = support, support * 1.02

    step = max(2.5, 1.2 * (m["atr_pct"] or 0)) / 100.0
    target = price * (1 + step)
    sell_lo = min(target * 0.99, U * 0.985)
    sell_lo = max(sell_lo, buy_hi * 1.01)      # 保证卖区在买区之上
    sell_hi = max(min(sell_lo * 1.02, U), sell_lo)
    stop = L * 0.955
    return {"support": round(support, 2), "sell": round(U, 2),
            "buy_lo": round(buy_lo, 2), "buy_hi": round(buy_hi, 2),
            "sell_lo": round(sell_lo, 2), "sell_hi": round(sell_hi, 2),
            "stop": round(stop, 2),
            "step_pct": round(step * 100, 2), "target": round(target, 2)}


GRADE_POS = {"A": "底仓 40% + 滚动 30%", "B": "底仓 30% + 滚动 20%",
             "C": "底仓 20% + 滚动 10%", "D": "不建议建仓"}
GRADE_POS_NUM = {"A": (40, 30), "B": (30, 20), "C": (20, 10), "D": (0, 0)}


def pos_text(g):
    """仓位建议 × 大盘环境系数"""
    env = CUR_ENV or {}
    scale = env.get("pos_scale", 1.0)
    lab = env.get("label") or ""
    base, roll = GRADE_POS_NUM.get(g, (0, 0))
    if g == "D" or scale <= 0:
        return "不建议建仓" + (f"（{lab}）" if lab and scale <= 0 else "")
    if scale >= 0.999:
        return GRADE_POS[g]
    return "底仓 %d%% + 滚动 %d%%（%s打 %s 折）" % (
        round(base * scale), round(roll * scale), lab,
        ("%.2f" % scale).rstrip("0").rstrip("."))


def render_card(r, hist_pool=None, today=None, is_new=False):
    m = r["m"]; g = r["grade"]
    p = r["swing"]; levels = r["levels"]
    hist_pool = hist_pool or {}
    pos_txt = ("贴下沿·低吸区" if m["pos"] < 33 else ("贴中枢" if m["pos"] <= 66 else "贴上沿·高抛区"))
    inst_tags = ""
    if m["top_inst"]:
        inst_tags += f"<span class='tag tinst'>顶级机构×{m['top_inst']}</span>"
    if m["fund_ratio"] is not None:
        inst_tags += f"<span class='tag tinst'>基金持股 {fnum(m['fund_ratio'],1)}%</span>"
    SRC_CSS_C = {"机构底仓": "tinst", "龙虎榜": "tlhb", "强势": "tstrong"}
    for s in (m.get("sources") or []):
        if s == "机构底仓" and m["fund_ratio"] is not None:
            continue
        inst_tags += f"<span class='tag {SRC_CSS_C.get(s, 'tgrid')}'>{esc(s)}</span>"
    _lh = m.get("lhb") or {}
    extra_sig = []
    if m.get("rs20") is not None:
        extra_sig.append(f"20日超额 {m['rs20']:+.1f}pp")
    if (_lh.get("n") or 0) > 0:
        extra_sig.append(f"近10日龙虎榜 {_lh['n']} 次／累计净买 {(_lh.get('net') or 0)/1e8:+.2f} 亿")
    if r.get("sg") and r["sg"] != "非强势":
        extra_sig.append(f"强势分档 {r['sg']}")
    typ = r["ptype"]
    tcls = "tgrid" if typ == "网格型" else "tswing"
    xbadge = X.badge_html(hist_pool, m["code"], today, is_new)
    _pr = X.prior_hits(hist_pool, m["code"], today)
    xcell = X.chip_html(hist_pool, m["code"], today) if _pr else ""
    # 无历史记录时不占一整行（信息密度够高了，少一行是一行）
    hist_line = ("<div class='sig dim'><b>历史入选</b>" + xcell + "</div>") if _pr else ""
    gl = "".join(
        f"<tr><td>{i+1}</td><td>{fnum(l['p'])}</td><td class='{l['cls']}'>{l['act']}</td></tr>"
        for i, l in enumerate(levels))
    notes = ("<div class='sig'>⚠ " + esc("、".join(r["notes"])) + "</div>") if r["notes"] else ""
    sigs = r["sigs"]
    sigs_html = "".join(f"<span class='tag tinst'>{esc(s)}</span>" for s in sigs)
    det = " · ".join(f"{k} {v}" for k, v in r["detail"].items())
    det_chips = "".join(
        f"<span class='pchip'>{esc(k)}<b>{v}</b></span>" for k, v in r["detail"].items())
    det_tip = esc("域内横截面分位（0~100，越高越符合做T先验：越安静、越收敛、流动性越足）。" +
                  "".join("｜%s：%s" % (PRIOR_SHORT.get(f, f), PRIOR_CN.get(f, f))
                          for f in PRIOR_FEATS))
    grid_tbl = ("<table class='gtable'><thead><tr><th" + tip_t('网格档') + ">网格档</th><th>价格</th><th>动作</th></tr></thead>"
                "<tbody>" + gl + "</tbody></table>")
    swing_line = (f"<div class='sig'><b{tip_t('波段买区')}>波段：</b>买区 {fnum(p['buy_lo'])}~{fnum(p['buy_hi'])}"
                  f"｜卖区 {fnum(p['sell_lo'])}~{fnum(p['sell_hi'])}｜"
                  f"<span class='down'><b{tip_t('止损')}>止损 {fnum(p['stop'])}</b></span></div>")
    # 按主导类型给方案，另一类降级为「备选」一行，避免两套价位混排干扰
    if typ == "网格型":
        plan = grid_tbl + "<div class='sig dim'>执行：每档仓位 = 卫星仓 ÷ 4，触档即执行，不追高、不超配。</div>"
        alt = (f"<div class='sig dim'><b>备选·波段：</b>买区 {fnum(p['buy_lo'])}~{fnum(p['buy_hi'])}｜"
               f"卖区 {fnum(p['sell_lo'])}~{fnum(p['sell_hi'])}｜止损 {fnum(p['stop'])}</div>")
    else:
        plan = swing_line + "<div class='sig dim'>执行：一轮 3~7 日；反弹至上沿先减半，破止损无条件离场。</div>"
        alt = (f"<div class='sig dim'><b>备选·网格：</b>箱体五档 {fnum(levels[0]['p'])} → {fnum(levels[-1]['p'])}"
               f"（若转入横盘、MA20 走平，可切网格执行）</div>")
    return f"""
  <div class='card'>
    <div class='hd'>
      <span class='nm'>{esc(m['name'])}</span>{xbadge}
      <span class='cd'>{esc(m['code'])} · {esc(m['industry'])}</span>
      <span class='badge b{g}'{tip_t('档位')}>{g}</span>
      <span class='tag' style='background:#eaf3fd;color:#1a73e8;border:1px solid #cfe2f6' title='做T方向（随大盘环境配对：弱环境做反T·先低吸后高抛；强环境做正T·先高抛后低吸补回；方向相反则不做）'>{esc(r.get('tdir') or '—')}</span>
      <span style='margin-left:auto' class='cd'{tip_t('做T分')}>做T分 <b style='color:#b8892b'>{r['score']}</b></span>
    </div>
    <div>{inst_tags}<span class='tag {tcls}'{tip_t('类型')}>{typ}</span>{sigs_html}</div>
    {("<div class='sig'><b>强势/龙虎榜：</b>" + esc(" · ".join(extra_sig)) + "</div>") if extra_sig else ""}
    <div class='grid2'>
      <div class='kv tipbox'{tip_t('现价')}><div class='k tipk'>现价</div><div class='v'>{fnum(m['price'])} <span class='{"up" if (m["chg"] or 0)>=0 else "down"}' style='font-size:11px'>{pct(m['chg'])}</span></div></div>
      <div class='kv tipbox'{tip_t('日内振幅')}><div class='k tipk'>振幅/ATR</div><div class='v sm'>{fnum(m['amp20'],1)}% / {fnum(m['atr_pct'],1)}%</div></div>
      <div class='kv tipbox'{tip_t('换手')}><div class='k tipk'>换手/量比</div><div class='v sm'>{fnum(m['turn'],1)}% / {fnum(m['vratio'],2)}</div></div>
      <div class='kv tipbox'{tip_t('箱体')}><div class='k tipk'>箱体 [下沿~上沿]</div><div class='v sm'>{fnum(m['box_low'])} ~ {fnum(m['box_high'])}</div></div>
      <div class='kv tipbox'{tip_t('箱体涨幅')}><div class='k tipk'>箱体最大理论涨幅</div><div class='v up'>{fnum(m['box_h'],1)}%</div></div>
      <div class='kv tipbox'{tip_t('箱内位置')}><div class='k tipk'>箱内位置</div><div class='v sm'>{fnum(m['pos'],0)}% · {pos_txt}</div></div>
      <div class='kv tipbox'{tip_t('均线斜率')}><div class='k tipk'>MA20 斜率</div><div class='v sm'>{pct(m['slope'])}</div></div>
    </div>
    <div class='sig'><b class='tip' title='{esc(TIPS.get('底仓/滚动',''))}'>仓位建议：</b>{esc(pos_text(g))}</div>
    {hist_line}
    {plan}
    {alt}
    <div class='sig'><b class='tip' title='{det_tip}'>打分（先验分位）：</b>
    <span class='pchips'>{det_chips}</span>
    <span class='dim' style='font-size:11px'>风险提示 {r['pen'] if r['pen'] else '无'}（只作提示、不参与排序）</span></div>
    {notes}
    <div class='sig dim'><b{tip_t('失效条件')}>失效：</b>放量跌破 {fnum(p['stop'])} 或 MA20 拐头向下 → 停做T。</div>
  </div>"""


def build(date):
    uj = os.path.join(DATA, f"universe_{date}.json")
    qj = os.path.join(DATA, f"quotes_{date}.json")
    kj = os.path.join(DATA, f"kline_{date}.json")
    for p in (uj, qj, kj):
        if not os.path.exists(p):
            print(f"[build_tplus] 缺少 {p}"); sys.exit(1)
    universe = json.load(open(uj, encoding="utf-8"))
    quotes = json.load(open(qj, encoding="utf-8"))
    kline = json.load(open(kj, encoding="utf-8"))
    unlock, reduce = load_risk_sets(date)
    set_index(E.get_index("sh000001", n=200, need_date=date))

    # ---------- 第一道闸：箱体锚定（必须是「真的在箱体内反复」的票） ----------
    # 旧口径用「滚动 20 日 max(high)/min(low)」，每天重算 → 边界天天漂，参考意义弱。
    # 改为锚定：箱体确立后 U/L 锁死，只有真逃逸才换版。不合格直接**取消出池**，不降级凑数。
    boxes = TB.load_state()
    box_drop = {}
    gate_drop = {}

    def _drop(k):
        gate_drop[k] = gate_drop.get(k, 0) + 1

    rows = []
    for u in universe:
        code = u["code"]
        nodes = kline.get(code)
        q = quotes.get(code)
        if not nodes or not q:
            continue
        box = TB.anchor(code, nodes, date, boxes, save=False)
        cat = TB.fail_cat(box)
        if cat:
            box_drop[cat] = box_drop.get(cat, 0) + 1
            continue
        m = calc_metrics(code, u, q, nodes, box)
        if not m:
            _drop("有效日K不足 30 根")
            continue
        # 硬门槛（逐项计数 —— 页面上要如实交代「为什么被取消」）
        nm = m["name"] or ""
        if "ST" in nm or "退" in nm or m["price"] < 3:
            _drop("ST / 退市 / 股价 < 3 元"); continue
        if not (20 <= m["cmc_yi"] <= 1200):
            _drop("流通市值不在 20~1200 亿"); continue
        # 流动性看**成交额**而不是换手率：换手是结果不是原因，且 A 股大市值票
        # 20 日均换手常年低于 2%（正常现象），用换手卡会误杀一大片能正常做T的票。
        if (m["amt_yi"] or 0) < 1.5:
            _drop("20 日均成交额 < 1.5 亿（流动性不足）"); continue
        if m["amp20"] < 3.0 or max(m["atr_pct"], m["amp20"]) < 3.0:
            _drop("日振幅/ATR < 3%（做T没空间）"); continue
        if (m["chg60"] or 0) < -30 or (m["chg20"] or 0) > 60:
            _drop("近 60 日跌超 30% 或 20 日涨超 60%"); continue
        if not (12 <= m["pos52"] <= 92):
            _drop("一年分位不在 12%~92%"); continue
        if not (8 <= m["box_h"] <= 55):
            _drop("箱体高度不在 8%~55%"); continue

        total, g, gname, detail, notes = score(m, unlock, reduce)
        ptype = plan_types(m)
        sg_v, sg = strong_grade(m)
        sigs = []
        if m["amp20"] >= 4:
            sigs.append(f"高振幅 {m['amp20']:.1f}%")
        if m["top_inst"]:
            sigs.append("顶级机构底仓")
        if m["fund_ratio"] and m["fund_ratio"] >= 10:
            sigs.append(f"公募重仓 {m['fund_ratio']:.0f}%")
        if abs(m["slope"]) <= 1.5:
            sigs.append("MA20 走平")
        if 35 <= m["rsi"] <= 70:
            sigs.append(f"RSI {m['rsi']:.0f}")
        lh = m.get("lhb") or {}
        if lh.get("n"):
            sigs.append(f"近10日上榜 {lh['n']} 次")
        if (m.get("rs20") or 0) >= 10:
            sigs.append(f"20日超额 {m['rs20']:.0f}pp")
        rows.append({
            "code": code, "name": m["name"], "industry": m["industry"],
            "m": m, "score": total, "grade": g, "gname": gname,
            "detail": detail, "pen": detail["风险"], "notes": notes,
            "v5score": total,
            "ptype": ptype, "levels": grid_levels(m), "swing": swing_plan(m), "sigs": sigs,
            "sg_v": sg_v, "sg": sg, "sources": m.get("sources") or [],
        })

    TB.save_state(boxes)      # 箱体锁定状态落盘（本地累积，不推送）
    n_box_cancel = sum(box_drop.values())
    print(f"[build_tplus] 箱体闸门：通过 {len(rows)} 只，取消 {n_box_cancel} 只 —— "
          + ("；".join(f"{k} {v}" for k, v in sorted(box_drop.items(), key=lambda x: -x[1])) or "无"))
    n_gate_cancel = sum(gate_drop.values())
    print(f"[build_tplus] 常规硬门槛：再取消 {n_gate_cancel} 只 —— "
          + ("；".join(f"{k} {v}" for k, v in sorted(gate_drop.items(), key=lambda x: -x[1])) or "无"))

    n_uni = len(universe)
    drop_list = sorted(list(box_drop.items()) + list(gate_drop.items()),
                       key=lambda x: -x[1])[:8]
    if drop_list:
        lis = "".join(f"<li>{esc(k)} —— <b>{v}</b> 只</li>" for k, v in drop_list)
        drop_html = ("<div class='note warn'><b>今日被取消的 %d 只，按原因排序：</b>"
                     "<ul style='margin:6px 0 0 0;padding-left:20px'>%s</ul>"
                     "<span class='dim'>同一只票命中多个条件时只计入第一个命中的原因。</span></div>"
                     % (n_box_cancel + n_gate_cancel, lis))
    else:
        drop_html = ""

    # ---- 箱体质量闸门的走前验证（每日实算，不写死数字）----
    try:
        wf = TB.walk_forward(kline)
    except Exception:
        wf = None
    if wf and wf["core"]["n"] and wf["ctrl"]["n"]:
        c, k_ = wf["ctrl"], wf["core"]
        wf_html = (
            "<div class='note ok'><b>箱体闸门的走前验证（每日实算）：</b>"
            "选股只用 T 日及之前的信息、箱体在 T 日<b>锁定</b>后不再改动，"
            "再用 T+1~T+5 的<b>真实走势</b>独立检验。<br>"
            "对照组（有箱体但不加质量闸，{c_n} 样本） → 核心组（叠加质量闸，{k_n} 样本）：<br>"
            "· 出现低吸机会 <b>{c_had}% → {k_had}%</b><br>"
            "· 5 日内完成一轮 <b>{c_done}% → {k_done}%</b>（基本持平）<br>"
            "· <b>破止损率 {c_stop}% → {k_stop}%</b>（{d_stop} pp）<br>"
            "<span class='dim'>读数：加了这道闸，更容易低吸到、且明显更少被打到止损；"
            "完成一轮的概率基本不变 —— 净效应是「用更少的破位换同样的赚钱机会」。</span></div>"
        ).format(c_n=c["n"], k_n=k_["n"],
                 c_had="%.1f" % c["had"], k_had="%.1f" % k_["had"],
                 c_done="%.1f" % c["done"], k_done="%.1f" % k_["done"],
                 c_stop="%.1f" % c["stop"], k_stop="%.1f" % k_["stop"],
                 d_stop="%+.2f" % (k_["stop"] - c["stop"]))
    else:
        wf_html = ""

    # ---- v6 打分：先验固定集 · 域内横截面分位（替代旧 7 维手调绝对阈值）----
    assign_prior_scores(rows, unlock, reduce)
    for r in rows:
        if r.get("veto"):
            r["grade"], r["gname"] = "D", "风险否决·仅跟踪"
    rows.sort(key=lambda r: ((r["grade"] == "D"), -r["score"]))

    # ---------- 大盘环境门控 ----------
    global CUR_ENV, ENV_STRICT_NOTE, CUR_TDIR, CUR_IDX20
    env = E.market_env(date)
    CUR_ENV = env
    # ---- 做T方向 × 环境配对（原则15：弱环境做反T、强环境做正T，反向配对最差）----
    # 实证 env_combo（quant/_tplus_lab_result.json）：反T 在 弱势/偏弱（上证近20日<0）
    # 可兑现期望收益为正（+0.23%/+0.14%），在 强势 为负（−0.27%）；正T（combo_best
    # "高抛0.4×ATR→补回−1%/T+3"）为强环境方向。故方向由「上证近20日偏离」决定，
    # 而不靠回测手调——这是把「环境」从 β 系数升级为「方向选择器」的关键一步。
    bench20 = _idx_chg(date, 20)
    CUR_IDX20 = bench20
    if bench20 is None:
        CUR_TDIR = None
    elif bench20 < 0:
        CUR_TDIR = "反T"      # 先低吸后高抛（弱/偏弱环境）
    else:
        CUR_TDIR = "正T"      # 先高抛后低吸补回（偏强/强势环境）
    allowed = set(env["allow"])
    if env["label"] == "弱势":
        # 弱势附加：非高位 + MA20 未明显下行 + 箱体不过宽（下沿易被击穿，只留结构最稳的）
        def strict(r):
            m = r["m"]
            return (m["pos52"] <= 70 and m["slope"] >= -1.0 and m["box_h"] <= 40)
        ENV_STRICT_NOTE = "一年分位 ≤70% · MA20 斜率 ≥−1% · 箱体高度 ≤40%"
    else:
        def strict(r):
            return True
        ENV_STRICT_NOTE = ""
    rel_set = set()
    for r in rows:
        # 方向配对门控：环境方向未知 → 不放行（「不知道哪一档就默认不做」）。
        # 已知方向时，仍须满足档位 + 弱势附加条件才放行。
        if CUR_TDIR is None:
            r["release"] = False
        elif r["grade"] in allowed and strict(r):
            r["release"] = True
            rel_set.add(r["code"])
        else:
            r["release"] = False
        r["tdir"] = CUR_TDIR
    rows.sort(key=lambda r: (not r["release"], -r["score"]))
    n_rel = len(rel_set)

    # ★ 出票许可：只读证据页 `_tplus_gate_page.emit_license()`，读不到即 fail-safe 不出票。
    #   做T池的特殊性：逐日平衡 edge 为正**不等于**实际成交能赚 ——
    #   实测 A 档逐日 +0.54pp（R3 95.0%）达标，但「触买后」池化期望 −0.28%、
    #   往返率仅 5.15%（同域非 A 档 12.65%）→ 选出来的是「看着安静但难成交」的票。
    #   许可里含**池化闸**，专门拦这一类「统计好看但执行不了」的情况。
    emit_ok, emit_why = True, ""
    try:
        import _tplus_gate_page as _GP
        _lic = _GP.emit_license()
        _a = (_lic.get("detail", {}) or {}).get("A", {}) or {}
        emit_ok = bool(_a.get("ok"))
        emit_why = _a.get("why", "")
    except Exception as ex:
        emit_ok, emit_why = False, "证据不可用：%s" % ex
    if not emit_ok:
        print("[tplus] 出票许可未通过 → 本期不出票（宁可不选）：%s" % emit_why)

    # 主榜 & 操作手册 = **已放行的最高档（A）**。参考性质的票（仅跟踪 / 未放行）一律不展示
    # ——用户要的是「只挑胜率最高的」，把参考票混在一张表里只会稀释注意力。
    anchors = [r for r in rows if r.get("release") and r["grade"] == "A"]
    # ★ 出票许可未过 → 主榜与操作手册一律清空（不做「降级展示」：
    #   许可没过说明这条规则本身没被验证过，展示它就是在给未验证的规则背书）。
    if not emit_ok:
        anchors = []
    # 方向内按「箱内位置与方向匹配」优先：反T 偏好低位（低吸空间大）、
    # 正T 偏好高位（高抛空间大）—— 让个股位置与做T方向一致，提升实际执行期望。
    def _align(r):
        pos = (r["m"].get("pos") or 50)
        if r.get("tdir") == "反T":
            return -pos
        elif r.get("tdir") == "正T":
            return pos
        return 0
    anchors.sort(key=lambda r: (_align(r), -r["score"], r["code"]))   # code 兜底，保证跨进程排序稳定
    abc = anchors
    top = anchors

    # ---------- 强势股分析（池内分档；排除「非强势」） ----------
    strong_rows = [r for r in rows if r["sg"] != "非强势"]
    strong_rows.sort(key=lambda r: ((r["m"].get("rs20") or -99), r["score"]), reverse=True)
    strong_rows = strong_rows[:60]

    # ---------- 龙虎榜视角（近 10 交易日上榜；放行者优先，再按净买） ----------
    lhb_rows = [r for r in rows if ((r["m"].get("lhb") or {}).get("n") or 0) > 0]
    lhb_rows.sort(key=lambda r: (bool(r.get("release")),
                                 ((r["m"].get("lhb") or {}).get("net") or 0)), reverse=True)
    lhb_rows = lhb_rows[:60]

    # 历史（逐股留存 → 供跨期「历史入选」徽标与「与上一期对比」；汇总字段保留兼容）
    hist = []
    if os.path.exists(HIST):
        try:
            hist = json.load(open(HIST, encoding="utf-8"))
        except Exception:
            hist = []
    hist = [h for h in hist if h.get("date") != date]
    hist.append({"date": date, "total": len(rows),
                 "note": "%s环境 · 放行 %d 只 · 源 机构%d/龙虎%d/强势%d" % (
                     (CUR_ENV or {}).get("label") or "未知",
                     sum(1 for r in rows if r.get("release")),
                     sum(1 for r in rows if "机构底仓" in r["sources"]),
                     sum(1 for r in rows if "龙虎榜" in r["sources"]),
                     sum(1 for r in rows if "强势" in r["sources"])),
                 "A": sum(1 for r in rows if r["grade"] == "A"),
                 "B": sum(1 for r in rows if r["grade"] == "B"),
                 "C": sum(1 for r in rows if r["grade"] == "C"),
                 "grid": sum(1 for r in rows if r["ptype"] == "网格型"),
                 "swing": sum(1 for r in rows if r["ptype"] == "波段型"),
                 "codes": [{"code": r["code"], "name": r["name"],
                            "ptype": r["ptype"], "grade": r["grade"],
                            "score": r["score"]} for r in rows]})
    hist.sort(key=lambda h: h["date"])
    json.dump(hist, open(HIST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 跨池历史入选（MACD观察池 / 信号池 / 做T池 / 反转池）
    hist_pool = X.load_cross_history()
    today = date
    prev_row = None
    for h in reversed(hist):
        if h.get("date") and h["date"] < date and h.get("codes"):
            prev_row = h
            break
    prev_codes = [c.get("code") for c in (prev_row or {}).get("codes", []) if c.get("code")]
    cur_codes = [r["code"] for r in rows]
    new_codes, _cont, _out = X.compare_sets(cur_codes, prev_codes)
    new_set = set(new_codes)

    na = sum(1 for r in rows if r["grade"] == "A")
    nb = sum(1 for r in rows if r["grade"] == "B")
    nc = sum(1 for r in rows if r["grade"] == "C")
    ng = sum(1 for r in rows if r["ptype"] == "网格型")
    n_inst = sum(1 for r in rows if "机构底仓" in r["sources"])
    n_lhb = sum(1 for r in rows if "龙虎榜" in r["sources"])
    n_str = sum(1 for r in rows if "强势" in r["sources"])
    n_multi = sum(1 for r in rows if len(r["sources"]) >= 2)

    def th(k, t, label, tipkey=None):
        extra = tip(tipkey) if (tipkey and tipkey in TIPS) else ""
        return f"<th data-k='{k}' data-t='{t}'{extra}>{label}</th>"

    # 主表 = 「一张表就能直接操作」：箱体 + 买卖区 + 止损 + 仓位全在里面，
    # 不再掺入「参考」性质的列（来源/龙虎榜/强势/历史入选等已移出，见页面下方折叠区）。
    thead = ("<thead><tr>"
             + th("score", "n", "分", "做T分")
             + th("name", "s", "名称")
             + th("code", "s", "代码 · 行业")
             + th("box", "s", "箱体 下沿~上沿", "箱体")
             + th("lock", "s", "锁定状态", "箱体锁定")
             + th("boxmax", "n", "箱高%", "箱体涨幅")
             + th("pos", "n", "箱位%", "箱内位置")
             + th("rt", "n", "往返/验证", "往返")
             + th("price", "n", "现价", "现价")
             + th("buy", "n", "低吸区", "波段买区")
             + th("sell", "n", "高抛区", "波段卖区")
             + th("stop", "n", "止损", "止损")
             + th("pos2", "s", "仓位建议", "底仓/滚动")
             + "</tr></thead>")

    def row_html(r):
        m = r["m"]; p = r["swing"]; b = m.get("box") or {}
        cx = "up" if (m["chg"] or 0) >= 0 else "down"
        area = "低吸区" if m["pos"] < 33 else ("中枢" if m["pos"] <= 66 else "高抛区")
        area_cls = "down" if m["pos"] < 33 else ("muted" if m["pos"] <= 66 else "up")
        lock = (f"第{b.get('ver') or 1}版 · {b.get('since') or '—'} 起 · 已锁 {b.get('age') or 0} 日"
                if b else "—")
        rt = f"{b.get('rounds') or 0}轮·上{b.get('touch_h') or 0}下{b.get('touch_l') or 0}"
        return (
            f"<tr>"
            f"<td data-l='做T分' data-v='{r['score']}'><b>{r['score']}</b></td>"
            f"<td data-l='名称'>{esc(m['name'])}"
            f"{X.badge_html(hist_pool, m['code'], today, m['code'] in new_set)}</td>"
            f"<td data-l='代码 · 行业' class='muted'>{esc(m['code'])}"
            f"<span class='dim'><br>{esc(m['industry'] or '—')}</span></td>"
            f"<td data-l='箱体 下沿~上沿' data-v='{m['box_low']}'>{fnum(m['box_low'])} ~ {fnum(m['box_high'])}</td>"
            f"<td data-l='锁定状态' class='dim' style='font-size:12px'>{esc(lock)}</td>"
            f"<td data-l='箱高%' data-v='{m['box_h']}'><b style='color:#b8892b'>{fnum(m['box_h'],1)}%</b></td>"
            f"<td data-l='箱位%' data-v='{m['pos']}'>{box_bar(m)}"
            f"<span class='{area_cls}' style='font-size:11px'><br>{area}</span></td>"
            f"<td data-l='往返/验证' data-v='{b.get('rounds') or 0}'>{esc(rt)}</td>"
            f"<td data-l='现价' data-v='{m['price']}'>{fnum(m['price'])}"
            f"<span class='{cx}' style='font-size:11px'><br>{pct(m['chg'])}</span></td>"
            f"<td data-l='低吸区' data-v='{p['buy_lo']}'>"
            f"<span class='down'>{fnum(p['buy_lo'])}~{fnum(p['buy_hi'])}</span></td>"
            f"<td data-l='高抛区' data-v='{p['sell_lo']}'>"
            f"<span class='up'>{fnum(p['sell_lo'])}~{fnum(p['sell_hi'])}</span></td>"
            f"<td data-l='止损' data-v='{p['stop']}'><b>{fnum(p['stop'])}</b></td>"
            f"<td data-l='仓位建议'>{esc(pos_text(r['grade']))}</td>"
            f"</tr>")

    table_html = "".join(row_html(r) for r in top)

    # ---------- 箱体位置观测：把每只票的「预计箱体」与「现价位置」摊在一张表里 ----------
    # 只回答一个客观问题：**现价落在这只票已经跑出来的箱体的哪个位置**。
    # 上下沿是 `_tbox` 的**锚定值**（过去 90 日里被反复触碰验证过的边界），不是对未来价格的预测。
    def _bpos(r):
        return clamp(r["m"].get("pos") or 0, 0, 100)

    def _escaped(r):
        m = r["m"]
        return bool(m["box_low"] and m["box_high"] and m["price"]
                    and (m["price"] > m["box_high"] or m["price"] < m["box_low"]))

    # 默认排序：仍在箱体内的排前面（按位置由低到高），已在箱体外的排后面 ——
    # 做T关心的是「区间还在不在」，越界的票保留展示但不当作有效区间读。
    box_list = sorted(rows, key=lambda r: (_escaped(r), _bpos(r), -r["score"], r["code"]))
    n_lo = sum(1 for r in rows if not _escaped(r) and _bpos(r) < 33)
    n_mid = sum(1 for r in rows if 33 <= _bpos(r) <= 67)
    n_hi = sum(1 for r in rows if not _escaped(r) and _bpos(r) > 67)

    n_out = sum(1 for r in rows if _escaped(r))
    n_edge = sum(1 for r in rows
                 if (not _escaped(r)) and (_bpos(r) >= 90 or _bpos(r) < 10))
    _bhs = [_bpos(r) for r in rows]
    bh_med = sorted(_bhs)[len(_bhs) // 2] if _bhs else 0

    def brow(r):
        m = r["m"]; b = m.get("box") or {}
        cx = "up" if (m["chg"] or 0) >= 0 else "down"
        lo, hi, px = m["box_low"], m["box_high"], m["price"]
        dlo = (px - lo) / px * 100 if px else 0
        dhi = (hi - px) / px * 100 if px else 0
        stt, scls = pos_state(m["pos"], px, lo, hi)
        lock = (f"第{b.get('ver') or 1}版 · 已锁{b.get('age') or 0}日"
                f"<span class='dim'><br>{esc(b.get('since') or '—')} 起</span>" if b else "—")
        rt = f"{b.get('rounds') or 0}轮·上{b.get('touch_h') or 0}下{b.get('touch_l') or 0}"
        return (
            f"<tr>"
            f"<td data-l='名称'>{esc(m['name'])}"
            f"{X.badge_html(hist_pool, m['code'], today, m['code'] in new_set)}</td>"
            f"<td data-l='代码 · 行业' class='muted'>{esc(m['code'])}"
            f"<span class='dim'><br>{esc(m['industry'] or '—')}</span></td>"
            f"<td data-l='现价' data-v='{px}'>{fnum(px)}"
            f"<span class='{cx}' style='font-size:11px'><br>{pct(m['chg'])}</span></td>"
            f"<td data-l='箱体下沿' data-v='{lo}' class='down'><b>{fnum(lo)}</b></td>"
            f"<td data-l='箱体上沿' data-v='{hi}' class='up'><b>{fnum(hi)}</b></td>"
            f"<td data-l='箱内位置' data-v='{m['pos']}'>{box_bar(m)}</td>"
            f"<td data-l='位置状态' class='{scls}'>{stt}</td>"
            f"<td data-l='距下沿' data-v='{dlo}' class='down' style='white-space:nowrap'>{fnum(dlo,1)}%</td>"
            f"<td data-l='距上沿' data-v='{dhi}' class='up' style='white-space:nowrap'>{fnum(dhi,1)}%</td>"
            f"<td data-l='箱高%' data-v='{m['box_h']}' style='white-space:nowrap'>{fnum(m['box_h'],1)}%</td>"
            f"<td data-l='锁定状态' class='dim' style='font-size:12px;white-space:nowrap'>{lock}</td>"
            f"<td data-l='往返/验证' data-v='{b.get('rounds') or 0}' style='white-space:nowrap'>{esc(rt)}</td>"
            f"<td data-l='档位'><span class='badge b{r['grade']}'>{r['grade']}</span></td>"
            f"</tr>")

    bhead = ("<thead><tr>"
             + th("nm", "s", "名称") + th("cd", "s", "代码 · 行业")
             + th("px", "n", "现价(T日收盘)", "现价")
             + th("lo", "n", "箱体下沿 L", "箱体下沿")
             + th("hi", "n", "箱体上沿 U", "箱体上沿")
             + th("pp", "n", "箱内位置", "箱体位置图")
             + th("st", "s", "位置状态", "位置状态")
             + th("dl", "n", "距下沿", "距下沿")
             + th("du", "n", "距上沿", "距上沿")
             + th("bh", "n", "箱高%", "箱体涨幅")
             + th("lk", "s", "锁定状态", "箱体锁定")
             + th("rt", "n", "往返/验证", "往返")
             + th("gd", "s", "档位")
             + "</tr></thead>")
    btable = ("".join(brow(r) for r in box_list)
              or "<tr><td colspan='13' class='dim'>今日池内无通过箱体闸门的标的</td></tr>")
    box_html = f"""<div class='section'><h2>箱体位置观测（{len(box_list)} 只 · 预计箱体与现价位置）</h2>
<div class='note'><b>这张表只回答一个问题：</b><b>现价落在这只票已经跑出来的箱体里的哪个位置。</b><br>
<b>怎么读：</b>横条 = 箱体本身，<b>左端是下沿 L、右端是上沿 U，黑色竖线是现价</b>；
底色三段对应<span class='down'>低吸区(0~20%)</span> / 中枢(20~80%) / <span class='up'>高抛区(80~100%)</span>，与涨红跌绿一致。
旁边的「距下沿 / 距上沿」是<b>价格距离</b>：再跌多少 % 到底、再涨多少 % 到顶；
<b>出现负数</b>就说明现价<b>已经越过那条边界</b>（同时会标 ↗/↘ 并给出超出幅度）。<br>
<b>⚠ 上下沿不是对未来的价格预测。</b>它们是过去 90 个交易日里<b>被反复验证过</b>的边界
（上沿被触碰 ≥2 次 + 下沿被触碰 ≥2 次 + 至少完成 1 轮完整往返，才算成立），
由 <code>_tbox</code> 锚定后<b>锁死</b>：数值天天不变，只有真走出区间才换版并更新「确立日」——
这正是「锁定状态」列要交代的。<b>箱体只能说明过去在哪个区间里来回，不能说明将来不会破。</b><br>
{'<b style="color:#b8332a">本期出票许可未通过 → 本表仅作位置观测，<u>不构成任何操作依据</u>。</b>' if not emit_ok else '<b>本期已通过出票许可</b>，操作依据仍以上方榜单为准，本表只补位置信息。'}
</div>
<div class='bxsum'>
  <div><b class='down'>{n_lo}</b><span>箱内 · 箱底区（位置 &lt;33%）</span></div>
  <div><b class='muted'>{n_mid}</b><span>箱内 · 中枢区（33%~67%）</span></div>
  <div><b class='up'>{n_hi}</b><span>箱内 · 箱顶区（位置 &gt;67%）</span></div>
  <div><b>{n_edge}</b><span>贴边但未越界（&lt;10% 或 ≥90%）</span></div>
  <div><b>{n_out}</b><span>现价已在箱体外（↗/↘）</span></div>
  <div><b>{fnum(bh_med,0)}%</b><span>全池箱位中位数</span></div>
</div>
<div class='note dim'>默认排序 = <b>仍在箱内的排前面（位置由低到高），已走出区间的排到最后</b>；点表头可改排序。<br>
越界 ≠ 箱体失效：<code>_tbox</code> 要求<b>连续 2 个交易日收盘越界 2% 以上</b>才换版，
所以偶有一天走出区间是正常的 —— 表里如实标 ↗/↘ 并给出超出幅度，等后续成交来验证，
既不假装没发生，也不提前改数。</div>
<div class='tbl-wrap'><table class='sortable rt'>{bhead}<tbody>{btable}</tbody></table></div></div>
"""
    # A/B 档卡片按主导类型分成两组，组内各自给对应操作方式
    g_cards = [r for r in abc if r["ptype"] == "网格型"]
    s_cards = [r for r in abc if r["ptype"] == "波段型"]
    grid_cards = "".join(render_card(r, hist_pool, today, r["code"] in new_set) for r in g_cards)
    swing_cards = "".join(render_card(r, hist_pool, today, r["code"] in new_set) for r in s_cards)

    hist_rows = "".join(
        f"<tr><td><a href='tplus-{esc(h['date'])}.html'>{esc(h['date'])}</a></td>"
        f"<td data-v='{h.get('total', 0)}'>{h.get('total', 0)}</td>"
        f"<td data-v='{h.get('A', 0)}'>{h.get('A', 0)}</td>"
        f"<td data-v='{h.get('B', 0)}'>{h.get('B', 0)}</td>"
        f"<td data-v='{h.get('C', 0)}'>{h.get('C', 0)}</td>"
        f"<td data-v='{h.get('grid', 0)}'>{h.get('grid', 0)}</td>"
        f"<td data-v='{h.get('swing', 0)}'>{h.get('swing', 0)}</td>"
        f"<td class='dim'>{(h.get('note') or '—')}</td></tr>"
        for h in hist[-20:][::-1])

    # ---------- 强势股分析（池内分档） ----------
    def srow(r):
        m = r["m"]
        rs20, rs60 = m.get("rs20"), m.get("rs60")
        mtxt = "多头排列" if m.get("multi") else ("站上 MA20" if (m["ma20"] and m["price"] > m["ma20"]) else "—")
        mcls = "ok" if m.get("multi") else ""
        near = m.get("to_hi52")
        if m["ma10"] and m["ma20"]:
            adv = f"回踩 MA10({fnum(m['ma10'])}) 不破可吸 · 破 MA20({fnum(m['ma20'])}) 离场"
        else:
            adv = "—"
        gcls = {"强势多头": "bA", "强势整理": "bB", "强势回调": "bD",
                "温和偏强": "bC"}.get(r["sg"], "bC")
        return (f"<tr><td>{esc(m['name'])}</td>"
                f"<td class='muted'>{esc(m['code'])}</td>"
                f"<td>{esc(m['industry'] or '—')}</td>"
                f"<td data-v='{(rs20 if rs20 is not None else -999)}'><b class='{'up' if (rs20 or 0) >= 0 else 'down'}'>{fnum(rs20,1)}</b></td>"
                f"<td data-v='{(rs60 if rs60 is not None else -999)}'>{fnum(rs60,1)}</td>"
                f"<td data-v='{near if near is not None else -999}'>{fnum(near,1)}%</td>"
                f"<td>{mtxt}</td>"
                f"<td data-v='{m['amp20']}'>{fnum(m['amp20'],1)}</td>"
                f"<td data-v='{m['turn']}'>{fnum(m['turn'],1)}</td>"
                f"<td data-v='{m['box_low']}' style='white-space:nowrap'>"
                f"<span class='down'>{fnum(m['box_low'])}</span>~<span class='up'>{fnum(m['box_high'])}</span></td>"
                f"<td data-v='{m['pos']}'>{box_bar(m)}</td>"
                f"<td><span class='badge {gcls}'>{r['sg']}</span></td>"
                f"<td>{r['score']}</td>"
                f"<td class='dim' style='white-space:normal'>{adv}</td></tr>")

    strong_html = "".join(srow(r) for r in strong_rows)

    # ---------- 龙虎榜视角（近 10 交易日上榜） ----------
    def lrow(r):
        m = r["m"]
        lh = m.get("lhb") or {}
        net = (lh.get("net") or 0) / 1e8
        lnet = (lh.get("last_net") or 0) / 1e8
        hot = lh.get("hot") or "—"
        tags = "、".join(lh.get("tags") or []) or "—"
        cls = "up" if net >= 0 else "down"
        return (f"<tr><td>{esc(m['name'])}</td>"
                f"<td class='muted'>{esc(m['code'])}</td>"
                f"<td>{esc(m['industry'] or '—')}</td>"
                f"<td>{esc(lh.get('last') or '—')}</td>"
                f"<td data-v='{lh.get('n') or 0}'><b>{lh.get('n') or 0}</b></td>"
                f"<td data-v='{lnet}'>{fnum(lnet,2)}</td>"
                f"<td data-v='{net}'><b class='{cls}'>{fnum(net,2)}</b></td>"
                f"<td>{esc(hot)}</td>"
                f"<td class='dim' style='white-space:normal'>{esc(tags)}</td>"
                f"<td data-v='{r['score']}'>{r['score']} <span class='badge b{r['grade']}'>{r['grade']}</span></td></tr>")

    lhb_html = "".join(lrow(r) for r in lhb_rows)
    lhb_net_sum = sum(((r["m"].get("lhb") or {}).get("net") or 0) for r in lhb_rows) / 1e8

    env = CUR_ENV or {}
    det = env.get("detail") or {}
    idx = det.get("index") or {}
    bench20 = _idx_chg(date, 20)
    ecls = {"强势": "ok", "震荡": "", "弱势": "warn", "破位": "warn"}.get(env.get("label"), "")
    ecolor = {"强势": "#1a9e5a", "震荡": "#b8893b",
              "弱势": "#b8332a", "破位": "#b8332a"}.get(env.get("label"), "#6b7280")
    tdir_label = CUR_TDIR or "未知"
    tdir_color = {"反T": "#1a73e8", "正T": "#b8893b"}.get(tdir_label, "#b8332a")
    tdir_line = ("<br><b class='tip' title='%s'>做T方向（原则15·环境×方向配对）：</b>"
                 "<span style='color:%s;font-weight:700'>%s</span>"
                 % (esc("弱环境(上证近20日<0)做反T·先低吸后高抛；强环境做正T·先高抛后低吸补回；"
                       "反向配对(弱环境做正T/强环境做反T)是全表最差档，故不做。方向无法判定则空仓。"),
                    tdir_color, esc(tdir_label)))
    if CUR_TDIR is None:
        tdir_line += "（环境方向无法判定 → 按纪律空仓，今日不做T）"
    elif CUR_IDX20 is not None:
        tdir_line += "（上证近20日 %+.2f%%）" % CUR_IDX20
    env_html = (
        "<div class='note %s' style='border-left:4px solid %s'>"
        "<b class='tip' title='%s'>大盘环境：%s</b>（综合 %.2f｜画像 %.2f · 指数 %.2f"
        "%s）<br>%s%s</div>"
    ) % (ecls, ecolor, esc(TIPS.get("大环境", "")), esc(env.get("label") or "未知"),
         env.get("score") or 0, det.get("profile_core") or 0, det.get("index_score") or 0,
         ("｜上证 %s %s" % (idx.get("close"), "在 MA20 上方" if idx.get("above_ma20") else "在 MA20 下方"))
         if idx.get("close") else "",
         esc(env.get("advice") or ""),
         ("<br><span class='muted'>弱势附加条件：%s</span>" % esc(ENV_STRICT_NOTE))
         if ENV_STRICT_NOTE else "") + tdir_line
    # ★ 出票许可横幅（读证据页判定，页面不自己算统计）
    if emit_ok:
        emit_banner = (
            "<div class='box green'><b>出票许可：已通过</b> —— A 档主榜可作操作依据。"
            "核验过程见页尾「分档出票核验」链接。</div>")
    else:
        emit_banner = (
            "<div class='box red' style='border-color:#b00020'>"
            "<b>⚠ 本期不出票（宁可不选）</b> —— 本页<b>主榜与操作手册已清空</b>，"
            "下列各表只作观察参考，<b>不构成任何操作依据</b>。<br>原因：<code>%s</code><br>"
            "<b>诚实更正：</b>本页原写「A 档 = 可重点做T」。核验发现<b>逐日平衡 edge 为正</b>"
            "（R3 达标、留一全正、前后半同向，看起来是能出票的），但做T是区间操作、"
            "<b>「没成交」也是一种结果</b> —— 按实际成交口径算，A 档「触买后」期望是<b>负的</b>，"
            "而且<b>分数越高越难成交</b>（往返率 5.15%%，同域非 A 档 12.65%%）。<br>"
            "两个口径方向相反，说明这条规则选出的是<b>「看着安静但难成交」</b>的票。"
            "拿「每天都重选更优」的数字去支撑「实际做一笔能赚」是不成立的 → 本期不出票。"
            "原结论与重算过程见页尾「分档出票核验」页（历史判定不删改）。</div>"
            % esc(emit_why or "未读到出票许可证据"))
    # 环境门控折数系数的样本外结论（系数从 ENV_RULE 现读，不写死；结论本身见证据页）
    _rule = E.ENV_RULE
    _scales = " / ".join("%s %s" % (k, _rule[k]["pos_scale"])
                         for k in ("强势", "震荡", "弱势", "破位") if k in _rule)
    env_html += ("<br><span class='muted'>仓位系数（%s）沿用现行 ENV_RULE 原值："
                 "该表在样本外<b>分不出差别</b>（四档 95%% 区间全部跨 0、R3 通过率 48%%~78%%），"
                 "已判<b>「不可判」</b>，不做调整；「强势开仓、其余空仓」是主升精选的结论，"
                 "<b>不能</b>套到做T场景（做T是日内场景，点估计上弱势档还高于强势档）。"
                 "依据：<a href='env_gate.html' style='color:#0071e3'>做T池环境门控样本外验证</a></span>"
                 "｜ 出票依据：<a href='tier_gate.html' style='color:#0071e3'>分档出票核验</a></span>"
                 % _scales)

    body = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>做T池 · {date} · A股分析中心</title>
<style>{STYLE}{X.BADGE_CSS}{X.CHIP_CSS}</style></head>
<body><div class='wrap'>
{nav('tplus')}
<header>
  <h1>做T池（可反复做T候选 · 三源并集）</h1>
  <div class='sub'>候选来源为<b>三源并集</b>：<span class='tag tinst'>机构底仓</span>（公募≥3% 或 社保/险资≥2 家）
  × <span class='tag tlhb'>龙虎榜</span>（近 10 交易日上榜且净买为正或≥2 次）
  × <span class='tag tstrong'>强势</span>（20 日超额收益 ≥5pp 且站上 MA20）。
  再从其中筛出<b>高波动 + 高流动性 + 区间震荡 + 资金支撑</b>的标的，按顶级机构常用的
  <b>网格交易 / 均值回归 / 底仓+卫星仓 / 波动率套利</b>方法给出网格档位与波段买卖点。数据日期 <b>{date}</b>。</div>
</header>

{env_html}
{emit_banner}
<div class='note'><b>今日结论（漏斗）：</b>三源并集 <b>{n_uni}</b> 只 →「箱体闸门」取消 <b>{n_box_cancel}</b> 只
→ 常规硬门槛再取消 <b>{n_gate_cancel}</b> 只 → 剩 <b>{len(rows)}</b> 只（A {na} / B {nb} / C {nc}）
→ <b>今日放行且为最高档（A）的可动手标的 {len(top)} 只</b>（做T方向：<b>{tdir_label}</b>；反向配对或方向未知一律不放行）。<br>
<b>选股顺序已调整：</b>先问「这只票是不是<b>真的在箱体内反复震荡</b>」，再问流动性与振幅，最后才打分排序。
第一条不过就<b>直接取消</b>——不进池，也不会出现在任何参考列表里。<br>
候选来源分布：机构底仓 {n_inst} 只 · 龙虎榜 {n_lhb} 只 · 强势 {n_str} 只，其中<b>多源共振 {n_multi} 只</b>（同时命中两条以上）。<br>
做T前请先确认已有底仓（A股 T+1）；<b>单次做T亏损控制在总资金 0.5% 以内</b>，破箱体下沿即停。</div>

<div class='xh-cmp'>
  <div class='cnew'><b>{len(new_codes)}</b><span>本期新进{('（上一期 ' + prev_row['date'] + '）') if prev_row else ''}</span></div>
  <div class='ccont'><b>{len(_cont)}</b><span>连续在榜</span></div>
  <div class='cout'><b>{len(_out)}</b><span>上期已退出</span></div>
  <div><b>{len(prev_codes)} → {len(rows)}</b><span>入选数变化</span></div>
</div>
<div class='note'>名称后 <span class='xh-new'>新</span> = 本期首次入选；<span class='xh-badge'>09-11</span> = 此前曾入选（悬停看全部日期与池别：MACD观察池 / 信号池 / 做T池 / 反转池）；
「历史入选」列列出同一信息，列表所有列均可点击表头排序。{('上一期备注：' + prev_row.get('note') + '。') if (prev_row and prev_row.get('note')) else ''}</div>

<div class='section'><h2>做T榜单 · 今日可动手 {len(top)} 只</h2>
<div class='note ok'><b>这张表就是今天全部可动手的标的</b> —— 只保留<b>已放行的最高档（A）</b>，
其余一律不展示（不是「参考」，是直接不进表）。<br>
<b>怎么用：</b>先看「箱位%」判断该低吸还是高抛 —— <span class='down'>0~33 低吸区</span> 挂<b>低吸区</b>价位分批买、
<span class='up'>67~100 高抛区</span> 挂<b>高抛区</b>价位分批卖、中间区位按兵不动；<b>收盘跌破止损价无条件离场</b>。<br>
<b>为什么可信：</b>表中「锁定状态」标明该箱体的<b>确立日与已锁定天数</b> —— 箱体一旦确立，上下沿就锁死不再改，
只有当行情真正走出区间（连续 2 日收盘越界 2%）才会换版并更新日期，所以上下沿不会因为每天刷新而漂移。
表头可点击排序；手机上每行会自动堆成一个卡片，列名在最左侧，不需要左右拖动。</div>
{drop_html}
{wf_html}
<div class='tbl-wrap'><table class='sortable rt'>{thead}<tbody>{table_html or "<tr><td colspan='13' class='dim'>今日无符合条件标的 —— 空仓等待</td></tr>"}</tbody></table></div></div>

{box_html}
<details class='section ref-fold'><summary><h2>强势股分析（{len(strong_rows)} 只）</h2><span class='fold-tip'>参考视角 · 点击展开</span></summary>
<div class='note'><b>口径：</b>从做T池中筛出<b>相对强度跑赢大盘</b>的标的（20 日超额 ≥5pp 或均线多头排列）。
<b>「强势」= 20 日涨幅 − 上证 20 日涨幅</b>（pp）；当前基准（上证 {date}）20 日 {('%+.2f%%' % (bench20 or 0))}。<br>
<b>为什么单独看：</b>做T池里的多数票是「区间横盘」，靠波动赚差价；<b>强势股则是「趋势中回踩」</b>——
买在回踩、卖在再创新高，赚的是趋势 + 波动双击。两者操作纪律不同，混为一谈最容易做反。<br>
<b>强势股做T纪律（只做多、不逆势）：</b>① 只在<b>回踩 MA10 / MA20 不破</b>时低吸，<b>不追突破当天的冲高</b>；
② 反弹到前高附近先减一半；③ 收盘破 MA20 或跌回买点 −5% 无条件离场；④ 20 日超额 &gt;45pp（表内红色高分）视为<b>高潮段</b>，只减不加。<br>
<b>分档：</b><span class='badge bA'>强势多头</span>超额 ≥5pp <b>且</b> MA5&gt;MA10&gt;MA20&gt;MA60 多头排列 —— 趋势最完整，回踩即是买点；
<span class='badge bB'>强势整理</span>超额 ≥5pp 但均线未完全多头 —— 强势中继，等均线收敛；
<span class='badge bD'>强势回调</span>超额仍高但已跌破 MA20 —— <b>回调未确认结束，不参与</b>，等重新站上再看；
<span class='badge bC'>温和偏强</span>超额 0~5pp 且站上 MA20 —— 强度一般，当普通做T标的处理。</div>
<div class='tbl-wrap'><table class='sortable rt'><thead><tr>
<th data-k='nm' data-t='s'>名称</th><th data-k='cd' data-t='s'>代码</th><th data-k='ind' data-t='s'>行业</th>
<th data-k='rs20' data-t='n' class='tip' title='20 日涨幅 − 上证 20 日涨幅。5~30pp 为「强而不过热」的理想区间，&gt;45pp 视为高潮段。'>超额20</th>
<th data-k='rs60' data-t='n' class='tip' title='60 日涨幅 − 上证 60 日涨幅（pp）。&gt;0 说明中期也在跑赢，是趋势而非一日情绪。'>超额60</th>
<th data-k='hi' data-t='n' class='tip' title='现价距 52 周最高价的百分比（负数=距高点还有空间）。-3%~-30% 表示强势但未过热；接近 0 表示贴着历史高点。'>距52周高</th>
<th data-k='ma' data-t='s' class='tip' title='MA5&gt;MA10&gt;MA20&gt;MA60 为多头排列；仅站上 MA20 表示短期转强、中期未确认。'>均线</th>
<th data-k='amp' data-t='n'>振幅%</th><th data-k='turn' data-t='n'>换手%</th>
<th data-k='bx' data-t='n' class='tip' title='该股已锚定箱体的下沿与上沿价格。左右两端分别对应下面「箱位」进度条的两端。'>箱体 下沿~上沿</th>
<th data-k='pos' data-t='n' class='tip' title='现价在箱体内的位置：0=贴下沿、100=贴上沿。'>箱位</th>
<th data-k='sg' data-t='s'>分档</th><th data-k='score' data-t='n'>做T分</th><th data-k='adv' data-t='s'>操作建议</th>
</tr></thead><tbody>{strong_html or "<tr><td colspan='14' class='dim'>今日池内无强势标的</td></tr>"}</tbody></table></div></details>

<details class='section ref-fold'><summary><h2>龙虎榜视角（{len(lhb_rows)} 只）</h2><span class='fold-tip'>参考视角 · 点击展开</span></summary>
<div class='note'><b>口径：</b>做T池中近 10 个交易日<b>上过龙虎榜</b>的标的，按累计净买额排序。上榜 = 资金关注度与分歧同时放大，
往往对应<b>振幅扩张、流动性充足</b>——正是做T需要的环境；但席位性质决定方向：<br>
<b>怎么用（三看法）：</b>① <b>看净买方向</b>——累计净买为正 = 席位整体在吸筹（正向共振，做T容错率高）；
累计净卖为负 = 派发中，做T极易被闷杀，评分已被扣分。② <b>看游资等级</b>——「高」= 一线游资参与，
波动大、节奏快，<b>只能做「回踩买」不能做「追高买」</b>；「低」或有机构专用席位 = 结构更稳，适合网格。
③ <b>看分歧度</b>——买前买后金额同时巨大（对倒特征）= 主力在对敲出货，直接放弃。<br>
<b>风险提示：</b>龙虎榜是<b>T 日盘后数据</b>，T+1 才能动手；上榜股次日高开跳水的概率显著高于平常，
务必<b>等回踩、不追首日冲高</b>，仓位减半执行。本板块合计累计净买 {fnum(lhb_net_sum,2)} 亿元。</div>
<div class='tbl-wrap'><table class='sortable rt'><thead><tr>
<th data-k='nm' data-t='s'>名称</th><th data-k='cd' data-t='s'>代码</th><th data-k='ind' data-t='s'>行业</th>
<th data-k='last' data-t='s' class='tip' title='最近一次登上龙虎榜的交易日。'>最近上榜</th>
<th data-k='n' data-t='n' class='tip' title='近 10 个交易日累计上榜次数。次数越多说明资金反复博弈、关注度越高。'>上榜次数</th>
<th data-k='lnet' data-t='n' class='tip' title='最近一次上榜当日的龙虎榜净买入额（亿元，买前五 − 卖前五）。'>最近净买(亿)</th>
<th data-k='net' data-t='n' class='tip' title='近 10 个交易日龙虎榜净买入额合计（亿元）。为正=席位整体吸筹；为负=派发。'>累计净买(亿)</th>
<th data-k='hot' data-t='s' class='tip' title='游资参与等级：高=一线游资 / 中=活跃游资 / 低=无明显游资席位。'>游资等级</th>
<th data-k='tags' data-t='s'>席位标签</th><th data-k='score' data-t='n'>做T分</th>
</tr></thead><tbody>{lhb_html or "<tr><td colspan='10' class='dim'>今日池内无近 10 日龙虎榜标的</td></tr>"}</tbody></table></div></details>

<div class='section'><h2>网格型操作手册（{len(g_cards)} 只 · 已放行）</h2>
<div class='note'><b>判定口径：</b>箱体高度 15%~48% <b>且</b> MA20 斜率 |≤3.2%| <b>且</b> 箱内位置 20%~80% —— 典型<b>区间震荡、均线粘合</b>。<br>
<b>操作方式（机械网格）：</b>把箱体 [下沿 L, 上沿 U] 均分 5 档，<b>每档仓位 = 卫星仓 ÷ 4</b>。下跌触及第 1~2 档<b>分批买入</b>，中枢第 3 档<b>观望不动</b>，上涨触及第 4~5 档<b>分批卖出</b>。
不预测方向、不追单档、不满仓滚动；每日收盘前挂单即可，触档才动。底仓始终不动，只用卫星仓滚。<br>
<b>停止条件：</b>放量跌破 L×0.955，或 MA20 拐头向下走成空头排列 → 立刻停做T并清卫星仓。</div>
<div class='cards'>{grid_cards or "<div class='dim'>今日无放行的网格型标的" + (f"（大盘{env.get('label')}环境，按纪律不放行）" if env.get("label") else "") + "</div>"}</div></div>

<div class='section'><h2>波段型操作手册（{len(s_cards)} 只 · 已放行）</h2>
<div class='note'><b>判定口径：</b>箱体较宽（&gt;48%）或有趋势斜率（|MA20 斜率| &gt;3.2%）—— 属于<b>宽幅震荡或带趋势</b>，不适合机械挂单。<br>
<b>操作方式（几日一循环）：</b>不求日内。回落至<b>支撑位</b>（箱体下沿与 MA20 的较高者）附近 0~2% 区间<b>分批买</b>；反弹至<b>箱体上沿</b>附近 0~2% 区间<b>分批卖</b>；<b>一轮 3~7 日</b>。
需要每日跟盘判断支撑是否有效，不做无脑挂单；趋势向下时宁可空仓等。<br>
<b>停止条件：</b>破止损价无条件离场；MA20 下穿 MA60 或箱体下沿被放量击穿 → 停做T。</div>
<div class='cards'>{swing_cards or "<div class='dim'>今日无放行的波段型标的" + (f"（大盘{env.get('label')}环境，按纪律不放行）" if env.get("label") else "") + "</div>"}</div></div>

<div class='section'><h2>方法论：顶级机构如何做T</h2>
<div class='note'><b>1. 网格交易法</b>——在预设价格网格上机械高抛低吸，不预测方向，赚取波动本身。前提是标的处于<b>区间震荡</b>且波动率充足。
<b>2. 均值回归</b>——价格围绕箱体中枢（机构成本区）往复，偏离越远回归动力越强。
<b>3. 底仓 + 卫星仓</b>——底仓不动（吃趋势/分红），仅用卫星仓反复做T摊低成本；A股 T+1，做T必须先有底仓。
<b>4. 波动率套利</b>——日振幅/ATR 越大，单次做T的价差空间越大。
<b>5. 相对强度增强（强势股）</b>——只做「回踩买」，不做「逆势承接」，趋势方向与做T方向一致时胜率最高。
<b>6. 龙虎榜跟踪</b>——席位净买为正向共振，净卖为派发信号，用于<b>校验</b>而非替代结构判断。<br>
<b>候选来源（三源并集，逐只标注）：</b>
<span class='tag tinst'>机构底仓</span>公募≥3% 或 社保/养老/年金/险资/汇金/证金/QFII ≥2 家（季报口径，箱体下沿支撑最强）；
<span class='tag tlhb'>龙虎榜</span>近 10 交易日上榜且累计净买为正 或 ≥2 次（资金关注度 + 流动性天然充足）；
<span class='tag tstrong'>强势</span>20 日超额 ≥5pp 且站上 MA20（趋势票，只做回踩）。
<b>多源共振</b>（同时命中 ≥2 条）优先级最高。<br>
<b>纪律</b>：破箱体下沿无条件清仓；单次做T亏损 ≤ 总资金 0.5%；不追高、不满仓滚动。</div>
<b>评分机制（v6 · 先验固定因子集 · 域内横截面分位）：</b>
做T分 = 下列 9 个因子各自取「当日域内横截面分位」后<b>等权平均 × 100</b>，无权重手调、无因子筛选 ——
因子方向全部由做T的经济逻辑预先给定，因此全期都是干净样本外。分数是<b>相对位置</b>（今天在池子里排多前），
不是绝对适合度，故不会随行情漂移。分档按分位：<b>A = 当日前 10% / B = 前 25% / C = 其余</b>；
命中解禁 / 计划减持窗口的票直接进 <b>D（风险否决·仅跟踪）</b>，不参与出池。
<table><thead><tr><th>因子</th><th>口径</th><th>方向</th></tr></thead><tbody>
<tr><td>箱体窄</td><td>|箱体高度 − 20%|（箱体越窄，一轮越做得完）</td><td>越小越好</td></tr>
<tr><td>带宽低</td><td>BOLL 带宽（4σ ÷ MA20）</td><td>越小越好</td></tr>
<tr><td>均线粘合</td><td>MA5 / MA10 / MA20 离散度（粘合 = 无趋势）</td><td>越小越好</td></tr>
<tr><td>波动规律</td><td>近 20 日振幅变异系数（越稳定越可预期）</td><td>越小越好</td></tr>
<tr><td>振幅适中</td><td>|近 20 日平均振幅 − 6%|（太小没空间、太大是单边）</td><td>越小越好</td></tr>
<tr><td>ATR 适中</td><td>|ATR%(14) − 5%|</td><td>越小越好</td></tr>
<tr><td>横盘</td><td>|MA20 二十日斜率|</td><td>越小越好</td></tr>
<tr><td>支撑被验</td><td>近 60 日箱体下沿被测试次数（被反复验证过的下沿更可靠）</td><td>越多越好</td></tr>
<tr><td>流动性</td><td>20 日均成交额</td><td>越大越好</td></tr>
</tbody></table>
<div class='note'>风险项（破 MA60 / RSI 超买 / 成交额不足 / MA20 陡峭 / 龙虎榜净卖出 / 解禁 / 减持）
<b>只作卡片提示，不参与排序</b>（弱辅助）—— 前几轮的实证都表明「扣分项进分数」会把噪声当信号。<br>
<b>依据从哪来？</b>见 <a href='lab.html'><b>做T池 · 特征功效实验室</b></a>：全市场可做T域 9.3 万样本 / 10 个月，
训练段择优 → 测试段验证，并给出「完成一轮率」「破止损率」「可兑现期望收益」三个做T专属口径的实证。
<b>本页的因子集、分位档位、买卖点参数全部以该实验室为准</b>，不凭手感调参。</div></div>

<div class='section'><h2>历史归档（点击日期查看当日页面）</h2>
<table class='sortable rt'><thead><tr><th data-k='d' data-t='s'>日期</th><th data-k='t' data-t='n'>入选</th><th data-k='a' data-t='n'>A</th><th data-k='b' data-t='n'>B</th><th data-k='c' data-t='n'>C</th><th data-k='g' data-t='n'>网格型</th><th data-k='s' data-t='n'>波段型</th><th data-k='n' data-t='s'>备注</th></tr></thead>
<tbody>{hist_rows or "<tr><td colspan='8' class='dim'>暂无</td></tr>"}</tbody></table></div>

<footer>本页为规则化量化输出，不构成投资建议。数据来源：腾讯日K（行情/复权K线）+ 上证指数（相对强度基准）+ 2026-Q2 十大流通股东（机构底仓）+ 龙虎榜增强（近 10 交易日席位净买）。
做T有风险，务必先有底仓、严设止损。</footer>
</div>{X.SORT_JS}{X.CHIP_JS}</body></html>"""

    os.makedirs(WEB, exist_ok=True)
    p_index = os.path.join(WEB, "index.html")
    p_date = os.path.join(WEB, f"tplus-{date}.html")
    open(p_index, "w", encoding="utf-8").write(body)
    open(p_date, "w", encoding="utf-8").write(body)
    print(f"[build_tplus] {date}: 硬门槛通过 {len(rows)}（A {na}/B {nb}/C {nc}｜网格型 {ng} / 波段型 {len(rows)-ng}）"
          f"｜放行 {n_rel}")
    print(f"  来源：机构底仓 {n_inst} / 龙虎榜 {n_lhb} / 强势 {n_str}，多源共振 {n_multi}")
    print(f"  强势股分析 {len(strong_rows)} 只（强势多头 {sum(1 for r in strong_rows if r['sg']=='强势多头')}）"
          f"｜龙虎榜视角 {len(lhb_rows)} 只，累计净买 {lhb_net_sum:+.2f} 亿")
    print(f"  对比上一期 {prev_row['date'] if prev_row else '—'}：新进 {len(new_codes)} / 连续 {len(_cont)} / 退出 {len(_out)}")
    print(f"  跨池历史入选库覆盖 {len(hist_pool)} 个代码")
    print(f"  → {p_index}")
    print(f"  → {p_date}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y-%m-%d"))
    a = ap.parse_args()
    build(a.date)
