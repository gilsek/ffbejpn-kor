"""Run Japanese OCR over build/out/sprite_work/in/*.png.

Supports:
- Per-file caching in build/out/sprite_work/cache/
- Parallel chunks via --chunk-id and --num-chunks
- Real-time progress reporting

usage: python -u tools/run_sprite_ocr.py [--chunk-id 0] [--num-chunks 4] [--merge]
"""
import argparse
import io
import json
import os
import re
import sys
import time
from pathlib import Path
from PIL import Image
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
WORK_DIR = ROOT / 'build/out/sprite_work'
IN_DIR = WORK_DIR / 'in'
CACHE_DIR = WORK_DIR / 'cache'
TARGETS_DIR = ROOT / 'build/out/sprite_targets'
MODELS_DIR = ROOT / 'build/out/models'

JP_CHAR_RE = re.compile(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]')
NON_JP_RE = re.compile(r'^[0-9A-Za-z\s\.,:;!\?_/\-\+\*=\(\)\[\]#%&]+$')


def load_engine():
    from rapidocr_onnxruntime import RapidOCR
    return RapidOCR(
        rec_model_path=str(MODELS_DIR / 'japan_PP-OCRv3_rec_infer.onnx'),
        rec_keys_path=str(MODELS_DIR / 'japan_dict.txt'),
        intra_op_num_threads=2,
        inter_op_num_threads=2,
    )


def ocr_file(engine, path):
    im = Image.open(path).convert('RGBA')
    bg = Image.new('RGB', im.size, (58, 58, 64))
    bg.paste(im, (0, 0), im)
    res, _ = engine(np.array(bg))
    if not res:
        return {'text': '', 'score': 0.0, 'w': im.width, 'h': im.height}
    texts = []
    scores = []
    for box, text, score in res:
        clean = text.strip()
        if clean:
            texts.append(clean)
            scores.append(float(score))
    return {
        'text': ''.join(texts),
        'score': float(sum(scores) / len(scores)) if scores else 0.0,
        'w': im.width,
        'h': im.height
    }


def run_chunk(chunk_id, num_chunks):
    sys.stdout.reconfigure(encoding='utf-8')
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    all_files = sorted(IN_DIR.glob('*.png'))
    chunk_files = [f for i, f in enumerate(all_files) if i % num_chunks == chunk_id]
    total = len(chunk_files)
    print(f'[Chunk {chunk_id}/{num_chunks}] Total files to process: {total}', flush=True)

    engine = load_engine()
    t0 = time.time()
    done = 0
    skipped = 0

    for idx, f in enumerate(chunk_files):
        cfile = CACHE_DIR / f'{f.name}.json'
        if cfile.exists():
            skipped += 1
            done += 1
            continue

        res = ocr_file(engine, f)
        cfile.write_text(json.dumps(res, ensure_ascii=False), encoding='utf-8')
        done += 1

        if (idx + 1) % 50 == 0 or (idx + 1) == total:
            elapsed = time.time() - t0
            rate = (done - skipped) / max(elapsed, 0.001)
            print(f'[Chunk {chunk_id}/{num_chunks}] {done}/{total} done ({skipped} cached, {rate:.1f} it/s)', flush=True)

    print(f'[Chunk {chunk_id}/{num_chunks}] Completed in {time.time() - t0:.1f}s.', flush=True)


def load_records():
    idx_path = ROOT / 'build/out/sprite_sheets/index.json'
    rec_path = TARGETS_DIR / 'records.txt'
    records_map = {}
    if idx_path.exists() and rec_path.exists():
        idx = json.loads(idx_path.read_text(encoding='utf-8'))
        for line in rec_path.read_text(encoding='utf-8').splitlines():
            p = line.split('|')
            if len(p) == 4:
                sheet, cell, ja, ko = p[0].strip(), int(p[1].strip()), p[2].strip(), p[3].strip()
                if sheet in idx and cell - 1 < len(idx[sheet]):
                    spr_name = idx[sheet][cell - 1]
                    records_map[spr_name] = (ja, ko)
    return records_map


def load_glossary():
    glossary = {}
    gpath = WORK_DIR / 'glossary.tsv'
    if gpath.exists():
        for line in gpath.read_text(encoding='utf-8').splitlines():
            p = line.split('\t')
            if len(p) >= 2 and p[0].strip() and p[1].strip():
                glossary[p[0].strip()] = p[1].strip()
    return glossary


def merge_and_generate_ocr_json():
    sys.stdout.reconfigure(encoding='utf-8')
    print('Merging OCR cache and generating ocr.json...', flush=True)
    records_map = load_records()
    glossary = load_glossary()
    all_files = sorted(IN_DIR.glob('*.png'))

    # Collect cache
    ocr_results = {}
    missing_count = 0
    for f in all_files:
        cfile = CACHE_DIR / f'{f.name}.json'
        if cfile.exists():
            ocr_results[f.name] = json.loads(cfile.read_text(encoding='utf-8'))
        else:
            missing_count += 1

    if missing_count > 0:
        print(f'Warning: {missing_count} files not yet processed in cache!', flush=True)

    items = []
    
    # Track ja -> ko usage to enforce consistency
    ja_to_ko = dict(glossary)
    for spr_name, (ja, ko) in records_map.items():
        if ja not in ja_to_ko:
            ja_to_ko[ja] = ko

    # Suffixes for paired buttons
    pair_suffixes = ['_on.png', '_off.png', '_s1.png', '_s2.png', '_1.png', '_2.png', '_3.png', '_press.png', '_selected.png', '_dis.png']

    for f in all_files:
        fname = f.name
        ocr_data = ocr_results.get(fname, {'text': '', 'score': 0.0, 'w': 0, 'h': 0})
        text = ocr_data.get('text', '').strip()
        score = ocr_data.get('score', 0.0)
        w = ocr_data.get('w', 0)
        h = ocr_data.get('h', 0)

        # 1. Human ground truth
        if fname in records_map:
            ja, ko = records_map[fname]
            items.append({
                'name': fname,
                'ja': ja,
                'ko': ko,
                'uncertain': False
            })
            continue

        # 2. Check if OCR text has Japanese characters
        if not text:
            continue
        if NON_JP_RE.match(text):
            continue
        if not JP_CHAR_RE.search(text):
            continue

        # If it's a known non-JP symbol or misrecognition (e.g. single weird kanji on an icon)
        uncertain = False
        if score < 0.65 or len(text) <= 1:
            uncertain = True

        ko = ja_to_ko.get(text, '')
        if not ko:
            uncertain = True

        items.append({
            'name': fname,
            'ja': text,
            'ko': ko,
            'uncertain': uncertain
        })

    # Consistency pass for paired sprites:
    # If sprite A has ja/ko and sprite B is the companion button (e.g. button_1 and button_2), unify ja and ko
    item_by_name = {it['name']: it for it in items}
    for it in list(items):
        name = it['name']
        for sfx in pair_suffixes:
            if name.endswith(sfx):
                base = name[:-len(sfx)]
                # check companion suffixes
                for other_sfx in pair_suffixes:
                    comp_name = base + other_sfx
                    if comp_name != name and comp_name in item_by_name:
                        comp = item_by_name[comp_name]
                        # Propagate human-verified or known translation
                        if not it['uncertain'] and comp['uncertain']:
                            comp['ja'] = it['ja']
                            comp['ko'] = it['ko']
                            comp['uncertain'] = False
                        elif it['uncertain'] and not comp['uncertain']:
                            it['ja'] = comp['ja']
                            it['ko'] = comp['ko']
                            it['uncertain'] = False
                        elif it['ko'] and not comp['ko']:
                            comp['ko'] = it['ko']
                        elif comp['ko'] and not it['ko']:
                            it['ko'] = comp['ko']
                break

    # Final sort
    items.sort(key=lambda x: x['name'])
    
    out_path = WORK_DIR / 'ocr.json'
    out_path.write_text(json.dumps(items, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'Saved {len(items)} items to {out_path}', flush=True)

    uncertain_count = sum(1 for it in items if it['uncertain'])
    print(f'Summary: Total target sprites = {len(items)}, Uncertain = {uncertain_count}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--chunk-id', type=int, default=0)
    parser.add_argument('--num-chunks', type=int, default=1)
    parser.add_argument('--merge', action='store_true')
    args = parser.parse_args()

    if args.merge:
        merge_and_generate_ocr_json()
    else:
        run_chunk(args.chunk_id, args.num_chunks)
