# -*- coding: utf-8 -*-
"""个股 → 东方财富详情页链接（共享工具）。

用途：任何渲染个股名称的地方，统一走这里生成外链，避免各生成器各写一套。

  from _emlink import em_url, link, esc
  link("sz000049", "德赛电池")   ->  <a class="emlk" href="https://quote.eastmoney.com/sz000049.html" ...>德赛电池</a>

链接形态（东财标准个股页）：
  https://quote.eastmoney.com/sz000049.html
  https://quote.eastmoney.com/sh600519.html
  https://quote.eastmoney.com/bj430047.html
"""
import os
import re
import json

EM_BASE = "https://quote.eastmoney.com"

_HERE = os.path.dirname(os.path.abspath(__file__))
NAME_FILE = os.path.join(_HERE, "_stock_names.json")

_PREF = ("sh", "sz", "bj")

# 代码 → 交易所前缀（无前缀时按号段推断）
_SH_PREFIX = ("6", "9")          # 沪市主板 / 科创板 / B股
_SZ_PREFIX = ("0", "3")          # 深市主板 / 创业板
_BJ_PREFIX = ("4", "8")          # 北交所 / 新三板


def norm_code(code):
    """把各种写法归一化为「带前缀的小写代码」。

    支持：sz000049 / 000049 / 000049.SZ / SZ000049 / 000049.sz
    无法识别时返回 None。
    """
    if code is None:
        return None
    s = str(code).strip()
    if not s:
        return None
    s = s.replace(" ", "")
    # 600519.SH / 000049.sz 形式
    m = re.match(r"^(\d{6})[.\-_]?(sh|sz|bj)$", s, re.I)
    if m:
        return m.group(2).lower() + m.group(1)
    # hk00700 / us 等形式：保持原样交由调用方判断
    m = re.match(r"^(sh|sz|bj)(\d{6})$", s, re.I)
    if m:
        return m.group(1).lower() + m.group(2)
    m = re.match(r"^(\d{6})$", s)
    if m:
        num = m.group(1)
        if num[0] in _SH_PREFIX:
            return "sh" + num
        if num[0] in _SZ_PREFIX:
            return "sz" + num
        if num[0] in _BJ_PREFIX:
            return "bj" + num
        return "sz" + num
    return None


def em_url(code):
    """代码 → 东方财富个股页 URL；无法识别返回 None（调用方降级为纯文本）。"""
    c = norm_code(code)
    if not c:
        return None
    return "%s/%s.html" % (EM_BASE, c)


def esc(s):
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def link(code, name=None, cls="emlk", title=None, raw=False):
    """渲染个股名称外链。code 不可识别时退化为纯文本。

    raw=True 时 name 视为已转义（调用方自行 esc），避免二次转义。
    """
    txt = (name if raw else esc(name if name is not None else code))
    if not txt:
        txt = esc(code)
    url = em_url(code)
    if not url:
        return txt
    t = ' title="%s"' % esc(title) if title else ""
    c = ' class="%s"' % esc(cls) if cls else ""
    return ('<a%s href="%s" target="_blank" rel="noopener noreferrer"%s>%s</a>'
            % (c, url, t, txt))


# ---------------- 名称 → 代码 表 ----------------
_CACHE = {"map": None, "rev": None}


def load_names(path=None):
    """读 quant/_stock_names.json -> {带前缀代码: 名称}（缺文件返回 {}）。"""
    p = path or NAME_FILE
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def name_aliases(nm):
    """一个名称的等价写法（页面里常见的简称/全角/含空格/带特别处理前缀）。

    数据源的名称偶尔带「XD/XR/DR」除权前缀、全角字母、内部空格，或科创板的
    「-W/-U/-UW」特别处理后缀；页面正文里往往写成干净的简称。
    """
    if not nm:
        return []
    out = [nm]
    s = nm.replace(" ", "").replace("\u3000", "")
    if s != nm:
        out.append(s)
    # 全角字母 → 半角
    half = s.translate({0xFF21 + i: 0x41 + i for i in range(26)})
    if half != s:
        out.append(half)
        s = half
    # 特别处理后缀 -W / -U / -UW / -WD
    m = re.match(r"^(.*?)[-－](U|W|UW|WD|D)$", s)
    if m and len(m.group(1)) >= 3:
        out.append(m.group(1))
    # 除权前缀
    m = re.match(r"^(XD|XR|DR)(.{3,})$", s)
    if m:
        out.append(m.group(2))
    return out


def name_map(path=None):
    """返回 (name2code, code2name)。名称唯一时才可安全反查。"""
    if _CACHE["map"] is None:
        c2n = load_names(path)
        n2c = {}
        dup = set()
        for code, nm in c2n.items():
            if not nm:
                continue
            for alias in name_aliases(nm):
                if len(alias) < 3:
                    continue
                if alias in n2c and n2c[alias] != code:
                    dup.add(alias)       # 同名不同码 → 放弃反查，避免链错
                else:
                    n2c[alias] = code
        for nm in dup:
            n2c.pop(nm, None)
        _CACHE["map"] = n2c
        _CACHE["rev"] = c2n
    return _CACHE["map"], _CACHE["rev"]


def refresh_names(codes=None, batch=80, quiet=False):
    """用腾讯快照重建/增量更新名称表。codes 为空则取全市场码表。"""
    import _tx_fetch as T                                      # 延迟导入，避免循环依赖
    if codes is None:
        p = os.path.join(_HERE, "q2_full", "_code2industry.json")
        try:
            codes = list(json.load(open(p, encoding="utf-8")).keys())
        except Exception:
            codes = []
    old = load_names()
    q = T.fetch_qt(codes, batch=batch)
    for c, v in q.items():
        if v.get("name"):
            old[c] = v["name"]
    json.dump(old, open(NAME_FILE, "w", encoding="utf-8"), ensure_ascii=False)
    _CACHE["map"] = None
    if not quiet:
        print("[_emlink] 名称表已更新：%d 条" % len(old))
    return old


if __name__ == "__main__":
    import sys
    if "--refresh" in sys.argv:
        # 重建全市场名称表（腾讯离线快照，约 20 秒）
        refresh_names()
        sys.exit(0)
    for a in (sys.argv[1:] or ["sz000049", "600519", "430047", "000049.SZ"]):
        print("%-12s -> %s" % (a, em_url(a)))
    m, c = name_map()
    print("名称表 %d 条（可反查 %d）" % (len(c), len(m)))
