# -*- coding: utf-8 -*-
"""统一顶部导航栏。

所有 A股看板页面共用，保证跳转入口与位置一致，且都带「返回主页」。
- topnav(): 依赖各生成器已定义的 .topnav CSS（build_dashboards / build_block / build_exec / build_sections 等）。
- selfcontained_nav(): 自带内联样式，用于未定义 .topnav CSS 的页面（板块强度 / 心理雷达 / 行业最强榜等）。

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

# 统一导航哨兵：selfcontained_nav 注入此注释，_apply_nav 借此做到幂等 + 自愈（不重复注入）。
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
    ("版块总览", "sections/index.html"),
]


def _rel(link_web_path: str, from_web_dir: str) -> str:
    """计算 link_web_path（相对 web/ 根）相对 from_web_dir（相对 web/ 根，可为空）的路径。"""
    target_dir = os.path.dirname(link_web_path)
    if from_web_dir in (None, "", "."):
        return link_web_path
    rel = os.path.relpath(target_dir, from_web_dir).replace(os.sep, "/")
    base = os.path.basename(link_web_path)
    return (rel + "/" + base) if rel != "." else base


def topnav(current_web_dir: str = "", home: str = "../../index.html", prefix: str = "") -> str:
    """依赖调用方已定义的 .topnav / .topnav a CSS（金色主题）。"""
    items = "".join(
        f"<a href='{prefix}{_rel(p, current_web_dir)}'>{t}</a>" for t, p in SECTIONS)
    items += f"<a href='{home}'>返回主页</a>"
    return f"<div class='topnav'>{items}</div>"


def selfcontained_nav(current_web_dir: str = "", home: str = "../../index.html", prefix: str = "") -> str:
    """自带内联样式，不依赖外部 CSS，可注入任意页面顶部。"""
    bar = ("display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px;padding:12px 4px;"
           "border-bottom:1px solid rgba(184,137,59,.3);font-size:13px;")
    a = ("color:#b8893b;text-decoration:none;padding:5px 12px;border:1px solid rgba(184,137,59,.35);"
         "border-radius:20px;white-space:nowrap;")
    items = "".join(
        f"<a href='{prefix}{_rel(p, current_web_dir)}' style='{a}'>{t}</a>" for t, p in SECTIONS)
    items += f"<a href='{home}' style='{a}'>返回主页</a>"
    return f"{NAV_SENTINEL}\n<div style='{bar}'>{items}</div>"
