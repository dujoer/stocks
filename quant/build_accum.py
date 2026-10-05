# -*- coding: utf-8 -*-
"""
增仓精选 · 每日选股页（build_accum.py v3）
=====================================
基于 _accum_lab 的信号帧（机构/私募季度增持 I × 融资融券 1/3/5 日净增仓 M × 日频事件）做当日选股。
定稿规则（20 交易日回测，移动止盈口径，证据见 lab.html）：
  S 档 = 5日融资净买入占成交额 ≥4%（M强）+ 机构/私募季度增持（I）
  A 档 = ≥3 信号共振 且 （融资增仓 M 或 机构/私募 I）
  B 档 = 2 个信号触发（观察仓）
  不入选 = 仅 1 个信号（≈基线，无超额）

★ 胜率不是写死的：每次运行都会先调用 `_accum_lab.py --matured --no-html` 用最新 K 线
  重跑回测并刷新 accum_result.json，页面上的胜率 / 基线 / 阈值敏感性 / 模块对照全部随之滚动。
  回测只取「前瞻已走满 20 个交易日」的入场日，不把被截断的样本算成 20 日胜率（早期版本踩过这个坑）。

每日持久化（与其它板块一致）：
  web/accumulation/combined_{DS}.html   当期页（历史留档）
  web/accumulation/stat_{DS}.json       当期统计快照（供门户读取）
  web/accumulation/index.html           最新一期（等于最新 combined）
  web/accumulation/history.html          每日归档 + 事后兑现跟踪（自包含）
  quant/accum/history.json              本地历史累积（逐期逐票，T+1/T+5 + 移动止盈结算）
每次运行会先对历史各期做兑现回填（数据够即结算），再入当期 —— 累积的可兑现胜率与其它池同口径。

用法： python build_accum.py 2026-09-21
      python build_accum.py --all        # 重生成全部已归档期页面
"""
import os, sys, json, collections, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import _accum_lab as L

OUT = os.path.join(ROOT, "web", "accumulation")
DATA = os.path.join(HERE, "accum")
HIST = os.path.join(DATA, "history.json")
os.makedirs(OUT, exist_ok=True)
os.makedirs(DATA, exist_ok=True)

RED, GRN, BLUE, GOLD = "#ea4335", "#34a853", "#1a73e8", "#b8893b"
SIG_CN = L.SIG_CN
SIG_ORDER = ["pe", "sun", "person", "fund", "block", "exec", "lhb", "m1", "m3", "m5"]
I_KEYS = ("pe", "sun", "person", "fund")
M_KEYS = ("m1", "m3", "m5")

# 分档出票许可：由 quant/_accum_tier_gate.py 产出（单一真源 `_gate_common.tier_license_windows`）。
# 判据：生产窗口(20日) edge>0 ＋ 全部窗口 R3≥95% ＋ 全部窗口绝对收益 R3≥95%
#       ＋ 留一法全正 ＋ 前/后半同为正。
# 历史坑：原实现按 max(WINDOWS)=60 单窗口判 `edge>0 且 er3_min≥95%`，B 档在 20 日
#         er3_min=0.926 不达标却在 60 日 0.9995 放行 —— 窗口挑优；且漏掉绝对收益/留一/前后半。
# 「候选改法」一类是在同一批样本里挑出来的变体，永不参与判定（挑赢家本身就是过拟合）。
EVIDENCE = os.path.join(HERE, "_accum_tier_gate.json")
RULE2TIER = {"S 档（现行生产）": "S",
             "A 档（现行生产·M或I）": "A",
             "B 档（观察仓·2信号）": "B"}


def tier_evidence():
    """读分档显著性证据；读不出任何东西时返回 {}（调用方按「不出票」处理，fail-safe）。

    ★ 判据只认 `_accum_tier_gate.json` 的 `allow_detail`（由门禁脚本用统一口径写入）。
      读不到该键（旧版证据文件）时**一律判不出票** —— 宁可空仓，也不退回旧宽松判据，
      否则「旧文件 + 新判据」会静默产出两套结论。
    """
    try:
        d = json.load(open(EVIDENCE, encoding="utf-8"))
    except Exception:
        return {}
    lic = d.get("allow_detail") or {}
    if not lic:
        return {}
    per = d.get("per") or {}
    pk = d.get("primary")
    st = (per.get(str(pk)) or per.get(pk) or {}).get("stat") or {}
    out = {}
    for name, tier in RULE2TIER.items():
        ld = lic.get(name)
        if ld is None:
            continue
        s = st.get(name) or {}
        out[tier] = {"ok": bool(ld.get("ok")),
                     "why": ld.get("why", ""),
                     "edge": s.get("edge", 0.0), "r3": s.get("er3_min", 0.0),
                     "wr": s.get("wr", 0.0), "days": s.get("days", 0), "n": s.get("n", 0)}
    return out
TIER_CN = {"S": "S 强共振", "A": "A 共振", "B": "B 观察"}


def load_result():
    p = os.path.join(OUT, "accum_result.json")
    if os.path.exists(p):
        return json.load(open(p, encoding="utf-8"))
    return {}


def refresh_result(days=20, timeout=1800):
    """每日重算回测，刷新 accum_result.json —— 页面胜率因此随真实行情滚动更新，
    不再是一份写死的历史快照。失败时沿用旧文件（页面会标出基准日）。"""
    p = os.path.join(OUT, "accum_result.json")
    before = ""
    if os.path.exists(p):
        try:
            before = json.load(open(p, encoding="utf-8")).get("asof", "")
        except Exception:
            pass
    cmd = [sys.executable, "-u", os.path.join(HERE, "_accum_lab.py"),
           "--days", str(days), "--matured", "--no-html"]
    try:
        r = subprocess.run(cmd, cwd=HERE, capture_output=True, text=True, timeout=timeout)
        tail = (r.stdout or "").strip().splitlines()
        print("[回测重算] " + (tail[-1] if tail else "无输出"))
        if r.returncode != 0:
            print("[回测重算] 退出码 %s：%s" % (r.returncode, (r.stderr or "")[-400:]))
    except Exception as e:
        print("[回测重算] 失败（沿用旧结果）：%r" % (e,))
    res = load_result()
    print("[回测基准] 数据截至 %s｜入场窗口 %s｜完整前瞻=%s（上一版 %s）" % (
        res.get("asof", "?"), res.get("window", []), res.get("matured"), before or "无"))
    return res


# ---------------------------------------------------------------
# 历史累积
# ---------------------------------------------------------------
def load_hist():
    if os.path.exists(HIST):
        try:
            h = json.load(open(HIST, encoding="utf-8"))
            if isinstance(h, list):
                return h
        except Exception:
            pass
    return []


def save_hist(hist):
    hist.sort(key=lambda h: h.get("date", ""))
    with open(HIST, "w", encoding="utf-8") as f:
        json.dump(hist, f, ensure_ascii=False, indent=1)


def entry_price(K, code, T):
    try:
        ds, last = K[code][0], K[code][1]
        return last[ds.index(T)]
    except Exception:
        return None


def upsert(hist, date, rows, universe_n, K):
    """写入/覆盖当期条目（S+A 档逐票入库，B 档只留计数）。"""
    nS = sum(1 for r in rows if r["tier"] == "S")
    nA = sum(1 for r in rows if r["tier"] == "A")
    nB = sum(1 for r in rows if r["tier"] == "B")
    picks = []
    for r in rows:
        if r["tier"] not in ("S", "A"):
            continue
        picks.append({
            "code": r["code"], "name": r["name"], "tier": r["tier"],
            "score": r["score"], "n_sig": r["n_sig"], "m5r": r.get("m5r", 0.0),
            "entry": entry_price(K, r["code"], date),
        })
    row = {"date": date, "universe": universe_n, "nS": nS, "nA": nA, "nB": nB,
           "picks": picks}
    for i, h in enumerate(hist):
        if h.get("date") == date:
            hist[i] = row
            break
    else:
        hist.append(row)
    return hist


def settle(hist, K):
    """对历史每期每票回填事后收益（移动止盈口径，与回测同规则）。
    K 不变则结果不变，幂等；新交易日入库后旧期会自动重算。

    ★ 成熟度：只有「真实退出」（硬止损/跟踪止盈/走满 MAXFWD 日）才计入胜率统计；
    因数据只到今天而被强行「满期强平」的样本记为 pending，不混入胜率——
    否则前几天的前瞻只有 3~7 根，算出来的「胜率」是截断数字，不是 20 日胜率。
    """
    MAXFWD = getattr(L, "MAXFWD", 20)
    for h in hist:
        T = h.get("date", "")
        tot = 0
        win = 0
        pend = 0
        sret = 0.0
        for p in h.get("picks", []):
            code = p.get("code")
            sim = L.simulate(K, code, T) if code in K else None
            if sim:
                ret, w, fwd, rs = sim
                matured = (rs in ("硬止损", "跟踪止盈")) or (fwd >= MAXFWD)
                p["sim"] = {"ret": round(ret * 100, 2), "win": bool(w),
                            "fwd": fwd, "reason": rs, "matured": matured}
                if matured:
                    tot += 1
                    win += 1 if w else 0
                    sret += ret
                else:
                    pend += 1
            else:
                p.pop("sim", None)
            # T+1 / T+5 裸收益（不走退出规则，仅供观察短期反应）
            f1 = f5 = None
            try:
                ds, last = K[code][0], K[code][1]
                i = ds.index(T)
                ep = last[i]
                if ep:
                    if i + 1 < len(ds):
                        f1 = round((last[i + 1] / ep - 1) * 100, 2)
                    if i + 5 < len(ds):
                        f5 = round((last[i + 5] / ep - 1) * 100, 2)
            except Exception:
                pass
            p["f1"], p["f5"] = f1, f5
        h["nSettle"] = tot
        h["pending"] = pend
        h["wins"] = win
        h["wr"] = round(win / tot * 100, 1) if tot else None
        h["avg"] = round(sret / tot * 100, 2) if tot else None
    return hist


def pending_summary(hist):
    """未到期（前瞻不足）样本数合计。"""
    return sum(h.get("pending", 0) for h in hist)


def hist_summary(hist):
    tot = sum(h.get("nSettle", 0) for h in hist)
    win = sum(h.get("wins", 0) for h in hist)
    return {
        "periods": len(hist),
        "n": tot,
        "wr": round(win / tot * 100, 1) if tot else None,
    }


# ---------------------------------------------------------------
# 选股
# ---------------------------------------------------------------
def scan(date):
    K = L.load_kline()
    cal = L.trading_days(K)
    if date not in cal:
        date = cal[-1]
        print(f"[warn] 指定日不在交易日历，回退最新数据日 {date}")
    q2 = L.load_q2_flags()
    snaps = L.load_margin_snapshots()
    mh = L.load_margin_em()
    frame = L.signal_frame(date, K, q2, snaps, cal, mh=mh)

    nm = {}
    try:
        nm = json.load(open(os.path.join(HERE, "_stock_names.json"), encoding="utf-8"))
    except Exception:
        pass
    c = json.load(open(L.CACHE, encoding="utf-8"))
    names = {code: (nm.get(code) or (bars[-1].get("name") if bars else None) or code)
             for code, bars in c.items()}

    rows = []
    for code, sig in frame.items():
        has_daily = any(k in sig and sig[k] > 0 for k in L.DAILY)
        if not has_daily:
            continue
        sc = L.composite(sig)
        if sc <= 0:
            continue
        n_sig = sum(1 for k in L.ALLSIG if k in sig and sig[k] > 0)
        I = any(k in sig and sig[k] > 0 for k in I_KEYS)
        M = any(k in sig and sig[k] > 0 for k in M_KEYS)
        m5r = sig.get("_mr5") or 0.0
        if m5r >= L.MARG_TH[5] and I:
            tier = "S"
        elif n_sig >= 3 and (M or I):
            tier = "A"
        elif n_sig == 2:
            tier = "B"
        else:
            tier = "C"
        rows.append({
            "code": code, "name": names.get(code, code), "score": round(sc, 3),
            "n_sig": n_sig, "sig": sig, "tier": tier,
            "m5r": round(m5r * 100, 1),
        })
    tier_rank = {"S": 0, "A": 1, "B": 2, "C": 3}
    # 末位以 code 兜底：dict/set 迭代顺序跨进程不稳定，否则同参数的页面 sha 会漂
    rows.sort(key=lambda r: (tier_rank[r["tier"]], -r["n_sig"], -r["score"], r["code"]))
    return date, rows, len(frame), K


def sig_badges(sig):
    out = []
    for k in SIG_ORDER:
        if k in sig and sig[k] > 0:
            tip = ""
            if k == "block":
                tip = f"（额 {sig.get('_block_val',0)/1e4:.0f}万 折价 {sig.get('_block_disc',0):.1f}%）"
            elif k == "exec":
                tip = f"（增持 {sig.get('_exec_amt',0)/1e4:.0f}万元）"
            elif k == "lhb":
                tip = f"（净买 {sig.get('_lhb_net',0)/1e4:.0f}万）"
            elif k in ("m1", "m3", "m5"):
                w = {"m1": "1日", "m3": "3日", "m5": "5日"}[k]
                r = sig.get("_mr" + k[1])
                tip = f"（{w}融资净买入占成交额 {r*100:.1f}%）" if r is not None else ""
            out.append(f"<span class='bdg' title='{tip}'>{SIG_CN[k]}</span>")
    return "".join(out)


def _ret_color(v):
  if v is None:
    return "#8a929c"
  return RED if v > 0 else (GRN if v < 0 else "#8a929c")


def _hub_note(date):
  """底座溯源：本次数据来自哪个源、覆盖多少、哪个维度滞后。

  ★ 融资融券是**数据源客观滞后**（东财实测末根 2026-08-19，滞后 42 天，
    接口参数已核对无误）。页面必须如实标注，不能让人以为是当日数据。
  """
  hp = os.path.join(HERE, "hub", "%s.json" % (date.replace("-", "") if date else ""))
  mp = os.path.join(HERE, "hub", "manifest.json")
  if not (os.path.exists(hp) and os.path.exists(mp)):
    return ("<div class='evi' style='margin-top:12px;background:#f7f7f5;"
            "border-color:#e0ded6;color:#6b6b6b'><b>数据溯源</b>："
            "未接入统一数据底座（<code>_datahub.py</code>），本页各数据源独立抓取。"
            "建议先跑 <code>python quant/_datahub.py --date {D}</code>。</div>"
            .replace("{D}", date or "—"))
  try:
    mf = json.load(open(mp, encoding="utf-8"))
  except Exception:
    return ""
  src = mf.get("sources") or {}
  cnt = mf.get("counts") or {}
  rows = []
  for k in ("margin", "exec", "block", "lhb", "quotes", "flow"):
    if k in src:
      rows.append("　· %s：%s（%s 只）" % (k, src[k], cnt.get(k, "—")))
  return ("<div class='evi' style='margin-top:12px;background:#f2f7fd;"
          "border-color:#cfe0f5;color:#1a4e85'><b>数据溯源（统一数据底座）</b>："
          "本次数据日 <b>{D}</b>，底座覆盖 <b>{cov}</b>。<br>{rows}<br>"
          "<b style='color:#9a5b1e'>⚠ 融资融券维度数据源客观滞后</b>："
          "东财接口实测末根为 2026-08-19（滞后 42 天，接口参数已核对无误）。"
          "因此本池的「融资 1/3/5 日增仓」模块用的是 8 月中旬的真实数据，"
          "<b>不是 9 月末的</b> —— 该模块结论请按此理解。</div>"
          .replace("{D}", date or "—").replace("{cov}", mf.get("coverage", "—"))
          .replace("{rows}", "<br>".join(rows) or "—"))


def _ablate_block():
  """因子消融 + 严格样本外检验结论块。

  ★ 铁律：所有数字从 accum_ablate.json / accum_oos.json 动态读，
    **绝不在此写死**（用户 2026-10-01 明确要求）。文件不存在时如实说明未跑，
    不编造结论。
  """
  p_ab = os.path.join(OUT, "accum_ablate.json")
  p_oos = os.path.join(OUT, "accum_oos.json")
  if not (os.path.exists(p_ab) and os.path.exists(p_oos)):
    return ("<div class='evi' style='margin-top:12px;background:#f7f7f5;"
            "border-color:#e0ded6;color:#6b6b6b'><b>因子消融实验</b>："
            "尚未运行（<code>_accum_ablate.py</code> + <code>_accum_oos.py</code>），"
            "本页不展示任何未经检验的因子结论。</div>")
  try:
    ab = json.load(open(p_ab, encoding="utf-8"))
    oos = json.load(open(p_oos, encoding="utf-8"))
  except Exception:
    return ""

  L_ = ab.get("loo", {})
  neg = [k for k, v in L_.items() if v.get("verdict") == "负贡献"]
  SIG_CN = {"pe": "私募增持", "sun": "阳光私募", "person": "个人(牛散)增持",
            "fund": "公募增持", "block": "大宗交易", "exec": "高管增持",
            "lhb": "席位异动", "m1": "多空增仓1日", "m3": "多空增仓3日",
            "m5": "多空增仓5日"}
  neg_cn = "、".join(SIG_CN.get(k, k) for k in neg) or "无"

  cl = ab.get("cleaned", {})
  base_oos = ab.get("base", [0, 0, 0])[1]        # 随机基线
  all_wr = cl.get("all_wr")                       # 全因子胜率（消融时实测）
  cln_wr = cl.get("wr")
  cln_n = cl.get("n")
  all_n = cl.get("all_n")

  smry = oos.get("summary", {})
  clean_row = smry.get("清洗基线(无闸门)", {})
  pct_clean = clean_row.get("pctile")              # 清洗后胜率在随机分布的分位
  wr_clean = clean_row.get("wr_real") or cln_wr

  def _pct(x):
    return "—" if x is None else ("%.1f%%" % x)

  def _num(x):
    return "—" if x is None else ("%d" % x)

  rows = []
  for k in ("清洗基线(无闸门)", "融资5日≥4% 且机构增持", "距250日高 低于中位",
            "MA20斜率 > 0", "20日涨幅 低于中位"):
    v = smry.get(k)
    if not v:
      continue
    rows.append("　· %s：胜率 %s（n=%s）｜ 随机分位 %s"
                % (k, _pct(v.get("wr_real")), _num(v.get("n_real") or v.get("n_total")),
                   _pct(v.get("pctile"))))
  detail = "<br>".join(rows) or "　·（无闸门通过检验）"

  delta_txt = ("%+.1fpp" % (cln_wr - all_wr)) if (cln_wr is not None and all_wr is not None) else "—"
  out = []
  out.append("<div class='evi' style='margin-top:12px;background:#fff8ec;"
             "border-color:#f0dcb4;color:#7a4a12'>")
  out.append("<b>因子消融 × 严格样本外检验（2026-10-02 新增，结论原样放这里不做美化）</b><br><br>")
  out.append("<b>① 留一法找出的负贡献因子：{neg}</b><br>".format(neg=neg_cn))
  out.append("　留一法 = 从全信号里去掉某个因子，看胜率是升还是降；<b>去掉后反而升的因子就是拖累项</b>。"
             "事件驱动类信号（大宗交易、公募增持）本质是「异动」，异动＝短期超买＝均值回归，"
             "把它们当利好会拉低胜率。<br>")
  out.append("　剔除后：全信号胜率 <b>{a}</b>（n={an}）→ <b>{c}</b>（n={cn}），{d}，随机基线 <b>{b}</b>。"
             "<b>但这还不是可上线的结论</b> —— 样本在时间上高度集中（见 ③）。<br><br>".format(
                 a=_pct(all_wr), an=_num(all_n), c=_pct(cln_wr),
                 cn=_num(cln_n), d=delta_txt, b=_pct(base_oos)))
  out.append("<b>② 随机对照：为什么不能只看胜率</b><br>")
  out.append("　同 n、同入场日、独立随机抽样 200 遍，看该组合在随机分布里的分位。"
             "分位越低才说明真的有超额。关键一条：<b>清洗后胜率 {wr} 的随机分位只有 {pct}</b> —— "
             "意味着随机抽 200 遍里有这么多次也能达到同等水平，<b>它并不突出</b>。"
             "此前页面上出现过的「71.6%／edge +11.6pp」是<b>在同一份数据上既挑参数又验收</b>的结果，"
             "属过拟合，<b>已作废</b>。<br>".format(wr=_pct(wr_clean), pct=_pct(pct_clean)))
  out.append("　{d}<br><br>".format(d=detail))
  out.append("<b>③ 样本外切分失败（根本原因）</b><br>")
  out.append("　事件类原始数据（<code>block_chg</code>／<code>exec_chg</code>／<code>lhb_detail</code>）"
             "<b>只覆盖最近约 3 个月</b>（block 最早 2026-07-01、exec 09-02、lhb 09-01），"
             "清洗后 {n} 个样本<b>全部挤在最后一段</b>，前两段各 0 个样本 → "
             "<b>无法做真正的样本外切分</b>。<br>".format(n=_num(cln_n)))
  out.append("　所以现在能诚实说的是：<b>「剔除负贡献因子」这个方向在留一法上站得住</b>，"
             "但<b>「提高胜率」这件事目前无法证明</b> —— 不是策略一定无效，而是样本长度还不够检验。<br><br>")
  out.append("<b>④ 现在的处置</b>：<b>不改选股规则</b>，页面照实展示现有口径与 edge。"
             "待历史事件文件补齐（≥3 个月）后重跑 <code>_accum_oos.py</code>，"
             "只有「各可比段全部样本外跑赢 + 随机分位≥90」双通过，才会写进规则。"
             "脚本：<code>_accum_ablate.py</code>（消融）／<code>_accum_oos.py</code>（样本外＋随机对照）。")
  out.append("</div>")
  return "".join(out)


def archive_rows(hist, cur_date):
    """历史归档表（只显示 ≤ 当期 的期次，保证当期页不含未来信息）。"""
    rows = [h for h in hist if h.get("date", "") <= cur_date]
    out = []
    for h in sorted(rows, key=lambda x: x["date"], reverse=True):
        d = h["date"]
        ds = d.replace("-", "")
        cur = " style='font-weight:700'" if d == cur_date else ""
        wr = h.get("wr")
        wrs = f"{wr:.1f}%" if wr is not None else "待结算"
        if wr is None:
            wrc = "#8a929c"
        else:
            wrc = RED if wr >= 70 else (GOLD if wr >= 60 else "#8a929c")
        pend = h.get("pending", 0)
        tiny = h.get("nSettle", 0) < 10
        settle_txt = (f"{h.get('nSettle',0)}/{h.get('nS',0)+h.get('nA',0)}"
                      + (f" <span style='color:#8a929c'>+{pend}观察中</span>" if pend else "")
                      + (" <span style='color:#8a929c;font-weight:400'>样本过小</span>" if tiny else ""))
        out.append(
            f"<tr><td{cur}><a href='combined_{ds}.html'>{d}</a></td>"
            f"<td>{h.get('universe','—')}</td><td>{h.get('nS',0)}</td><td>{h.get('nA',0)}</td>"
            f"<td>{h.get('nB',0)}</td><td>{settle_txt}</td>"
            f"<td style='color:{wrc};font-weight:700'>{wrs}</td></tr>")
    return "".join(out)


def render_history(hist):
    """每日归档 + 事后兑现跟踪页（自包含）。"""
    summ = hist_summary(hist)
    rows = []
    for h in sorted(hist, key=lambda x: x["date"], reverse=True):
        d = h["date"]
        ds = d.replace("-", "")
        wr = h.get("wr")
        wrc = _ret_color(wr - 50) if wr is not None else "#8a929c"
        rows.append(
            f"<tr><td><a href='combined_{ds}.html'>{d}</a></td>"
            f"<td>{h.get('universe','—')}</td><td>{h.get('nS',0)}</td><td>{h.get('nA',0)}</td>"
            f"<td>{h.get('nB',0)}</td>"
            f"<td>{h.get('nSettle',0)}"
            + (f" <span style='color:#8a929c;font-weight:400'>/{h.get('pending',0)}</span>" if h.get("pending", 0) else "")
            + "</td>"
            f"<td style='color:{wrc};font-weight:700'>{wr if wr is not None else '—'}"
            f"{'%' if wr is not None else ''}</td>"
            f"<td style='color:{_ret_color(h.get('avg'))}'>{h.get('avg') if h.get('avg') is not None else '—'}</td></tr>")

    # 逐期明细（近 10 期）
    detail = []
    for h in sorted(hist, key=lambda x: x["date"], reverse=True)[:10]:
        d = h["date"]
        ds = d.replace("-", "")
        ps = h.get("picks", [])
        if not ps:
            detail.append(f"<div class='hrow'><div class='hd'><a href='combined_{ds}.html'>{d}</a>"
                          f"<span class='hsub'>候选 {h.get('universe','—')} · 无 S/A 档入选</span></div></div>")
            continue
        trs = []
        for p in ps:
            sim = p.get("sim")
            if sim:
                rc = _ret_color(sim["ret"])
                rt = f"<span style='color:{rc};font-weight:700'>{sim['ret']:+.2f}%</span>" \
                     f"<span class='why'>{sim['reason']}·{sim['fwd']}日</span>"
            else:
                rt = "<span class='why'>未到期</span>"
            f1 = p.get("f1")
            f5 = p.get("f5")
            tc = GOLD if p["tier"] == "S" else RED
            trs.append(
                f"<tr><td><a href='https://quote.eastmoney.com/{p['code']}.html' target='_blank'>{p['name']}</a></td>"
                f"<td style='color:{tc};font-weight:700'>{p['tier']}</td><td>{p.get('n_sig','—')}</td>"
                f"<td>{p.get('m5r',0):.1f}%</td>"
                f"<td style='color:{_ret_color(f1)}'>{f1 if f1 is not None else '—'}</td>"
                f"<td style='color:{_ret_color(f5)}'>{f5 if f5 is not None else '—'}</td>"
                f"<td>{rt}</td></tr>")
        wr = h.get("wr")
        detail.append(
            f"<div class='hrow'><div class='hd'><a href='combined_{ds}.html'>{d}</a>"
            f"<span class='hsub'>候选 {h.get('universe','—')} 只 · S {h.get('nS',0)} / A {h.get('nA',0)}"
            f" · 已兑现 {h.get('nSettle',0)}"
            + (f"（另有 {h.get('pending',0)} 个未走完 20 日，不计入胜率）" if h.get("pending", 0) else "")
            + f" · 胜率 <b style='color:{_ret_color((wr or 0)-50)}'>{wr if wr is not None else '—'}"
            f"{'%' if wr is not None else ''}</b></span></div>"
            f"<table><tr><th>名称</th><th>档</th><th>共振</th><th>5日融资占比</th>"
            f"<th>T+1</th><th>T+5</th><th>结算（移动止盈）</th></tr>{''.join(trs)}</table></div>")

    html = CSS_HEAD + f"""<title>增仓精选 · 每日归档与兑现跟踪</title>{CSS_COMMON}<style>
.hrow{{margin:0 0 16px}}
.hd{{font-size:14px;font-weight:700;margin:0 0 6px}}
.hsub{{font-weight:400;color:#6b7280;font-size:12px;margin-left:8px}}
.why{{display:block;font-size:11px;color:#8a929c}}
</style></head><body><div class="wrap">
<h1>每日归档 · 兑现跟踪</h1>
<p class="sub">共 {summ['periods']} 期 ｜ <b>已真实兑现</b> {summ['n']} 个（另有 {pending_summary(hist)} 个未走完 20 日，观察中不计入）｜
累计可兑现胜率 <b style="color:{_ret_color((summ['wr'] or 0)-50)}">{summ['wr'] if summ['wr'] is not None else '—'}{'%' if summ['wr'] is not None else ''}</b>
（与回测口径一致：止损 −12% ／ 浮盈 +6% 激活、回撤 3% 跟踪 ／ 满 20 日强平；
<b>只有真实退出（硬止损 / 跟踪止盈 / 走满 20 日）才计入胜率</b>，前瞻不足被截断的不算）｜
<a href='index.html'>最新一期</a> · <a href='lab.html'>回测证据</a></p>

<div class="card"><h2>各期概览</h2>
<table><tr><th>数据日</th><th>候选域</th><th>S 档</th><th>A 档</th><th>B 档</th><th>已兑现 / 观察中</th><th>胜率</th><th>均值收益</th></tr>
{''.join(rows) if rows else "<tr><td colspan='8'>暂无归档</td></tr>"}</table>
<div class="note">T+1 / T+5 为裸涨跌幅（不走退出规则），结算列按移动止盈规则兑现；两者口径不同，别混用。</div></div>

<div class="card"><h2>近 10 期逐票明细</h2>
{''.join(detail) if detail else "<div class='note'>暂无明细。</div>"}</div>

<div class="rule"><b>说明</b><br>
· 归档按<b>交易日逐期</b>留档：每期生成 <code>combined_&#123;YYYYMMDD&#125;.html</code> 与 <code>stat_&#123;YYYYMMDD&#125;.json</code>，门户按最新一期更新。<br>
· S / A 档逐票入库（含当日收盘价，作入场价），每次运行都会重算历史各期的事后兑现 —— <b>这是真实留痕，不是回测拟合</b>。<br>
· 样本会随交易日累积，短期数字统计脆弱；<b>退出纪律 &gt; 入场筛选</b>。</div>
</div></body></html>"""
    p = os.path.join(OUT, "history.html")
    open(p, "w", encoding="utf-8").write(html)
    return p


CSS_HEAD = """<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
"""

# 与其它板块页面保持一致的公共样式块（历史/归档页与当期页共用）
CSS_COMMON = """<style>
*{box-sizing:border-box}
body{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#23262b}
.wrap{max-width:1440px;margin:0 auto;padding:36px 20px 60px}
h1{font-size:26px;margin:0 0 4px;color:#1c2430}
.sub{color:#8a929c;font-size:13px;margin:0 0 20px}
.card{background:#fff;border:1px solid rgba(0,0,0,.08);border-radius:16px;padding:18px 20px;margin:0 0 18px;box-shadow:0 1px 3px rgba(20,30,50,.05)}
.card h2{font-size:16px;margin:0 0 12px;color:#1c2430;display:flex;align-items:center;gap:8px}
.card h2:before{content:"";width:4px;height:16px;background:#b8893b;border-radius:3px}
.kpi{display:flex;flex-wrap:wrap;gap:12px}
.k{flex:1;min-width:150px;background:linear-gradient(135deg,#fafbff,#f0f4ff);border:1px solid #dde6ff;border-radius:14px;padding:13px;text-align:center}
.k .v{font-size:24px;font-weight:800}
.k .l{font-size:12px;color:#6b7280;margin-top:4px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:7px 9px;border-bottom:1px solid #eef0f3;text-align:center}
th{background:#f7f9fc;color:#5b6573;font-weight:600}
td a{color:#1c2430;text-decoration:none} td a:hover{color:#1a73e8}
.rule{background:#fff7ed;border:1px solid #fed7aa;color:#9a5b1e;border-radius:12px;padding:12px 14px;font-size:13px;line-height:1.8}
.note{color:#6b7280;font-size:12px;line-height:1.7}
code{background:#f1f3f4;padding:1px 5px;border-radius:5px;font-size:12px}
</style>"""


def render(date, rows, universe_n, res, hist):
    S = [r for r in rows if r["tier"] == "S"]
    A = [r for r in rows if r["tier"] == "A"]
    B = [r for r in rows if r["tier"] == "B"]
    cons = res.get("cons_wr", {})
    mod_wr = res.get("mod_wr", {})
    base_wr = res.get("base_wr", (0, 0, 0))
    sens = res.get("sens_wr", {})
    days = res.get("days", 20)

    def wr3(k):
        v = mod_wr.get(k) or (0, 0.0, 0.0)
        return v

    s_v6 = wr3("v6_M强(≥5日占比4%)+I")
    v3 = wr3("v3_≥3共振+M且I")
    m_no_i = wr3("_对照_M无I")
    i_no_m = wr3("_对照_I无M")
    sel_wr = res.get("sel_wr", (0, 0.0, 0.0))
    edge = (sel_wr[1] - base_wr[1]) if base_wr[0] else 0.0
    _sw = (res.get("sig_wr", {}) or {}).get("m5") or (0, (0, 0.0, 0.0))
    m5_wr = _sw[1] if isinstance(_sw, (list, tuple)) and len(_sw) == 2 else (0, 0.0, 0.0)
    asof = res.get("asof", "")
    win_ = res.get("window", []) or []
    win_txt = (f"{win_[0]} ~ {win_[1]}" if len(win_) == 2 else "—")
    matured = bool(res.get("matured", False))
    n_pend = pending_summary(hist)
    cons_rows = "".join(
        f"<tr><td>≥{m} 个信号</td><td>{v[0]}</td>"
        f"<td style='color:{RED if v[1]>=60 else GRN};font-weight:700'>{v[1]:.1f}%</td><td>{v[2]:.2f}%</td></tr>"
        for m, v in sorted(cons.items(), key=lambda x: int(x[0].replace('≥','').replace(' 个信号','')) if isinstance(x[0], str) else 0))
    mod_rows = "".join(
        f"<tr><td>{'S 档规则' if k.startswith('v6') else k.split('_',1)[1]}</td><td>{v[0]}</td>"
        f"<td style='color:{RED if v[1]>=70 else BLUE};font-weight:700'>{v[1]:.1f}%</td><td>{v[2]:.2f}%</td></tr>"
        for k, v in mod_wr.items() if not k.startswith("_"))
    sens_rows = "".join(
        f"<tr><td>5日净买入占比 ≥{float(k)*100:.0f}%</td><td>{v[0]}</td>"
        f"<td style='color:{RED if v[1]>=70 else BLUE};font-weight:700'>{v[1]:.1f}%</td><td>{v[2]:.2f}%</td></tr>"
        for k, v in sorted(sens.items(), key=lambda x: float(x[0])))

    def card(r):
        tc = {"S": "#b8893b", "A": RED, "B": BLUE}.get(r["tier"], "#888")
        return f"""<div class='stk{'' if r["tier"]!="S" else " stkS"}'>
<div class='h'><a class='nm' href='https://quote.eastmoney.com/{r["code"]}.html' target='_blank'>{r["name"]}</a>
<span class='cd'>{r["code"].upper()}</span><span class='tier' style='background:{tc}1a;color:{tc}'>{TIER_CN.get(r["tier"], r["tier"])}</span>
<span class='sc'>增仓分 {r["score"]:.2f}</span></div>
<div class='sg'>{sig_badges(r["sig"])}</div></div>"""


    # ---- 分档出票许可（读显著性证据，读不到 = 一律不出票）----
    evd = tier_evidence()
    emit = sorted(t for t, v in evd.items() if v.get("ok"))
    ev_rows = "".join(
        "<tr><td>%s</td><td class='num'>%d</td><td class='num'>%d</td>"
        "<td class='num' style='color:%s;font-weight:700'>%+.2f pp</td>"
        "<td class='num'>%.0f%%</td><td>%s</td></tr>"
        % (TIER_CN.get(t, t), (evd[t]["n"] or 0), (evd[t]["days"] or 0),
           (RED if evd[t]["edge"] > 0 else GRN), evd[t]["edge"],
           (evd[t]["r3"] or 0) * 100,
           ("<b style='color:%s'>可出票</b>" % RED) if evd[t]["ok"] else "未达 95% 门槛 → 不出票")
        for t in sorted(evd.keys()))
    ev_tbl = ("<table><tr><th>档位</th><th class='num'>回测样本</th><th class='num'>入场日</th>"
              "<th class='num'>逐日平衡超额</th><th class='num'>R3（保守）</th><th>判定</th></tr>"
              "%s</table>" % ev_rows) if ev_rows else ""
    emit_txt = ("、".join(TIER_CN.get(t, t) for t in emit)) if emit else "无"
    cards = "".join(card(r) for r in [x for x in (S + A + B) if x["tier"] in emit][:40])

    def trow(r, i):
        return (f"<tr><td>{i}</td><td><a href='https://quote.eastmoney.com/{r['code']}.html' "
                f"target='_blank'>{r['name']}</a></td><td>{r['code'].upper()}</td><td>{TIER_CN.get(r['tier'], r['tier'])}</td>"
                f"<td>{r['n_sig']}</td><td>{r.get('m5r', 0):.1f}%</td><td>{r['score']:.2f}</td><td class='sgtd'>{sig_badges(r['sig'])}</td></tr>")
    tbl = "".join(trow(r, i + 1) for i, r in enumerate(S + A + B))

    summ = hist_summary(hist)
    arc_rows = archive_rows(hist, date)

    html = f"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>增仓精选 · {date}</title>
<style>
*{{box-sizing:border-box}}
body{{margin:0;font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;background:#f5f6f8;color:#23262b}}
.wrap{{max-width:1440px;margin:0 auto;padding:36px 20px 60px}}
h1{{font-size:26px;margin:0 0 4px;color:#1c2430}}
.sub{{color:#8a929c;font-size:13px;margin:0 0 20px}}
.card{{background:#fff;border:1px solid rgba(0,0,0,.08);border-radius:16px;padding:18px 20px;margin:0 0 18px;box-shadow:0 1px 3px rgba(20,30,50,.05)}}
.card h2{{font-size:16px;margin:0 0 12px;color:#1c2430;display:flex;align-items:center;gap:8px}}
.card h2:before{{content:"";width:4px;height:16px;background:{GOLD};border-radius:3px}}
.kpi{{display:flex;flex-wrap:wrap;gap:12px}}
.k{{flex:1;min-width:150px;background:linear-gradient(135deg,#fafbff,#f0f4ff);border:1px solid #dde6ff;border-radius:14px;padding:13px;text-align:center}}
.k .v{{font-size:24px;font-weight:800}}
.k .l{{font-size:12px;color:#6b7280;margin-top:4px}}
.stkgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:12px}}
.stk{{background:#fbfcfe;border:1px solid #e8ecf3;border-radius:12px;padding:12px 14px}}
.stkS{{background:linear-gradient(135deg,#fffaf0,#fdf3e0);border-color:#ecd9ae}}
.nm{{font-weight:700;font-size:15px;color:#1c2430;text-decoration:none}}
.nm:hover{{color:{BLUE}}}
.cd{{font-size:11px;color:#8a929c}}
.tier{{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:700}}
.sc{{margin-left:auto;font-size:12px;color:#6b7280}}
.sg{{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px}}
.bdg{{font-size:11px;background:#eef3fb;color:#3c5a83;border:1px solid #d8e2f2;border-radius:9px;padding:2px 8px}}
table{{width:100%;border-collapse:collapse;font-size:13px}}
th,td{{padding:7px 9px;border-bottom:1px solid #eef0f3;text-align:center}}
th{{background:#f7f9fc;color:#5b6573;font-weight:600}}
td a{{color:#1c2430;text-decoration:none}} td a:hover{{color:{BLUE}}}
.sgtd{{text-align:left;white-space:normal}}
.rule{{background:#fff7ed;border:1px solid #fed7aa;color:#9a5b1e;border-radius:12px;padding:12px 14px;font-size:13px;line-height:1.8}}
.evi{{background:#f0f7ff;border:1px solid #cfe3ff;border-radius:12px;padding:12px 14px;font-size:13px;line-height:1.8}}
.note{{color:#6b7280;font-size:12px;line-height:1.7}}
.hrow{{margin:0 0 16px}}
.hd{{font-size:14px;font-weight:700;margin:0 0 6px}}
.hsub{{font-weight:400;color:#6b7280;font-size:12px;margin-left:8px}}
.why{{display:block;font-size:11px;color:#8a929c}}
</style></head><body><div class="wrap">
<h1>增仓精选</h1>
<p class="sub">数据日 {date} ｜ 候选域 {universe_n} 只（带日频增仓事件）｜ S 档 {len(S)} · A 档 {len(A)} · B 档 {len(B)}
｜ <a href='history.html'>每日归档 · 兑现跟踪</a>（已 {summ['periods']} 期 / <b>已真实兑现</b> {summ['n']} 个，胜率
<b style="color:{_ret_color((summ['wr'] or 0)-50)}">{summ['wr'] if summ['wr'] is not None else '—'}{'%' if summ['wr'] is not None else ''}</b>；另有 {n_pend} 个未走完 20 日，观察中不计入）</p>

<div class="card"><h2>选股逻辑：机构/私募 × 融资增仓 双模块</h2>
<div class="kpi">
<div class="k" style="background:linear-gradient(135deg,#fffaf0,#fdf3e0);border-color:#ecd9ae"><div class="v" style="color:{GOLD}">{s_v6[1]:.1f}%</div><div class="l">S 档胜率（M强×机构私募，n={s_v6[0]}）</div></div>
<div class="k"><div class="v" style="color:{GRN if (evd.get('A',{}).get('wr') or 0) < 55 else BLUE}">{(evd.get('A',{}).get('wr') or 0):.1f}%</div><div class="l">A 档胜率（现行规则「≥3共振且 M 或 I」· 全候选域口径，n={evd.get('A',{}).get('n',0)}）</div></div>
<div class="k"><div class="v" style="color:#888">{base_wr[1]:.1f}%</div><div class="l">随机基线（{days}日回测）</div></div>
<div class="k"><div class="v">{len(S)}</div><div class="l">今日 S 档（融资强增仓×机构私募）</div></div>
<div class="k"><div class="v" style="color:{RED if edge > 0 else GRN}">{edge:+.1f}pp</div><div class="l">入选整体 vs 随机基线（{sel_wr[1]:.1f}% / n={sel_wr[0]}）</div></div>
</div>
<div class="evi" style="margin-top:12px;background:#f0faf3;border-color:#cfe9d8;color:#1a6b3c">
<b>上面胜率是每日随行情重算的滚动回测值</b>：本次基准 <b>数据截至 {asof or '—'}</b>，
入场日窗口 <b>{win_txt}</b>，{'每笔样本均完整走满 %d 个交易日（不走满的不计入）。' % days if matured else '<b style="color:#9a5b1e">含前瞻不足被截断的样本，仅供参考</b>。'}
每次日更都会用最新 K 线重跑一次回测，数字会随市场变化而变动 —— 若你两次打开看到不同数值，是数据滚动导致的，不是页面出错。
{'' if date >= (max([h.get('date','') for h in hist]) if hist else date) else '<br><b style="color:#9a5b1e">注意：本页是历史期<b>回填重生成版</b>，回测基准用的是最新数据日，不等于该期当天当时的快照。</b>'}<br>
<b style="color:#9a5b1e">口径修正说明</b>：早期版本用「最近 20 个交易日」当入场日，最后几天的样本前瞻只有 1~19 根就被强行「满期强平」，
等于把几天的短期涨跌当成 20 日结果，S 档因此显示过 80%+ 的虚高胜率。改为只取<b>前瞻已走满 20 日</b>的入场日后，
S 档 ≈62%、A 档 ≈60%、基线 ≈57%，超额明显收窄 —— <b>这是真实水平，之前那个数字不可用</b>。</div>
<div class="evi" style="margin-top:12px"><b>条件模块（先验固定）</b>：<br>
<b>Ⅰ 机构/私募增持（季度维度 Q2）</b>：私募 · 阳光私募 · 个人(牛散) · 公募 十大流通股东增持；<br>
<b>Ⅱ 融资融券 1/3/5 日净增仓（日频，东财全量序列 · T+1 公布口径）</b>：融资净买入占成交额 ≥2%/4%/4% 触发，
其中 <b>5 日占比</b>本次回测为 {m5_wr[1]:.1f}%（n={m5_wr[0]}）；<br>
<b>Ⅲ 日频事件</b>：大宗交易（折价加权）· 高管增持 · 席位异动。<br>
档位规则：<b>S 档</b> = 5日融资净买入占比≥4% 且 机构/私募增持；<b>A 档</b> = ≥3 信号共振且（M <b>或</b> I）；<b>B 档</b> = 2 信号观察仓。
退出纪律与主升/反转池一致：止损 −12% ／ 浮盈 +6% 激活、回撤 3% 跟踪 ／ 满 20 日强平。证据见 <a href='lab.html'>回测证据页（top25 口径）</a>。<br>
<span class="note">口径更正：早期版本把 A 档写成「≥3共振且（M 或 I）」却标注 59.4% ——
那个数字属于「M <b>且</b> I」的另一种写法。按<b>生产实际执行的规则</b>在<b>全候选域</b>上重算，
A 档胜率只有 {evd.get('A',{}).get('wr',0):.1f}%（n={evd.get('A',{}).get('n',0)}），低于同期候选域整体水平。</span></div>
{_ablate_block()}
{_hub_note(date)}</div>

<div class="card"><h2>分档出票许可（由显著性检验决定，不是人工挑选）</h2>
{ev_tbl or "<div class='note'>未读到分档显著性证据 → 一律不出票。</div>"}
<div class="evi" style="margin-top:10px">
判据沿用大盘环境门控的同一把尺子：<b>逐日平衡超额 &gt; 0 且 bootstrap 通过率 ≥ 95%</b> 才算达标，
否则宁可空仓。<b>本期可出票的档位：{emit_txt}。</b>
未达标的档仍照原规则列出（数据不隐藏），但<b>不作为买入依据</b>。
完整判定过程见 <a href='tier_gate.html'>分档规则显著性检验 tier_gate.html</a>。</div></div>

<div class="card"><h2>{'可执行档位' if emit else '本期无可执行标的'}（由显著性门槛决定）</h2>
{(("<div class='stkgrid'>%s</div>" % cards) if cards else
  "<div class='note'>本期<b>没有任何档位通过显著性门槛</b>，不出票。<br>"
  "触发明细仍完整列在下面的名单里（数据不隐藏，可自行跟踪），但本页不把它们当作已验证的买入信号。"
  "宁可不选，不乱选。</div>")}
</div>

<div class="card"><h2>完整名单（S + A + B 档）</h2>
<table><tr><th>#</th><th>名称</th><th>代码</th><th>档</th><th>共振数</th><th>5日融资占比</th><th>增仓分</th><th>触发信号</th></tr>{tbl}</table>
<div class="note">名单按规则照实列出（不隐藏数据）；只有带出票许可的档位才算买入依据 —— 本期<b>可出票：{emit_txt}</b>。B 档（2 信号）仅作观察仓；1 信号 ≈基线，不入选。</div></div>

<div class="card"><h2>历史归档（每日留档 · 事后结算）</h2>
<table><tr><th>数据日</th><th>候选域</th><th>S</th><th>A</th><th>B</th><th>已兑现 / 观察中</th><th>胜率</th></tr>{arc_rows}</table>
<div class="note">逐期留档 <code>combined_&#123;YYYYMMDD&#125;.html</code> ＋ 统计快照 <code>stat_&#123;YYYYMMDD&#125;.json</code>；
完整逐票明细见 <a href='history.html'>每日归档页</a>。结算口径与回测一致（移动止盈）。</div></div>

<div class="card"><h2>条件模块回测（入场 {win_txt} · 数据截至 {asof or '—'}）</h2>
<table><tr><th>模块组合</th><th>可测样本</th><th>胜率</th><th>均值收益</th></tr>{mod_rows}</table>
<div class="note" style="margin-top:8px">对照（随回测同步重算）：仅 M 无 I（n={m_no_i[0]}, {m_no_i[1]:.1f}%）／ 仅 I 无 M（n={i_no_m[0]}, {i_no_m[1]:.1f}%）—— 对照用于判断两模块是否真的互补，数值每日滚动。</div></div>

<div class="card"><h2>5日融资占比阈值敏感性（单调 = 先验阈值非拟合）</h2>
<table><tr><th>阈值</th><th>可测样本</th><th>胜率</th><th>均值收益</th></tr>{sens_rows}</table></div>

<div class="card"><h2>共识度曲线</h2>
<table><tr><th>共振门槛</th><th>可测样本</th><th>胜率</th><th>均值收益</th></tr>{cons_rows}</table></div>

<div class="rule"><b>⚠️ 数据覆盖与局限（务必阅读）</b><br>
· 多空增仓维度已升级为<b>东财全量融资融券日频序列</b>（T+1 公布口径，事件域 945 只逐只抓取），不再是稀疏快照近似；但 5 日占比阈值 {L.MARG_TH[5]*100:.0f}% 为先验设定，敏感性已验证方向稳定（单调）。<br>
· 私募/阳光私募/个人(牛散)/公募增持为 <b>2026Q2 季度维度</b>；阳光私募与一般私募/保险在股东名中难严格区分，事件可为 0。<br>
· S 档 20 日样本 n={s_v6[0]}，≥6% 占比档 n=34 更小；统计脆弱，须样本外持续验证，<b>退出纪律 &gt; 入场筛选</b>。<br>
· 高管增持覆盖 9-02 起；席位异动（龙虎榜）有断档日；大宗交易 20/20 日。<br>
· 归档页的「累计胜率」是<b>逐交易日入选后真实走出来的结果</b>，样本随日累积，短期不代表稳态。</div>
</div></body></html>"""
    p = os.path.join(OUT, f"combined_{date.replace('-', '')}.html")
    open(p, "w", encoding="utf-8").write(html)
    # 入口页只跟随「最新一期」：补跑/回填历史旧期时不把 index 倒退
    latest = max([h.get("date", "") for h in hist]) if hist else date
    if date >= latest:
        open(os.path.join(OUT, "index.html"), "w", encoding="utf-8").write(html)
    # 统计快照（供门户读取，与其它板块 stat_*.json 同构）
    snap_name = _stat_name(date)
    stat = {
        "date": date,
        "n_universe": universe_n,
        "nS": len(S), "nA": len(A), "nB": len(B),
        "model": "accum_v3",
        "hist_periods": summ["periods"],
        "hist_n": summ["n"],
        "hist_wr": summ["wr"],
        "lab_S_wr": round(s_v6[1], 1), "lab_S_n": s_v6[0],
        "lab_A_wr": round(v3[1], 1), "lab_A_n": v3[0],
    }
    json.dump(stat, open(snap_name, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    return p


def _stat_name(date):
    return os.path.join(OUT, "stat_%s.json" % date.replace("-", ""))


def run(date, K=None, hist=None, refresh=True):
    """跑一期：重算回测 → 入库 → 回填 → 出页（含 index/history）。返回 (date, rows, hist)。"""
    res = refresh_result() if refresh else load_result()
    date, rows, universe_n, K = scan(date)
    hist = load_hist() if hist is None else hist
    hist = upsert(hist, date, rows, universe_n, K)
    hist = settle(hist, K)
    save_hist(hist)
    nS = sum(1 for r in rows if r["tier"] == "S")
    nA = sum(1 for r in rows if r["tier"] == "A")
    nB = sum(1 for r in rows if r["tier"] == "B")
    print(f"[scan] {date} 候选 {len(rows)}/{universe_n}  S档={nS}  A档={nA}  B档={nB}")
    p = render(date, rows, universe_n, res, hist)
    hp = render_history(hist)
    print(f"[done] {p}  {hp}")
    return date, rows, K, hist


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    hist = load_hist()
    if "--all" in flags:
        # 回填全部历史期：回测只重算一次（同一份 K 末根 → 各期共用），后续期直接复用
        K = None
        first = True
        for h in sorted(hist, key=lambda x: x["date"]):
            _, _, K, hist = run(h["date"], K=K, hist=hist, refresh=first)
            first = False
        print(f"[all] 重生成 {len(hist)} 期")
        return
    if args:
        date = args[0]
    else:
        K0 = L.load_kline()
        date = L.trading_days(K0)[-1]
    run(date, hist=hist)


if __name__ == "__main__":
    main()
