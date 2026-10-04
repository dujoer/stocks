# -*- coding: utf-8 -*-
"""诊断：本地与远端（dujoer/stocks）差异文件，到底是「本地新」还是「远端新」。

用途：当 `_push_incremental.py --dry-run` 报出大量「更新」时，先用本脚本**看清方向**，
再决定是推送还是回滚 —— 避免把「远端领先于本地」误判成「本地有改动」而推错。

用法：
    python quant/_diag_remote_diff.py                     # 查默认关键文件
    python quant/_diag_remote_diff.py web/xxx/a.html ...  # 查指定文件

★ 背景（2026-10-04）：曾出现「本地领先远端 353 个文件」——根因是**推送 55MB 耗时会超过
  Bash 默认超时（120s），被 SIGTERM 截断，只推完前 1~2 批**，而输出里仍显示"推送完成"。
  对策：推送时显式设长超时（≥600s）或减小 `--batch-mb` 分批。
"""
import sys, os, base64, difflib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _push_incremental as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
t = P.remote_tree()

CHECK = sys.argv[1:] or [
    "quant/_nav.py", "quant/build_portal.py", "quant/_page_registry.py",
    "web/docs/DAILY_UPDATE_SOP.html", "web/accumulation/combined_20260930.html"]

for rel in CHECK:
    lp = os.path.join(ROOT, rel)
    if not os.path.exists(lp):
        print("%-46s 本地缺失" % rel)
        continue
    local = open(lp, encoding="utf-8", errors="ignore").read()
    sha = t.get(rel)
    if not sha:
        print("%-46s 远端缺失（本地新增）" % rel)
        continue
    try:
        d = P.api(P.API + "/git/blobs/" + sha)
        remote = base64.b64decode(d["content"]).decode("utf-8", "ignore")
    except Exception as ex:
        print("%-46s 取远端 blob 失败: %s" % (rel, ex))
        continue
    same = (local.strip() == remote.strip())
    print("%-46s 本地 %7d 字符 | 远端 %7d 字符 | %s"
          % (rel, len(local), len(remote), "内容一致(仅空白差异)" if same else "★内容不同"))
    if not same:
        dl = [x for x in difflib.unified_diff(remote.splitlines(), local.splitlines(),
                                             "远端", "本地", lineterm="", n=1)]
        print("   差异行数 %d，前 12 行:" % len(dl))
        for x in dl[:12]:
            print("     " + x[:110])
