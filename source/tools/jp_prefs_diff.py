"""Android SharedPreferences XML 비교 + 엔진 버전표(InitializeRequest.json) 대조.

사용: python -I tools/jp_prefs_diff.py A.xml B.xml [--replies translations/server/replies/InitializeRequest.json] [--ref-xml 앱XML]
- 키/값 기준 비교(추가/삭제/변경). 긴 값은 앞 60자만 표시.
- --replies 지정 시 c1qYg84Q(a4hXTIm0=이름, wM9AfX6I=버전)를 keyF_<이름>/key<이름> 으로 --ref-xml 과 대조.
읽기 전용.
"""
import argparse, json, sys, xml.etree.ElementTree as ET


def load(path):
    root = ET.parse(path).getroot()
    d = {}
    for e in root:
        n = e.get("name")
        d[n] = (e.tag, e.get("value") if e.get("value") is not None else (e.text or ""))
    return d


def short(v, n=60):
    v = str(v)
    return v if len(v) <= n else v[:n] + "...(%d)" % len(v)


def diff(a, b, la, lb):
    add = sorted(set(b) - set(a)); rem = sorted(set(a) - set(b))
    chg = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    print("== %s -> %s : keys %d -> %d | added %d removed %d changed %d" % (la, lb, len(a), len(b), len(add), len(rem), len(chg)))
    for k in add[:10]: print("  + %s = %s" % (k, short(b[k][1])))
    for k in rem[:10]: print("  - %s = %s" % (k, short(a[k][1])))
    for k in chg[:10]: print("  ~ %s: %s -> %s" % (k, short(a[k][1]), short(b[k][1])))


def versions(replies):
    j = json.load(open(replies, encoding="utf-8"))
    return {r["a4hXTIm0"]: r["wM9AfX6I"] for r in j["c1qYg84Q"]}


def compare_versions(vers, ref, label):
    same = diff_ = miss = 0; ex = []
    for name, ver in vers.items():
        key = "key" + name
        if key not in ref:
            miss += 1; ex.append(("MISSING", key, ver, None)); continue
        if ref[key][1] == str(ver): same += 1
        else: diff_ += 1; ex.append(("DIFF", key, ver, ref[key][1]))
    print("== replies(%d entries) vs %s : same %d, different %d, missing-in-app %d" % (len(vers), label, same, diff_, miss))
    for t, k, v, r in ex[:15]: print("  %s %s reply=%s app=%s" % (t, k, v, short(r) if r is not None else "-"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xmls", nargs="+")
    ap.add_argument("--replies")
    ap.add_argument("--ref-xml", help="응답과 대조할 XML(기본: 마지막 xml)")
    a = ap.parse_args()
    ds = [load(p) for p in a.xmls]
    for i in range(len(ds) - 1):
        diff(ds[i], ds[i + 1], a.xmls[i].split("/")[-1].split("\\")[-1], a.xmls[i + 1].split("/")[-1].split("\\")[-1])
    if a.replies:
        ref = load(a.ref_xml) if a.ref_xml else ds[-1]
        compare_versions(versions(a.replies), ref, a.ref_xml or a.xmls[-1])


if __name__ == "__main__":
    sys.exit(main())
