# -*- coding: utf-8 -*-
"""最终一致性同步：把 web/**/*.html + 根 index.html 与 GitHub 仓库对齐。

做法（串行、无并发，避免 409）：
  1. 计算本地目标内容的 git blob sha（与 _push_lhb.push_file 相同的污染剥离规则）；
  2. 取远程同名文件 sha 比对；
  3. 不一致才重推，推后再次校验，直到一致。
这样可修复「多轮并发推送交错导致线上版本混杂」的问题。
"""
import sys, os, re, glob, time, hashlib
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _push_lhb as P

ROOT = P.ROOT
RELS = sorted(["index.html"] + [
    os.path.relpath(p, ROOT).replace(os.sep, "/")
    for p in glob.glob(os.path.join(ROOT, "web", "**", "*.html"), recursive=True)
])


def target_blob_sha(rel):
    raw = open(os.path.join(ROOT, rel), "rb").read()
    if rel.endswith(".html"):
        try:
            txt = raw.decode("utf-8")
            txt = re.sub(r' data-page-node-id="[^"]*"', "", txt)
            raw = txt.encode("utf-8")
        except Exception:
            pass
    h = hashlib.sha1()
    h.update(("blob %d\0" % len(raw)).encode("ascii"))
    h.update(raw)
    return h.hexdigest()


def remote_sha(rel):
    try:
        return P.get_sha(rel)
    except Exception:
        return None


def main():
    ok = fail = 0
    fails = []
    for rel in RELS:
        if any(frag in rel for frag in P.EXCLUDE_FRAGMENTS):
            continue
        want = target_blob_sha(rel)
        if remote_sha(rel) == want:
            ok += 1
            continue
        done = False
        for attempt in range(5):
            try:
                P.push_file(rel)
            except Exception:
                pass
            time.sleep(0.5 + attempt * 0.6)
            if remote_sha(rel) == want:
                done = True
                break
        if done:
            ok += 1
            print("SYNCED %s" % rel, flush=True)
        else:
            fail += 1
            fails.append(rel)
            print("FAIL   %s" % rel, flush=True)
    print("SYNC_DONE ok=%d fail=%d total=%d" % (ok, fail, len(RELS)), flush=True)
    if fails:
        print("FAILED_LIST: " + ", ".join(fails), flush=True)


if __name__ == "__main__":
    main()
