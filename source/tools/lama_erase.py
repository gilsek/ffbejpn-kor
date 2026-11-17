"""LaMa(로컬 GPU)로 스프라이트 속 글자를 지운다. 한글 그리기는 하지 않음.

실행(가상환경 필수):
  build/out/lama_venv/Scripts/python.exe -I tools/lama_erase.py --in DIR --out DIR [--mask DIR] [--auto-mask]

- 마스크: <mask>/<이름>.png (흰색=지울 영역). 없으면 --auto-mask 로 자동 생성.
- 투명 픽셀은 어두운 배경에 얹어 처리하고, 결과에 원본 알파를 그대로 다시 적용한다.
- 작은 스프라이트는 짧은 변이 --target-size(기본 192) 이상이 되도록 정수배 확대 후 축소.
- 마스크 영역만 결과로 교체(경계는 살짝 페더링)해서 나머지 픽셀은 원본과 동일.
- v2: (1) --siblings: 같은 아틀라스·같은 크기이면서 글자 밖 배경이 일치하는 형제 스프라이트의
  실제 픽셀로 먼저 채움 (2) --border N: 가장자리 N px(테두리 장식)은 마스크에서 제외
  (3) --prefill rowmedian|rowblend: 가로창 평균으로 채워 그라데이션·광택 복원. patch: 같은 행 내부 질감 패치 복사.
"""
import argparse
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

BG = (32, 32, 32)  # 투명부 임시 배경
DEFAULT_MANIFEST = Path(__file__).resolve().parent.parent / "build/out/sprite_work/manifest.json"


def auto_mask(rgba, grow=3, thr=40, white_min=190, border=6, inset_frac=0.0):
    """글자 획+외곽선 마스크. 밝은 무채색 + 국소 대비가 큰 픽셀을 잡고 grow px 팽창.
    border px(불투명 bbox 기준) 안쪽만 허용 → 테두리 장식 제외."""
    rgb, alpha = rgba[:, :, :3], rgba[:, :, 3]
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    h, w = gray.shape
    k = max(5, (min(h, w) // 4) | 1)
    bg = cv2.medianBlur(gray, k)
    diff = cv2.absdiff(gray, bg)
    m = ((diff > thr) | (rgb.min(axis=2) >= white_min)) & (alpha > 16)
    m = m.astype(np.uint8) * 255
    ys, xs = np.where(alpha > 16)
    if len(xs):
        x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    else:
        x0, x1, y0, y1 = 0, w, 0, h
    ins = max(border, int(round(inset_frac * min(x1 - x0, y1 - y0))))
    keep = np.zeros_like(m)
    keep[y0 + ins:y1 - ins, x0 + ins:x1 - ins] = 255
    m = cv2.bitwise_and(m, keep)
    if grow > 0:
        ker = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * grow + 1, 2 * grow + 1))
        m = cv2.bitwise_and(cv2.dilate(m, ker), keep)
    return m


def load_lama():
    import torch
    from simple_lama_inpainting import SimpleLama
    dev = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return SimpleLama(device=dev), dev


def composite(rgba):
    a = rgba[:, :, 3:4].astype(np.float32) / 255.0
    return (rgba[:, :, :3].astype(np.float32) * a + np.array(BG, np.float32) * (1 - a)).astype(np.uint8)


def row_median_prefill(comp, mask, bad, alpha, border):
    """마스크 영역을 '가로로 긴 창(±15px x ±2행)'의 비마스크·불투명·내부 픽셀 평균(정규화 컨볼루션)으로 채움.
    세로 그라데이션과 좌우 명암을 살린다. 가중치가 부족하면 창을 키워 반복."""
    h, w = mask.shape
    good = (~bad) & (alpha > 250)
    if border > 0:
        g2 = np.zeros_like(good)
        g2[border:h - border, border:w - border] = good[border:h - border, border:w - border]
        good = g2
    gf = good.astype(np.float32)
    num_src = comp.astype(np.float32) * gf[:, :, None]
    res = np.zeros((h, w, 3), np.float32)
    done = np.zeros((h, w), bool)
    need = mask > 127
    for kx, ky in ((15, 2), (30, 4), (60, 10), (200, 40)):
        ksz = (2 * kx + 1, 2 * ky + 1)
        wgt = cv2.boxFilter(gf, -1, ksz, normalize=False, borderType=cv2.BORDER_REPLICATE)
        num = cv2.boxFilter(num_src, -1, ksz, normalize=False, borderType=cv2.BORDER_REPLICATE)
        ok = need & ~done & (wgt >= 6)
        res[ok] = num[ok] / wgt[ok][:, None]
        done |= ok
        if not (need & ~done).any():
            break
    out = comp.copy()
    out[done] = np.clip(res[done], 0, 255).astype(np.uint8)
    return out


def patch_fill(comp, mask, alpha, border, grow_excl=2):
    """같은 스프라이트 안의 테두리·마스크 밖 내부 질감을 같은 행에서 가져와 마스크를 메운다.
    행마다 마스크 구간 [a,b]의 왼쪽/오른쪽 유효 띠를 구멍 경계에서 거울 반사로 타일링하고(경계 연속),
    구멍 안 위치에 따라 좌→우 선형 가중으로 섞어 이음매를 부드럽게 한다. 같은 행(y)에서만 가져오므로
    세로 그라데이션이 유지된다. 양쪽 띠가 모두 없는 행은 못 채움(→LaMa). 반환 (이미지, 채운 bool)"""
    h, w = mask.shape
    m = mask > 127
    excl = cv2.dilate(m.astype(np.uint8), np.ones((2 * grow_excl + 1,) * 2, np.uint8)) > 0
    valid = ~excl & (alpha > 250)
    valid[:border] = False
    valid[h - border:] = False
    valid[:, :border] = False
    valid[:, w - border:] = False
    out = comp.copy()
    filled = np.zeros((h, w), bool)

    def mirror(row_valid, row_img, edge, step, xs):
        """edge에서 step 방향으로 연속된 유효 띠를 찾아 xs 위치별 반사 소스 반환(없으면 None)."""
        x = edge
        for _ in range(10):  # 이웃 행 마스크 팽창에 막힌 가장자리를 건너뛰어 첫 유효 픽셀을 찾음
            if 0 <= x < w and not row_valid[x]:
                x += step
        edge = x
        n = 0
        while 0 <= x < w and row_valid[x]:
            n += 1
            x += step
        if n < 3:
            return None
        k = np.abs(xs)                       # 구멍 경계로부터의 거리(0부터)
        per = 2 * n
        r = k % per
        r = np.where(r >= n, per - 1 - r, r)  # 반사
        return row_img[edge + step * r]

    for y in range(h):
        xs_m = np.where(m[y])[0]
        if len(xs_m) == 0:
            continue
        a, b = xs_m.min(), xs_m.max()
        L = mirror(valid[y], comp[y], a - 1 - grow_excl, -1, xs_m - a)
        R = mirror(valid[y], comp[y], b + 1 + grow_excl, 1, b - xs_m)
        if L is None and R is None:
            continue
        if L is None:
            val = R.astype(np.float32)
        elif R is None:
            val = L.astype(np.float32)
        else:
            t = ((xs_m - a) / max(1, b - a))[:, None]
            val = L.astype(np.float32) * (1 - t) + R.astype(np.float32) * t
        out[y, xs_m] = np.clip(val, 0, 255).astype(np.uint8)
        filled[y, xs_m] = True
    return out, filled


def sibling_fill(t_rgba, t_mask, sibs, tol, sib_grow=3):
    # 형제 마스크는 이미 grow 만큼 부풀려 있으므로 채울 픽셀은 tm & ~sm 로 충분
    """형제 스프라이트(rgba, mask)에서 배경이 일치하는 것의 실제 픽셀로 마스크를 채운다.
    반환: (채운 RGBA 배열, 채움 여부 bool 배열, 사용한 형제 수)"""
    h, w = t_mask.shape
    tm = t_mask > 127
    out = t_rgba.copy()
    filled = np.zeros((h, w), bool)
    ker = np.ones((2 * sib_grow + 1, 2 * sib_grow + 1), np.uint8)
    cands = []
    for s_rgba, s_mask in sibs:
        sm = s_mask > 127
        # 일치 검사는 두 마스크를 sib_grow 만큼 더 부풀린 바깥(글자 글로우 배제)에서만 한다
        both = cv2.dilate((tm | sm).astype(np.uint8), ker) > 0
        common = ~both
        if common.sum() < 0.3 * h * w:
            continue
        d = np.abs(t_rgba.astype(np.int16) - s_rgba.astype(np.int16)).max(axis=2)
        if d[common].max() > tol:
            continue
        avail = tm & ~sm
        if avail.any():
            cands.append((d[common].mean(), -avail.sum(), s_rgba, avail))
    used = 0
    for _, _, s_rgba, avail in sorted(cands, key=lambda c: (c[0], c[1])):
        take = avail & ~filled
        if take.any():
            out[take] = s_rgba[take]
            filled |= take
            used += 1
    return out, filled, used


def erase(lama, rgba, mask, target=192, feather=2, prefill="none", border=6, sibs=None, tol=4):
    """rgba: HxWx4 uint8, mask: uint8 HxW(255=지움). (RGBA PIL, 통계 dict) 반환."""
    h, w = rgba.shape[:2]
    stats = {"mask_px": int((mask > 127).sum()), "sib_px": 0, "sib_used": 0, "outside_diff": 0, "residual": 0.0,
             "bright_before": 0, "bright_after": 0}
    if stats["mask_px"] == 0:
        return Image.fromarray(rgba, "RGBA"), stats
    work = rgba
    rem = mask > 127
    if sibs:
        work, filled, used = sibling_fill(rgba, mask, sibs, tol)
        rem = rem & ~filled
        stats["sib_px"] = int(filled.sum())
        stats["sib_used"] = used
    comp = composite(work)
    if prefill == "patch":
        comp, pf = patch_fill(comp, mask, rgba[:, :, 3], border)
        stats["patch_px"] = int(pf.sum())
        rem = rem & ~pf
    if rem.any():
        remask = rem.astype(np.uint8) * 255
        inp = comp
        if prefill in ("rowmedian", "rowblend"):
            pre = row_median_prefill(comp, remask, rem | (mask > 127), work[:, :, 3], border)
            if prefill == "rowmedian":  # 채운 값을 바탕으로 이음매 링만 LaMa로 다듬기
                ring = cv2.dilate(remask, np.ones((7, 7), np.uint8)) & ~cv2.erode(remask, np.ones((5, 5), np.uint8))
                inp, remask, comp = pre, ring, pre
        s = min(6, max(1, int(np.ceil(target / min(h, w)))))
        big = cv2.resize(inp, (w * s, h * s), interpolation=cv2.INTER_CUBIC) if s > 1 else inp
        mbig = cv2.resize(remask, (w * s, h * s), interpolation=cv2.INTER_NEAREST) if s > 1 else remask
        mbig = (mbig > 127).astype(np.uint8) * 255
        out = np.array(lama(Image.fromarray(big), Image.fromarray(mbig)))[: h * s, : w * s]
        if s > 1:
            out = cv2.resize(out, (w, h), interpolation=cv2.INTER_AREA)
        # 하드 합성: 마스크 밖 가중치 0, 마스크 안쪽 1px 링만 50% 페더링, 나머지 100%
        mk = (remask > 127)
        inner = cv2.erode((mask > 127).astype(np.uint8), np.ones((3, 3), np.uint8)) > 0  # 전체 마스크의 안쪽
        soft = np.where(mk, np.where(inner, 1.0, 0.5 if feather > 0 else 1.0), 0.0).astype(np.float32)
        soft = soft[:, :, None]
        if prefill == "rowblend":  # LaMa 결과와 행 평균 채움을 50:50 혼합
            out = ((out.astype(np.float32) + pre.astype(np.float32)) / 2)
        comp = (out.astype(np.float32) * soft + comp.astype(np.float32) * (1 - soft))
        comp = np.clip(comp, 0, 255).astype(np.uint8)
    m = mask > 127
    result = rgba.copy()          # 마스크 밖은 원본 RGBA 바이트 그대로
    result[m, :3] = comp[m]       # 마스크 안만 RGB 교체, 알파는 원본 유지
    stats["outside_diff"] = int((result[~m] != rgba[~m]).any(axis=1).sum())
    bb = bright_text(rgba)[m]
    ba = bright_text(result)[m] & bb   # 원본 글자색이던 픽셀이 여전히 밝은 무채색인 것만
    stats["bright_before"], stats["bright_after"] = int(bb.sum()), int(ba.sum())
    stats["residual"] = float(ba.sum() / max(1, bb.sum()))
    return Image.fromarray(result, "RGBA"), stats


def bright_text(rgba):
    """밝은 무채색(흰 글자색) 픽셀."""
    rgb = rgba[:, :, :3].astype(np.int16)
    return (rgb.min(axis=2) >= 190) & ((rgb.max(axis=2) - rgb.min(axis=2)) <= 40) & (rgba[:, :, 3] > 16)


def is_text_only_label(rgba, panel_ratio=0.45, left_ratio=0.30):
    """투명 배경 글자뿐인 라벨 판정(둘 다 만족해야 라벨 → 제외):
    (1) 불투명(alpha>128) 영역의 가장 큰 연결 덩어리가 bbox 면적의 panel_ratio 미만(= 단단한 패널/버튼 면 없음)
    (2) 글자 마스크(border=0, grow=3)를 뺀 불투명 영역이 bbox 면적의 left_ratio 미만(= 글자 밖에 지울 배경이 없음)
    반환 (라벨여부, 큰덩어리비율, 글자밖불투명비율)"""
    op = (rgba[:, :, 3] > 128).astype(np.uint8)
    ys, xs = np.where(op > 0)
    if len(xs) == 0:
        return True, 0.0, 0.0
    area = float((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1))
    n, lab, st, _ = cv2.connectedComponentsWithStats(op, connectivity=8)
    big = st[1:, cv2.CC_STAT_AREA].max() / area
    left = float(((op > 0) & ~(auto_mask(rgba, 3, border=0) > 127)).sum()) / area
    return (big < panel_ratio and left < left_ratio), float(big), left


def make_sheets(src, res, mdir, sdir, names, per=12):
    """원본|마스크|결과 행 12개씩 시트. 배경은 녹색 체커 대신 단색."""
    from PIL import ImageDraw
    sdir.mkdir(parents=True, exist_ok=True)
    for k in range(0, len(names), per):
        chunk = names[k:k + per]
        rows = []
        for n in chunk:
            o = Image.open(src / n).convert("RGBA")
            m = Image.open(mdir / n).convert("L").convert("RGBA")
            r = Image.open(res / n).convert("RGBA")
            sc = max(1, min(3, 300 // o.width))
            rows.append((n, [im.resize((o.width * sc, o.height * sc), Image.NEAREST) for im in (o, m, r)]))
        W = max(sum(i.width for i in ims) + 40 for _, ims in rows)
        H = sum(max(i.height for i in ims) + 14 for _, ims in rows)
        sheet = Image.new("RGBA", (W, H), (90, 140, 90, 255))
        d = ImageDraw.Draw(sheet)
        y = 0
        for n, ims in rows:
            d.text((2, y), n, fill=(255, 255, 255, 255)); y += 12
            x = 0
            for im in ims:
                sheet.alpha_composite(im, (x, y)); x += im.width + 20
            y += max(i.height for i in ims) + 2
        sheet.convert("RGB").save(sdir / f"sheet_{k // per + 1:03d}.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", required=True, help="입력 PNG 또는 폴더")
    ap.add_argument("--out", required=True, help="출력 PNG 또는 폴더")
    ap.add_argument("--mask", help="마스크 PNG/폴더(흰색=지움). 파일명은 입력과 동일")
    ap.add_argument("--auto-mask", action="store_true", help="마스크가 없으면 자동 생성")
    ap.add_argument("--grow", type=int, default=3, help="자동 마스크 팽창 px (기본 3)")
    ap.add_argument("--thr", type=int, default=40, help="자동 마스크 대비 임계값")
    ap.add_argument("--border", type=int, default=6, help="가장자리 N px(테두리 장식)는 자동 마스크에서 제외 (기본 6)")
    ap.add_argument("--inset", type=float, default=0.0, help="추가로 제외할 테두리 비율(불투명 bbox 짧은 변 기준)")
    ap.add_argument("--prefill", choices=["none", "rowmedian", "rowblend", "patch"], default="none", help="LaMa 전 행 중간값 채우기")
    ap.add_argument("--siblings", action="store_true", help="같은 아틀라스·크기 형제 픽셀로 먼저 채움")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="atlas,w,h 그룹 정보 manifest.json")
    ap.add_argument("--sib-tol", type=int, default=4, help="형제 배경 일치 허용 오차(RGBA 채널 최대차)")
    ap.add_argument("--target-size", type=int, default=192)
    ap.add_argument("--save-mask", help="사용한 마스크를 이 폴더에 저장")
    ap.add_argument("--list", help="처리할 파일명 목록 텍스트(한 줄에 하나)")
    ap.add_argument("--skip-existing", action="store_true")
    ap.add_argument("--ocr", help="ocr.json: 이 목록의 파일만 처리하고 투명 라벨은 제외(report에 기록)")
    ap.add_argument("--report", help="처리 결과 JSON 리포트 경로")
    ap.add_argument("--sheets", help="원본|마스크|결과 비교 시트 폴더(시트당 12장)")
    ap.add_argument("--residual-thr", type=float, default=0.10, help="잔상 비율 기준(마스크 안 원본 밝은 글자색 중 남은 비율)")
    a = ap.parse_args()

    inp, out = Path(a.inp), Path(a.out)
    allfiles = [inp] if inp.is_file() else sorted(inp.glob("*.png"))
    files = allfiles
    if a.list:
        want = {l.strip() for l in Path(a.list).read_text(encoding="utf-8").splitlines() if l.strip()}
        files = [f for f in files if f.name in want or f.stem in want]
    if a.ocr:
        names = {e["name"] for e in json.loads(Path(a.ocr).read_text(encoding="utf-8"))}
        files = [f for f in files if f.name in names]
    if not (inp.is_file() and out.suffix):
        out.mkdir(parents=True, exist_ok=True)
    mdir = Path(a.mask) if a.mask else None
    if a.save_mask:
        Path(a.save_mask).mkdir(parents=True, exist_ok=True)

    def get_mask(f, rgba):
        if mdir is not None:
            mp = mdir / f.name if mdir.is_dir() else mdir
            if mp.exists():
                return np.array(Image.open(mp).convert("L").resize((rgba.shape[1], rgba.shape[0]), Image.NEAREST))
        if a.auto_mask:
            return auto_mask(rgba, a.grow, a.thr, border=a.border, inset_frac=a.inset)
        return None

    groups = {}
    if a.siblings:
        mf = Path(a.manifest)
        if mf.exists():
            avail = {f.name for f in allfiles}
            for e in json.loads(mf.read_text(encoding="utf-8")):
                if e["name"] in avail:
                    groups.setdefault((e["atlas"], e["w"], e["h"]), []).append(e["name"])
        else:
            print(f"[경고] manifest 없음: {mf}", file=sys.stderr)
    name2grp = {n: k for k, v in groups.items() for n in v}
    cache = {}

    def load(name):
        if name not in cache:
            rgba = np.array(Image.open(inp / name if inp.is_dir() else inp).convert("RGBA"))
            cache[name] = (rgba, get_mask(Path(name), rgba))
        return cache[name]

    lama, dev = load_lama()
    print(f"device={dev} files={len(files)} prefill={a.prefill} siblings={a.siblings}", flush=True)
    t_all = time.time()
    rep = {"processed": 0, "excluded_labels": [], "no_mask": [], "residual": [], "outside_diff_total": 0,
           "outside_diff_nonzero": [], "params": {k: getattr(a, k) for k in ("grow", "thr", "border", "inset", "prefill", "siblings", "residual_thr")}}
    done = []
    for i, f in enumerate(files, 1):
        dst = (out / f.name) if not (inp.is_file() and out.suffix) else out
        if a.skip_existing and dst.exists():
            continue
        rgba, mask = load(f.name) if inp.is_dir() else (np.array(Image.open(f).convert("RGBA")), None)
        if not inp.is_dir():
            mask = get_mask(f, rgba)
        if mask is None:
            print(f"[skip] 마스크 없음: {f.name}", file=sys.stderr)
            continue
        if a.ocr:
            lab, big, left = is_text_only_label(rgba)
            if lab:
                rep["excluded_labels"].append({"name": f.name, "big": round(big, 2), "left": round(left, 2)})
                continue
        if int((mask > 127).sum()) == 0:
            rep["no_mask"].append(f.name)
        if a.save_mask:
            Image.fromarray(mask).save(Path(a.save_mask) / f.name)
        sibs = []
        g = name2grp.get(f.name)
        if g:
            for n in groups[g]:
                if n != f.name:
                    s_rgba, s_mask = load(n)
                    if s_mask is not None:
                        sibs.append((s_rgba, s_mask))
        t = time.time()
        res, st = erase(lama, rgba, mask, a.target_size, prefill=a.prefill, sibs=sibs, tol=a.sib_tol)
        res.save(dst)
        rep["processed"] += 1
        rep["outside_diff_total"] += st["outside_diff"]
        if st["outside_diff"]:
            rep["outside_diff_nonzero"].append(f.name)
        if st["bright_before"] >= 20 and st["residual"] > a.residual_thr:
            rep["residual"].append({"name": f.name, "ratio": round(st["residual"], 3), "bright_before": st["bright_before"], "bright_after": st["bright_after"]})
        done.append(f.name)
        pct = 100 * st["sib_px"] / max(1, st["mask_px"])
        print(f"[{i}/{len(files)}] {f.name} {rgba.shape[1]}x{rgba.shape[0]} {time.time()-t:.2f}s "
              f"mask={st['mask_px']} 형제채움={pct:.0f}%({st['sib_used']}장)", flush=True)
    rep["excluded_count"] = len(rep["excluded_labels"])
    rep["elapsed_sec"] = round(time.time() - t_all, 1)
    rep["outside_diff_zero_verified"] = rep["outside_diff_total"] == 0
    if a.report:
        Path(a.report).write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.sheets and a.save_mask:
        make_sheets(inp, out, Path(a.save_mask), Path(a.sheets), done)
    print(f"total {time.time()-t_all:.1f}s processed={rep['processed']} excluded={rep['excluded_count']} "
          f"residual={len(rep['residual'])} outside_diff={rep['outside_diff_total']}")


if __name__ == "__main__":
    main()
