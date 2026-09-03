# -*- coding: utf-8 -*-
"""统一顶部导航栏。

所有 A股看板页面共用，保证跳转入口与位置一致，且都带「返回主页」。
- topnav(): 依赖各生成器已定义的 .topnav CSS（build_dashboards / build_exec / build_sections 等）。
- selfcontained_nav(): 自带内联样式，用于未定义 .topnav CSS 的页面（板块强度 / 心理雷达 / 行业最强榜等）。
"""
from __future__ import annotations

# (标签, 相对链接片段) —— 统一入口，改这里即全局生效
_LINKS = [
    ("每日总览", "daily_overview.html"),
    ("龙虎榜分析", "lhb.html"),
    ("游资看板", "hotmoney.html"),
    ("板块强度", "sector-strength-index.html"),
    ("高管增减持", "exec.html"),
    ("版块总览", "sections.html"),
]


def topnav(rel: str = "", home: str = "../index.html") -> str:
    """依赖调用方已定义的 .topnav / .topnav a CSS（金色主题）。"""
    items = "".join(f"<a href='{rel}{h}'>{t}</a>" for t, h in _LINKS)
    items += f"<a href='{home}'>返回主页</a>"
    return f"<div class='topnav'>{items}</div>"


def selfcontained_nav(rel: str = "", home: str = "../index.html") -> str:
    """自带内联样式，不依赖外部 CSS，可注入任意页面顶部。"""
    bar = ("display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px;padding:12px 4px;"
           "border-bottom:1px solid rgba(184,137,59,.3);font-size:13px;")
    a = ("color:#b8893b;text-decoration:none;padding:5px 12px;border:1px solid rgba(184,137,59,.35);"
         "border-radius:20px;white-space:nowrap;")
    items = "".join(f"<a href='{rel}{h}' style='{a}'>{t}</a>" for t, h in _LINKS)
    items += f"<a href='{home}' style='{a}'>返回主页</a>"
    return f"<div style='{bar}'>{items}</div>"
