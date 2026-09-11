/* ============================================================
   通用交互 (A股看板) — 由 _apply_theme.py 注入每个页面。
   功能：① 当前页导航高亮 ② 带 data-wb 的列表表可点表头排序
        ③ 每表上方搜索框做全表筛选。
   对已有自备排序脚本的表(th.sort 且非 data-wb)不接管，避免重复绑定。
   ============================================================ */
(function () {
  "use strict";

  /* ① 当前页导航高亮 —— 保证「有且仅有一项」被点亮
     先按「web/ 相对路径」精确匹配（避免同名 index.html 误点亮多个），
     再依次降级：前缀归属（归档/明细子页）→ 同目录首页 → 同目录唯一项。
     导航链接是相对路径，须经 a.href 解析成绝对 URL 再比较。 */
  try {
    function pageKey(pathname) {
      var p = String(pathname || "").replace(/\.html$/i, "");
      var i = p.indexOf("/web/");
      if (i > -1) return p.slice(i + 1);    // "web/sector/index"
      return p.replace(/^.*\//, "");        // 仓库根 index.html -> "index"
    }
    function keyOf(href) {
      var cut = String(href || "").split("#")[0];
      var q = cut.indexOf("?");
      var search = q > -1 ? cut.slice(q).toLowerCase() : "";
      var p = q > -1 ? cut.slice(0, q) : cut;
      try { p = new URL(p, location.href).pathname; } catch (e) {}
      return { key: pageKey(p), search: search };
    }
    function dirOf(k) { return k.replace(/\/[^\/]*$/, ""); }

    var curKey = pageKey(location.pathname);
    var curSearch = (location.search || "").toLowerCase();
    var entries = [];
    document.querySelectorAll(".topnav a, nav a, .wb-nav a").forEach(function (a) {
      var h = a.getAttribute("href") || "";
      if (!h || h === "#" || h.indexOf("javascript:") === 0) return;
      var info = keyOf(a.href || h);
      if (!info.key) return;
      if (curSearch && !info.search) return;
      if (info.search && curSearch.indexOf(info.search) < 0) return;
      entries.push({ a: a, key: info.key });
    });

    /* 1) 精确命中 */
    var picked = entries.filter(function (e) { return e.key === curKey; });

    /* 2) 前缀归属：归档/明细子页点亮其所属板块主项（取最长匹配） */
    if (!picked.length) {
      var pre = entries.filter(function (e) { return curKey.indexOf(e.key) === 0; });
      if (pre.length) {
        pre.sort(function (x, y) { return y.key.length - x.key.length; });
        picked = [pre[0]];
      }
    }

    /* 3) 同目录：唯一项直接命中；多候选时只取目录首页(index) */
    if (!picked.length) {
      var cd = dirOf(curKey), uniq = {};
      entries.forEach(function (e) { if (dirOf(e.key) === cd) uniq[e.key] = e; });
      var ks = Object.keys(uniq);
      if (ks.length === 1) {
        picked = [uniq[ks[0]]];
      } else if (ks.length > 1) {
        var idx = ks.filter(function (k) { return /\/index$/.test(k); });
        if (idx.length === 1) picked = [uniq[idx[0]]];
      }
    }

    picked.forEach(function (e) { e.a.classList.add("cur"); });
  } catch (e) {}

  /* 工具：判断单元格是否为数值 */
  function isNum(s) {
    if (s == null) return false;
    s = String(s).replace(/[,\s%]/g, "");
    if (s === "" || s === "—" || s === "-") return false;
    return !isNaN(parseFloat(s)) && isFinite(parseFloat(s));
  }
  function cellText(tr, ci) {
    var c = tr.children[ci];
    if (!c) return "";
    if (c.dataset && c.dataset.val !== undefined) return c.dataset.val;
    return c.textContent || "";
  }

  /* ②+③ 列表表排序 + 筛选 */
  document.querySelectorAll("table[data-wb]").forEach(function (tbl) {
    var thead = tbl.querySelector("thead");
    if (!thead) return;
    var ths = thead.querySelectorAll("th");
    if (ths.length < 1) return;

    /* 搜索框 */
    try {
      var box = document.createElement("input");
      box.type = "search";
      box.className = "wb-search";
      box.placeholder = "筛选本表（输入关键字，支持跨列）…";
      box.setAttribute("aria-label", "筛选表格");
      tbl.parentNode.insertBefore(box, tbl);
      box.addEventListener("input", function () {
        var q = box.value.trim().toLowerCase();
        var rows = tbl.querySelectorAll("tbody tr");
        var shown = 0;
        rows.forEach(function (tr) {
          var hit = !q || tr.textContent.toLowerCase().indexOf(q) >= 0;
          tr.style.display = hit ? "" : "none";
          if (hit) shown++;
        });
        var old = tbl.parentNode.querySelector(".wb-empty");
        if (old) old.parentNode.removeChild(old);
        if (q && shown === 0) {
          var tip = document.createElement("div");
          tip.className = "wb-empty";
          tip.textContent = "无匹配结果";
          tbl.parentNode.insertBefore(tip, tbl.nextSibling);
        }
      });
    } catch (e) {}

    /* 排序：列级数值自动识别 */
    ths.forEach(function (th, ci) {
      if (th.dataset && th.dataset.noSort !== undefined) return;
      th.style.cursor = "pointer";
      th.classList.add("sort");
      th.addEventListener("click", function () {
        var numeric = th.classList.contains("num");
        if (!numeric) {
          var sample = tbl.querySelectorAll("tbody tr");
          var nN = 0, nT = 0;
          sample.forEach(function (r) {
            if (r.children[ci]) { nT++; if (isNum(cellText(r, ci))) nN++; }
          });
          numeric = nT > 0 && nN / nT >= 0.7;
        }
        var asc = th.dataset.asc !== "1";
        var rows = [].slice.call(tbl.querySelectorAll("tbody tr"));
        rows.sort(function (a, b) {
          var va = cellText(a, ci), vb = cellText(b, ci);
          if (numeric) {
            var fa = parseFloat(String(va).replace(/[,\s%]/g, "")) || 0;
            var fb = parseFloat(String(vb).replace(/[,\s%]/g, "")) || 0;
            return asc ? fa - fb : fb - fa;
          }
          va = String(va || ""); vb = String(vb || "");
          return asc ? va.localeCompare(vb, "zh") : vb.localeCompare(va, "zh");
        });
        var tb = tbl.querySelector("tbody");
        rows.forEach(function (r) { tb.appendChild(r); });
        ths.forEach(function (x) { x.classList.remove("sorted"); x.removeAttribute("data-asc"); });
        th.classList.add("sorted");
        th.dataset.asc = asc ? "1" : "0";
      });
    });
  });
})();
