# -*- coding: utf-8 -*-
"""每日更新后一键刷新「本地数据库 + 静态数据切片」。

流程：
  1) 把当日（或全部）新生成的 JSON 增量 upsert 进 SQLite 主库（INSERT OR REPLACE，历史自动留存）
  2) 重新导出列式压缩 JSON 切片到 web/data/，供 web/db/index.html 动态查询

用法：
  python quant/db_update.py              # 全量重导入 + 重导出
  python quant/db_update.py 2026-09-07   # 只增量导入该日 + 重导出
"""
import os
import sys
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else None
    # 1) 增量/全量导入主库
    cmd = [PY, "db.py", "import"]
    if date:
        cmd += ["--date", date]
    print(">>>", " ".join(cmd))
    subprocess.run(cmd, cwd=HERE, check=True)
    # 2) 重新导出切片
    print(">>> python db_export.py")
    subprocess.run([PY, "db_export.py"], cwd=HERE, check=True)
    print("数据库刷新完成。")


if __name__ == "__main__":
    main()
