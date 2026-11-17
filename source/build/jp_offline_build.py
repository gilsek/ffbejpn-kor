"""JP 11.0.0 -> offline APK, built the same way as the Global Offline app (Elvlin/exvius-offline).

Mirrors upstream `exvius/android_build.py` + `exvius/android_offline.py`:
  * Java transport callers (Cocos HTTP, Cocos downloader, video, web views) are rewritten to call
    `com.exvius.local.LocalGameBridge`, which answers in-process from the embedded Python engine
    (Chaquopy). No sockets, no PC server.
  * The embedded runtime (Chaquopy + com.exvius.local + TestInitProvider) is taken unchanged from the
    built Global Offline APK, with only its Global-specific strings switched to JP.
  * libgame.so stays byte-for-byte original; native changes live in the Frida Gadget script
    (`build/frida/jp_offline.js`), loaded at startup by TestInitProvider (System.loadLibrary("exviustest")).

Differences from Global (JP has no such classes / not needed for JP):
  * no Play Games / Facebook / Helpshift / soomla smali (JP Java layer has none of these classes);
  * no game-assets.apk art pack (JP keeps its own assets in the APK), so getAssetsPath and
    Lapis.onCreate installAssets are left alone;
  * DataDownloadActivity is not the launcher yet: engine data is installed with `run-as` (debuggable build).

usage: python -I build/jp_offline_build.py [--script-path /data/local/tmp/frida_script.js]
inputs : build/out/jp_offline/dec (apktool d of JP base.apk), build/out/jp_offline/orig/*.apk,
         build/out/gl_offline/dec (apktool d of exvius-offline-v0.1.22.apk)
output : build/out/jp_offline/dist/*.apk (signed with ~/.android/debug.keystore) -> adb install-multiple
"""
from pathlib import Path
import argparse, json, os, re, shutil, subprocess, sys, tempfile, zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/out/jp_offline'
JP_DEC, GL_DEC = OUT / 'dec', ROOT / 'build/out/gl_offline/dec'
WORK, DIST = OUT / 'work', OUT / 'dist'
APKTOOL = ROOT / 'build/out/apktool_3.0.3.jar'
SDK = Path.home() / 'AppData/Local/Android/Sdk/build-tools/35.0.0'
ANDROID_JAR = Path.home() / 'AppData/Local/Android/Sdk/platforms/android-36/android.jar'
KEYSTORE = Path.home() / '.android/debug.keystore'
OLD_PKG, NEW_PKG = 'com.square_enix.ffbejpn', 'com.exvius.jpkorean.app'
JPP = 'com/square_enix/ffbejpn'
ANDROID = '{http://schemas.android.com/apk/res/android}'
RUNTIME_SRC = ROOT / 'build/android_runtime/src'
DEX_TO_SMALI = ROOT / 'build/android_runtime/tools/DexToSmali.java'
RUNTIME_CLASSES = ('DataUpdates.java', 'DataPack.java', 'DataDownloadActivity.java', 'DataDownloadService.java',
                   'UpdateProvider.java')
RELEASE_VERSION_CODE, RELEASE_VERSION_NAME = 197, '0.1.0'   # 197(첫 공개를 이 빌드로 교체, 이전 195·196 위에 설치되게 코드는 유지): 티켓 자동 보충 제거, 앱 내 업데이트 설치(UpdateProvider) 수정 / 196: 소환 탭 FFBE/FF SERIES/COLLAB, 레이드 반복 결과 스크롤 (2026-11-17)
# 195 (0.1.0): ffbe/{mst_ko,flat_ko} 팩 항목 설치

sys.path.insert(0, str(Path(__file__).resolve().parent))
import deploy_jp_frida as FRIDA  # noqa: E402


def replace_method(text, signature, body):
    pattern = r'(?m)^\.method ' + re.escape(signature) + r'\n.*?^\.end method'
    text, count = re.subn(pattern, lambda _: '.method ' + signature + '\n' + body + '\n.end method', text, flags=re.S)
    if count != 1:
        raise ValueError(f'Expected exactly one method: {signature}; found {count}')
    return text


def sub1(text, pattern, repl, what, flags=0):
    text, count = re.subn(pattern, repl, text, flags=flags)
    if count != 1:
        raise ValueError(f'Expected one {what}; found {count}')
    return text


def edit(path, fn):
    path.write_text(fn(path.read_text(encoding='utf-8')), encoding='utf-8')


def patch_java(smali):
    """Port of android_offline.prepare_offline_code for the JP class layout."""
    L = smali / 'org/cocos2dx/lib'
    # 1) Cocos HTTP (all game API calls) -> in-process engine.
    edit(L / 'Cocos2dxHttpURLConnection.smali', lambda t: sub1(t,
        r'invoke-virtual \{([^}]+)\}, Ljava/net/URL;->openConnection\(\)Ljava/net/URLConnection;',
        r'invoke-static {\1}, Lcom/exvius/local/LocalGameBridge;->openConnection(Ljava/net/URL;)Ljava/net/HttpURLConnection;',
        'Cocos HTTP openConnection'))
    # 2) Cocos asynchronous downloader: keep queue/native callbacks, replace I/O (JP client class is d.d.a.a.a).
    def downloader(t):
        t = sub1(t, r'    new-instance v0, Ld/d/a/a/a;\n.*?    iput-object v0, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader;->_httpClient:Ld/d/a/a/a;',
                 '    nop', 'downloader HTTP client constructor', flags=re.S)
        return replace_method(t, 'public static createDownloader(IILjava/lang/String;I)Lorg/cocos2dx/lib/Cocos2dxDownloader;', '''    .locals 1
    new-instance v0, Lorg/cocos2dx/lib/Cocos2dxDownloader;
    invoke-direct {v0}, Lorg/cocos2dx/lib/Cocos2dxDownloader;-><init>()V
    iput p0, v0, Lorg/cocos2dx/lib/Cocos2dxDownloader;->_id:I
    iput-object p2, v0, Lorg/cocos2dx/lib/Cocos2dxDownloader;->_tempFileNameSufix:Ljava/lang/String;
    iput p3, v0, Lorg/cocos2dx/lib/Cocos2dxDownloader;->_countOfMaxProcessingTasks:I
    return-object v0''')
    edit(L / 'Cocos2dxDownloader.smali', downloader)
    edit(L / 'Cocos2dxDownloader$3.smali', lambda t: replace_method(t, 'public run()V', '''    .locals 5
    new-instance v0, Lorg/cocos2dx/lib/DownloadTask;
    invoke-direct {v0}, Lorg/cocos2dx/lib/DownloadTask;-><init>()V
    iget-object v1, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader$3;->val$downloader:Lorg/cocos2dx/lib/Cocos2dxDownloader;
    invoke-static {v1}, Lorg/cocos2dx/lib/Cocos2dxDownloader;->access$400(Lorg/cocos2dx/lib/Cocos2dxDownloader;)Ljava/util/HashMap;
    move-result-object v2
    iget v3, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader$3;->val$id:I
    invoke-static {v3}, Ljava/lang/Integer;->valueOf(I)Ljava/lang/Integer;
    move-result-object v4
    invoke-virtual {v2, v4, v0}, Ljava/util/HashMap;->put(Ljava/lang/Object;Ljava/lang/Object;)Ljava/lang/Object;
    iget-object v2, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader$3;->val$url:Ljava/lang/String;
    iget-object v4, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader$3;->val$path:Ljava/lang/String;
    invoke-static {v1, v3, v2, v4}, Lcom/exvius/local/LocalCocosTasks;->load(Ljava/lang/Object;ILjava/lang/String;Ljava/lang/String;)V
    return-void'''))
    edit(L / 'Cocos2dxDownloader$4.smali', lambda t: replace_method(t, 'public run()V', '''    .locals 1
    iget-object v0, p0, Lorg/cocos2dx/lib/Cocos2dxDownloader$4;->val$downloader:Lorg/cocos2dx/lib/Cocos2dxDownloader;
    invoke-static {v0}, Lcom/exvius/local/LocalCocosTasks;->cancel(Ljava/lang/Object;)V
    return-void'''))
    # 3) Movie URIs -> local media.
    edit(L / 'Cocos2dxVideoView.smali', lambda t: sub1(t,
        r'invoke-virtual \{([^}]+)\}, Landroid/media/MediaPlayer;->setDataSource\(Landroid/content/Context;Landroid/net/Uri;\)V',
        r'invoke-static {\1}, Lcom/exvius/local/LocalGameBridge;->setLocalMediaSource(Landroid/media/MediaPlayer;Landroid/content/Context;Landroid/net/Uri;)V',
        'URI video loader'))
    # 4) Web views: POST submissions, client setup and resource interception stay local.
    edit(smali / JPP / 'webview/a$b.smali', lambda t: sub1(t,
        r'invoke-virtual \{([^}]+)\}, Landroid/webkit/WebView;->postUrl\(Ljava/lang/String;\[B\)V',
        r'invoke-static {\1}, Lcom/exvius/local/LocalGameBridge;->postLocalPage(Landroid/webkit/WebView;Ljava/lang/String;[B)V',
        'web page submission'))
    for path in (smali / JPP / 'webview/a$a.smali', L / 'Cocos2dxWebView.smali'):
        edit(path, lambda t: sub1(t,
            r'(?m)^(    invoke-virtual \{([^,]+), [^}]+\}, Landroid/webkit/WebView;->setWebViewClient\(Landroid/webkit/WebViewClient;\)V)$',
            r'    invoke-static {\2}, Lcom/exvius/local/LocalGameBridge;->configureWebView(Landroid/webkit/WebView;)V\n\1',
            'web view setup'))
    intercept = '''
.method public shouldInterceptRequest(Landroid/webkit/WebView;Ljava/lang/String;)Landroid/webkit/WebResourceResponse;
    .locals 1
    invoke-static {p2}, Lcom/exvius/local/LocalGameBridge;->webResource(Ljava/lang/String;)Landroid/webkit/WebResourceResponse;
    move-result-object v0
    return-object v0
.end method

.method public shouldInterceptRequest(Landroid/webkit/WebView;Landroid/webkit/WebResourceRequest;)Landroid/webkit/WebResourceResponse;
    .locals 1
    invoke-interface {p2}, Landroid/webkit/WebResourceRequest;->getUrl()Landroid/net/Uri;
    move-result-object v0
    invoke-virtual {v0}, Landroid/net/Uri;->toString()Ljava/lang/String;
    move-result-object v0
    invoke-static {v0}, Lcom/exvius/local/LocalGameBridge;->webResource(Ljava/lang/String;)Landroid/webkit/WebResourceResponse;
    move-result-object v0
    return-object v0
.end method
'''
    for path in (smali / JPP / 'webview/b.smali', L / 'Cocos2dxWebView$Cocos2dxWebViewClient.smali'):
        t = path.read_text(encoding='utf-8')
        if 'shouldInterceptRequest(' in t:
            raise ValueError('Review existing web resource interception in ' + path.name)
        path.write_text(t + intercept, encoding='utf-8')
    # 5) No external browser / app launches.
    edit(L / 'Cocos2dxHelper.smali', lambda t: replace_method(t, 'public static openURL(Ljava/lang/String;)Z',
                                                             '    .locals 1\n    const/4 v0, 0x0\n    return v0'))
    # 6) Network state: report "available" from local data, like Global (Lapis.getNetworkState).
    edit(smali / JPP / 'Lapis.smali', lambda t: replace_method(t, 'public static getNetworkState()I', '''    .locals 1
    invoke-static {}, Lcom/exvius/local/LocalGameBridge;->localDataState()I
    move-result v0
    return v0'''))


def merge_runtime(work):
    """Global runtime DEX trees -> JP smali_classes2..5; the Global downloader classes are replaced."""
    for i, src in enumerate(('smali_classes4', 'smali_classes5', 'smali_classes6', 'smali_classes7'), start=2):
        dst = work / f'smali_classes{i}'
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(GL_DEC / src, dst)
    # DataUpdates/DataPack/DataDownloadActivity are rebuilt from build/android_runtime (own HTTP
    # downloader, Korean activity, JP pack layout); keep GameAssets and Local* from the Global build.
    for root in work.glob('smali_classes*'):
        local = root / 'com/exvius/local'
        if not local.is_dir():
            continue
        for pattern in ('DataUpdates*.smali', 'DataPack*.smali', 'DataDownloadActivity*.smali'):
            for path in local.glob(pattern):
                path.unlink()
    shutil.copytree(GL_DEC / 'assets/chaquopy', work / 'assets/chaquopy', dirs_exist_ok=True)
    patch_engine(work / 'assets/chaquopy/app.imy')


def install_runtime(work, manifest_url=None, assets_prefix=None, require_installed=True):
    """javac -> d8 -> DexToSmali (apktool's baksmali) -> work/smali_classes5/com/exvius/local."""
    if not ANDROID_JAR.is_file():
        raise FileNotFoundError(ANDROID_JAR)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        src = tmp / 'src'
        shutil.copytree(RUNTIME_SRC, src)
        java = src / 'com/exvius/local/DataUpdates.java'
        text = java.read_text(encoding='utf-8')
        if manifest_url:
            text = sub1(text, r'(private static final String LATEST = )"[^"]*"',
                        lambda m: m[1] + '"' + manifest_url + '"', 'LATEST constant')
        if assets_prefix:
            if not assets_prefix.endswith('/'):
                assets_prefix += '/'
            text = sub1(text, r'(private static final String ASSETS = )"[^"]*"',
                        lambda m: m[1] + '"' + assets_prefix + '"', 'ASSETS constant')
        if not require_installed:
            # Dev data is installed with adb/run-as and has no exvius/data/installed.json.
            text = sub1(text, r'private static final boolean REQUIRE_INSTALLED = true;',
                        'private static final boolean REQUIRE_INSTALLED = false;', 'REQUIRE_INSTALLED constant')
        java.write_text(text, encoding='utf-8')
        cls, dex, tool, smali = tmp / 'cls', tmp / 'dex', tmp / 'tool', tmp / 'smali'
        for folder in (cls, dex, tool, smali):
            folder.mkdir()
        run(['javac', '-encoding', 'UTF-8', '--release', '8', '-classpath', ANDROID_JAR, '-d', cls,
             *[src / 'com/exvius/local' / name for name in RUNTIME_CLASSES]])
        run([SDK / 'd8.bat', '--release', '--min-api', '21', '--lib', ANDROID_JAR, '--output', dex,
             *sorted(map(str, cls.rglob('*.class')))])
        run(['javac', '-encoding', 'UTF-8', '--release', '8', '-classpath', APKTOOL, '-d', tool, DEX_TO_SMALI])
        java_cp = os.pathsep.join([str(APKTOOL), str(tool)])
        run(['java', '-cp', java_cp, 'DexToSmali', dex / 'classes.dex', smali])
        dst = work / 'smali_classes5/com/exvius/local'
        produced = sorted((smali / 'com/exvius/local').glob('*.smali'))
        if not produced:
            raise RuntimeError('DexToSmali produced no classes')
        for path in produced:
            shutil.copyfile(path, dst / path.name)
        print('runtime classes ->', ', '.join(p.name for p in produced))



ENGINE_SRC = ROOT.parent / 'ffbe_offline_modfix/upstream/source/memorial/android/src/main/python/android_game.py'
JP_VERSIONS = r'''
    # JP: the client's own registry is authoritative for EVERY table version. The Global reply templates
    # author a few Global-only versions (e.g. F_DEFINE_MST=227; JP ships 337) that the JP client would then
    # try to fetch. FORCE_TABLE_VERSIONS is the engine's existing last-applied override, read at import.
    import re as _re
    _registry = static / 'client' / 'shared_prefs' / 'gamedata.xml'
    if _registry.is_file():
        _rows = _re.findall(r'<string name="key(F_[A-Za-z0-9_]+)">(-?\d+)</string>', _registry.read_text(encoding='utf-8'))
        os.environ['FORCE_TABLE_VERSIONS'] = ','.join(n + '=' + v for n, v in _rows)
'''


JP_TUTORIAL = r'''
    # JP VersionInfoResponse queues every supplied master, including equal versions.
    # Send pending versions only; LoginScene still checks actual local files and queues missing ones.
    import jp_versions as _jp_versions
    _jp_versions.install(native_files)
    import jp_korean as _jp_korean
    _jp_korean.install(game.server)
    # JP start-up switches, granted through the engine's own switch state (served in the 8J1R5PXG container
    # like every other switch). Ids are the JP F_DEFINE_MST values; positions agree in JP and Global F_SWITCH_MST.
    #  * TUTORIAL_END_SWITCH_ID 10003001 (type 100 bit 4): off -> LoginScene::changeNextScene calls
    #    restartMission for the suspended tutorial mission, which a new local save does not have (black screen).
    #  * UPDATE_TERMS_OF_SERVICE_SWITCH_ID 10000826 (JP; Global uses 10000140), type 10 bit 366: off ->
    #    LoginScene::isUpdatedPolicy is false, the terms web page (live notice server) is required and
    #    LoginScene::initConnect skips GetUserInfo/2/3 + GetReinforcementInfo, the user-state chain.
    from player_state import switch_position
    def _jp_startup_switches(_player):
        _granted = False
        for _sid in (10003001, 10000826):
            _pos = switch_position(_sid)
            if _pos and _player is not None and _pos[1] not in _player.switches.get(_pos[0], set()):
                _player.grant_switch(*_pos)
                _granted = True
                print('JP: start-up switch ' + str(_sid) + ' granted ' + repr(_pos), flush=True)
        return _granted
    if _jp_startup_switches(game.server.State.player):
        game.server.State.state_dirty = True
    # Title New Game (build/frida/jp_title_menu.js -> LocalGameBridge.titleAction("new") -> title_action):
    # offline_menu.new_game backs the save up to state/backups/ and loads a fresh one, which lacks the start-up
    # switches above (granted only here, at engine start). Grant them again and save before the client logs in.
    _title_action = title_action
    def _jp_title_action(game, action):
        _result = _title_action(game, action)
        if str(action) == 'new':
            _server = game.server
            with _server.STATE_LOCK:
                if _jp_startup_switches(_server.State.player):
                    _server.State.player.save(_server.st.STATE_FILE, force=True)
            print('JP: title New Game -> fresh save with start-up switches', flush=True)
        return _result
    globals()['title_action'] = _jp_title_action
    # JP-only reply group: UserTermsOfServiceInfoResponse (GameResponseFactory tag ApeF67xo, field 73b1uBje ->
    # UserTermsOfServiceInfo+0x21). LoginScene::isUpdatedPolicy checks it FIRST, at LoginScene::initConnect,
    # before DefineMst (and so the terms switch above) is loaded. 1 = terms accepted. Global has no such group.
    _replies = game.server.State.replies
    _init = _replies.get('75fYdNxq')
    if isinstance(_init, dict) and 'ApeF67xo' not in _init:
        _replies['75fYdNxq'] = dict(_init, ApeF67xo=[{'73b1uBje': '1'}])
        print('JP: Initialize reply carries ApeF67xo terms-accepted', flush=True)
    # Summon list banner. Global 9.0.0 splits GachaScheduleMst.bannerInfo (4yT7FUqj) "<list>,0:<detail>" into a
    # bare list slot and a detail vector (engine _gacha_schedule_banner_string). JP 11.0.0 keeps ONE string and
    # GachaTopScene::setListLayout passes it whole to FileUtils::fullPathForFilename (traced 2026-11-08), so the
    # mixed form names no file and the list row draws nothing. Serve the bare list image for JP.
    # Challenge "clear without continuing": JP MissionEnd has no continue-count group, so count the
    # start/continue requests in the engine (build/engine_overlay/jp_mission.py).
    import jp_mission as _jp_mission
    _jp_mission.install(game.server.st.STATE_FILE)
    # Mailbox: the Global daily 8th-anniversary ticket (item 1209002123) is not in JP F_ITEM_MST and crashes the
    # JP mail list; stop issuing it and drop existing ones (build/engine_overlay/jp_mail.py).
    import jp_mail as _jp_mail
    _jp_mail.install(game.server)
    # Other Global-engine -> JP reply differences (special-challenge titles, ...): build/engine_overlay/jp_compat.py.
    import jp_compat as _jp_compat
    _jp_compat.install(game.server)
    import ffbe_gacha as _fg
    import jp_gacha as _jp_gacha
    _jp_gacha.install(_fg)
    _fg._gacha_schedule_banner_string = lambda banner, detail='', extras=(): banner or _fg.GACHA_DEFAULT_BANNER_ART
    print('JP: gacha schedule bannerInfo = bare list image', flush=True)
    # Summon effect pattern (zoU5J3Kq). The engine picks it from the GLOBAL F_GACHA_EFFECT_PATTERN_MST (69 rows,
    # e.g. NV -> 20), but the JP client looks it up in the JP table (1473 rows; 20 does not exist there) and shows
    # 召喚演出の再生に失敗しました. Use the JP generic rows (gachaId 0, group 200010 = standard summon, the
    # heaviest weight per rarity; 6 has none in that group -> the 5 row) and JP Vision Card group 200011
    # (ids 6210..6215 = card rarity 1..6). Source: JP F_GACHA_EFFECT_PATTERN_MST (ffbejpdata), 2026-11-08.
    # Weighted like the original: (pattern id, weight ixDq7yJ8) of the JP generic rows per rarity, so ★5/NV can
    # open as a lower-rarity crystal and upgrade (user decision 2026-11-08).
    import player_state as _ps, random as _rnd
    _JP_PATTERN = {1: [('12', 100)], 2: [('13', 100)], 3: [('6200', 100)], 4: [('6201', 75), ('6202', 25)],
                   5: [('6203', 70), ('6204', 10), ('6205', 20)], 6: [('6203', 70), ('6204', 10), ('6205', 20)],
                   7: [('6206', 30), ('6207', 30), ('6208', 20), ('6209', 20)],
                   8: [('6224', 20), ('6225', 20), ('6226', 10), ('6227', 10), ('6228', 40)]}
    def _jp_pattern(rarity, gacha_id=None):
        rows = _JP_PATTERN.get(int(rarity or 1), _JP_PATTERN[5])
        return _rnd.choices([p for p, _ in rows], weights=[w for _, w in rows])[0]
    _ps.effect_pattern_for = _jp_pattern
    _fg.VC_EFFECT_PATTERN_BASE = 6209
    print('JP: gacha effect patterns from the JP table (weighted)', flush=True)
    # Summon archive groups: Global seasons 1-4 + JP Season 5 (from 2024-12-27; JP banners carry 'season').
    import gacha_archive as _ga
    # JP 11.0.0 has three summon tabs (GachaMst::isPayType / isFreeType / isExchangeType) and no Global
    # "Limited Time" tab: file Global event code 50 on the pay tab. JP box code 7 is FREE.
    _wire = _ga.wire_type
    _ga.wire_type = lambda banner, code: _jp_gacha.wire_type(banner, code, _wire)
    if not any(k == 'season5' for k, _ in _ga.GROUPS):
        _ga.GROUPS = tuple(g for g in _ga.GROUPS if g[0] != 'collaborations') + (('season5', 'Season 5'),) + \
            tuple(g for g in _ga.GROUPS if g[0] == 'collaborations')
    # Global banner art map for the Frida feeder (build/make_jp_banners.py -> engine data -> files/exvius/).
    import shutil as _sh, os as _os, ffbe_config as _cfg
    _src = _os.path.join(_cfg.HERE, 'jp_banner_art.json')
    if _os.path.isfile(_src):
        _sh.copyfile(_src, str(root / 'jp_banner_art.json'))
        print('JP: banner art map -> ' + str(root / 'jp_banner_art.json'), flush=True)
    # Stand-in PNG sizes for the same feeder (build/make_jp_art_dims.py): a same-length unit sheet must not be
    # swapped for a banner (build/out/summon_sprite/rain_lasswell.md).
    _src = _os.path.join(_cfg.HERE, 'jp_art_dims.json')
    if _os.path.isfile(_src):
        _sh.copyfile(_src, str(root / 'jp_art_dims.json'))
        print('JP: banner art dims -> ' + str(root / 'jp_art_dims.json'), flush=True)
    # Area resource id -> CPK table for the parade pack binder (build/make_area_resource_cpk_map.py ->
    # files/exvius/, read by build/frida/jp_parade_res.js).
    _src = _os.path.join(_cfg.HERE, 'area_resource_cpk.json')
    if _os.path.isfile(_src):
        _sh.copyfile(_src, str(root / 'area_resource_cpk.json'))
        print('JP: area resource cpk map -> ' + str(root / 'area_resource_cpk.json'), flush=True)
    # Rm area list for the Frida gate-touch hook (build/make_jp_rm_areas.py -> jp_compat.JP_RM_TEST_AREAS and
    # build/frida/jp_offline.js read the same set).
    _src = _os.path.join(_cfg.HERE, 'jp_rm_areas.json')
    if _os.path.isfile(_src):
        _sh.copyfile(_src, str(root / 'jp_rm_areas.json'))
        print('JP: rm area list -> ' + str(root / 'jp_rm_areas.json'), flush=True)
'''


def patch_engine(imy):
    """Replace android_game.pyc with the JP-adjusted source (Chaquopy imports .py from app.imy)."""
    src = ENGINE_SRC.read_text(encoding='utf-8')
    anchor = "    root = Path(writable_root)\n"
    if src.count(anchor) != 1:
        raise ValueError('android_game.start layout changed')
    src = src.replace(anchor, JP_VERSIONS + anchor)
    anchor = "    game = LocalGame(root)\n"
    if src.count(anchor) != 1:
        raise ValueError('android_game.start LocalGame line changed')
    src = src.replace(anchor, anchor + JP_TUTORIAL)
    tmp = imy.with_suffix('.new')
    # Engine data overlay: files here replace same-named files in app.imy. Chaquopy re-extracts app.imy on every
    # launch, so edits made on the device via run-as are overwritten; data must be baked in here.
    overlay = {p.name: p.read_bytes() for p in (ROOT / 'build/engine_overlay').glob('*') if p.is_file()}
    with zipfile.ZipFile(imy) as zin, zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            if info.filename in overlay:
                zout.writestr(info.filename, overlay.pop(info.filename))
            elif info.filename != 'android_game.pyc':
                zout.writestr(info, zin.read(info.filename))
        for name, data in overlay.items():
            zout.writestr(name, data)
        print('engine overlay applied')
        zout.writestr('android_game.py', src)
    tmp.replace(imy)


def engine_data():
    """Engine data = Global release `static/` (minus the Global art pack) + JP client version registry."""
    static = OUT / 'engine/static'
    if not (static / 'mst_decoded/F_UNIT_MST.ndjson').is_file():
        raise FileNotFoundError('extract static/ from the Global data release into ' + str(static))
    rows = json.loads((ROOT / 'translations/server/replies/InitializeRequest.json').read_text(encoding='utf-8'))['c1qYg84Q']
    prefs = static / 'client/shared_prefs'
    prefs.mkdir(parents=True, exist_ok=True)
    body = ''.join(f'<string name="key{r["a4hXTIm0"]}">{r["wM9AfX6I"]}</string>' for r in rows)
    (prefs / 'gamedata.xml').write_text("<?xml version='1.0' encoding='utf-8'?>\n<map>" + body + '</map>\n', encoding='utf-8')
    print('JP version registry rows:', len(rows))


KO_FONT = OUT.parent / 'ko_font/ko_game_font.ttf'   # build/make_ko_font.py (Binggrae + JP kanji, script font)
KO_UI_FONT = OUT.parent / 'ko_font/ko_ui_font.ttf'  # build/make_ko_font.py (NotoSansKR + JP kanji, UI font)


def apply_ko_font(work):
    """Map UI slot TT_RodinCattleya-B.ttf -> UI font (NotoSansKR) and script slot FOT-SkipStd-E.otf -> Binggrae."""
    if not KO_FONT.is_file():
        print('Korean font not built (python -E -P build/make_ko_font.py); JP fonts kept')
        return
    ui_src = KO_UI_FONT if KO_UI_FONT.is_file() else KO_FONT
    shutil.copyfile(ui_src, work / 'assets/font/TT_RodinCattleya-B.ttf')
    shutil.copyfile(KO_FONT, work / 'assets/font/FOT-SkipStd-E.otf')
    print('Korean font -> TT_RodinCattleya-B.ttf:', ui_src.stat().st_size,
          'bytes; FOT-SkipStd-E.otf:', KO_FONT.stat().st_size, 'bytes')


KO_UI = OUT.parent / 'ko_ui'   # build/apply_ko_ui.py (Korean UI text + sprites)


def apply_ko_ui(work):
    """assets/cpk/common.cpk and resources.cpk -> the Korean rebuilds (build/apply_ko_ui.py)."""
    for name in ('common.cpk', 'resources.cpk'):
        src = KO_UI / name
        if not src.is_file():
            print('Korean UI not built (python -I build/apply_ko_ui.py); JP', name, 'kept')
            continue
        shutil.copyfile(src, work / 'assets/cpk' / name)
        print('Korean UI ->', 'assets/cpk/' + name, src.stat().st_size, 'bytes')


RELEASE_PERMISSIONS = (
    '<uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC"/>'
    '<uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES"/>')
RELEASE_COMPONENTS = (
    '<service android:exported="false" android:name="com.exvius.local.DataDownloadService"'
    ' android:foregroundServiceType="dataSync"/>'
    '<activity android:configChanges="keyboardHidden|orientation|screenSize" android:exported="true"'
    ' android:label="Exvius KR" android:name="com.exvius.local.DataDownloadActivity"'
    ' android:screenOrientation="portrait" android:theme="@android:style/Theme.NoTitleBar.Fullscreen">'
    '<intent-filter><action android:name="android.intent.action.MAIN"/>'
    '<category android:name="android.intent.category.LAUNCHER"/></intent-filter></activity>'
    '<provider android:authorities="__PKG__.updates" android:exported="false"'
    ' android:grantUriPermissions="true" android:name="com.exvius.local.UpdateProvider"/>')
# The JP APK's androidx FileProvider is obfuscated (getUriForFile renamed), so the update APK is served by
# com.exvius.local.UpdateProvider instead. FILE_PATHS_XML is kept only so older build steps still find it.
FILE_PATHS_XML = '''<?xml version="1.0" encoding="utf-8"?>
<paths>
    <files-path name="updates" path="exvius/updates/"/>
</paths>
'''


def patch_manifest(work, release=False, allow_cleartext=False):
    path = work / 'AndroidManifest.xml'
    t = path.read_text(encoding='utf-8')
    providers = (f'<provider android:authorities="{NEW_PKG}.init" android:exported="false" android:initOrder="2147483647" '
                 f'android:name="com.exvius.offline.test.TestInitProvider"/>'
                 f'<provider android:authorities="{NEW_PKG}.localgame" android:exported="false" android:initOrder="2147483647" '
                 f'android:name="com.exvius.local.LocalGameProvider"/>')
    if release:
        # Debuggable off; 16 KB page compatibility; cleartext only for a local test manifest.
        extra = ' android:pageSizeCompat="enabled"'
        if allow_cleartext:
            extra += ' android:usesCleartextTraffic="true"'
            # networkSecurityConfig overrides usesCleartextTraffic: allow the adb-reverse test server too.
            nsc = work / 'res/xml/network_security_config.xml'
            edit(nsc, lambda s: s.replace('</network-security-config>',
                 '    <domain-config cleartextTrafficPermitted="true">\n'
                 '        <domain includeSubdomains="false">127.0.0.1</domain>\n'
                 '    </domain-config>\n</network-security-config>'))
        t = sub1(t, r'(<application [^>]*?)( android:debuggable="[^"]*")?(\s*>)',
                 lambda m: m[1] + extra + m[3], '<application> tag')
        # The distribution build ships one universal APK: no Play-feature split plumbing.
        t = sub1(t, r'\s*android:requiredSplitTypes="[^"]*"', '', 'requiredSplitTypes attribute')
        t = sub1(t, r'\s*android:splitTypes="[^"]*"', '', 'splitTypes attribute')
        t = sub1(t, r'\s*<meta-data android:name="com\.android\.vending\.splits\.required"[^>]*/>',
                 '', 'com.android.vending.splits.required meta-data')
        t = sub1(t, r'\s*<meta-data android:name="com\.android\.vending\.splits"[^>]*/>',
                 '', 'com.android.vending.splits meta-data')
        t = t.replace('android:label="FFBE"', 'android:label="Exvius KR"')
        # The download activity becomes the launcher; Lapis keeps its whole activity, minus MAIN/LAUNCHER.
        t = sub1(t, r'\s*<intent-filter>\s*<action android:name="android\.intent\.action\.MAIN"/>\s*'
                    r'<category android:name="android\.intent\.category\.LAUNCHER"/>\s*</intent-filter>',
                 '', 'Lapis launcher filter')
        t = sub1(t, r'(<uses-permission android:name="android\.permission\.POST_NOTIFICATIONS"/>)',
                 lambda m: m[1] + RELEASE_PERMISSIONS, 'POST_NOTIFICATIONS tag')
        t = sub1(t, r'</application>', providers + RELEASE_COMPONENTS.replace('__PKG__', NEW_PKG) + '</application>', '</application>')
        xml = work / 'res/xml/exvius_file_paths.xml'
        xml.parent.mkdir(parents=True, exist_ok=True)
        xml.write_text(FILE_PATHS_XML, encoding='utf-8')
    else:
        t = sub1(t, r'(<application [^>]*?)( android:debuggable="[^"]*")?(\s*>)',
                 lambda m: m[1] + ' android:debuggable="true"' + m[3], '<application> tag')
        t = t.replace('android:label="FFBE"', 'android:label="Exvius KR 개발"')   # tell it apart from the release app
        t = sub1(t, r'</application>', providers + '</application>', '</application>')
    path.write_text(t, encoding='utf-8')
    yml = work / 'apktool.yml'
    if release:
        edit(yml, lambda s: s.replace('versionCode: 193', f'versionCode: {RELEASE_VERSION_CODE}')
             .replace('versionName: 11.0.0', f'versionName: {RELEASE_VERSION_NAME}'))
    else:
        edit(yml, lambda s: s.replace('versionName: 11.0.0', 'versionName: 11.0.0-offline'))


PUBLIC_RE = re.compile(r'<public type="([^"]+)" name="([^"]+)"(?: id="(0x[0-9a-f]+)")?')
RESOURCE_EXTS = ('.9.png', '.png', '.xml', '.jpg', '.jpeg', '.webp')


def merge_split_resources(work):
    """Fold split_config.xhdpi.apk into WORK so one APK can resolve everything without a split.

    The xhdpi split carries 15 drawables; 13 of them exist only there (base's public.xml leaves their
    exact IDs as gaps) and base smali hard-codes two of them (0x7f050003, 0x7f050025), so they must be
    merged with their original IDs. split_config.ja.apk is dropped: all 45 of its strings already have a
    non-empty default value in base under the same resource ID.
    """
    split = OUT / 'orig/split_config.xhdpi.apk'
    if not split.is_file():
        raise FileNotFoundError(split)
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        run(['java', '-jar', APKTOOL, 'd', '-s', '-f', '-o', tmp / 'dec', split])
        dec_res = tmp / 'dec/res'
        pub_path = work / 'res/values/public.xml'
        pub_text = pub_path.read_text(encoding='utf-8')
        have = {(t, n) for t, n, _ in PUBLIC_RE.findall(pub_text) if _}
        split_ids = {(t, n): i for t, n, i in PUBLIC_RE.findall((dec_res / 'values/public.xml').read_text(encoding='utf-8')) if i}
        copied, pinned = [], []
        for folder in sorted(p for p in dec_res.iterdir() if p.is_dir() and p.name != 'values'):
            ftype = folder.name.split('-', 1)[0]
            target = work / 'res' / folder.name
            target.mkdir(parents=True, exist_ok=True)
            for src in sorted(folder.iterdir()):
                if not src.is_file():
                    continue
                name = src.name
                for ext in RESOURCE_EXTS:
                    if name.endswith(ext):
                        name = name[:-len(ext)]
                        break
                key = (ftype, name)
                if key not in split_ids:
                    raise ValueError(f'{split.name}: no resource id for {key}')
                dst = target / src.name
                if not dst.exists():
                    shutil.copyfile(src, dst)
                    copied.append(f'{folder.name}/{src.name}')
                if key not in have:
                    pub_text = pub_text.replace('</resources>',
                        f'    <public type="{key[0]}" name="{key[1]}" id="{split_ids[key]}" />\n</resources>')
                    have.add(key)
                    pinned.append(f'{key[0]}/{key[1]}={split_ids[key]}')
        if not copied:
            raise ValueError(f'{split.name}: nothing to merge (already merged?)')
        pub_path.write_text(pub_text, encoding='utf-8')
    print(f'xhdpi split -> WORK: {len(copied)} files, {len(pinned)} resource ids pinned: '
          + ', '.join(pinned), flush=True)


def merge_native_libs(base_apk, native_apk, out):
    """Put the arm64 split's lib/ into the apktool-built base, STORED (extractNativeLibs=false)."""
    added = 0
    with zipfile.ZipFile(base_apk) as base, zipfile.ZipFile(native_apk) as native, \
            zipfile.ZipFile(out, 'w') as zout:
        names = set()
        for info in base.infolist():
            if info.filename.startswith('lib/'):
                raise ValueError(f'{base_apk.name} already contains {info.filename}')
            zi = zipfile.ZipInfo(info.filename, info.date_time)
            zi.compress_type = info.compress_type
            zi.external_attr = info.external_attr
            zout.writestr(zi, base.read(info.filename))
            names.add(info.filename)
        for info in native.infolist():
            if not info.filename.startswith('lib/'):
                continue
            if info.filename in names:
                raise ValueError(f'duplicate entry {info.filename}')
            zi = zipfile.ZipInfo(info.filename, info.date_time)
            zi.compress_type = zipfile.ZIP_STORED
            zi.external_attr = info.external_attr
            zout.writestr(zi, native.read(info.filename))
            names.add(info.filename)
            added += 1
    if added == 0:
        raise ValueError(f'{native_apk.name} contributed no lib/ entries')
    print(f'universal APK: {added} native libraries merged into {out.name} (STORED)', flush=True)


def run(cmd, **kw):
    print('$', ' '.join(map(str, cmd))[:200], flush=True)
    subprocess.run([str(c) for c in cmd], check=True, **kw)


def rename(src, dst, version_code=None):
    cmd = [sys.executable, '-I', ROOT / 'build/rename_package.py', src, dst, OLD_PKG, NEW_PKG]
    run(cmd + ([version_code] if version_code else []))


def align_sign(unsigned, final):
    aligned = final.with_suffix('.aligned.apk')
    run([SDK / 'zipalign.exe', '-f', '-p', '4', unsigned, aligned])
    run([SDK / 'apksigner.bat', 'sign', '--ks', KEYSTORE, '--ks-pass', 'pass:android', '--key-pass', 'pass:android',
         '--out', final, aligned], shell=False)
    aligned.unlink()


def build_native_split(script_path, release_bundle=None):
    """arm64 split: original libgame (unchanged) + Global runtime natives (Chaquopy, Python, Frida Gadget)."""
    src = OUT / 'orig/split_config.arm64_v8a.apk'
    out = OUT / 'tmp_arm64.apk'
    gl_lib = GL_DEC / 'lib/arm64-v8a'
    skip = {'libgame.so', 'libbacktrace-native.so', 'libcrashpad_handler.so', 'libexviustest.js.so', 'libexviustest.config.so'}
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(out, 'w') as zout:
        for info in zin.infolist():
            if info.filename.startswith('META-INF/') or info.filename == 'stamp-cert-sha256':
                continue
            zout.writestr(info, zin.read(info.filename))
        for lib in sorted(gl_lib.iterdir()):
            if lib.name in skip:
                continue
            name = 'lib/arm64-v8a/' + lib.name
            if release_bundle is not None and lib.name == 'libexviustest.so':
                # The vendored Frida/V8 gadget carries one unused default path "/data/local/tmp"
                # (V8 fallback loader). The release APK must not contain the dev path at all, so
                # overwrite it in place with a same-length, non-existent path.
                data = lib.read_bytes()
                if data.count(b'/data/local/tmp') != 1:
                    raise ValueError('unexpected /data/local/tmp count in libexviustest.so')
                data = data.replace(b'/data/local/tmp', b'/data/local/tmx')
                zout.writestr(name, data, compress_type=zipfile.ZIP_STORED)
                continue
            zout.write(lib, name, compress_type=zipfile.ZIP_STORED)
        if release_bundle is not None:
            # Release: the bundle is a file in the APK, loaded by relative path (Global android_build.py form).
            info = zipfile.ZipInfo('lib/arm64-v8a/libexviustest.js.so')
            zout.writestr(info, release_bundle, compress_type=zipfile.ZIP_STORED)
            cfg = {'interaction': {'type': 'script', 'path': 'libexviustest.js.so'}, 'runtime': 'qjs'}
        else:
            # Dev: the script stays on /data/local/tmp and is pushed with adb (deploy_jp_frida.py).
            cfg = {'interaction': {'type': 'script', 'path': script_path, 'on_change': 'reload'}, 'runtime': 'qjs'}
        zout.writestr(zipfile.ZipInfo('lib/arm64-v8a/libexviustest.config.so'), json.dumps(cfg, indent=2))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--script-path', default='/data/local/tmp/frida_script.js',
                    help='Frida Gadget script location on the device (dev: pushed with adb).')
    ap.add_argument('--release', action='store_true',
                    help='distribution build: download activity launcher, debuggable off, Frida bundle embedded.')
    ap.add_argument('--manifest-url', help='override DataUpdates.LATEST (local test manifest server).')
    ap.add_argument('--assets-prefix', help='override DataUpdates.ASSETS (local test asset server).')
    ap.add_argument('--allow-cleartext', action='store_true',
                    help='usesCleartextTraffic for a local http test build (release only).')
    args = ap.parse_args()
    if args.release:
        # The release app installs beside the dev app (com.exvius.jpkorean.app) instead of replacing it.
        global NEW_PKG
        NEW_PKG = FRIDA.RELEASE_PKG
        assert len(NEW_PKG) == len(OLD_PKG), 'rename_package.py needs a same-length package name'
    for need in (JP_DEC / 'apktool.yml', GL_DEC / 'smali_classes7', APKTOOL, KEYSTORE, ANDROID_JAR):
        if not need.exists():
            raise FileNotFoundError(need)
    if WORK.exists():
        shutil.rmtree(WORK)
    shutil.copytree(JP_DEC, WORK)
    apply_ko_font(WORK)
    apply_ko_ui(WORK)
    patch_java(WORK / 'smali')
    merge_runtime(WORK)
    install_runtime(WORK, args.manifest_url, args.assets_prefix, require_installed=args.release)
    patch_manifest(WORK, release=args.release, allow_cleartext=args.allow_cleartext)
    if args.release:
        merge_split_resources(WORK)   # one universal APK needs the xhdpi drawables inside the base
    engine_data()
    release_bundle = None
    if args.release:
        release_bundle = FRIDA.build_bundle(release=True).encode('utf-8')
        print('release Frida bundle:', len(release_bundle), 'bytes')
    DIST.mkdir(parents=True, exist_ok=True)
    tmp_base = OUT / 'tmp_base.apk'
    run(['java', '-jar', APKTOOL, 'b', '-f', '-o', tmp_base, WORK])
    if args.release:
        # Universal: fold the arm64 native libraries into the base instead of shipping splits.
        universal = OUT / 'tmp_universal.apk'
        merge_native_libs(tmp_base, build_native_split(args.script_path, release_bundle), universal)
        parts = {'base': universal}
        for stale in sorted(DIST.glob('split_*.apk')) + sorted(DIST.glob('split_*.apk.idsig')):
            stale.unlink()   # dev split set must not leak into the release stage
            print('removed stale:', stale.name, flush=True)
    else:
        parts = {'base': tmp_base, 'split_config.arm64_v8a': build_native_split(args.script_path, release_bundle),
                 'split_config.xhdpi': OUT / 'orig/split_config.xhdpi.apk', 'split_config.ja': OUT / 'orig/split_config.ja.apk'}
    for name, src in parts.items():
        renamed = OUT / f'tmp_{name}.renamed.apk'
        rename(src, renamed, RELEASE_VERSION_CODE if args.release else None)   # every split must match the base
        align_sign(renamed, DIST / f'{name}.apk')
        renamed.unlink()
    print('built:', *sorted(p.name for p in DIST.glob('*.apk')))


if __name__ == '__main__':
    main()
