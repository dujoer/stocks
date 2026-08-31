
  var I18N = {
    zh:{
      t_kicker:"A股 · 群体行为金融研判",
      t_title:"群体心理风险雷达 · 日报索引",
      t_sub:"行为金融偏差 · 拥挤度 · 融资 · 热度 — 综合风险雷达系列。基于 westock 官方行情数据的真实查询结果，按交易日逐期归档。",
      t_updated:"最近更新：2026-08-25（收录 08-17 ~ 08-25 共 7 期，08-22~08-23 周末休市）",
      s_issues:"期", s_issues_lbl:"已归档日报（每日独立保留）",
      s_all:"全部", s_risk_lbl:"各期风险等级（7 期同为「高」）",
      s_span_lbl:"覆盖交易日跨度（08-22~08-23 周末休市；最新 08-25）",
      t_trend:"涨股比走势（市场广度）", t_trend_note:"08-19 广度崩至 8%（恐慌/踩踏），08-20 修复至 73%，08-21 反弹后分化回落至 45%，08-24 放量普跌广度再崩至 26%，08-25 缩量普涨广度暴拉回 76%（官方「狂热」标签与真实广度共振向上，但量缩、技术极弱 = 低质量反弹）。08-22~08-23 周末休市无交易；08-25 为最新一期。全线 7 期风险等级均为「高」。",
      t_traj:"情绪周期轨迹（六阶段定位）", t_traj_note:"六阶段框架：绝望 → 怀疑 → 乐观 → 狂热 → 焦虑 → 自满。本序列由 08-17「狂热」经分歧、恐慌，08-21 回落至「怀疑（分歧加剧）」，08-24 转入「恐慌 / 退潮」（广度崩塌），08-25 由恐慌回「修复 / 分歧（弱反弹）」（缩量普涨、广度回暖至 76%，但量缩、技术极弱）。08-22~08-23 周末休市。",
      t_reports:"每日风险雷达", t_source:"数据来源与口径",
      src_mcp:"行情数据源", src_real:"真实性约束", src_gap:"口径缺口", src_cycle:"分析框架",
      t_disclaimer_t:"免责声明：", t_disclaimer:"本报告基于公开市场数据的行为金融视角研判，仅供研究与学习参考，不构成任何投资建议或买卖要约。市场有风险，决策须独立，盈亏自负。报告中的情绪周期定位、认知偏差与风险等级为主观框架下的观察结论，可能随数据更新而调整。",
      t_foot:"群体心理风险雷达 · A股日报索引 · 单文件离线版 · 0 外部引用",
      c_upratio:"涨股比", c_limitup:"涨停", c_board:"连板", c_turn:"成交",
      view:"查看完整报告 →"
    },
    en:{
      t_kicker:"A-Share · Behavioral Finance",
      t_title:"Crowd Psychology Risk Radar · Index",
      t_sub:"Behavioral bias · Crowding · Margin · Heat — a serial risk radar. Real queries from westock official market data, archived per trading day.",
      t_updated:"Last updated: 2026-08-25 (7 issues, 08-17 ~ 08-25; 08-22/23 weekend closed)",
      s_issues:"issues", s_issues_lbl:"Archived daily reports (each day preserved)",
      s_all:"all", s_risk_lbl:"Risk level per issue (all 7 = High)",
      s_span_lbl:"Trading-day coverage span (08-22/23 weekend closed; latest 08-25)",
      t_trend:"Up-Stock Ratio Trend (Breadth)", t_trend_note:"Breadth collapsed to 8% on 08-19 (panic), rebounded to 73% on 08-20, fell to 45% on 08-21, collapsed again to 26% on 08-24 amid broad sell-off, then roared back to 76% on 08-25 in a volume-shrinking rally (official 'Euphoria' tag now aligns upward with real breadth, yet volume-down & technics weak = low-quality bounce). 08-22/23 weekend closed; 08-25 is the latest issue. All 7 issues rated High risk.",
      t_traj:"Sentiment Cycle Path (6-stage)", t_traj_note:"Six-stage frame: Despair → Doubt → Optimism → Euphoria → Anxiety → Complacency. Path runs from 08-17 Euphoria through divergence & panic, to Doubt (divergence intensifying) on 08-21, into Panic / Washout (breadth collapse) on 08-24, then 08-25 shifts from panic back to Repair / Divergence (weak bounce) — volume-shrinking rally, breadth recovers to 76%, yet volume-down & technics weak. 08-22/23 weekend closed.",
      t_reports:"Daily Risk Radars", t_source:"Sources & Notes",
      src_mcp:"Market data", src_real:"Authenticity", src_gap:"Coverage gaps", src_cycle:"Framework",
      t_disclaimer_t:"Disclaimer: ", t_disclaimer:"This report is a behavioral-finance read on public market data for research and study only — not investment advice or an offer. Markets carry risk; decide independently and own the outcome. Sentiment positioning, biases and risk grades are subjective observations under a fixed framework and may shift with new data.",
      t_foot:"Crowd Psychology Risk Radar · A-Share Index · single-file offline · 0 external refs",
      c_upratio:"Up-ratio", c_limitup:"Limit-up", c_board:"Board", c_turn:"Turnover",
      view:"View full report →"
    }
  };

  var REPORTS = [
    {
      file:"crowd-psychology-risk-radar-20260817.html", date:"2026-08-17",
      risk:"高", riskEn:"High",
      cycleZh:"狂热", cycleEn:"Euphoria",
      cycleNoteZh:"情绪狂热 + 估值高估象限", cycleNoteEn:"Euphoria + overvaluation quadrant",
      up:"78%", limitup:"110", board:"4板", turn:"¥2.39万亿",
      summaryZh:"涨股比78%、涨停110、连板4板，两融周增触发狂热阈值；PMI 49.2 等基本面未跟上，逼近反身性末端高危区，下行风险大于上行弹性。",
      summaryEn:"Up-ratio 78%, 110 limit-up, 4-board; margin surge triggers euphoria threshold. Fundamentals (PMI 49.2) lag — near reflexivity-end danger zone, downside > upside."
    },
    {
      file:"crowd-psychology-risk-radar-20260818.html", date:"2026-08-18",
      risk:"高", riskEn:"High",
      cycleZh:"狂热末端 + 分歧", cycleEn:"Euphoria end + Divergence",
      cycleNoteZh:"狂热→分歧降温", cycleNoteEn:"Cooling from euphoria to divergence",
      up:"38%", limitup:"81", board:"4板", turn:"¥2.40万亿",
      summaryZh:"涨股比骤降至38%、涨停81、跌停1→6；资金由AI硬件高低切至农业/消费，杠杆仍加仓AI而价格松动，杠杆-价格背离放大尾部风险。",
      summaryEn:"Up-ratio plunges to 38%, 81 limit-up, limit-down 1→6; funds rotate from AI hardware to agriculture/consumer; margin still adds AI while price softens — divergence amplifies tail risk."
    },
    {
      file:"crowd-psychology-risk-radar-20260819.html", date:"2026-08-19",
      risk:"高", riskEn:"High",
      cycleZh:"焦虑 / 恐慌", cycleEn:"Anxiety / Panic",
      cycleNoteZh:"踩踏式退潮", cycleNoteEn:"Cascading sell-off",
      up:"8%", limitup:"38", board:"3板", turn:"¥2.51万亿",
      summaryZh:"涨股比崩至8%、涨停38、跌停130；创业板−6.26%，AI硬件踩踏出清；融资逆势加仓AI而价格暴跌，强平/多杀多风险积聚。",
      summaryEn:"Up-ratio collapses to 8%, 38 limit-up, 130 limit-down; ChiNext −6.26%, AI hardware cascades; margin still buys AI into price crash — forced-liquidation risk builds."
    },
    {
      file:"crowd-psychology-risk-radar-20260820.html", date:"2026-08-20",
      risk:"高", riskEn:"High",
      cycleZh:"怀疑（修复中）", cycleEn:"Doubt (recovering)",
      cycleNoteZh:"超跌反弹", cycleNoteEn:"Oversold rebound",
      up:"73%", limitup:"84", board:"4板", turn:"¥2.08万亿",
      summaryZh:"涨股比修复至73%、涨停84、跌停13；但指数仅小幅回升、成交缩至¥2.08万亿；杠杆由AI切向新能源/资源/卫星，去风险信号。",
      summaryEn:"Up-ratio recovers to 73%, 84 limit-up, 13 limit-down; indices only modestly up, turnover shrinks to ¥2.08tn; margin rotates from AI to new-energy/resources — de-risking signal."
    },
    {
      file:"crowd-psychology-risk-radar-20260821.html", date:"2026-08-21",
      risk:"高", riskEn:"High",
      cycleZh:"怀疑（分歧加剧）", cycleEn:"Doubt (divergence intensifying)",
      cycleNoteZh:"反弹后分化 / 轮动", cycleNoteEn:"Post-rebound divergence / rotation",
      up:"45%", limitup:"58", board:"3板", turn:"¥1.879万亿",
      summaryZh:"涨股比回落至45%、涨停58、跌停15、成交缩至¥1.879万亿；医药全面退潮，资金切贵金属/资源/硬件；官方「狂热」标签与真实广度背离=诱多陷阱。",
      summaryEn:"Up-ratio falls to 45%, 58 limit-up, 15 limit-down, turnover ¥1.879tn; pharma rolls over, funds rotate to precious metals/resources/hardware; official 'euphoria' tag diverges from real breadth = bait trap."
    }
    ,
    {
      file:"crowd-psychology-risk-radar-20260824.html", date:"2026-08-24",
      risk:"高", riskEn:"High",
      cycleZh:"恐慌 / 退潮", cycleEn:"Panic / Washout",
      cycleNoteZh:"广度崩塌", cycleNoteEn:"Breadth collapse",
      up:"26%", limitup:"48", board:"4板", turn:"¥2.007万亿",
      summaryZh:"涨股比崩塌至26%、涨停48、跌停14、成交放量至¥2.007万亿（+1282亿）；科技硬件开盘即兑现，资金切低位防御+贵金属；官方「中性」标签与真实26%广度背离=广度崩塌。",
      summaryEn:"Up-ratio collapses to 26%, 48 limit-up, 14 limit-down, turnover expands to ¥2.007tn (+128.2bn); tech sold at open, funds rotate to low-level defensives + precious metals; official 'Neutral' tag diverges from real 26% breadth = breadth collapse."
    }
    ,
    {
      file:"crowd-psychology-risk-radar-20260825.html", date:"2026-08-25",
      risk:"高", riskEn:"High",
      cycleZh:"修复 / 分歧（弱反弹）", cycleEn:"Repair / Divergence (weak bounce)",
      cycleNoteZh:"缩量普涨 / 低质量反弹", cycleNoteEn:"Volume-shrinking rally / low-quality bounce",
      up:"76%", limitup:"70", board:"5板", turn:"¥1.8318万亿",
      summaryZh:"涨股比暴拉至76%、涨停70、跌停4、成交缩至¥1.8318万亿（−1756亿）；官方「狂热」标签与真实76%广度共振向上，但量缩、小盘占优、技术极弱、估值偏高 = 缩量普涨 / 低质量反弹。",
      summaryEn:"Up-ratio roars to 76%, 70 limit-up, 4 limit-down, turnover shrinks to ¥1.8318tn (−175.6bn); official 'Euphoria' tag aligns upward with real 76% breadth, yet volume-down, small-cap led, technics weak, valuation high = volume-shrinking rally / low-quality bounce."
    }
  ];

  var HOLIDAYS = [
    {date:"2026-08-22", cycleZh:"周末休市", cycleEn:"Weekend closed", noteZh:"周六 · 无交易", noteEn:"Sat · no trading"},
    {date:"2026-08-23", cycleZh:"周末休市", cycleEn:"Weekend closed", noteZh:"周日 · 无交易", noteEn:"Sun · no trading"}
  ];
  var TRAJ = REPORTS.concat(HOLIDAYS).sort(function(a,b){ return a.date < b.date ? -1 : 1; });

  function chip(label, val){
    return '<span class="rchip"><i>'+label+'</i><b>'+val+'</b></span>';
  }

  function renderReports(lang){
    var box = document.getElementById('reports');
    box.innerHTML = REPORTS.map(function(r){
      var rc = (r.risk==='高')?'rhi':((r.risk==='中')?'rmid':'rlo');
      return ''+
      '<a class="rcard" href="'+r.file+'">'+
        '<div class="rhead">'+
          '<span class="rdate">'+r.date+'</span>'+
          '<span class="rbadge '+rc+'">'+(lang==='en'?r.riskEn:r.risk)+'</span>'+
        '</div>'+
        '<div class="rcycle">'+(lang==='en'?r.cycleEn:r.cycleZh)+
          '<span class="rnote">'+(lang==='en'?r.cycleNoteEn:r.cycleNoteZh)+'</span></div>'+
        '<div class="rchips">'+
          chip(I18N[lang].c_upratio, r.up)+
          chip(I18N[lang].c_limitup, r.limitup)+
          chip(I18N[lang].c_board, r.board)+
          chip(I18N[lang].c_turn, r.turn)+
        '</div>'+
        '<p class="rsum">'+(lang==='en'?r.summaryEn:r.summaryZh)+'</p>'+
        '<span class="rgo">'+I18N[lang].view+'</span>'+
      '</a>';
    }).join('');
  }

  function renderTraj(lang){
    var box = document.getElementById('traj');
    box.innerHTML = TRAJ.map(function(r){
      var isHoliday = !!r.noteZh;
      var note = lang==='en' ? (r.cycleNoteEn || r.noteEn) : (r.cycleNoteZh || r.noteZh);
      return '<div class="t'+(isHoliday?' holiday':'')+'">'+
        '<div class="d">'+r.date+'</div>'+
        '<div class="e">'+(lang==='en'?r.cycleEn:r.cycleZh)+'</div>'+
        '<div class="n">'+note+'</div>'+
      '</div>';
    }).join('');
  }

  function applyLang(lang){
    document.documentElement.lang = (lang==='en'?'en':'zh-CN');
    document.querySelectorAll('[data-i18n]').forEach(function(el){
      var key = el.getAttribute('data-i18n');
      if(I18N[lang][key]!=null) el.innerHTML = I18N[lang][key];
    });
    document.getElementById('btnZh').classList.toggle('active', lang==='zh');
    document.getElementById('btnEn').classList.toggle('active', lang==='en');
    renderTraj(lang);
    renderReports(lang);
    try{ history.replaceState(null,'', lang==='en'?'?lang=en':'?lang=zh'); }catch(e){}
  }

  function setLang(lang){ applyLang(lang); }

  (function(){
    var p = null;
    try{ p = new URLSearchParams(location.search).get('lang'); }catch(e){}
    applyLang((p==='en')?'en':'zh');
  })();
