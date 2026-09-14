# -*- coding: utf-8 -*-
"""「版块总览」已合并到总门户。

本脚本现在只生成一个自动重定向页，避免旧书签 / 外部链接失效。
原来的「版块说明 / 数据流 / 更新时间 / 自检清单」等内容已下沉到
build_portal.py 统一在总门户展示。
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "web", "sections", "index.html")

os.makedirs(os.path.dirname(OUT), exist_ok=True)

HTML = """<!DOCTYPE html>
<html lang='zh-CN'>
<head>
<meta charset='UTF-8'>
<meta http-equiv='refresh' content='0; url=../../index.html'>
<title>版块总览已合并至总门户 · A股分析中心</title>
</head>
<body>
<p>版块总览已合并至 <a href='../../index.html'>A股分析中心 · 总门户</a>，正在跳转…</p>
</body>
</html>
"""

with open(OUT, "w", encoding="utf-8") as f:
    f.write(HTML)
print(f"OK -> {OUT}（已重定向到总门户）")
