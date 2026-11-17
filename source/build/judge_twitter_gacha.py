#!/usr/bin/env python3
"""FFBE JP 공식 트위터(FFRS_JP) 소환 트윗 판정 스크립트 (순수 로컬 집계, 네트워크/모델 호출 없음).

입력 (build/out/jp_offline/gacha_jp/):
  twitter_text_hydrogen.jsonl  트윗당 1줄 (텍스트 추출 결과)
  twitter_identify.jsonl       이미지당 1줄 (배너 판독)
  twitter_identify_agy.jsonl   이미지당 1줄 (같은 file이 있으면 이 쪽을 우선)
  --targets                    판독 대상 이미지 목록 txt (없으면 판독 대기 구분만 생략)
출력 (같은 폴더):
  twitter_verdict.jsonl, twitter_gacha_identities.json, twitter_verdict_report.md

사용법:
  python -I -X utf8 build/judge_twitter_gacha.py [--targets 경로]
"""
import argparse
import collections
import json
import random
import re
import sys
import unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
GACHA_DIR = ROOT / "build" / "out" / "jp_offline" / "gacha_jp"
DEFAULT_TARGETS = Path(
    r"C:\Users\USER\AppData\Local\Temp\claude\cf8960ff5439d3bc"
    r"\8c51e8ce-0d8e-4980-ae4a-6beb5f865020\scratchpad\all_targets.txt"
)

# 같은 트윗의 본문과 배너는 같은 소환을 가리킨다고 본다(문자열 대조는 판정 조건이 아니라 참고 사유).
# 배너가 소환이면 본문 추출이 없어도 배너의 제목·유닛으로 정체를 만든다.
# 무료 소환(type=free 또는 이름에 無料)은 구현 대상에서 빼 두기로 했다(사용자 결정 2026-11-16).
# 트윗의 소환이 전부 무료면 판정이 "별도-무료"가 되고, 무료 정체는 twitter_gacha_free.json 으로 따로 나간다.
VERDICTS = ["확정", "이미지만", "텍스트만", "별도-무료", "제외"]


# 다만 가격이 무료일 뿐 고유 풀·확정 조건이 이름에 적힌 배너(ALL Neo Vision確定, コラボユニット確定 등)는 본 목록에 남긴다.
OWN_POOL = re.compile(r"確定|neo ?vision|nv|コラボ|100%|セレクト", re.I)


def is_free(name, typ=None):
    n = unicodedata.normalize("NFKC", name or "")
    return (typ == "free" or "無料" in n) and not OWN_POOL.search(n)
IDENT_SOURCE_VERDICTS = ("확정", "이미지만", "텍스트만")
STATUSES = ("확정", "이미지만", "텍스트만")
FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_(\d+)_(\d+)\.[A-Za-z0-9]+$")
SERIES_SPLIT = re.compile(r"[,，、]")


def str_or_none(x):
    if x is None:
        return None
    s = str(x).strip()
    return s or None


def as_list(x):
    return x if isinstance(x, list) else []


def norm(s):
    """NFKC, 공백과 기호(유니코드 P/S 범주) 제거, 소문자화."""
    if s is None:
        return ""
    s = unicodedata.normalize("NFKC", str(s))
    keep = []
    for ch in s:
        if ch.isspace() or unicodedata.category(ch)[0] in "PS":
            continue
        keep.append(ch)
    return "".join(keep).lower()


def parse_file(name):
    m = FILE_RE.match(name)
    if not m:
        return None, None
    return m.group(2), m.group(1)  # (tweet id, date)


def read_jsonl(path):
    rows, bad = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                bad += 1
                continue
            if isinstance(obj, dict):
                rows.append(obj)
            else:
                bad += 1
    return rows, bad


def unit_name(u):
    if isinstance(u, dict):
        return str_or_none(u.get("name"))
    return str_or_none(u)


def gachas_of(rec):
    if not rec:
        return []
    return [g for g in as_list(rec.get("gachas")) if isinstance(g, dict)]


def name_match(gname, title):
    a, b = norm(gname), norm(title)
    if not a or not b:
        return False
    if a == b:
        return True
    return min(len(a), len(b)) >= 4 and (a in b or b in a)


def unit_hits(text_units, im):
    """text_units: 정규화된 텍스트 유닛명(2자 이상) 목록."""
    blob = norm("".join(im["unit_names"]) + im["title"] + "".join(im["subtitles"]))
    im_norm = [norm(x) for x in im["unit_names"] if norm(x)]
    hits = []
    for u in text_units:
        if u in blob:
            hits.append(u)
            continue
        for iu in im_norm:
            if iu == u or (len(iu) >= 2 and (iu in u or u in iu)):
                hits.append(u)
                break
    return hits


def series_hits(text_series, im_series):
    iss = norm(im_series)
    if len(iss) < 2:
        return []
    hits = []
    for part in SERIES_SPLIT.split(text_series or ""):
        p = norm(part)
        if len(p) >= 2 and (p in iss or iss in p):
            hits.append(part.strip())
    return hits


def judge(rec, imgs, pending_n):
    """rec: 텍스트 레코드 또는 None. 반환: (판정, 하위 사유, 근거 목록)."""
    is_gacha = bool(rec) and rec.get("is_gacha") is True
    gachas = gachas_of(rec)
    named = [g for g in gachas if str_or_none(g.get("name"))]
    gacha_imgs = [im for im in imgs if im["kind"] == "gacha"]

    evidence = []
    if gacha_imgs and is_gacha:
        for gi, g in enumerate(gachas):
            gname = str_or_none(g.get("name"))
            if not gname:
                continue
            tunits = []
            for u in as_list(g.get("units")):
                n = norm(unit_name(u))
                if len(n) >= 2 and n not in tunits:
                    tunits.append(n)
            tseries = str_or_none(g.get("series"))
            for im in gacha_imgs:
                if name_match(gname, im["title"]):
                    evidence.append({"type": "name", "gacha_idx": gi, "gacha": gname,
                                     "file": im["file"], "detail": im["title"]})
                uh = unit_hits(tunits, im)
                if uh:
                    evidence.append({"type": "unit", "gacha_idx": gi, "gacha": gname,
                                     "file": im["file"], "detail": uh})
                sh = series_hits(tseries, im["series"])
                if sh:
                    evidence.append({"type": "series", "gacha_idx": gi, "gacha": gname,
                                     "file": im["file"], "detail": sh})

    types = {e["type"] for e in evidence}
    if gacha_imgs and is_gacha:
        verdict = "확정"
        reason = ",".join(sorted(types)) if types else "같은 트윗(문자 대조 안 됨)"
    elif gacha_imgs:
        verdict = "이미지만"
        reason = "본문 추출 없음" if rec is None else "본문은 소환 공지 아님"
    elif is_gacha and named:
        verdict = "텍스트만"
        if pending_n > 0:
            reason = "판독대기"
        elif imgs:
            reason = "이미지가 소환 아님"
        else:
            reason = "이미지 없음"
    else:
        verdict = "제외"
        reason = "소환 공지 아님"
    return verdict, reason, evidence


def cell(s):
    return str(s).replace("|", "/").replace("\n", " ")


def tweet_sort_key(t):
    return (0, int(t)) if t.isdigit() else (1, t)


def main():
    ap = argparse.ArgumentParser(description="FFRS_JP 소환 트윗 판정")
    ap.add_argument("--targets", default=str(DEFAULT_TARGETS),
                    help="판독 대상 이미지 목록 txt (한 줄에 경로 하나)")
    args = ap.parse_args()

    # 1) 텍스트 레코드
    text_path = GACHA_DIR / "twitter_text_hydrogen.jsonl"
    text_rows, text_bad = read_jsonl(text_path)
    TEXT = {}
    text_noid = text_dup = 0
    for r in text_rows:
        tid = str_or_none(r.get("id"))
        if not tid:
            text_noid += 1
            continue
        if tid in TEXT:
            text_dup += 1
        TEXT[tid] = r  # 같은 id가 여럿이면 마지막 줄을 씀

    # 2) 이미지 판독 (agy가 identify보다 우선)
    files = {}
    id_stats = {}
    for name, src in [("twitter_identify.jsonl", "identify"),
                      ("twitter_identify_agy.jsonl", "agy")]:
        p = GACHA_DIR / name
        if not p.exists():
            id_stats[src] = None
            continue
        rows, bad = read_jsonl(p)
        id_stats[src] = {"rows": len(rows), "bad": bad}
        for r in rows:
            fn = str_or_none(r.get("file"))
            if not fn:
                continue
            r = dict(r)
            r["_src"] = src
            files[fn] = r
    both = 0
    seen_src = collections.Counter()
    img_by_tid = collections.defaultdict(list)
    if id_stats.get("identify") and id_stats.get("agy"):
        ident_rows, _ = read_jsonl(GACHA_DIR / "twitter_identify.jsonl")
        agy_rows, _ = read_jsonl(GACHA_DIR / "twitter_identify_agy.jsonl")
        both = len({str_or_none(r.get("file")) for r in ident_rows} &
                   {str_or_none(r.get("file")) for r in agy_rows})
    unparsed = []
    for fn, r in files.items():
        tid, fdate = parse_file(fn)
        if tid is None:
            unparsed.append(fn)
            continue
        img_by_tid[tid].append({
            "file": fn,
            "date": fdate,
            "kind": (str_or_none(r.get("kind")) or "").lower(),
            "title": str_or_none(r.get("title")) or "",
            "subtitles": [str(s) for s in as_list(r.get("subtitles")) if s not in (None, "")],
            "unit_names": [str(u) for u in as_list(r.get("unit_names")) if u not in (None, "")],
            "series": str_or_none(r.get("series")),
            "src": r.get("_src"),
        })
        seen_src[r.get("_src")] += 1
    for tid in img_by_tid:
        img_by_tid[tid].sort(key=lambda im: im["file"])

    # 3) 판독 대상 목록 -> 판독 대기
    targets = set()
    tp = Path(args.targets) if args.targets else None
    targets_found = bool(tp and tp.exists())
    if targets_found:
        for line in tp.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s:
                targets.add(re.split(r"[\\/]", s)[-1])
    else:
        print(f"경고: 판독 대상 목록이 없어 판독 대기 구분을 생략한다 ({tp})")
    pending_by_tid = collections.Counter()
    for fn in targets:
        if fn in files:
            continue
        tid, _ = parse_file(fn)
        if tid is not None:
            pending_by_tid[tid] += 1

    # 4) 트윗 단위 판정
    universe = sorted(set(TEXT) | set(img_by_tid), key=tweet_sort_key)
    rows_out = []
    gachas_by_tid = {}
    for tid in universe:
        rec = TEXT.get(tid)
        imgs = img_by_tid.get(tid, [])
        verdict, reason, evidence = judge(rec, imgs, pending_by_tid.get(tid, 0))
        if verdict == "이미지만":
            items = [(im["title"], None) for im in imgs if im["kind"] == "gacha" and im["title"]]
        else:
            items = [(str_or_none(g.get("name")), str_or_none(g.get("type"))) for g in gachas_of(rec)
                     if str_or_none(g.get("name"))]
        src_verdict = verdict
        if verdict in IDENT_SOURCE_VERDICTS and items and all(is_free(n, t) for n, t in items):
            reason = f"{verdict}: {reason}"
            verdict = "별도-무료"
        date = (rec or {}).get("date") or next((im["date"] for im in imgs if im["date"]), None)
        gachas = gachas_of(rec)
        gachas_by_tid[tid] = gachas
        text_gachas = [{
            "name": str_or_none(g.get("name")),
            "type": g.get("type"),
            "start_iso": g.get("start_iso"),
            "end_iso": g.get("end_iso"),
            "units": [n for n in (unit_name(x) for x in as_list(g.get("units"))) if n],
        } for g in gachas]
        rows_out.append({
            "id": tid,
            "date": date,
            "verdict": verdict,
            "_src_verdict": src_verdict,
            "reason": reason,
            "evidence": evidence,
            "phase": (rec or {}).get("phase"),
            "text_gachas": text_gachas,
            "images": [{"file": im["file"], "kind": im["kind"], "title": im["title"],
                        "unit_names": im["unit_names"]} for im in imgs],
            "_imgs": imgs,
        })
    vcount = collections.Counter(r["verdict"] for r in rows_out)

    # 5) 소환 정체 묶기
    members = collections.defaultdict(list)
    nameless = 0
    for vr in rows_out:
        if vr["_src_verdict"] not in ("확정", "텍스트만"):
            continue
        ym = (vr["date"] or "")[:7]
        for gi, g in enumerate(gachas_by_tid[vr["id"]]):
            name = str_or_none(g.get("name"))
            if not name:
                nameless += 1
                continue
            si = str_or_none(g.get("start_iso"))
            if si:
                key = f"{norm(name)}|{si}"
            else:
                units = sorted({norm(unit_name(x)) for x in as_list(g.get("units"))
                                if norm(unit_name(x))})
                key = f"{norm(name)}|{'|'.join(units)}|{ym}"
            ev_files = sorted({e["file"] for e in vr["evidence"] if e["gacha_idx"] == gi})
            if not vr["evidence"] and vr["_src_verdict"] == "확정" and                     sum(1 for x in gachas_by_tid[vr["id"]] if str_or_none(x.get("name"))) == 1:
                ev_files = sorted(im["file"] for im in vr["_imgs"] if im["kind"] == "gacha")
            members[key].append({"tid": vr["id"], "date": vr["date"], "g": g, "name": name,
                                 "verdict": vr["_src_verdict"], "files": ev_files})

    # 이미지만: 배너 한 장이 소환 하나. 제목·유닛이 같은 배너(같은 달)는 하나로 묶는다.
    for vr in rows_out:
        if vr["_src_verdict"] != "이미지만":
            continue
        ym = (vr["date"] or "")[:7]
        for im in vr["_imgs"]:
            if im["kind"] != "gacha" or not im["title"]:
                continue
            units = sorted({norm(u) for u in im["unit_names"] if norm(u)})
            key = f"img|{norm(im['title'])}|{'|'.join(units)}|{ym}"
            g = {"name": im["title"], "type": None, "units": [{"name": u, "rarity": None} for u in im["unit_names"]],
                 "series": im["series"]}
            members[key].append({"tid": vr["id"], "date": vr["date"], "g": g, "name": im["title"],
                                 "verdict": "이미지만", "files": [im["file"]]})

    idents = []
    for key, ms in members.items():
        name = collections.Counter(m["name"] for m in ms).most_common(1)[0][0]
        types = collections.Counter(str_or_none(m["g"].get("type")) for m in ms
                                    if str_or_none(m["g"].get("type")))
        typ = types.most_common(1)[0][0] if types else None
        rerun = any(m["g"].get("rerun") is True for m in ms)
        start_iso = next((str_or_none(m["g"].get("start_iso")) for m in ms
                          if str_or_none(m["g"].get("start_iso"))), None)
        end_iso = next((str_or_none(m["g"].get("end_iso")) for m in ms
                        if str_or_none(m["g"].get("end_iso"))), None)
        units, useen = [], set()
        for m in ms:
            for u in as_list(m["g"].get("units")):
                n = unit_name(u)
                if n and n not in useen:
                    useen.add(n)
                    rar = u.get("rarity") if isinstance(u, dict) else None
                    units.append({"name": n, "rarity": rar})
        series_list = []
        for m in ms:
            s = str_or_none(m["g"].get("series"))
            if s and s not in series_list:
                series_list.append(s)
        prices, pseen = [], set()
        for m in ms:
            for p in as_list(m["g"].get("prices")):
                sp = p if isinstance(p, str) else json.dumps(p, ensure_ascii=False)
                if sp not in pseen:
                    pseen.add(sp)
                    prices.append(sp)
        tweets = sorted({m["tid"] for m in ms}, key=tweet_sort_key)
        images = sorted({f for m in ms for f in m["files"]})
        vs = {m["verdict"] for m in ms}
        status = next(x for x in STATUSES if x in vs)
        dates = sorted(m["date"] for m in ms if m["date"])
        if start_iso and re.match(r"^\d{4}", start_iso):
            year = start_iso[:4]
        else:
            year = dates[0][:4] if dates else "unknown"
        idents.append({
            "name": name, "type": typ, "rerun": rerun, "start_iso": start_iso,
            "end_iso": end_iso, "units": units, "series": ", ".join(series_list) or None,
            "prices": prices, "tweets": tweets, "images": images, "status": status,
            "year": year,
        })
    idents.sort(key=lambda d: (d["year"], d["start_iso"] or "", d["name"]))
    free_idents = [d for d in idents if is_free(d["name"], d["type"])]
    idents = [d for d in idents if not is_free(d["name"], d["type"])]

    # 6) 출력 파일
    out_v = GACHA_DIR / "twitter_verdict.jsonl"
    with open(out_v, "w", encoding="utf-8", newline="\n") as f:
        for vr in rows_out:
            rec = {k: v for k, v in vr.items() if not k.startswith("_")}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    out_i = GACHA_DIR / "twitter_gacha_identities.json"
    out_i.write_text(json.dumps(idents, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (GACHA_DIR / "twitter_gacha_free.json").write_text(
        json.dumps(free_idents, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # 7) 보고서
    L = []
    add = L.append
    add("# FFRS_JP 소환 트윗 판정 보고서")
    add("")
    add("## 입력 요약")
    add(f"- 텍스트 레코드: {len(text_rows)}줄 (잘못된 줄 {text_bad}, id 없음 {text_noid}, 중복 id {text_dup})")
    add(f"- 판독 레코드(identify): {id_stats.get('identify')}, (agy): {id_stats.get('agy')}")
    add(f"- 같은 file이 두 파일에 있어 agy를 채택한 수: {both}")
    add(f"- 판독 대상 목록: {'있음 ' + str(len(targets)) + '개' if targets_found else '없음(판독 대기 구분 생략)'}")
    pend_total = sum(pending_by_tid.values())
    pend_outside = sum(v for t, v in pending_by_tid.items() if t not in set(universe))
    add(f"- 판독 대기 이미지 {pend_total}장 (대상 트윗 밖 {pend_outside}장은 판정 대상 아님)")
    add(f"- 대상 트윗 {len(universe)}개, 파일명 규칙 불일치 판독 파일 {len(unparsed)}개")
    add("")
    add("## 1. 판정별 트윗 수")
    add("| 판정 | 트윗 수 |")
    add("|---|---:|")
    for v in VERDICTS:
        add(f"| {v} | {vcount.get(v, 0)} |")
    add(f"| 합계 | {len(rows_out)} |")
    add("")
    add("## 2. 하위 사유별 수")
    add("| 판정 | 하위 사유 | 트윗 수 |")
    add("|---|---|---:|")
    sub = collections.Counter((r["verdict"], r["reason"]) for r in rows_out
                              if r["verdict"] != "제외")
    for (v, rsn), n in sorted(sub.items()):
        add(f"| {v} | {rsn} | {n} |")
    add("")
    add("## 3. 연도 x 판정")
    years = sorted({(r["date"] or "unknown")[:4] for r in rows_out})
    add("| 연도 | " + " | ".join(VERDICTS) + " | 합계 |")
    add("|---|" + "---:|" * (len(VERDICTS) + 1))
    for y in years:
        cnt = collections.Counter(r["verdict"] for r in rows_out if (r["date"] or "unknown")[:4] == y)
        add(f"| {y} | " + " | ".join(str(cnt.get(v, 0)) for v in VERDICTS)
            + f" | {sum(cnt.values())} |")
    add("")
    add("## 4. 근거 종류별 수")
    add("확정 트윗 중 해당 근거를 하나 이상 가진 트윗 수와, 전체 근거 항목(gacha x 이미지 쌍) 수.")
    add("| 근거 | 트윗 수 (확정) | 근거 항목 수 (전체) |")
    add("|---|---:|---:|")
    strong = [r for r in rows_out if r["verdict"] == "확정"]
    for t in ("name", "unit", "series"):
        tw = sum(1 for r in strong if any(e["type"] == t for e in r["evidence"]))
        items = sum(1 for r in rows_out for e in r["evidence"] if e["type"] == t)
        add(f"| {t} | {tw} | {items} |")
    add("")
    add("## 5. 소환 정체")
    st_count = collections.Counter(d["status"] for d in idents)
    add(f"- 총 정체 수: {len(idents)} (무료 소환 {len(free_idents)}개는 twitter_gacha_free.json 으로 분리)")
    add("- status별: " + ", ".join(f"{s} {st_count.get(s, 0)}" for s in STATUSES))
    add("")
    add("연도 x status")
    add("| 연도 | 확정 | 이미지만 | 텍스트만 | 합계 |")
    add("|---|---:|---:|---:|---:|")
    for y in sorted({d["year"] for d in idents}):
        c = collections.Counter(d["status"] for d in idents if d["year"] == y)
        add(f"| {y} | {c.get('확정', 0)} | {c.get('이미지만', 0)} | {c.get('텍스트만', 0)} | {sum(c.values())} |")
    add("")
    add("type x status")
    add("| type | 확정 | 이미지만 | 텍스트만 | 합계 |")
    add("|---|---:|---:|---:|---:|")
    for t in sorted({d["type"] or "(없음)" for d in idents}):
        c = collections.Counter(d["status"] for d in idents if (d["type"] or "(없음)") == t)
        add(f"| {cell(t)} | {c.get('확정', 0)} | {c.get('이미지만', 0)} | {c.get('텍스트만', 0)} | {sum(c.values())} |")
    add("")
    for s in ("확정", "이미지만"):
        grp = [d for d in idents if d["status"] == s]
        withimg = sum(1 for d in grp if d["images"])
        add(f"- {s} 정체 중 이미지가 붙은 수: {withimg} / {len(grp)}")
    add("")
    add("## 6. 표본 검토 (random.seed(0), 판정별 고정 추출)")
    add("열: 트윗 id | 날짜 | 텍스트 소환명·유닛 | 이미지 title·unit_names | 근거")
    add("")
    random.seed(0)
    plan = [("확정", 15), ("이미지만", 20), ("텍스트만", 10)]
    for v, k in plan:
        pool = sorted([r for r in rows_out if r["verdict"] == v],
                      key=lambda r: tweet_sort_key(r["id"]))
        picked = random.sample(pool, min(k, len(pool)))
        add(f"### {v} ({len(picked)}건 / 전체 {len(pool)}건)")
        add("| 트윗 id | 날짜 | 텍스트 소환명·유닛 | 이미지 title·unit_names | 근거 |")
        add("|---|---|---|---|---|")
        for r in picked:
            tg = [g for g in r["text_gachas"] if g["name"]]
            tcell = "; ".join(f"{g['name']}({'/'.join(g['units'][:5])})" for g in tg[:3]) or "(소환명 없음)"
            if r["text_gachas"] == [] and tg == []:
                tcell = "(텍스트 레코드 없음)" if TEXT.get(r["id"]) is None else tcell
            ims = r["images"]
            icell = "; ".join(f"{im['title']} [{'/'.join(im['unit_names'][:4])}] ({im['kind']})"
                              for im in ims[:3])
            if len(ims) > 3:
                icell += f" 외 {len(ims) - 3}장"
            icell = icell or "(이미지 없음)"
            if r["evidence"]:
                ecell = "; ".join(f"{e['type']}: {e['gacha']} <-> {e['file']}"
                                  for e in r["evidence"][:3])
                if len(r["evidence"]) > 3:
                    ecell += f" 외 {len(r['evidence']) - 3}건"
            else:
                ecell = f"근거 없음 ({r['reason']})"
            add(f"| {cell(r['id'])} | {cell(r['date'] or '')} | {cell(tcell)} | {cell(icell)} | {cell(ecell)} |")
        add("")
    out_r = GACHA_DIR / "twitter_verdict_report.md"
    out_r.write_text("\n".join(L) + "\n", encoding="utf-8")

    # 콘솔 요약
    for v in VERDICTS:
        print(f"{v}: {vcount.get(v, 0)}")
    print(f"무료 소환(별도): {len(free_idents)}")
    print(f"소환 정체: {len(idents)} (" + ", ".join(
        f"{s} {st_count.get(s, 0)}" for s in STATUSES) + ")")
    print(f"출력: {out_v.name}, {out_i.name}, {out_r.name}")


if __name__ == "__main__":
    main()
