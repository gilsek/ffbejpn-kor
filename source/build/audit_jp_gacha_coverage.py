"""Read-only banner/master audit; writes evidence, never regenerates the overlay."""
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_jp_banners as M
import ffbe_gacha as G


def main():
    jp, _, _ = M.jp_masters()
    jp_by = {r['3HriTp6B']: r for r in jp}
    engine = {r['3HriTp6B']: r for r in map(json.loads, (M.STATIC / 'mst_decoded/F_UNIT_MST.ndjson').read_text(encoding='utf-8').splitlines())}
    names = {r['key'].removeprefix('MST_UNIT_NAME_'): r['v'][0] for r in map(json.loads, (M.STATIC / 'text_decoded/F_TEXT_UNITS_NAME.ndjson').read_text(encoding='utf-8').splitlines())}
    original = {str(b['id']): b for b in G.all_banners()}
    authored = json.loads((M.OVERLAY / 'gacha_authored.json').read_text(encoding='utf-8'))['banners']
    current = {str(b['id']): b for b in authored}
    report = json.loads((M.REPORT / 'report.json').read_text(encoding='utf-8'))
    audit = []
    for a in report['preview_audit']:
        if a['basis'] != 'featured unit absent from JP-compatible pool':
            continue
        b = original[a['id']]
        featured = [str(u) for u in (b.get('community') or {}).get('unit_ids') or []]
        if isinstance(b.get('pool'), dict):
            featured += [str(u) for t in b['pool'].get('tiers') or [] for u in t.get('featured') or []]
        rows = []
        keep = {str(r['unit_id']) for r in current[a['id']]['pool']}
        for u in dict.fromkeys(featured):
            family = [v for v in jp_by if v[:-1] == u[:-1]]
            supported = [v for v in family if v in engine and int(jp_by[v].get('9fW0TePj') or 0) >= 5]
            reason = ('absent_jp_family' if not family else 'no_engine_form_ge5' if not supported
                      else 'low_rarity_source_outside_pool' if u in jp_by and int(jp_by[u].get('9fW0TePj') or 0) < 5
                      else 'family_match_requires_identity_check' if u not in jp_by
                      else 'supported_family_outside_banner_pool')
            rows.append({'id': u, 'english': names.get(u, ''), 'reason': reason,
                         'jp_forms': [{'id': v, 'name': jp_by[v].get('G4L0YIB2'), 'rarity': jp_by[v].get('9fW0TePj'), 'engine': v in engine, 'in_pool': v in keep} for v in family]})
        audit.append({'id': a['id'], 'banner': a['banner'], 'named_units': (b.get('community') or {}).get('units'), 'featured': rows})
    eligible = set()
    for b in authored:
        if isinstance(b.get('pool'), list):
            eligible.update(str(r['unit_id']) for r in b['pool'] if isinstance(r, dict) and r.get('unit_id'))
    missing = [{'id': u, 'name': r.get('G4L0YIB2'), 'rarity': r.get('9fW0TePj'), 'title': r.get('taQ69cIx'), 'engine': u in engine}
               for u, r in jp_by.items() if str(r.get('9fW0TePj', '')).isdigit() and int(r['9fW0TePj']) >= 5 and not any(v[:-1] == u[:-1] for v in eligible)]
    family_min = {}
    for u, r in jp_by.items():
        if u in engine and str(r.get('9fW0TePj', '')).isdigit():
            family_min[u[:-1]] = min(int(r['9fW0TePj']), family_min.get(u[:-1], 99))
    base_coverage = {}
    for rarity in (5, 7):
        families = {u[:-1] for u, r in jp_by.items() if u in engine and str(r.get('9fW0TePj')) == str(rarity) and family_min[u[:-1]] == rarity}
        base_coverage[str(rarity)] = {'families': len(families), 'not_in_current_list': sorted(families - {u[:-1] for u in eligible})}
    result = {'identity_limit': 'Numeric family = generator id[:-1], not a verified cross-region character identity. Coverage does not reconstruct any omitted original banner pool.',
              'base_family_coverage': base_coverage,
              'empty_previews': audit, 'featured_reasons': dict(Counter(r['reason'] for a in audit for r in a['featured'])),
              'banner_reason_sets': dict(Counter(','.join(sorted({r['reason'] for r in a['featured']})) for a in audit)),
              'jp_units': len(jp), 'engine_units': len(engine), 'eligible_families': len({u[:-1] for u in eligible}),
              'jp_forms_ge5_without_eligible_family': missing, 'unmatched_art': report['unmatched_jp']}
    dest = M.REPORT / 'coverage-audit.json'
    dest.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf-8')
    print(json.dumps({k: (len(v) if isinstance(v, list) else v) for k, v in result.items()}, ensure_ascii=False))
    print('unmatched archives:', dict(Counter(json.loads((M.ROOT / 'build/jp_gacha_art.json').read_text(encoding='utf-8'))[n]['cpk'] for n in report['unmatched_jp'])))


if __name__ == '__main__':
    main()
