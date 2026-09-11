# -*- coding: utf-8 -*-
"""统一顶部导航栏。

所有 A股看板页面共用，保证跳转入口与位置一致。
- topnav(): 生成 <div class='topnav'>，依赖 _theme.css 中的 .topnav 样式。
- selfcontained_nav(): 生成同样的 <div class='topnav'>，仅多带 UNIFIED_NAV 哨兵，
  供旧生成器调用；最终由 _apply_theme.py 统一注入主题并确保唯一。

链接采用「相对 web/ 根的规范路径」，按【当前页面所在子目录】动态计算相对链接，
因此无论页面在 web/<板块>/ 下哪一层，导航都能正确跳转。

目录约定（web/ 下按板块分层）：
  market/   大盘总览 + 游资看板 + 状态报告 + 连板周报
  lhb/      龙虎榜主看板 + 归档 + 入口页
  sector/   板块强度（每日 / 趋势 / 索引）
  exec/     高管增减持
  block/    大宗交易
  research/ 个股调研
  shareholder/ 行业最强榜
  psychology/ 群体心理风险雷达
  sections/ 版块总览
  docs/     操作手册
"""
from __future__ import annotations
import os

# 统一导航哨兵：selfcontained_nav 注入此注释，便于后续工具识别已统一处理。
NAV_SENTINEL = "<!-- UNIFIED_NAV -->"

# (标签, 相对 web/ 根的规范路径)
SECTIONS = [
    ("每日总览", "market/index.html"),
    ("龙虎榜分析", "lhb/lhb.html"),
    ("游资看板", "market/hotmoney.html"),
    ("板块强度", "sector/index.html"),
    ("高管增减持", "exec/index.html"),
    ("大宗交易", "block/index.html"),
    ("群体心理", "psychology/index.html"),
    ("个股调研", "research/index.html"),
    ("行业最强", "shareholder/2026-q2-industry-elite.html"),
    ("牛人追踪", "shareholder/tracker.html"),
    ("信号池", "picks/index.html"),
    ("做T池", "tplus/index.html"),
    ("版块总览", "sections/index.html"),
    ("数据中心", "db/index.html"),
]


def _rel(link_web_path: str, from_web_dir: str) -> str:
    """计算 link_web_path（相对 web/ 根）相对 from_web_dir（相对 web/ 根，可为空）的路径。"""
    target_dir = os.path.dirname(link_web_path)
    if from_web_dir in (None, "", "."):
        return link_web_path
    rel = os.path.relpath(target_dir, from_web_dir).replace(os.sep, "/")
    base = os.path.basename(link_web_path)
    return (rel + "/" + base) if rel != "." else base


def topnav(current_web_dir: str = "", home: str = "../../index.html", prefix: str = "",
           extra: tuple = ()) -> str:
    """生成标准 <div class='topnav'> 导航条。

    extra: 追加的「板块内横链」[(标签, 相对 web/ 根的规范路径), ...]，
    插在主导航之后、首页之前，用于串联同一板块下的多页链路。
    这些链接带 class='xlink'，调用方可自行加样式与主营导航区分。
    """
    items = "".join(
        f"<a href='{prefix}{_rel(p, current_web_dir)}'>{t}</a>" for t, p in SECTIONS)
    items += "".join(
        f"<a href='{prefix}{_rel(p, current_web_dir)}' class='xlink'>{t}</a>" for t, p in extra)
    items += f"<a href='{home}' class='home'>首页</a>"
    return f"<div class='topnav'>{items}</div>"


def selfcontained_nav(current_web_dir: str = "", home: str = "../../index.html", prefix: str = "",
                      extra: tuple = ()) -> str:
    """语义同 topnav()，仅多带 UNIFIED_NAV 哨兵，兼容旧生成器调用。
    实际样式由 _theme.css 统一提供，不再内联金色药丸。
    """
    return f"{NAV_SENTINEL}\n{topnav(current_web_dir, home, prefix, extra)}"
