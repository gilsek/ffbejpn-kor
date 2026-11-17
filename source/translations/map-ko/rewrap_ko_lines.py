#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""map_text_ko.json 의 한국어 대사 중 대화창 폭(20자)을 넘는 줄을 다시 끊는다.

- 값만 바꾸고 키는 건드리지 않는다.
- 태그(<...>)는 표시 길이에서 제외하고, 태그 자체는 절대 쪼개지 않는다.
- 원문(키)의 본문 줄 수와 같게 맞추는 것을 우선하고, 불가능하면 최소 줄 수로 늘린다.
- 실행: python -I -X utf8 rewrap_ko_lines.py [--dry-run]
- 여러 번 실행해도 결과가 같다(이미 20자 이하인 항목은 대상이 아니므로).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE / "map_text_ko.json"
BACKUP = HERE / "map_text_ko.before_rewrap.json"
REPORT = HERE / "rewrap_report.json"

TAG_RE = re.compile(r"<[^<>]*>")
BR = "<br>"
PAGE = "<page>"
MAX_LEN = 20
PUNCT = set("，‚、。…！？!?」』")
SPACE_CHARS = set(" 　\t")
# 줄바꿈 위치로 인정하는 문자(공백 뒤 또는 구두점 뒤)
BREAK_CHARS = SPACE_CHARS | PUNCT


# ---------------------------------------------------------------- 유틸

def visible(s: str) -> str:
    """태그를 제거한 표시 문자열."""
    return TAG_RE.sub("", s)


def is_structural(chunk: str) -> bool:
    """화자 이름 줄처럼 표시 글자가 없는 조각."""
    return visible(chunk).strip() == ""


def display_len(s: str) -> int:
    return len(visible(s))


def leading_ws(s: str) -> str:
    m = re.match(r"[ 　\t]*", s)
    return m.group() if m else ""


def normalize_for_assert(s: str) -> str:
    """공백과 <br> 만 제거한 비교용 문자열."""
    s = s.replace(BR, "")
    return "".join(ch for ch in s if ch not in SPACE_CHARS)


# ---------------------------------------------------------------- 구조 해석

def parse_parts(value: str):
    """값을 ('struct', 원문조각) / ('run', [본문조각...]) 목록으로 나눈다.

    <page> 는 화면 경계이므로 그 뒤 본문은 새 run 으로 분리한다.
    구조가 애매하면 None 을 돌려준다.
    """
    chunks = value.split(BR)
    parts = []
    run: list[str] = []

    def flush():
        nonlocal run
        if run:
            parts.append(("run", run))
            run = []

    for chunk in chunks:
        if is_structural(chunk):
            flush()
            parts.append(("struct", chunk))
            continue
        if PAGE in chunk:
            tail = chunk[chunk.rfind(PAGE) + len(PAGE):]
            if visible(tail).strip():
                # <page> 뒤에 같은 조각 안에 표시 글이 있으면 경계가 애매하다.
                return None
            run.append(chunk)
            flush()  # 페이지 경계
            continue
        run.append(chunk)
    flush()
    return parts


def shape(parts):
    return tuple(("S",) if kind == "struct" else ("B", len(chunks))
                 for kind, chunks in parts)


# ---------------------------------------------------------------- 재줄바꿈

def solve_run(chunks: list[str], k_target: int):
    """본문 조각들을 k_target 줄(가능하면)로 다시 끊어 줄 문자열 목록을 돌려준다.

    반환: (lines, used_k) 또는 None.
    """
    # 이어붙이기: 줄 경계는 공백 하나로 연결(앞 줄이 공백/전각 공백으로 끝나면 생략)
    cont_prefixes = [leading_ws(c) for c in chunks[1:]]
    indent = ""
    if cont_prefixes and all(p.startswith("　") for p in cont_prefixes):
        indent = os.path.commonprefix(cont_prefixes)
        if not indent.startswith("　"):
            indent = ""

    cleaned = [chunks[0]]
    for c in chunks[1:]:
        cleaned.append(c[len(leading_ws(c)):])

    joined = cleaned[0]
    for c in cleaned[1:]:
        if visible(joined) and visible(joined)[-1] in SPACE_CHARS:
            joined += c
        else:
            joined += " " + c

    # 원자(문자/태그) 목록
    atoms: list[tuple[str, str]] = []
    for m in re.finditer(r"<[^<>]*>|[\s\S]", joined):
        tok = m.group(0)
        atoms.append(("t", tok) if TAG_RE.fullmatch(tok) else ("c", tok))

    vis = [(tok, i) for i, (kind, tok) in enumerate(atoms) if kind == "c"]
    m_count = len(vis)
    if m_count == 0:
        return None

    # 끊기 후보: (끊는 표시 문자 인덱스 k, 줄 끝 표시 인덱스 e, 다음 시작 표시 인덱스 ns)
    cuts = []
    for k, (ch, _ai) in enumerate(vis):
        if ch not in BREAK_CHARS:
            continue
        if ch in SPACE_CHARS:
            cuts.append((k, k, k + 1))       # 공백은 버린다
        else:
            cuts.append((k, k + 1, k + 1))   # 구두점은 줄 끝에 남긴다

    def trimmed_width(s: int, e: int) -> int:
        ts, te = s, e
        while ts < te and vis[ts][0] in SPACE_CHARS:
            ts += 1
        while te > ts and vis[te - 1][0] in SPACE_CHARS:
            te -= 1
        return te - ts

    def has_text(s: int, e: int) -> bool:
        return any(vis[i][0] not in SPACE_CHARS for i in range(s, e))

    def solve(k_lines: int):
        if k_lines < 1 or k_lines > m_count:
            return None
        ideal = (m_count + len(indent) * (k_lines - 1)) / k_lines
        # layers[line][(line, start_vis)] = (cost, prev_state, cut_info)
        layers: list[dict] = [{(0, 0): (0.0, None, None)}]
        for li in range(k_lines):
            nxt: dict[tuple[int, int], tuple[float, tuple | None, tuple | None]] = {}
            for (line, s), (cost, _prev, _ci) in layers[li].items():
                if li == k_lines - 1:
                    e = m_count
                    ind = len(indent) if li > 0 else 0
                    if has_text(s, e) and trimmed_width(s, e) + ind <= MAX_LEN:
                        c = cost + (trimmed_width(s, e) + ind - ideal) ** 2
                        key = (li + 1, e)
                        cand = (c, (li, s), None)
                        old = nxt.get(key)
                        if old is None or cand[0] < old[0] - 1e-12:
                            nxt[key] = cand
                    continue
                for (k, e, ns) in cuts:
                    if e <= s or ns <= s:
                        continue
                    if not has_text(s, e):
                        continue
                    w = trimmed_width(s, e) + (len(indent) if li > 0 else 0)
                    if w > MAX_LEN:
                        continue  # 이 줄은 더 짧아야 한다
                    c = cost + (w - ideal) ** 2
                    key = (li + 1, ns)
                    cand = (c, (li, s), (k, e, ns))
                    old = nxt.get(key)
                    if old is None or cand[0] < old[0] - 1e-12:
                        nxt[key] = cand
            if not nxt:
                return None
            layers.append(nxt)
        end_key = (k_lines, m_count)
        last = layers[k_lines]
        if end_key not in last:
            return None
        # 경로 복원
        path = []
        state = end_key
        while state[0] > 0:
            cost, prev, ci = layers[state[0]][state]
            path.append((state, prev, ci))
            if prev is None:
                break
            state = prev
        path.reverse()
        return path

    chosen = None
    used_k = None
    sol = solve(k_target)
    if sol is not None:
        chosen, used_k = sol, k_target
    else:
        # 원문 줄 수가 불가능하면 필요한 최소 줄 수를 찾는다.
        for k in range(1, m_count + 1):
            sol = solve(k)
            if sol is not None:
                chosen, used_k = sol, k
                break
    if chosen is None:
        return None

    # 경로에서 줄별 원자 범위 계산
    ranges = []
    start_atom = 0
    for idx, (_state, _prev, ci) in enumerate(chosen):
        if idx == len(chosen) - 1:
            end_atom = len(atoms)
        else:
            k, e, ns = ci
            ch = vis[k][0]
            end_atom = vis[k][1] if ch in SPACE_CHARS else vis[k][1] + 1
        ranges.append((start_atom, end_atom))
        if idx < len(chosen) - 1:
            k, e, ns = ci
            start_atom = vis[k][1] + 1

    # 줄 문자열 생성 (양끝 공백 문자만 정리, 태그는 보존)
    lines = []
    for li, (a0, a1) in enumerate(ranges):
        line_atoms = atoms[a0:a1]
        # 첫/마지막 표시 문자가 공백이면 그 앞뒤 공백 원자만 제거
        first = last = None
        for j, (kind, tok) in enumerate(line_atoms):
            if kind == "c" and tok not in SPACE_CHARS:
                if first is None:
                    first = j
                last = j
        if first is None:
            return None
        kept = []
        for j, (kind, tok) in enumerate(line_atoms):
            if kind == "c" and tok in SPACE_CHARS and (j < first or j > last):
                continue
            kept.append(tok)
        text = "".join(kept)
        if li > 0 and indent:
            text = indent + text
        lines.append(text)
    return lines, used_k


# ---------------------------------------------------------------- 항목 처리

def rewrap_entry(key: str, value: str):
    """(new_value, info) 또는 (None, skip_reason)."""
    old_parts = parse_parts(value)
    if old_parts is None:
        return None, "태그/페이지 구조가 애매함"
    key_parts = parse_parts(key)
    if key_parts is None:
        return None, "원문 키의 태그/페이지 구조가 애매함"
    if len(old_parts) != len(key_parts):
        return None, "원문과 조각 구조 불일치"
    if shape(old_parts) != shape(key_parts):
        return None, "원문과 줄/태그 구조 불일치"

    out_ops = []
    used_total = 0
    key_total = 0
    for (kind, payload), (kkind, kpayload) in zip(old_parts, key_parts):
        if kind == "struct":
            out_ops.append(payload)
            continue
        k_target = len(kpayload)
        key_total += k_target
        res = solve_run(payload, k_target)
        if res is None:
            return None, "20자 이내로 끊을 수 있는 위치가 없음"
        lines, used_k = res
        used_total += used_k
        out_ops.append(BR.join(lines))

    new_value = BR.join(out_ops)

    if normalize_for_assert(value) != normalize_for_assert(new_value):
        raise AssertionError(f"내용이 바뀜: {key!r}\n{value!r}\n{new_value!r}")
    if any(display_len(x) > MAX_LEN for x in new_value.split(BR)):
        raise AssertionError(f"20자 초과 줄이 남음: {key!r}\n{new_value!r}")

    return new_value, {
        "used_total": used_total,
        "key_total": key_total,
    }


# ---------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="파일을 쓰지 않고 결과만 출력")
    args = ap.parse_args()

    data = json.loads(SRC.read_text(encoding="utf-8"))
    targets = [(k, v) for k, v in data.items()
               if BR in v and any(display_len(x) > MAX_LEN for x in v.split(BR))]

    changed = 0
    increased = []
    skipped = []
    changed_examples = []
    new_data = dict(data)

    for key, value in targets:
        new_value, info = rewrap_entry(key, value)
        if new_value is None:
            skipped.append({"key": key, "reason": info})
            continue
        if new_value == value:
            continue
        new_data[key] = new_value
        changed += 1
        if len(changed_examples) < 3:
            changed_examples.append({"key": key, "before": value, "after": new_value})
        if info["used_total"] > info["key_total"]:
            increased.append({
                "key": key,
                "before": value,
                "after": new_value,
                "key_body_lines": info["key_total"],
                "before_body_lines": len([c for c in value.split(BR) if not is_structural(c)]),
                "after_body_lines": info["used_total"],
            })

    report = {
        "source": SRC.name,
        "max_line_len": MAX_LEN,
        "target_count": len(targets),
        "changed_count": changed,
        "line_increased_count": len(increased),
        "line_increased": increased,
        "skipped_count": len(skipped),
        "skipped": skipped,
    }

    if args.dry_run:
        print(f"[dry-run] 대상 {len(targets)} / 변경 {changed} / "
              f"줄 증가 {len(increased)} / 건너뜀 {len(skipped)}")
        for ex in changed_examples:
            print("---", ex["key"])
            print("이전:", ex["before"])
            print("이후:", ex["after"])
        return 0

    if not BACKUP.exists():
        shutil.copyfile(SRC, BACKUP)
        print(f"백업 생성: {BACKUP.name}")
    else:
        print(f"백업 유지(이미 존재): {BACKUP.name}")

    text = json.dumps(new_data, ensure_ascii=False, indent=0, separators=(",", ": "))
    # 원본과 같은 CRLF 줄바꿈으로 저장
    with open(SRC, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace("\n", "\r\n"))

    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")

    print(f"대상 {len(targets)} / 변경 {changed} / "
          f"줄 증가 {len(increased)} / 건너뜀 {len(skipped)}")
    print(f"보고서: {REPORT.name}")
    for sk in skipped[:10]:
        print("  건너뜀:", sk["reason"], "|", sk["key"][:60])
    return 0


if __name__ == "__main__":
    sys.exit(main())
