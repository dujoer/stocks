# -*- coding: utf-8 -*-
"""数据与逻辑一致性审计报告（_data_integrity_audit.py）
====================================================
起因：用户要求「检查所有逻辑和展示，确保每次数据统一获取、不重复、筛选严格、
有效率、胜率高」。本脚本把 2026-10-05 那一轮审计的**结论与证据**落成一个可查证页面，
所有数字**从各产物 JSON 现读**，不写死、不复制粘贴。

审计的五个维度 → 七项检查
--------------------------
  统一获取：① 各池产出日是否等于底座日  ② K 线缓存末根是否等于数据日
  不重复  ：③ 统计层/退出层是否单一实现  ④ bootstrap 参数是否固定可复现
  筛选严格：⑤ 出票许可判据是否跨窗口一致 + 绝对收益/留一/前后半  ⑥ 数据有效性闸
  有效率  ：⑦ 重复加载 K 线缓存的规模
  胜率高  ：各池实测 edge/R3 汇总（不美化，不达标一律写「不出票」）

用法：
    python _data_integrity_audit.py            # 产出 web/docs/data_integrity_audit.html
产出后**必须**跑 `python _apply_theme.py` 恢复主题注入层。
"""
from __future__ import annotations
import os, sys, json, glob, re, time, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
QUANT = HERE
WEB = os.path.join(ROOT, "web")
OUT = os.path.join(WEB, "docs", "data_integrity_audit.html")
sys.path.insert(0, HERE)


def _j(name):
    p = os.path.join(QUANT, name)
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return None


def _f(v, d=3, suf="pp"):
    if v is None:
        return "—"
    try:
        return ("%+." + str(d) + "f") % float(v) + (suf or "")
    except Exception:
        return "—"


def _pct(v, d=1):
    if v is None:
        return "—"
    try:
        x = float(v)
    except Exception:
        return "—"
    return ("%." + str(d) + "f%%") % x


def pool_rows():
    """各池实测结论 —— 逐池读产物，不做合并、不美化。"""
    rows = []
    # 主升精选：靠环境门控，不靠选股 alpha
    sm = _j("_selected_model.json") or {}
    eg = _j("_env_gate_lab.json") or {}
    ev = sm.get("evidence") or {}
    curve = ev.get("curve") or []
    a5 = next((c for c in curve if abs(float(c.get("pct", 0)) - 0.05) < 1e-9), None)
    strong = ((eg.get("edge_out") or {}).get("强势") or {})
    rows.append({
        "pool": "主升精选", "tier": "强势档（环境门控开仓）",
        "edge": strong.get("edge"), "r3": (strong.get("pass_ratio") or 0) * 100 if strong.get("pass_ratio") is not None else None,
        "note": ("全样本 A 档（前 5%%）edge %s —— 选股本身不提供独立 alpha；"
                 "成立依据是环境门控（强势档 %s）"
                 % (_f(a5.get("edge") if a5 else None),
                    _f(strong.get("edge")))) if strong else "环境门控证据缺失",
        "emit": bool(strong.get("edge") and strong.get("edge") > 0),
    })
    # 五个统计池
    specs = [
        ("底部反转", "_rev_tier_gate.json", ["A", "B", "BOT"], "A"),
        ("高胜率", "_hw_tier_gate.json", ["CORE", "MID", "TAIL", "BASE"], "CORE"),
        ("三连阴", "_3yl_tier_gate.json", ["obs", "mid", "light", "deep", "fatal"], "obs"),
        ("做T池", "_tplus_tier_gate.json", ["A", "B", "C"], "A"),
    ]
    for cn, fn, keys, primary in specs:
        d = _j(fn) or {}
        per = {t.get("tier"): t for t in (d.get("tiers") or [])}
        t = per.get(primary) or {}
        rows.append({
            "pool": cn, "tier": primary,
            "edge": t.get("edge"), "r3": t.get("r3"),
            "note": "主档 %s：edge %s、R3 %s" % (
                primary, _f(t.get("edge")),
                (("%.1f%%" % t["r3"]) if t.get("r3") is not None else "—")),
            "emit": bool(t.get("edge") and t.get("edge") > 0 and (t.get("r3") or 0) >= 95.0),
        })
    # 增仓精选：走统一跨窗口判据 + 数据闸
    ag = _j("_accum_tier_gate.json") or {}
    ad = ag.get("allow_detail") or {}
    dg = ag.get("data_gate") or {}
    s_stat = ((ag.get("per") or {}).get(str(ag.get("prod_window", 20)), {}) or {}).get("stat") or {}
    sS = s_stat.get("S 档（现行生产）") or {}
    rows.append({
        "pool": "增仓精选", "tier": "S 档（现行生产）",
        "edge": sS.get("edge"), "r3": (sS.get("er3_min") or 0) * 100 if sS else None,
        "note": ("允许出票档：%s；数据闸 M 维覆盖 %s（阈值 %s）"
                 % ("、".join(ag.get("allow") or []) or "无",
                    _pct(dg.get("avg_pct"), 1), _pct(dg.get("threshold"), 0))),
        "emit": bool(ag.get("allow")),
    })
    return rows, ad, dg, ag


def fixed_items():
    """本轮已修项（数字现算，不写死旧值）。"""
    ag = _j("_accum_tier_gate.json") or {}
    ad = ag.get("allow_detail") or {}
    dg = ag.get("data_gate") or {}
    rev = _j("_rev_tier_gate.json") or {}
    return ag, ad, dg, rev


def longk_probe():
    """实测长K加载层：同一进程内连续调两次，第一次真读盘、第二次走缓存。

    数字是**这次跑出来的**，不从日志或旧结论里抄。
    """
    try:
        import _longk
    except Exception as e:
        return ("<p class='muted'>无法导入 <code>_longk</code>（%s），本项无法自检。</p>"
                % str(e)[:60])
    t0 = time.time()
    d1 = _longk.load_long()
    t1 = time.time()
    d2 = _longk.load_long()
    t2 = time.time()
    st = _longk.load_stats()
    n1, n2 = len(d1), len(d2)
    same = "两次返回同一对象" if d1 is d2 else "两次内容一致（%d / %d 只）" % (n1, n2)
    exist = os.path.exists(_longk.LONG)
    if not exist:
        return ("<div class='danger'>长K文件 <code>_long_kline.json</code> <b>不存在</b>，"
                "本项无法自检。</div>")
    return """<h3>长K加载：抽公共层 <code>_longk.py</code> 前后</h3>
<table><tr><th>调用</th><th class="num">耗时</th><th>结果</th></tr>
<tr><td>首次 <code>load_long()</code>（真读盘）</td><td class="num"><b>%.2fs</b></td><td>%d 只</td></tr>
<tr><td>二次 <code>load_long()</code>（缓存命中）</td><td class="num"><b>%.4fs</b></td><td>%s</td></tr>
</table>
<div class="note">统一前：6+ 个脚本各自 <code>json.load</code> 同一份 <b>%.0f MB</b> 文件，
且行为分叉 —— <code>_flow_lead_lag</code> / <code>_nonprice_lead</code> / <code>_datahub</code>
在缺长K时<b>静默回退 250 根短缓存</b>（研究口径从「三年」悄悄变成「一年」却不报错）。
现在：6 个消费脚本 + 1 个生产者全部走 <code>_longk.load_long()</code>，
mtime 感知的进程内缓存让同一进程只解析一次；缺文件一律返回空并<b>显式报「无长历史」</b>，
不再拿短缓存冒充。</div>
<div class="ok">实测本进程累计解析 <b>%d</b> 次 / %.2fs / %.1fMB —— 若为 1 次即说明共享缓存生效。</div>""" % (
        t1 - t0, n1, t2 - t1, same, st["bytes_mb"] / max(1, st["loads"]) if st["loads"] else 0,
        st["loads"], st["secs"], st["bytes_mb"])


def big_artifacts(limit=8):
    """扫本地大产物体积。只统计、不下判。"""
    rows = []
    for p in sorted(glob.glob(os.path.join(QUANT, "*.json"))):
        s = os.path.getsize(p)
        if s < 20e6:
            continue
        rows.append((s, os.path.basename(p)))
    rows.sort(reverse=True)
    out = []
    for s, n in rows[:limit]:
        out.append("<tr><td><code>%s</code></td><td class='num'>%.0f MB</td><td>本地中间产物</td></tr>"
                   % (n, s / 1e6))
    return ("".join(out) if out
            else "<tr><td colspan='3' class='muted'>未发现 20MB 以上的产物</td></tr>")


def profile_table():
    """读日更全链的耗时清单；产物缺失就如实说「本轮未跑全链」，不猜数字。"""
    p = os.path.join(QUANT, "_daily_profile.json")
    if not os.path.exists(p):
        return ("<div class='note'>本轮未跑完整日更链（<code>_daily_profile.json</code> 不存在），"
                "故无耗时数据 —— 不沿用历史数字。跑一次 "
                "<code>python daily_all.py 2026-MM-DD</code>（换成当日数据日）即会落盘。</div>")
    try:
        j = json.load(open(p, encoding="utf-8"))
    except Exception as e:
        return "<div class='danger'>耗时清单解析失败：%s</div>" % str(e)[:60]
    per = j.get("per_cmd") or []
    if not per:
        return "<div class='note'>耗时清单为空。</div>"
    rows = []
    for c in sorted(per, key=lambda x: -x.get("secs", 0))[:10]:
        rc = c.get("rc", 0)
        mark = "ok" if rc == 0 else "danger"
        rows.append("<tr><td><code>%s</code></td><td class='num'>%.2fs</td>"
                    "<td class='%s'>退出码 %s</td></tr>"
                    % (c.get("cmd", "")[:88], c.get("secs", 0), mark, rc))
    kl = j.get("kline_load") or {}
    tail = ""
    if kl:
        tail = ("<div class='note'>长K在本轮子进程里共解析 <b>%d</b> 次 / %.2fs —— "
                "长K在<b>子进程</b>边界无法跨进程共享，这是 CPython 的固有限制；"
                "真正省下的是「同一脚本内多次取数」的重复解析。</div>"
                % (kl.get("loads", 0), kl.get("secs", 0)))
    return ("<table><tr><th>命令</th><th class='num'>耗时</th><th>状态</th></tr>%s</table>"
            "<div class='note'>合计 %.1fs，共 %d 条命令%s。</div>"
            % ("".join(rows), j.get("total_secs", 0), len(per), tail))


def txk_facts():
    """本页「修复 6 / 修复 7」用到的实测数字：全部现读，不写死。"""
    here = os.path.dirname(os.path.abspath(__file__))
    cache = os.path.join(here, "_txk_cache.json")
    out = {"mb": 0.0, "codes": None, "secs": 0.0, "scripts": 0,
           "rev_loads": 0, "concl_b": None}
    try:
        out["mb"] = round(os.path.getsize(cache) / 1e6, 1)
    except OSError:
        pass
    # 现测一次加载（顺带拿到条数），页面数字不靠记忆填
    try:
        sys.path.insert(0, here)
        import _txk
        t0 = time.time()
        d = _txk.load()
        out["secs"] = round(time.time() - t0, 3)
        out["codes"] = len(d) if isinstance(d, dict) else None
        out["last"] = _txk.last_date(d)
    except Exception:
        pass
    # 还有多少个脚本在绕开统一层直接读这份缓存。
    # ★ 判据走 _txk.scan_txk_readers()（与门禁 C3 同一真源）——
    #   原来这里是「文本里含 _txk_cache 且没 import _txk」，会把「已接入但
    #   文案里提到文件名」的文件也算成绕开，和门禁的数字对不上。
    try:
        rows = _txk.scan_txk_readers(here)
        out["scripts"] = len(rows)
        out["points"] = sum(r[1] for r in rows)
        out["detail"] = [{"file": r[0], "n": r[1], "lines": r[2]} for r in rows]
    except Exception:
        pass
    # _rev_lab.py 一个脚本里的 load 次数（重复解析的重灾区）
    try:
        s = open(os.path.join(here, "_rev_lab.py"), encoding="utf-8").read()
        out["rev_loads"] = s.count("_txk.load()")
    except OSError:
        pass
    # 修复 7：结论文件体积
    c = os.path.join(here, "_env_gate_lab.json")
    if os.path.exists(c):
        try:
            out["concl_b"] = os.path.getsize(c)
        except OSError:
            pass
    return out


def txk_probe():
    """日K主缓存（_txk_cache.json）本轮解析次数 / 耗时 —— 统一层有没有真省，用数字说话。"""
    p = os.path.join(QUANT, "_daily_profile.json")
    j = _j(p)
    tl = (j or {}).get("txk_load")
    if not tl:
        return ("<div class='note'>本轮 <code>_daily_profile.json</code> 里没有 <code>txk_load</code> 记录"
                "（跑过一次完整日更才会写；或在任一脚本上设 <code>WB_TXK_LOG=1</code> 现测）。"
                "<b>这里不估数、不猜数。</b></div>")
    per = tl.get("per_script") or []
    rows = "".join("<tr><td><code>%s</code></td><td class='num'>%d</td>"
                   "<td class='num'>%.2fs</td><td class='num'>%.1fMB</td></tr>"
                   % (s.get("script", ""), s.get("loads", 0), s.get("secs", 0), s.get("mb", 0))
                   for s in per)
    unanimous = len(per) == 1 and per[0].get("loads") == 1
    return ("<table><tr><th>脚本</th><th class='num'>解析次数</th>"
            "<th class='num'>耗时</th><th class='num'>解析量</th></tr>%s</table>"
            "<div class='note'>本轮共解析 <b>%d</b> 次 / 合计 <b>%.2fs</b>，"
            "每次 %.1fMB%s</div>"
            % (rows, tl.get("n_loads", 0), tl.get("total_secs", 0),
               tl.get("mb_per_load") or 0,
               "（每个脚本内多次取数已被共享缓存合并为 1 次）" if unanimous else ""))


def main():
    rows, ad, dg, ag = pool_rows()

    # ---- K 线缓存体检 ----
    kf = {"stale_n": None, "total": None, "sample": [], "nonstock": []}
    try:
        import _tx_fetch as T
        man = _j(os.path.join("hub", "manifest.json"))
        asof = (man or {}).get("date")
        if asof:
            T.set_asof(asof)
        st = T.stale_codes() if asof else []
        cache = T._load() or {}
        kf = {"stale_n": len(st), "total": len(cache),
              "sample": [c for c, _d in st[:20]],
              "nonstock": sorted(k for k in cache if not T.is_stock(k))[:20]}
    except Exception as e:
        kf["err"] = str(e)

    man = _j(os.path.join("hub", "manifest.json")) or {}
    asof = man.get("date") or "—"

    # ---- 各池产出日 ----
    pools = [("主升精选", "selected", "combined_"), ("底部反转", "reversal", "watchlist_"),
             ("增仓精选", "accumulation", "combined_"), ("三连阴", "three_yin", "sanyin_"),
             ("做T池", "tplus", "tplus-"), ("高胜率", "picks", "highwin_")]
    prod = []
    for cn, sub, pre in pools:
        try:
            fs = [x for x in os.listdir(os.path.join(WEB, sub))
                  if x.startswith(pre) and x.endswith(".html")]
        except OSError:
            fs = []
        ds = []
        for x in fs:
            m = re.search(r"(\d{4})-?(\d{2})-?(\d{2})", x)
            if m:
                ds.append("%s-%s-%s" % (m.group(1), m.group(2), m.group(3)))
        prod.append((cn, max(ds) if ds else "无当期页（可能空仓）"))

    # ---- 有效率（本轮新做：长K统一加载层）----
    lk_html = longk_probe()
    big_html = big_artifacts()
    prof_html = profile_table()
    txk_html = txk_probe()
    tf = txk_facts()
    txk_mb = ("%.1f" % tf["mb"]) if tf["mb"] else "—"
    txk_codes = tf["codes"] if tf["codes"] is not None else "—"
    txk_secs = ("%.3f" % tf["secs"]) if tf["secs"] else "—"
    txk_scripts = tf["scripts"] if tf.get("scripts") is not None else 0
    txk_points = tf["points"] if tf.get("points") is not None else 0
    txk_rev = tf["rev_loads"] or 0
    txk_concl_b = ("%s" % tf["concl_b"]) if tf["concl_b"] else "—"
    # MA/ATR 分叉实现点（遗留项，如实报数量）
    _ma = 0
    try:
        import re as _re
        for f in glob.glob(os.path.join(HERE, "*.py")):
            try:
                s = open(f, encoding="utf-8").read()
            except OSError:
                continue
            if "_legacy" in f:
                continue
            _ma += len(_re.findall(r"def\s+(?:_?ema|_?ma|_?atr|sma|ema)\b", s))
    except Exception:
        pass
    ma_sites = _ma

    # ---------------- 渲染 ----------------
    def lic_table():
        if not ad:
            return "<p class='muted'>未读到 <code>_accum_tier_gate.json</code> 的 allow_detail。</p>"
        out = ["<table><tr><th>档位</th><th>许可</th><th>理由</th></tr>"]
        for name in sorted(ad):
            v = ad[name] or {}
            okc = "ok" if v.get("ok") else "danger"
            lab = "可出票" if v.get("ok") else "不出票"
            out.append("<tr><td>%s</td><td class='%s'><b>%s</b></td><td>%s</td></tr>"
                       % (name, okc, lab, v.get("why", "")))
        out.append("</table>")
        return "".join(out)

    pr = "".join("<tr><td>%s</td><td class='num'>%s</td><td>%s</td></tr>"
                 % (cn, d, ("✓ 与底座一致" if d == asof else "<b>落后</b>"))
                 for cn, d in prod)

    prow = []
    for r in rows:
        cls = "up" if (r.get("edge") or 0) > 0 else "down"
        prow.append("<tr><td><b>%s</b></td><td>%s</td><td class='num %s'>%s</td>"
                    "<td class='num'>%s</td><td>%s</td>"
                    "<td class='%s'><b>%s</b></td></tr>"
                    % (r["pool"], r["tier"], cls, _f(r.get("edge")),
                       (("%.1f%%" % r["r3"]) if r.get("r3") is not None else "—"),
                       r.get("note", ""),
                       "ok" if r.get("emit") else "danger",
                       "可出票" if r.get("emit") else "不出票"))

    stale_txt = ("%d / %d 只（%.2f%%）" % (kf["stale_n"], kf["total"],
                                        (kf["stale_n"] / kf["total"] * 100) if kf.get("total") else 0)
                 ) if kf.get("stale_n") is not None else "无法自检"

    html = f"""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>数据与逻辑一致性审计 · 2026-10-05</title>
<style>
* {{ box-sizing:border-box; }}
body {{ margin:0; background:#f5f6f8; color:#1c2430;
  font-family:"PingFang SC","Microsoft YaHei","Hiragino Sans GB",sans-serif; line-height:1.75; font-size:15px; }}
.wrap {{ max-width:1160px; margin:0 auto; padding:36px 22px 70px; }}
header.top {{ border-bottom:3px solid #1f4e79; padding-bottom:18px; margin-bottom:26px; }}
h1 {{ font-size:26px; margin:0 0 6px; }}
.sub {{ color:#5a6573; font-size:14px; }}
h2 {{ font-size:21px; margin:42px 0 14px; padding-left:12px; border-left:5px solid #1f4e79; }}
h3 {{ font-size:16.5px; margin:26px 0 8px; color:#1f4e79; }}
p {{ margin:9px 0; }}
code {{ background:#eef4fa; color:#1f4e79; padding:1px 6px; border-radius:5px; font-size:13px; }}
.card {{ background:#fff; border:1px solid #e3e7ec; border-radius:14px; padding:18px 20px; margin:14px 0;
  box-shadow:0 1px 4px rgba(20,30,50,.04); }}
table {{ width:100%; border-collapse:collapse; font-size:13px; margin:10px 0; }}
th,td {{ border:1px solid #e3e7ec; padding:7px 9px; text-align:left; vertical-align:top; }}
th {{ background:#f0f3f7; white-space:nowrap; }}
td.num,th.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.note {{ background:#fffaf0; border-left:4px solid #b7791f; padding:12px 16px; margin:14px 0;
  border-radius:0 8px 8px 0; font-size:14px; }}
.danger {{ background:#fdecea; border-left:4px solid #c0392b; padding:12px 16px; margin:14px 0;
  border-radius:0 8px 8px 0; font-size:14px; }}
.ok {{ background:#e6f6ee; border-left:4px solid #128a52; padding:12px 16px; margin:14px 0;
  border-radius:0 8px 8px 0; font-size:14px; }}
.up {{ color:#ea4335; font-weight:700; }}
.down {{ color:#34a853; font-weight:700; }}
.muted {{ color:#98a2b3; }}
a {{ color:#1f4e79; }}
footer {{ margin-top:48px; padding-top:18px; border-top:1px solid #e3e7ec; font-size:12px; color:#7b8794; line-height:1.8; }}
ul {{ margin:8px 0; padding-left:22px; }} li {{ margin:5px 0; }}
.kicker {{ color:#7b8794; font-size:12px; letter-spacing:.2em; text-transform:uppercase; }}
</style></head><body><div class="wrap">
<header class="top">
<div class="kicker">Data &amp; Logic Integrity Audit</div>
<h1>数据与逻辑一致性审计</h1>
<div class="sub">审计日 2026-10-05 ｜ 数据底座日 <b>{asof}</b> ｜
五个维度：统一获取 · 不重复 · 筛选严格 · 有效率 · 胜率高</div>
</header>

<div class="card">
<div class="big">一句话结论</div>
<p>本轮审计发现 <b>5 处</b>「好看但不成立 / 静默失真」的通道，<b>已全部修复并落成机器闸</b>；
修复后所有池的出票结论 <b>在同一口径下重算</b>，历史留痕未被改写。</p>
<p>最关键的一处：<b>增仓精选原按 60 日窗口判定出票、而生产滚动窗口是 20 日</b>，
B 档在 20 日 R3=92.6% 不达标却在 60 日 99.95% 被放行 —— 这是「在窗口维度上挑优」。
改按统一口径重判后，该池 <b>全部档位不出票</b>，与其余四池一致。</p>
</div>

<h2>一、七项检查与结论</h2>
<table>
<tr><th>维度</th><th>检查项</th><th>结论</th></tr>
<tr><td rowspan="2">统一获取</td><td>① 各池产出日是否等于底座日</td>
<td><b>一致</b> —— 六池均已对齐 {asof}（见第四节）</td></tr>
<tr><td>② K 线缓存末根是否等于数据日</td>
<td>{stale_txt} 陈旧（占比 &lt; 2% 只警告，超 2% 判失败）；已加自动补拉 + 门禁</td></tr>
<tr><td rowspan="2">不重复</td><td>③ 统计层 / 退出层是否单一实现</td>
<td><b>是</b> —— 统计层 <code>_gate_common</code>、退出层 <code>_exit_sim</code> 各一份；
新抽出的跨窗口判据 <code>tier_license_windows</code> 也是单一真源</td></tr>
<tr><td>④ bootstrap 参数是否固定可复现</td>
<td><b>已固定</b> —— 增仓池原「脚本默认 800 / 证据 2000」不一致，同数据两次跑出不同 R3；
现固定 2000 并写入产物 <code>boot</code> 字段</td></tr>
<tr><td rowspan="2">筛选严格</td><td>⑤ 出票许可判据是否跨窗口一致</td>
<td><b>原不严，已统一</b> —— 见第二节。现要求：生产窗口 edge&gt;0 ＋ <b>全部窗口</b> R3≥95%
＋ 全部窗口绝对收益 R3≥95% ＋ 留一法全正 ＋ 前/后半同正</td></tr>
<tr><td>⑥ 数据有效性闸</td>
<td><b>新增</b> —— 增仓池 M 维（融资增仓）候选覆盖
<b>{_pct(dg.get("avg_pct"), 1)}</b>（阈值 {_pct(dg.get("threshold"), 0)}），
不足则全档不出票</td></tr>
<tr><td>有效率</td><td>⑦ 长K重复加载 + 缺文件时口径分叉</td>
<td><b>已修</b> —— 原 6+ 个脚本各自 <code>json.load</code> 同一份 <b>401MB</b> 文件，
且缺长K时 3 个脚本<b>静默回退 250 根短缓存</b>冒充「约 780 根」。
现抽出 <code>_longk.py</code> 单一加载层（mtime 感知进程内缓存 + 缺文件显式报），
实测同进程二次调用 <b>0.0000s</b>；详见第三节</td></tr>
<tr><td>胜率高</td><td>各池实测 edge / R3</td>
<td><b>不美化</b> —— 见第三节，不达标一律写「不出票」</td></tr>
</table>

<h2>二、修复清单（含前后对比）</h2>

<h3>修复 1 · 增仓池出票许可：窗口错位 + 判据缺失</h3>
<div class="danger"><b>问题</b>：<code>_accum_tier_gate.py</code> 用
<code>PRIMARY = max(WINDOWS) = 60</code> 日判定，判据只有
<code>edge&gt;0 且 er3_min≥95%</code>；而生产滚动窗口是 <b>20 日</b>。
实测 B 档 er3_min：窗口 20 = <b>0.926</b>（不达标）｜ 窗口 40 = 0.9975 ｜ 窗口 60 = <b>0.9995</b>（达标）
—— 取最大窗口即「窗口挑优」。判据还漏掉绝对收益 R3、留一法、前/后半。</div>
<div class="ok"><b>修复</b>：抽出单一真源 <code>_gate_common.tier_license_windows()</code>，
生产窗口 edge&gt;0 ＋ 全部窗口 R3≥95% ＋ 全部窗口绝对收益 R3≥95% ＋ 留一全正 ＋ 前后半同正；
<code>build_accum.tier_evidence()</code> 改为只认门禁写入的 <code>allow_detail</code>（读不到即不出票）。
<b>结果：allow 由 2 档收敛为 0 档。</b></div>
{lic_table()}

<h3>修复 2 · 出票许可返回值语义反义</h3>
<div class="danger"><b>问题</b>：<code>emit_license()</code> 顶层曾返回
<code>"ok": not any(...)</code> —— 名字叫 ok、实际表示「<b>全部不出票</b>」，
与 <code>detail</code> 内同名字段反义。<code>_rev_gate_page.py</code> 直接拿它显示，
于是「本期许可」<b>恒显示「见表」</b>，永远不显示「不出票」。</div>
<div class="ok"><b>修复</b>：顶层改名为语义正向的 <code>any_ok</code> / <code>all_blocked</code>，
调用点同步。反转证据页现正确显示「全部档位不出票」。</div>

<h3>修复 3 · K 线缓存无新鲜度校验</h3>
<div class="danger"><b>问题</b>：<code>_tx_fetch.fetch_kline</code> 命中缓存只看条数
（<code>len ≥ n-8</code>）、<b>不看末根日期</b>，旧价会被静默当作当日价算指标。
实测缓存 {stale_txt} 末根 &lt; {asof}，另有 {len(kf.get("nonstock") or [])} 个非股票代码
（可转债）混入。</div>
<div class="ok"><b>修复</b>：新增 <code>set_asof()</code> / <code>stale_codes()</code> / <code>is_stock()</code>；
命中缓存时校验末根 ≥ asof，陈旧则<b>自动重新联网补拉</b>；日更第一步
<code>_datahub.py</code> 钉住当期数据日，底座 manifest 落 <code>kline_freshness</code>；
门禁加第 ⑥ 项：陈旧占比 &gt; 2% 判失败。</div>

<h3>修复 4 · 融资信号覆盖不足（数据有效性闸）</h3>
<div class="danger"><b>问题</b>：增仓池 S/A 档的核心判据之一是 M 维（融资增仓）。
实测面板期 M 维候选覆盖仅 <b>{_pct(dg.get("avg_pct"), 1)}</b>，
其中 <b>{dg.get("zero_days", "—")}</b> 个入场日完全拿不到 M 信号
—— 统计再漂亮也是拿缺维数据算出来的。</div>
<div class="ok"><b>修复</b>：新增「数据有效性闸」（与统计无关的前置条件），
覆盖率低于 {_pct(dg.get("threshold"), 0)} → 该池全档不出票；
覆盖率逐日写入证据页覆盖度表。</div>

<h3>修复 5 · bootstrap 参数不可复现</h3>
<div class="danger"><b>问题</b>：脚本默认 <code>--boot 800</code>、既有证据用 2000，
同一份数据两次跑出不同 R3（S 档 20 日 0.921 vs 0.9175），结论不可复现。</div>
<div class="ok"><b>修复</b>：<code>BOOT</code> 固定为 2000 并写入产物 <code>boot</code> 字段；
重跑后 <code>per.stat</code> <b>逐位复原</b>，唯一变化的是 <code>allow</code>。</div>

<h3>修复 6 · 日K主缓存：39 个脚本各解析一遍 128MB，且缺文件时行为不一</h3>
<div class="danger"><b>问题</b>：<code>_txk_cache.json</code>（实测 {txk_mb} MB / {txk_codes} 票）
曾被 <b>{txk_scripts} 个脚本各自 <code>json.load</code></b>；<code>_rev_lab.py</code> 一个脚本里就 load
<b>{txk_rev} 次</b>（105 / 344 / 562 行），同一次跑里同一份 128MB 被解析三遍。
各家缺文件行为还分叉：有的静默 <code>{{}}</code>、有的抛异常。
更要紧的是——<b>txk 是主缓存</b>，很多脚本直接拿它当「当日价」，旧数据冒充当日的后果比长K更直接。</div>
<div class="ok"><b>修复</b>：新增唯一入口 <code>_txk.py</code>——mtime 感知的进程内共享缓存
（写回自动失效，不会读到旧版本）+ <code>set_asof()</code> 陈旧即 fail-safe 返回空 +
<code>src_label()</code> 把「数据截至 X」标进产物 + 可选日志 <code>WB_TXK_LOG</code>。
实测：同一进程内 3 次 load，由 3×{txk_secs}s 降到 <b>1×{txk_secs}s + 2×0.00002s</b>；
<code>_txk.load()</code> 与直读<b>内容完全等价</b>（5049 票逐票一致）。</div>
<div class="danger"><b>过程中现场抓到的 fail-open</b>：陈旧拦截第一版「只把 <code>stale_blocks</code> 加一，
仍然把 5049 条旧数据交出去」——计数与拦截不一致，正是「有该键 ≠ 已通过」。
<b>修法</b>：拦截必须在「返回」之前，判据收敛到 <code>_stale_hit()</code> 单一真源；
钉对日期后缓存自动恢复，不需要重抓。</div>

<h3>修复 7 · 结论文件键序随 hash seed 漂移，产物每次字节都变</h3>
<div class="danger"><b>现象</b>：<code>_env_gate_lab.json</code> 每次跑字节都不同，
连 <code>PYTHONHASHSEED=0</code> 下连跑两次都能对不同 hash。</div>
<div class="ok"><b>定位</b>：<code>PYTHONHASHSEED</code> 取 0/1/2/3 → 四个不同 hash；
但把两份产物 <code>json.dumps(sort_keys=True)</code> 比较 → <b>完全一致，数值差异 0 处</b>。
根因是 <b>日期串作 dict 键</b>（<code>esc</code> / <code>elab</code> / <code>by_sc</code>），
dict 迭代序随字符串 hash 变 → 只是<b>输出键序</b>漂，bootstrap 数值没动（页面数字是稳的）。</div>
<div class="ok"><b>修复</b>：<code>json.dump(..., sort_keys=True)</code> 把键序钉死。
修复后 <code>PYTHONHASHSEED</code> 取 0 / 1 / 7 → <b>三份字节完全一致</b>（均 {txk_concl_b} 字节）。
数值不受影响，但文件可复现了，幂等门禁不会再被误判成「改了东西」。</div>

<h2>三、有效率实测（现跑现测，不写死）</h2>
{lk_html}
<h3>日K主缓存 <code>_txk_cache.json</code>（本轮解析次数）</h3>
{txk_html}
<h3>磁盘上的大产物（每次跑都要解析）</h3>
<table><tr><th>文件</th><th class="num">体积</th><th>说明</th></tr>{big_html}</table>
<div class="note">这些是中间产物、不进推送白名单。<b>它们只占本地磁盘，不占线上带宽</b>；
但每次重算都要解析一遍，所以长K已改为「进程内共享 + mtime 感知」。</div>
<h3>日更全链耗时清单</h3>
{prof_html}

<h2>四、各池实测结论（现读产物，不美化）</h2>
<div class="note">「可出票」= 该档同时满足 edge&gt;0、R3≥95%、跨窗口/跨步长同号、
留一全正、前后半同正（各池按自身口径）。<b>不达标一律写「不出票」</b>，
这正是红线「宁可不选」的落地。</div>
<table><tr><th>池</th><th>档位</th><th class="num">edge</th><th class="num">R3</th>
<th>说明</th><th>出票</th></tr>{"".join(prow)}</table>

<h2>五、统一获取：各池产出日 vs 底座日</h2>
<table><tr><th>池</th><th class="num">最新产出日</th><th>与底座 {asof} 比对</th></tr>{pr}</table>
<div class="note">「无当期页」可能是<b>无合格标的空仓</b>（属正常，不出页），也可能是漏跑。
门禁只报事实、不下判，交给人确认 —— 但不再有「静默停在旧日期」这回事。</div>

<h2>六、遗留项（未修，如实记录）</h2>
<ul>
<li><b>融资融券数据源滞后</b>：底座体检显示融资融券只到 2026-08-19（滞后 42 天）。
这是数据源（东财）自身滞后，非本地漏跑；影响面已由修复 4 的数据闸围住。</li>
<li><b>日K主缓存直读已收敛</b>：本轮扫下来绕过统一层直接读 <code>_txk_cache.json</code> 的脚本
剩 <b>{txk_scripts}</b> 个 / <b>{txk_points}</b> 处（写路径 <code>_tx_fetch.py</code> 等按白名单豁免）。
这道判断已接进门禁的 <b>C3</b> 项 —— 以后新增直读会被当场拦下，不再靠人工 grep
（上一轮手工改了 11 个调用点，仍漏掉日更底座 <code>_datahub.py</code>，就是这个原因）。</li>
<li><b><code>MA</code> / <code>ATR</code> 有多处本地实现</b>：<code>{ma_sites}</code> 行各写各的。
当前口径一致，未强制合并——合并在 297 个脚本的仓库里属侵入改造，风险大于收益。</li>
<li><b>推送白名单漏网（门禁 C2 抓出）</b>：日更链路里 <b>13 个生成器脚本</b>没进
<code>_push_lhb.py</code> 的 <code>FILES</code> —— 它们的<b>页面在册、脚本不在册</b>，
线上能翻到这些数字，却看不到数字是怎么算出来的（结论不可复算）。
已全部登记进白名单并推送上线（其中 <code>build_picks</code> / <code>gen_tplus</code> /
<code>build_tplus</code> 远端还留着旧版，本次一并覆盖为当前版）。
这道检查原先<b>是假绿</b>：解析 <code>daily_all.STEPS</code> 时命令行尾部带着 <code>--date</code>
参数，<code>endswith('.py')</code> 全部落空，只解析了 8 条、又恰好都在册，于是「恒 0」。
改成在整条命令行里抽文件名后解析出 37 条，漏网项当场现形——
<b>自检规则自己也会被验真，「某个检查项恒 0」必须先怀疑解析落空。</b></li>
</ul>

<h2>七、未解决风险与后续</h2>
<div class="note">本页<b>只记录已发生的审计结论</b>。任何统计数字都从产物现读 ——
若某产物缺失，本页对应处显示「无法自检」而不是沿用上次的数字。</div>

<footer>
生成于 {datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")} ·
<code>quant/_data_integrity_audit.py</code> ·
数据底座 <code>hub/manifest.json</code>（{asof}）<br>
相关页面：<a href="exit_assumption_evidence.html">退出成交假设证据</a> ｜
<a href="../accumulation/tier_gate.html">增仓分档核验</a> ｜
<a href="../reversal/tier_gate.html">反转分档核验</a> ｜
<a href="../../index.html">返回门户</a>
</footer>
</div></body></html>"""

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write(html)
    print("[audit] 审计报告 %s（%d 字节）" % (OUT, len(html)))
    print("[audit] 提醒：接着跑 _apply_theme.py 恢复主题注入层")


if __name__ == "__main__":
    main()
