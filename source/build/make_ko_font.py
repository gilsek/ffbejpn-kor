"""Korean game font: Binggrae (the Memorial Edition font) + the JP font's glyphs Binggrae lacks (kanji etc.).

The JP client draws its text with assets/font/TT_RodinCattleya-B.ttf and FOT-SkipStd-E.otf (6,7xx kanji, no Hangul).
Binggrae (from the Memorial Edition Korean APK) has all 11,172 Hangul syllables but no kanji, so untranslated
Japanese text would lose its kanji. Until the translation removes them (the final goal), merge both:
  1. Binggrae CFF outlines -> TrueType quadratic (cu2qu), so both share one glyf table.
  2. Every code point of the JP font that Binggrae does not map gets the JP glyph (decomposed, unhinted)
     with its advance; Binggrae keeps its own Latin/kana/Hangul.
Output: build/out/ko_font/ko_game_font.ttf (jp_offline_build.py copies it over both assets/font files).

usage: python -E -P build/make_ko_font.py [--binggrae <ttf/otf or Memorial APK>] [--jp <JP TT_RodinCattleya-B.ttf>]
(fontTools from the user site, hence -E -P rather than -I.)
"""
import argparse, io, zipfile
from pathlib import Path
from fontTools.ttLib import TTFont, newTable
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.pens.recordingPen import DecomposingRecordingPen
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parents[1]
MEMORIAL_APK = ROOT.parent / 'ffbe_offline_modfix/artifacts/korean-display-test/ffbe-korean-binggrae.apk'
JP_FONT = ROOT / 'build/out/jp_offline/dec/assets/font/TT_RodinCattleya-B.ttf'
OUT = ROOT / 'build/out/ko_font/ko_game_font.ttf'
UI_VF = Path('C:/Windows/Fonts/NotoSansKR-VF.ttf')
UI_OUT = ROOT / 'build/out/ko_font/ko_ui_font.ttf'


def load_binggrae(path):
    path = Path(path)
    if path.suffix == '.apk':
        with zipfile.ZipFile(path) as z:
            return TTFont(io.BytesIO(z.read('assets/font/TT_RodinCattleya-B.ttf')))
    return TTFont(path)


def cff_to_glyf(font, max_err=1.0):
    """The fontTools otf2ttf recipe: quadratic outlines, glyf/loca instead of CFF."""
    order = font.getGlyphOrder()
    gs = font.getGlyphSet()
    glyphs = {}
    for name in order:
        pen = TTGlyphPen(None)
        gs[name].draw(Cu2QuPen(pen, max_err, reverse_direction=True))
        glyphs[name] = pen.glyph()
    del font['CFF ']
    if 'VORG' in font:
        del font['VORG']
    glyf = font['glyf'] = newTable('glyf')
    glyf.glyphOrder = order
    glyf.glyphs = glyphs
    font['loca'] = newTable('loca')
    maxp = font['maxp']
    maxp.tableVersion = 0x00010000
    for attr in ('maxZones', 'maxTwilightPoints', 'maxStorage', 'maxFunctionDefs', 'maxInstructionDefs',
                 'maxStackElements', 'maxSizeOfInstructions', 'maxComponentElements'):
        setattr(maxp, attr, 0)
    maxp.maxZones = 1
    maxp.maxComponentDepth = 0
    font['head'].glyphDataFormat = 0
    post = font['post']
    post.formatType = 2.0
    post.extraNames = []
    post.mapping = {}
    post.glyphOrder = order
    font.sfntVersion = '\x00\x01\x00\x00'


# Size tuning (2026-11-10, user chose option C from build/out/ko_font/variants/preview.png): the untouched Binggrae
# glyphs made one-line JP texts wrap to two lines. Measured against TT_RodinCattleya-B (units/em 1000): line height
# 1343 vs 1140, digits 576-693 wide vs 500, Hangul 980 vs kana/kanji 1000.
#   * line metrics (hhea, OS/2 typo/win) = the JP font's
#   * Binggrae glyphs (not the jp.* kanji) scaled to SCALE in x and y, advances too -> ~8% more per line
#   * digits 0-9 to the JP width 500 (stat columns line up as in the original), same SCALE in y
SCALE = 0.92
# 2026-11-14 사용자 요청: 모든 글자(빙그레·일판 한자·숫자)를 10% 더 작게. 줄 높이(hhea/OS2)는 그대로.
SIZE = 0.90


def tune(font, jp, dy=0):
    from fontTools.pens.transformPen import TransformPen
    hh, jh = font['hhea'], jp['hhea']
    hh.ascent, hh.descent, hh.lineGap = jh.ascent, jh.descent, jh.lineGap
    o, jo = font['OS/2'], jp['OS/2']
    o.usWinAscent, o.usWinDescent = jo.usWinAscent, jo.usWinDescent
    o.sTypoAscender, o.sTypoDescender, o.sTypoLineGap = jo.sTypoAscender, jo.sTypoDescender, jo.sTypoLineGap
    glyf, hmtx, gs = font['glyf'], font['hmtx'], font.getGlyphSet()
    digits = {font.getBestCmap()[c] for c in range(0x30, 0x3A)}
    for name in font.getGlyphOrder():
        if name not in hmtx.metrics:
            continue
        adv, lsb = hmtx[name]
        if name.startswith('jp.'):
            ax = ay = SIZE
        else:
            ax = (500 / adv if name in digits and adv else SCALE) * SIZE
            ay = SCALE * SIZE
        pen = TTGlyphPen(gs)
        gs[name].draw(TransformPen(pen, (ax, 0, 0, ay, 0, dy)))
        glyf[name] = pen.glyph()
        hmtx[name] = (int(round(adv * ax)), int(round(lsb * ax)))


def merge_jp_tune_and_save(base, jp, out_path, font_names, *, min_cp=0, dy=0):
    """Merge missing JP glyphs (e.g. kanji) into base font, apply U+201A comma alias, tune metrics, and save."""
    if base['head'].unitsPerEm != jp['head'].unitsPerEm:
        raise SystemExit('unitsPerEm differs; scale first')
    base_cmap = base.getBestCmap()
    jp_cmap = jp.getBestCmap()
    jp_gs = jp.getGlyphSet()
    order = list(base.getGlyphOrder())
    glyf, hmtx = base['glyf'], base['hmtx']
    vmtx = base['vmtx'] if 'vmtx' in base else None
    jp_vmtx = jp['vmtx'] if 'vmtx' in jp else None
    added = {}
    for cp in sorted(jp_cmap):
        if cp < min_cp or cp in base_cmap:
            continue
        src = jp_cmap[cp]
        if src not in added:
            name = 'jp.' + src
            rec = DecomposingRecordingPen(jp_gs)
            jp_gs[src].draw(rec)
            pen = TTGlyphPen(None)
            rec.replay(pen)
            glyf.glyphs[name] = pen.glyph()
            order.append(name)
            hmtx.metrics[name] = jp['hmtx'].metrics[src]
            if vmtx is not None:
                vmtx.metrics[name] = jp_vmtx.metrics[src] if jp_vmtx and src in jp_vmtx.metrics else (1000, 880)
            added[src] = name
        for table in base['cmap'].tables:
            if table.isUnicode() and (table.format == 12 or cp <= 0xFFFF):
                table.cmap[cp] = added[src]
    # Story rows are "id,text" and the client cuts the text at the next ASCII comma, so build/apply_ko_story.py
    # writes U+201A instead; draw it with the base comma so it looks the same.
    for table in base['cmap'].tables:
        if table.isUnicode():
            table.cmap[0x201A] = base_cmap[0x2C]
    base.setGlyphOrder(order)
    glyf.glyphOrder = order
    base['post'].glyphOrder = order
    for name in base['name'].names:
        if name.nameID in font_names:
            name.string = font_names[name.nameID]
    tune(base, jp, dy=dy)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    base.save(out_path)
    merged = TTFont(out_path)
    cm = merged.getBestCmap()
    rng = lambda a, z: sum(1 for c in cm if a <= c <= z)
    print('added', len(added), 'JP glyphs ->', out_path, out_path.stat().st_size, 'bytes;',
          'glyphs', len(merged.getGlyphOrder()), 'hangul', rng(0xAC00, 0xD7A3), 'kana', rng(0x3040, 0x30FF),
          'kanji', rng(0x4E00, 0x9FFF), 'ascii', rng(0x20, 0x7E))


def build_ui_font(vf_path, jp_path, out_path, weight=750):
    """Instantiate variable NotoSansKR font at Bold weight, strip unused OT tables, and merge missing JP glyphs."""
    vf = TTFont(vf_path)
    base = instancer.instantiateVariableFont(vf, {'wght': weight}, inplace=False)
    for tag in ('GSUB', 'GPOS', 'GDEF', 'BASE', 'STAT', 'HVAR', 'vhea', 'vmtx'):
        if tag in base:
            del base[tag]
    jp = jp_path if isinstance(jp_path, TTFont) else TTFont(jp_path)
    merge_jp_tune_and_save(
        base,
        jp,
        out_path,
        {1: 'NotoSansKR UI', 4: 'NotoSansKR UI', 6: 'NotoSansKRUI'},
        min_cp=0x20,
        dy=int(round(380 * (1 - SCALE * SIZE))),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--binggrae', default=str(MEMORIAL_APK))
    ap.add_argument('--jp', default=str(JP_FONT))
    ap.add_argument('--out', default=str(OUT))
    ap.add_argument('--ui-vf', default=str(UI_VF))
    ap.add_argument('--ui-out', default=str(UI_OUT))
    args = ap.parse_args()
    base = load_binggrae(args.binggrae)
    jp = TTFont(args.jp)
    cff_to_glyf(base)
    merge_jp_tune_and_save(
        base,
        jp,
        args.out,
        {1: 'Binggrae KO', 4: 'Binggrae KO', 6: 'BinggraeKO'},
        min_cp=0,
    )
    if args.ui_out and Path(args.ui_vf).is_file():
        build_ui_font(args.ui_vf, jp, args.ui_out, weight=750)


if __name__ == '__main__':
    main()
