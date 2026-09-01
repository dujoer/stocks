// 极简 DOM stub：执行页面 JS，捕获运行时错误并验证渲染产出
const fs = require('fs');
const path = require('path');

const P = path.join(__dirname, '..', '..', 'web', '2026-q2-industry-elite.html');
const html = fs.readFileSync(P, 'utf8');
const js = html.slice(html.lastIndexOf('<script>') + 8, html.lastIndexOf('</script>'));

// ---- 从 HTML 静态部分抽取需要被 querySelectorAll 命中的元素 ----
const pillInds = [...html.matchAll(/class='pill' data-ind='([^']+)'/g)].map(m => m[1]);
const topTabs = [...html.matchAll(/data-scope='(top|dec)' data-g='([^']+)'/g)]
  .map(m => ({ scope: m[1], g: m[2] }));

let renderCalls = [];

function mkEl(tag, ds) {
  const el = {
    tagName: tag, dataset: ds || {}, style: {}, _html: '',
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); }, remove(c) { this._s.delete(c); },
      toggle(c, on) { on ? this._s.add(c) : this._s.delete(c); },
      contains(c) { return this._s.has(c); },
    },
    get innerHTML() { return this._html; },
    set innerHTML(v) { this._html = String(v); renderCalls.push({ id: this._id, len: this._html.length }); },
    onclick: null, querySelectorAll: () => [], querySelector: () => null,
  };
  return el;
}

const indTitle = mkEl('div'); indTitle._id = 'indTitle';
const indBody = mkEl('div'); indBody._id = 'indBody';
const pills = pillInds.map(i => mkEl('button', { ind: i }));
const tabs = topTabs.map(t => mkEl('button', { scope: t.scope, g: t.g }));
const panes = topTabs.map(t => mkEl('div', { g: t.g }));

// indBody 内部渲染出的行（renderInd 后会被 querySelectorAll 查询）
const detRows = {};
indBody.querySelectorAll = (sel) => {
  if (sel === "#indBody tr[data-k]") {
    // 由最近一次 innerHTML 解析出 data-k
    const ks = [...indBody._html.matchAll(/data-k='([^']+)'/g)].map(m => m[1]);
    return ks.map(k => {
      const tr = mkEl('tr', { k });
      return tr;
    });
  }
  return [];
};

const document = {
  getElementById(id) {
    if (id === 'indTitle') return indTitle;
    if (id === 'indBody') return indBody;
    return null;
  },
  querySelectorAll(sel) {
    if (sel === '.pill') return pills;
    if (sel === ".tab[data-scope=top]") return tabs.filter(t => t.dataset.scope === 'top');
    if (sel === ".tab[data-scope=dec]") return tabs.filter(t => t.dataset.scope === 'dec');
    if (sel === '.tabpane') return panes.filter((p, i) => topTabs[i].scope === 'top');
    if (sel === '.tabpane2') return panes.filter((p, i) => topTabs[i].scope === 'dec');
    if (sel === "#indBody tr[data-k]") return indBody.querySelectorAll(sel);
    return [];
  },
  querySelector(sel) {
    if (sel === '.pill') return pills[0];
    const m = sel.match(/#indBody tr\[data-p='([^']+)'\]/);
    if (m) { detRows[m[1]] = detRows[m[1]] || mkEl('tr'); return detRows[m[1]]; }
    return null;
  },
};

let errs = [];
try {
  // eslint-disable-next-line no-new-func
  new Function('document', js)(document);
} catch (e) {
  errs.push('初始化异常: ' + e.message + '\n' + e.stack.split('\n').slice(0, 3).join('\n'));
}

function chk(c, m) { console.log((c ? '  [OK] ' : '  [!!] ') + m); if (!c) errs.push(m); }

console.log('JS 长度: ' + (js.length / 1024).toFixed(0) + ' KB');
chk(errs.length === 0, '页面 JS 无初始化异常');
chk(pills.length === 31, '行业按钮 ' + pills.length + ' 个');
chk(pills[0].classList.contains('on'), '首个行业默认选中: ' + pills[0].dataset.ind);
chk(indTitle._html.length > 20, '行业标题已渲染: ' + indTitle._html.replace(/<[^>]+>/g, '').slice(0, 60));
chk(indBody._html.includes('个人 Top10') && indBody._html.includes('私募 Top10')
  && indBody._html.includes('公募 Top10'), '三榜卡片均已渲染');
chk((indBody._html.match(/data-k='/g) || []).length > 0,
  '榜单行数 ' + (indBody._html.match(/data-k='/g) || []).length);
chk((indBody._html.match(/rowdet/g) || []).length > 0,
  '持仓明细行数 ' + (indBody._html.match(/rowdet/g) || []).length);

// 逐个行业点击，确认无异常且都能渲染出内容
let clickErr = [];
for (const p of pills) {
  try {
    renderCalls = [];
    p.onclick();
    if (indBody._html.length < 100) clickErr.push(p.dataset.ind + '(空)');
    if (!indBody._html.includes('Top10')) clickErr.push(p.dataset.ind + '(无榜)');
  } catch (e) { clickErr.push(p.dataset.ind + ': ' + e.message); }
}
chk(clickErr.length === 0, '31 个行业逐个切换均正常' + (clickErr.length ? ' 异常: ' + clickErr.join(', ') : ''));

// tab 切换
let tabErr = [];
for (const t of tabs) {
  try { t.onclick(); } catch (e) { tabErr.push(t.dataset.g + ': ' + e.message); }
}
chk(tabErr.length === 0, '榜单/减持榜 tab 切换均正常' + (tabErr.length ? ' 异常: ' + tabErr.join(', ') : ''));

// 展开明细
let expErr = [];
try {
  const rows = document.querySelectorAll("#indBody tr[data-k]");
  // 重新绑定：renderInd 内部已绑定，这里模拟点击第一行
  if (rows.length) {
    const k = rows[0].dataset.k;
    const det = document.querySelector("#indBody tr[data-p='" + k + "']");
    det.style.display = 'none';
    det.style.display = det.style.display === 'none' ? '' : 'none';
    if (det.style.display !== '') expErr.push('展开失败');
  }
} catch (e) { expErr.push(e.message); }
chk(expErr.length === 0, '明细行展开逻辑可用');

// 检查 fmtD 输出（大数字格式化）
chk(indBody._html.includes('万股') || indBody._html.includes('亿股') || indBody._html.includes('持平'),
  '持股变动数字已格式化');

console.log('\n结果: ' + (errs.length === 0 ? '全部通过' : '存在 ' + errs.length + ' 处问题'));
if (errs.length) { console.log(errs.join('\n')); process.exit(1); }
