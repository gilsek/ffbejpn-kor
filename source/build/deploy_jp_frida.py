"""Assemble/push JP hooks; --trace appends read-only gacha diagnostics, --restart restarts the app.

Dev builds keep the bundle on /data/local/tmp. Release builds (build/jp_offline_build.py --release)
embed a bundle built by build_bundle(release=True) as lib/arm64-v8a/libexviustest.js.so; that bundle
uses the app-private files/ paths and turns the debug/art staging hooks off.
"""
import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEV_NAMES = ['jp_summon_menu.js', 'jp_title_menu.js', 'jp_offline.js', 'jp_parade_res.js', 'jp_orientation.js',
             'jp_hide_explore.js', 'jp_clock.js', 'jp_hide_lump.js', 'jp_encount.js', 'jp_lb_index.js',
             'jp_profile_hangul.js', 'jp_seal_guard.js', 'jp_vc_guard.js', 'jp_mst_slice.js', 'jp_ui_override.js',
             'jp_icon_fallback.js', 'jp_event_menu.js', 'jp_rm_noscene.js', 'jp_talk_wrap.js', 'jp_stepup_tab.js',
             'jp_raid_result_scroll.js']
# Never embedded in the release bundle: dev-only slicing/clock/dump/diagnostic scripts.
RELEASE_EXCLUDE = {'jp_mst_slice.js', 'jp_clock.js', 'jp_sound_trace.js', 'jp_sound_check.js',
                   'jp_mst_timing.js', 'jp_cpk_dump.js', 'jp_gate_tab_trace.js', 'jp_find_miss.js',
                   'jp_gacha_trace.js'}
DEV_PKG = 'com.exvius.jpkorean.app'
# Release builds install beside the dev app under their own applicationId (same length: rename_package.py patches in place).
RELEASE_PKG = 'com.exvius.offline.jpkr'
RELEASE_FILES = '/data/data/' + RELEASE_PKG + '/files/'


def bundle_names(release=False, trace=False, sound_trace=False, sound_check=False, mst_timing=False,
                 cpk_dump=False, gate_trace=False, find_miss=False):
    names = [n for n in DEV_NAMES if not (release and n in RELEASE_EXCLUDE)]
    if not release:
        if trace:
            names.append('jp_gacha_trace.js')
        if sound_trace:
            names.append('jp_sound_trace.js')
        if sound_check:
            names.append('jp_sound_check.js')
        if mst_timing:
            names.append('jp_mst_timing.js')
        if cpk_dump:
            names.append('jp_cpk_dump.js')
        if gate_trace:
            names.append('jp_gate_tab_trace.js')
        if find_miss:
            names.append('jp_find_miss.js')
    return names


def build_bundle(release=False, loading_trace=False, trace=False, sound_trace=False, sound_check=False,
                 mst_timing=False, cpk_dump=False, gate_trace=False, find_miss=False):
    """Concatenate the hook scripts; release mode rewrites the /data/local/tmp paths."""
    names = bundle_names(release, trace, sound_trace, sound_check, mst_timing, cpk_dump, gate_trace, find_miss)
    source = '\n'.join((ROOT / 'build/frida' / name).read_text(encoding='utf-8') for name in names)
    if loading_trace:
        source = source.replace('const TRACE_INSTALL = false;', 'const TRACE_INSTALL = true;')
    # story nodes with no scene file: jp_rm_noscene.js clears them on entry (list from make_jp_rm_noscene.py)
    noscene = json.loads((ROOT / 'build/engine_overlay/jp_rm_noscene.json').read_text(encoding='utf-8'))['missions']
    marker = '/*__RM_NOSCENE__*/[]'
    if source.count(marker) != 1:
        raise ValueError('jp_rm_noscene marker not found exactly once')
    source = source.replace(marker, json.dumps(sorted(int(x) for x in noscene)))
    if release:
        source = source.replace("const LOCAL = '/data/local/tmp/ffbe/';", "const LOCAL = '" + RELEASE_FILES + "ffbe/';")
        source = source.replace('const DEBUG = true;', 'const DEBUG = false;')
        source = source.replace('const ART_DEV_OVERRIDE = true;', 'const ART_DEV_OVERRIDE = false;')
        source = source.replace("const FLAT = '/data/local/tmp/ffbe/';", "const FLAT = '" + RELEASE_FILES + "ffbe/';")
        source = source.replace("const DIR = '/data/local/tmp/ffbe/ui_ko/';", "const DIR = '" + RELEASE_FILES + "exvius/ui_ko/';")
        # Any leftover mention (mostly comments) must not ship the dev path.
        source = source.replace('/data/local/tmp/ffbe/', RELEASE_FILES + 'ffbe/')
        source = source.replace('/data/local/tmp', RELEASE_FILES.rstrip('/'))
        if '/data/local/tmp' in source:
            raise ValueError('release bundle still mentions /data/local/tmp')
        source = source.replace('/data/data/' + DEV_PKG + '/', '/data/data/' + RELEASE_PKG + '/')
        if DEV_PKG in source:
            raise ValueError('release bundle still mentions the dev package ' + DEV_PKG)
    return source


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace', action='store_true')
    parser.add_argument('--loading-trace', action='store_true', help='읽기 전용 설치 추적 활성화')
    parser.add_argument('--sound-trace', action='store_true', help='읽기 전용 사운드 추적(jp_sound_trace.js) 추가')
    parser.add_argument('--sound-check', action='store_true', help='빠진 소리 기록(jp_sound_check.js) 추가 -> files/exvius/sound_check.log')
    parser.add_argument('--mst-timing', action='store_true', help='로그인 마스터 로딩 시간 측정(jp_mst_timing.js) 추가')
    parser.add_argument('--cpk-dump', action='store_true', help='시험용: spdungeon CPK 배너 원본 덤프(jp_cpk_dump.js) 추가 + 목록을 기기 플래그 파일로 푸시')
    parser.add_argument('--cpk-dump-list', default='build/out/seal_room/banner_files.tsv', help='--cpk-dump 목록(cpk, file, size[, pin]) 경로, 저장소 기준')
    parser.add_argument('--cpk-dump-off', action='store_true', help='기기의 덤프 플래그 파일(/data/local/tmp/ffbe/dump_banners) 삭제')
    parser.add_argument('--cpk-dump-clean', action='store_true', help='앱 내부 files/cpk_dump 삭제용 1회 실행(jp_cpk_dump.js + 기기 dump_cleanup 플래그)')
    parser.add_argument('--gate-trace', action='store_true', help='읽기 전용: 차원의 틈새 탭 필터 비교값 기록(jp_gate_tab_trace.js)')
    parser.add_argument('--find-miss', action='store_true', help='읽기 전용: 찾지 못한 파일 이름 기록(jp_find_miss.js), 빈 텍스처 크래시 진단용')
    parser.add_argument('--release-out', type=Path, help='배포용 묶음을 이 파일로 쓴다(푸시하지 않음)')
    parser.add_argument('--restart', action='store_true')
    parser.add_argument('--no-push', action='store_true')
    args = parser.parse_args()
    if args.release_out:
        data = build_bundle(release=True)
        args.release_out.parent.mkdir(parents=True, exist_ok=True)
        args.release_out.write_text(data, encoding='utf-8')
        print('release bundle:', len(data), 'bytes ->', args.release_out)
        return
    source = build_bundle(release=False, loading_trace=args.loading_trace, trace=args.trace,
                          sound_trace=args.sound_trace, sound_check=args.sound_check,
                          mst_timing=args.mst_timing, cpk_dump=args.cpk_dump,
                          gate_trace=args.gate_trace, find_miss=args.find_miss)
    script = ROOT / 'build/out/jp_offline/frida_script.js'
    script.write_text(source, encoding='utf-8')
    subprocess.run(['node', '--check', str(script)], check=True)
    if not args.no_push:
        subprocess.run(['adb', 'push', str(script), '/data/local/tmp/frida_script.js'], check=True)
        if args.cpk_dump:  # jp_cpk_dump.js runs only while this list file exists on the device
            subprocess.run(['adb', 'push', str(ROOT / args.cpk_dump_list), '/data/local/tmp/ffbe/dump_banners'], check=True)
        if args.cpk_dump_clean:  # one-shot: jp_cpk_dump.js deletes files/cpk_dump while this flag exists
            subprocess.run(['adb', 'shell', 'touch', '/data/local/tmp/ffbe/dump_cleanup'], check=True)
    if args.cpk_dump_off:
        subprocess.run(['adb', 'shell', 'rm', '-f', '/data/local/tmp/ffbe/dump_banners', '/data/local/tmp/ffbe/dump_cleanup'], check=True)
    if args.restart:
        if args.no_push:
            parser.error('--restart requires pushing the script')
        subprocess.run(['adb', 'shell', 'am', 'force-stop', 'com.exvius.jpkorean.app'], check=True)
        subprocess.run(['adb', 'shell', 'am', 'start', '-n', 'com.exvius.jpkorean.app/com.square_enix.ffbejpn.Lapis'], check=True)


if __name__ == '__main__':
    main()
