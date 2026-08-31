# -*- coding: utf-8 -*-
"""从独立 JSON 生成可筛选/排序的交互式板块强度表。
数据源：quant/sector_strength_data.json（由 extract_sector_data.py 从原始内联 HTML 提取）。"""
import json, os

DATA_FILE = r'G:\ai\股票\quant\sector_strength_data.json'
OUT = r'G:\ai\股票\web\sector-strength-20260827.html'

with open(DATA_FILE, encoding='utf-8') as f:
    data = json.load(f)

DATE = '2026-08-27'
print('读取板块数:', len(data))

DATA_JSON = json.dumps(data, ensure_ascii=False)

HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>A股板块强度表 - __DATE__</title>
  <style>
    :root {
      --bg: #0d1117; --panel: #161b22; --border: #30363d;
      --text: #c9d1d9; --muted: #8b949e;
      --up: #d8392b; --down: #1a9e5a; --accent: #f0883e;
      --jc: #ff7b72; --xp: #79c0ff; --qz: #d2a8ff; --ch: #ffa657;
      --row-hover: rgba(240,136,62,0.06);
    }
    * { box-sizing: border-box; }
    body { margin:0; padding:24px; background:var(--bg); color:var(--text);
      font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; font-size:13px; }
    .container { max-width:1240px; margin:0 auto; }
    h1 { font-size:20px; margin:0 0 6px; color:#f0f6fc; }
    .subtitle { color:var(--muted); margin-bottom:16px; }
    .rule { background:var(--panel); border:1px solid var(--border); border-radius:8px;
      padding:12px 16px; margin-bottom:16px; line-height:1.8; }
    .rule strong { color:var(--accent); }
    .rule .tag { display:inline-block; padding:2px 8px; border-radius:4px;
      background:rgba(240,136,62,0.15); color:var(--accent); margin-right:6px; font-size:12px; }
    .toolbar { display:flex; flex-wrap:wrap; gap:10px; align-items:center;
      background:var(--panel); border:1px solid var(--border); border-radius:8px;
      padding:12px 14px; margin-bottom:14px; }
    .toolbar .grp { display:flex; align-items:center; gap:6px; }
    .toolbar label { color:var(--muted); font-size:12px; white-space:nowrap; }
    .toolbar input, .toolbar select {
      background:#0d1117; color:var(--text); border:1px solid var(--border);
      border-radius:6px; padding:6px 9px; font-size:13px; outline:none; }
    .toolbar input:focus, .toolbar select:focus { border-color:var(--accent); }
    .toolbar #search { min-width:180px; }
    .toolbar button {
      background:rgba(240,136,62,0.15); color:var(--accent); border:1px solid var(--accent);
      border-radius:6px; padding:6px 12px; font-size:13px; cursor:pointer; }
    .toolbar button:hover { background:rgba(240,136,62,0.28); }
    .toolbar .count { margin-left:auto; color:var(--muted); font-size:12px; }
    .toolbar .count b { color:var(--accent); }
    .tablewrap { background:var(--panel); border:1px solid var(--border); border-radius:8px; overflow:auto; max-height:74vh; }
    table { width:100%; border-collapse:collapse; }
    th, td { padding:8px 10px; text-align:right; border-bottom:1px solid var(--border); white-space:nowrap; }
    thead th { background:#21262d; color:#f0f6fc; font-weight:600; position:sticky; top:0; z-index:2;
      cursor:pointer; user-select:none; }
    thead th:hover { background:#2d333b; }
    thead th .arrow { color:var(--accent); font-size:11px; margin-left:3px; }
    thead th.nosort { cursor:default; }
    th:first-child, td:first-child, th:nth-child(2), td:nth-child(2) { text-align:left; }
    tr:hover { background:var(--row-hover); }
    .idx { color:var(--muted); width:42px; }
    .name { font-weight:500; }
    .kind { display:inline-block; margin-left:6px; padding:1px 5px; border-radius:3px;
      background:#30363d; color:var(--muted); font-size:11px; font-weight:normal; }
    .money { color:var(--text); }
    .up { color:var(--up); } .down { color:var(--down); }
    .strength { font-weight:700; position:relative; }
    .strength .bar { position:absolute; left:0; top:0; bottom:0; opacity:0.16; border-radius:0 3px 3px 0; pointer-events:none; }
    .strength .v { position:relative; z-index:1; }
    .behavior { font-weight:700; text-align:center; }
    .behavior.jc { color:var(--jc); } .behavior.xp { color:var(--xp); }
    .behavior.qz { color:var(--qz); } .behavior.ch { color:var(--ch); }
    .leader { color:var(--muted); font-size:12px; text-align:left; }
    .note { margin-top:12px; color:var(--muted); font-size:12px; }
    .empty { text-align:center; color:var(--muted); padding:40px; }
    @media (max-width:760px) {
      body { padding:12px; } table { font-size:12px; } th, td { padding:6px 5px; }
      .leader, th:nth-child(4), td:nth-child(4) { display:none; }
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>用暗盘资金数据 — 解读板块强弱</h1>
    <div class="subtitle">数据日期：__DATE__（收盘） | 数据来源：westock-mcp | 共 <span id="total">__TOTAL__</span> 个板块</div>

    <div class="rule">
      <span class="tag">计算公式</span>
      <strong>暗盘资金 = 主力资金 − 散户资金</strong>（即主力净流入）<br>
      <strong>板块强度 = 暗盘资金 ÷ 总成交额 × 100</strong><br>
      <span class="tag">主力行为</span>
      抢筹：强度 ≥ 3 &nbsp;|&nbsp; 建仓：1 &lt; 强度 &lt; 3 &nbsp;|&nbsp; 洗盘：−1 ≤ 强度 ≤ 1 &nbsp;|&nbsp; 出货：强度 &lt; −1
    </div>

    <div class="toolbar">
      <div class="grp">
        <label>搜索</label>
        <input id="search" type="text" placeholder="板块名 / 领涨股…" oninput="apply()">
      </div>
      <div class="grp">
        <label>类型</label>
        <select id="f-kind" onchange="apply()">
          <option value="all">全部</option>
          <option value="行业">行业</option>
          <option value="概念">概念</option>
        </select>
      </div>
      <div class="grp">
        <label>主力行为</label>
        <select id="f-behavior" onchange="apply()">
          <option value="all">全部</option>
          <option value="抢筹">抢筹</option>
          <option value="建仓">建仓</option>
          <option value="洗盘">洗盘</option>
          <option value="出货">出货</option>
        </select>
      </div>
      <div class="grp">
        <label>涨跌</label>
        <select id="f-dir" onchange="apply()">
          <option value="all">全部</option>
          <option value="up">上涨</option>
          <option value="down">下跌</option>
        </select>
      </div>
      <div class="grp">
        <label>强度区间</label>
        <select id="f-strength" onchange="apply()">
          <option value="all">全部</option>
          <option value="10">强度 ≥ 10</option>
          <option value="5">强度 ≥ 5</option>
          <option value="3">强度 ≥ 3（抢筹级）</option>
          <option value="n1">强度 &lt; −1（出货级）</option>
        </select>
      </div>
      <button onclick="resetAll()">重置</button>
      <button onclick="exportCsv()">导出CSV</button>
      <span class="count">当前显示 <b id="shown">0</b> / __TOTAL__</span>
    </div>

    <div class="tablewrap">
      <table>
        <thead>
          <tr>
            <th class="nosort">#</th>
            <th data-key="name">板块</th>
            <th data-key="pctVal" title="涨跌幅">涨幅</th>
            <th data-key="totalVal" title="总成交额">总成交额</th>
            <th data-key="mainVal" title="主力资金（净流入）">主力资金</th>
            <th data-key="retailVal" title="散户资金">散户资金</th>
            <th data-key="darkVal" title="暗盘资金 = 主力 − 散户">暗盘资金</th>
            <th data-key="strengthVal" title="板块强度 = 暗盘资金 ÷ 总成交额 × 100">板块强度</th>
            <th data-key="behaviorRank" title="抢筹≥3 / 建仓1~3 / 洗盘−1~1 / 出货<−1">主力行为</th>
            <th class="nosort">领涨股</th>
          </tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>

    <div class="note">点击表头可排序（再次点击切换升/降序）；组合筛选实时生效；导出CSV为当前筛选结果。</div>
  </div>

  <script>
    const DATA = __DATA_JSON__;
    const MAX_STRENGTH = Math.max.apply(null, DATA.map(d => Math.abs(d.strengthVal))) || 1;
    let sortKey = 'strengthVal', sortDir = 'desc';

    const behClass = { '抢筹':'qz', '建仓':'jc', '洗盘':'xp', '出货':'ch' };

    function esc(s){ return String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

    function getFiltered(){
      const q = document.getElementById('search').value.trim();
      const kind = document.getElementById('f-kind').value;
      const beh = document.getElementById('f-behavior').value;
      const dir = document.getElementById('f-dir').value;
      const str = document.getElementById('f-strength').value;
      return DATA.filter(d => {
        if (q && !(d.name.includes(q) || d.leader.includes(q))) return false;
        if (kind !== 'all' && d.kind !== kind) return false;
        if (beh !== 'all' && d.behavior !== beh) return false;
        if (dir === 'up' && d.pctVal < 0) return false;
        if (dir === 'down' && d.pctVal >= 0) return false;
        if (str === '10' && d.strengthVal < 10) return false;
        if (str === '3' && d.strengthVal < 3) return false;
        if (str === '5' && d.strengthVal < 5) return false;
        if (str === 'n1' && d.strengthVal >= -1) return false;
        return true;
      });
    }

    function sortRows(rows){
      const dir = sortDir === 'asc' ? 1 : -1;
      return rows.sort((a, b) => {
        let av = a[sortKey], bv = b[sortKey];
        if (typeof av === 'string'){ return av.localeCompare(bv, 'zh') * dir; }
        return (av - bv) * dir;
      });
    }

    function render(){
      let rows = getFiltered();
      rows = sortRows(rows);
      const tb = document.getElementById('tbody');
      if (!rows.length){ tb.innerHTML = '<tr><td colspan="10" class="empty">无匹配结果</td></tr>'; }
      else {
        tb.innerHTML = rows.map((d, i) => {
          const barW = Math.min(Math.abs(d.strengthVal) / MAX_STRENGTH * 100, 100);
          const barColor = d.strengthVal >= 0 ? 'var(--up)' : 'var(--down)';
          const darkCls = d.darkUp ? 'up' : 'down';
          const pctCls = d.pctVal >= 0 ? 'up' : 'down';
          const strCls = d.strengthVal >= 0 ? 'up' : 'down';
          return '<tr>' +
            '<td class="idx">' + (i+1) + '</td>' +
            '<td class="name">' + esc(d.name) + '<span class="kind">' + esc(d.kind) + '</span></td>' +
            '<td class="pct ' + pctCls + '">' + esc(d.pctText) + '</td>' +
            '<td class="money">' + esc(d.totalText) + '</td>' +
            '<td class="money">' + esc(d.mainText) + '</td>' +
            '<td class="money">' + esc(d.retailText) + '</td>' +
            '<td class="money ' + darkCls + '">' + esc(d.darkText) + '</td>' +
            '<td class="strength ' + strCls + '"><span class="bar" style="width:' + barW + '%;background:' + barColor + '"></span><span class="v">' + esc(d.strengthText) + '</span></td>' +
            '<td class="behavior ' + (behClass[d.behavior]||'') + '">' + esc(d.behavior) + '</td>' +
            '<td class="leader">' + esc(d.leader) + '</td>' +
          '</tr>';
        }).join('');
      }
      document.getElementById('shown').textContent = rows.length;
      updateArrows();
    }

    function updateArrows(){
      document.querySelectorAll('thead th[data-key]').forEach(th => {
        const base = th.textContent.replace(/[▲▼]/g, '').trim();
        if (th.dataset.key === sortKey){
          th.innerHTML = base + ' <span class="arrow">' + (sortDir === 'asc' ? '▲' : '▼') + '</span>';
        } else {
          th.innerHTML = base;
        }
      });
    }

    function apply(){ render(); }

    function resetAll(){
      document.getElementById('search').value = '';
      document.getElementById('f-kind').value = 'all';
      document.getElementById('f-behavior').value = 'all';
      document.getElementById('f-dir').value = 'all';
      document.getElementById('f-strength').value = 'all';
      sortKey = 'strengthVal'; sortDir = 'desc';
      render();
    }

    function exportCsv(){
      const rows = sortRows(getFiltered());
      const head = ['板块','类型','涨幅','总成交额','主力资金','散户资金','暗盘资金','板块强度','主力行为','领涨股'];
      const lines = [head.join(',')];
      rows.forEach(d => lines.push([d.name, d.kind, d.pctText, d.totalText, d.mainText, d.retailText, d.darkText, d.strengthText, d.behavior, d.leader].map(v => '"'+String(v).replace(/"/g,'""')+'"').join(',')));
      const blob = new Blob(['\\uFEFF'+lines.join('\\n')], {type:'text/csv;charset=utf-8'});
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = '板块强度_' + '__DATE__' + '.csv';
      a.click();
    }

    document.querySelectorAll('thead th[data-key]').forEach(th => {
      th.addEventListener('click', () => {
        const k = th.dataset.key;
        if (sortKey === k){ sortDir = sortDir === 'asc' ? 'desc' : 'asc'; }
        else { sortKey = k; sortDir = (k === 'name') ? 'asc' : 'desc'; }
        render();
      });
    });

    render();
  </script>
</body>
</html>
"""

HTML = (HTML
        .replace('__DATE__', DATE)
        .replace('__TOTAL__', str(len(data)))
        .replace('__DATA_JSON__', DATA_JSON))

with open(OUT, 'w', encoding='utf-8') as f:
    f.write(HTML)
print('已生成:', OUT, '大小(KB):', round(os.path.getsize(OUT)/1024, 1))
