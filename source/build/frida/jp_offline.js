// JP 11.0.0 offline hooks: the JP counterpart of upstream exvius/android_test.js.
// Loaded by Frida Gadget (libexviustest.so) from TestInitProvider, exactly as in the Global Offline app.
// libgame.so stays byte-for-byte original; every native change is here.
// Game API traffic does NOT pass through here: the Java layer sends it in-process to the embedded engine.
const logw = new NativeFunction(Module.getGlobalExportByName('__android_log_write'), 'int', ['int', 'pointer', 'pointer']);
const TAG = Memory.allocUtf8String('EXVIUS_JP');
function note(s) { logw(4, TAG, Memory.allocUtf8String(String(s))); }
function rstr(p) { // libc++ std::string
  try { const b = p.readU8(); if (b & 1) { const n = p.add(8).readU64().toNumber(); return p.add(16).readPointer().readUtf8String(Math.min(n, 400)); } return p.add(1).readUtf8String(b >> 1); } catch (e) { return ''; }
}
function setStd(p, str) { // overwrite a libc++ std::string in place (only if it fits)
  const bytes = []; for (let i = 0; i < str.length; i++) bytes.push(str.charCodeAt(i) & 0xff);
  const b0 = p.readU8();
  if (b0 & 1) { const n = p.add(8).readU64().toNumber(); if (bytes.length > n) return false; const d = p.add(16).readPointer(); d.writeByteArray(bytes); d.add(bytes.length).writeU8(0); p.add(8).writeU64(bytes.length); return true; }
  if (bytes.length > 22) return false; p.add(1).writeByteArray(bytes); p.add(1 + bytes.length).writeU8(0); p.writeU8(bytes.length << 1); return true;
}

// Local copy of the JP resource release (ffbejpdata): mst/ keeps its folder, everything else is flat.
const LOCAL = '/data/local/tmp/ffbe/';
const RESOURCE = /^https?:\/\/[^/]+\/lapis\/resource\/([^?]*)/;
let localized = 0;
const missingSeen = {};
// Korean scene CPKs (build/apply_ko_story.py -> build/deploy_ko_story.py) sit beside the originals in flat_ko/;
// a file there wins over flat/. Same length as flat/ + 3, still within libc++ capacity checks below.
const c_access = new NativeFunction(Module.getGlobalExportByName('access'), 'int', ['pointer', 'int']);
function localize(sp) {
  const m = RESOURCE.exec(rstr(sp)); if (!m) return;
  const rel = m[1];
  const name = rel.substring(rel.lastIndexOf('/') + 1);
  // Korean masters (build/apply_ko_names.py) likewise sit in mst_ko/ beside mst/.
  const isMst = rel.indexOf('mst/') === 0;
  const ko = LOCAL + (isMst ? 'mst_ko/' : 'flat_ko/') + name;
  const local = c_access(Memory.allocUtf8String(ko), 0) === 0 ? ko : (isMst ? LOCAL + rel : LOCAL + 'flat/' + name);
  // 2026-11-14: name the resource the release folder lacks (InitialDownloadScene then fails with a notice).
  if (local !== ko && c_access(Memory.allocUtf8String(local), 0) !== 0 && !missingSeen[rel]) { missingSeen[rel] = 1; note('LOCAL_MISSING ' + rel); }
  if (!setStd(sp, local)) note('LOCAL_FILE_TOO_LONG ' + rel);
  else if (++localized <= 5 || (localized & (localized - 1)) === 0) note('LOCAL_FILE count=' + localized + ' ' + local);
}

function install(m) {
  const exp = n => m.getExportByName(n);
  const attach = (n, cb) => { try { Interceptor.attach(exp(n), cb); } catch (e) { note('HOOK_FAILED ' + n + ' ' + e); } };
  const replace = (n, ret, args, fn) => { try { Interceptor.replace(exp(n), new NativeCallback(fn, ret, args)); } catch (e) { note('HOOK_FAILED ' + n + ' ' + e); } };
  if (TRACE_INSTALL) installLoadingTrace(m);

  // JP 11.0.0 ResultBaseScene::setRematchBtn: the reinforcement variant draws
  // <size=20>helper</size><br><size=26>rematch</size>, even with an empty helper.
  // Its call at +0x310 only selects the button's label/arrow layout. Return false
  // to that single caller to use the game's existing one-line layout (Y - 5).
  // All other reinforcement queries, including the retry action, stay original.
  const rematchLayout = exp('_ZN15ResultBaseScene13setRematchBtnEiiiii');
  const rematchLayoutReturn = rematchLayout.add(0x314);
  if (Instruction.parse(rematchLayoutReturn).mnemonic === 'tbz') {
    let reported = false;
    attach('_ZN10MissionMst21isEnableReinforcementEv', {
      onEnter() { this.rematchLabel = this.returnAddress.equals(rematchLayoutReturn); },
      onLeave(r) {
        if (!this.rematchLabel) return;
        r.replace(ptr(0));
        if (!reported) { reported = true; note('KO_REMATCH_LABEL single-line layout'); }
      }
    });
  } else note('KO_REMATCH_LABEL layout differs, left unchanged');

  // Sound (2026-11-09, build/out/jp_offline/sound/run1_stream.log): the APK's own ACBs are HCA-MX at 44100 Hz and
  // CriUtils::initializeLibrary sets the HCA-MX mixer to 44100, but every HCA-MX waveform in the ffbejpdata release
  // (866 waveforms: all BGM, 78 System.acb cues) is 48000 Hz. HCA-MX cannot resample, so those cues end at once
  // (criAtomExPlayer_GetStatus 3 after 200 ms) = no BGM / missing summon and button sounds. HCA (type 2) SE play.
  // Run the HCA-MX mixer and voice pool at 48000 so the release data plays. Installed first: the CRI library
  // initializes ~1.4 s after libgame loads. Only 44100 values are rewritten.
  if (HCAMX_RATE) {
    let hcamxPatched = 0;
    const rate = (tag, offs) => ({ onEnter(a) {
      const c = a[0]; if (c.isNull()) return;
      for (const o of offs) if (c.add(o).readS32() === 44100) { c.add(o).writeS32(HCAMX_RATE); hcamxPatched++; }
      note('HCAMX_RATE ' + tag + ' -> ' + offs.map(o => c.add(o).readS32()).join(','));
    } });
    // CriAtomExHcaMxConfig: float server_frequency, num_mixers, max_voices, max_input_channels, max_sampling_rate(+16),
    // output_channels, output_sampling_rate(+24), sound_renderer_type. Voice pool config: identifier, num_voices,
    // player_config { max_channels, max_sampling_rate(+12), ... } (values observed with jp_sound_trace.js).
    for (const n of ['criAtomExHcaMx_SetConfigForWorkSizeCalculation', 'criAtomExHcaMx_CalculateWorkSize', 'criAtomExHcaMx_Initialize'])
      attach(n, rate(n.replace('criAtomExHcaMx_', ''), [16, 24]));
    for (const n of ['criAtomExVoicePool_CalculateWorkSizeForHcaMxVoicePool', 'criAtomExVoicePool_AllocateHcaMxVoicePool'])
      attach(n, rate(n.replace('criAtomExVoicePool_', ''), [12]));
    // The APK's assets/android/se/Builtin.acb (80032 B: OK/NO buttons, logo-screen game start, download end) is
    // 44100 Hz HCA-MX and fails on the 48000 mixer (status 4, CRI error 44100/48000). Substituting the release
    // System.acb cues changed the logo-screen sound (its title cues differ), so keep Builtin's own audio: HCA-MX
    // streams are plain HCA, so mark its three HCA-MX waveforms as HCA (EncodeType 6 -> 2) and they play through the
    // HCA voice pool (max 44100) instead. WaveformTable EncodeType bytes at file offsets 1969/1976/1983/1990 = 6,2,6,6.
    const BUILTIN_SIZE = 80032, BUILTIN_ENCODE_TYPE_AT = [1969, 1983, 1990];
    const builtinCopies = [];
    attach('criAtomExAcb_LoadAcbData', { onEnter(a) {
      if (a[1].toInt32() !== BUILTIN_SIZE) return;
      if (!BUILTIN_ENCODE_TYPE_AT.every(o => a[0].add(o).readU8() === 6) || a[0].add(1976).readU8() !== 2) {
        note('BUILTIN_ACB layout differs, left as is'); return;
      }
      const copy = Memory.alloc(BUILTIN_SIZE); Memory.copy(copy, a[0], BUILTIN_SIZE);  // CRI keeps using this data
      for (const o of BUILTIN_ENCODE_TYPE_AT) copy.add(o).writeU8(2);
      builtinCopies.push(copy);  // kept alive for the process (80 KB per load; Builtin loads once per launch)
      a[0] = copy; note('BUILTIN_ACB HCA-MX -> HCA');
    } });
  }

  // End-service date gate (2026-02-08 JST): keep the normal title flow.
  replace('_ZN11CommonUtils14isRefundPeriodEv', 'int', [], () => 1);
  // CRI installer: read the release files stored on this device instead of the CDN.
  // Also deduplicate dstPath (a[1]) within the same batch (vectors at this+0x28 and this+0x40, stride 0x58,
  // dstPath at elem+0x08): CriFileInstallerImpl spawns 5 parallel CriFsInstaller workers (0x15d53c4), and if
  // the same uncached file (e.g. mission 42240101 queuing la00711_bgm_FF7R_Kikaitou_no_Kessen.acb twice) is
  // queued twice, Worker 1 deletes dstPath (0x15df898) while Worker 0 is copying to it (0x15df8d4), causing
  // CRIFSINSTALLER_STATUS_ERROR (3) -> [impl+0x68]=1 ("로컬 게임 데이터를 불러올 수 없습니다") on the first attempt.
  const addLoadSym = '_ZN16CriFileInstaller11addLoadFileERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEES8_S8_iii';
  const origAddLoad = new NativeFunction(exp(addLoadSym), 'void', ['pointer', 'pointer', 'pointer', 'pointer', 'int', 'int', 'int']);
  replace(addLoadSym, 'void', ['pointer', 'pointer', 'pointer', 'pointer', 'int', 'int', 'int'], (self, dstP, srcP, md5P, size, fileId, prio) => {
    const dst = rstr(dstP);
    if (dst) {
      for (const vecOff of [0x28, 0x40]) {
        let cur = self.add(vecOff).readPointer();
        const end = self.add(vecOff + 8).readPointer();
        while (!cur.isNull() && cur.compare(end) < 0) {
          if (rstr(cur.add(8)) === dst) {
            note('LOCAL_DUP_SKIP ' + dst);
            return;
          }
          cur = cur.add(0x58);
        }
      }
    }
    localize(srcP);
    origAddLoad(self, dstP, srcP, md5P, size, fileId, prio);
  });
  // 기존 우회: 구분자뿐인 실패 목록은 parseList(strtok -> NULL)를 크래시시킨다.
  // 실제 파일 실패가 없다는 뜻은 아니다. 실패 목록 원인 규명 전까지 이 우회는 유지한다.
  replace('_ZN16CriFileInstaller17addLoadFailedFileEv', 'void', ['pointer'], () => {});
  // Local data is already on the device: answer the download confirmation with "yes" (Global disables its DLC prompt).
  // JP 11.0.0's RmResumeInfo constructor leaves missionState (+0x30) unset (0 = "restart"), so every login
  // asks to resume a quest that does not exist. Global 9.0.0's constructor stores -1 there; do the same.
  // The singleton may already exist when these hooks install, so also fix it on the first shared() access.
  attach('_ZN12RmResumeInfoC2Ev', { onEnter(a) { this.t = a[0]; }, onLeave() { this.t.add(0x30).writeS32(-1); } });
  let rmFixed = false;
  attach('_ZN12RmResumeInfo6sharedEv', { onLeave(r) {
    if (rmFixed || r.isNull()) return; rmFixed = true;
    if (r.add(0x30).readS32() === 0) { r.add(0x30).writeS32(-1); note('RM_RESUME_STATE_INIT -1'); } } });
  attach('_ZN20DownloadConfirmScene11updateEventEv', { onEnter(a) {
    const t = a[0]; if (t.add(0x545).readU8() === 0) { t.add(0x545).writeU8(1); t.add(0x546).writeU8(1); note('DOWNLOAD_CONFIRM_AUTO_YES'); } } });
  // JP TicketMstList::getObjectList (0x1cddaa8) falls back to matching raw detailId against F_TICKET_MST when
  // ticketGroupId (+0x88) is 0, causing accidental Global detailId collisions on banners without a ticket group.
  // Guard isUseTicket only when ticketGroupId <= 0; banners with ticket_group_id (10020/10010) keep tickets active.
  let ticketGuarded = 0;
  attach('_ZN14GachaDetailMst11isUseTicketEv', {
    onEnter(a) { this.noGroup = a[0].add(0x88).readS32() <= 0; },
    onLeave(r) { if (this.noGroup && r.toInt32()) { r.replace(0); if (++ticketGuarded <= 5) note('GACHA_TICKET_NO_GROUP_GUARD'); } }
  });
  // Fit & center gacha banners proportionally inside each scene's LayoutCache box, and sync GachaTopScene pressed overlays.
  try {
    const spriteWidth = new NativeFunction(exp('_ZN10GameSprite8getWidthEv'), 'int', ['pointer']);
    const spriteHeight = new NativeFunction(exp('_ZN10GameSprite9getHeightEv'), 'int', ['pointer']);
    const spriteSetSize = new NativeFunction(exp('_ZN10GameSprite7setSizeEff'), 'void', ['pointer', 'float', 'float']);
    const nodeAnchor = new NativeFunction(exp('_ZNK7cocos2d4Node14getAnchorPointEv'), 'pointer', ['pointer']);
    const nodeGetX = new NativeFunction(exp('_ZNK7cocos2d4Node12getPositionXEv'), 'float', ['pointer']);
    const nodeGetY = new NativeFunction(exp('_ZNK7cocos2d4Node12getPositionYEv'), 'float', ['pointer']);
    const nodeSetX = new NativeFunction(exp('_ZN7cocos2d4Node12setPositionXEf'), 'void', ['pointer', 'float']);
    const nodeSetY = new NativeFunction(exp('_ZN7cocos2d4Node12setPositionYEf'), 'void', ['pointer', 'float']);
    const lcGetWidth = new NativeFunction(exp('_ZN11LayoutCache8getWidthEv'), 'float', ['pointer']);
    const lcGetHeight = new NativeFunction(exp('_ZN11LayoutCache9getHeightEv'), 'float', ['pointer']);
    const scrlGetBanner = new NativeFunction(exp('_ZNK18GachaDetailScrlObj9getBannerEv'), 'pointer', ['pointer']);
    let topListDepth = 0;
    attach('_ZN13GachaTopScene13setListLayoutEv', {
      onEnter() { topListDepth++; },
      onLeave() { topListDepth--; }
    });
    attach('_ZN12SpriteButton19initForChangeSpriteEiffiP10GameSpriteS1_ib', {
      onEnter(a) {
        if (topListDepth <= 0 || a[2].isNull() || a[3].isNull()) return;
        const w = spriteWidth(a[2]), h = spriteHeight(a[2]);
        if (w > 0 && h > 0 && (spriteWidth(a[3]) !== w || spriteHeight(a[3]) !== h)) {
          spriteSetSize(a[3], w, h);
        }
      }
    });
    let inScrlAdd = false, lastLc = ptr(0), fitReports = 0;
    const scrlOffsets = new Map();
    attach('_ZN15LayoutCacheList9getObjectERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE', {
      onLeave(r) { if (inScrlAdd) lastLc = r; }
    });
    attach('_ZN18GachaDetailScrlObj9addObjectEiff', {
      onEnter(a) {
        this.obj = a[0];
        inScrlAdd = true;
        lastLc = ptr(0);
        scrlOffsets.delete(this.obj.toString());
      },
      onLeave() {
        inScrlAdd = false;
        try {
          if (!this.obj || this.obj.isNull()) return;
          const node = scrlGetBanner(this.obj);
          if (node.isNull()) return;
          const srcW = spriteWidth(node), srcH = spriteHeight(node);
          if (srcW <= 0 || srcH <= 0) return;
          const isKeyItem = this.obj.add(0x350).readU8() !== 0;
          let lcW = 0, lcH = 0;
          if (isKeyItem) {
            lcW = 640; lcH = 268;
          } else if (!lastLc.isNull()) {
            lcW = lcGetWidth(lastLc); lcH = lcGetHeight(lastLc);
          }
          if (lcW <= 0 || lcH <= 0) return;
          const scale = Math.min(lcW / srcW, lcH / srcH);
          const fitW = srcW * scale, fitH = srcH * scale;
          if (Math.abs(fitW - srcW) > 0.5 || Math.abs(fitH - srcH) > 0.5) {
            spriteSetSize(node, fitW, fitH);
          }
          const dx = lcW - fitW, dy = lcH - fitH;
          scrlOffsets.set(this.obj.toString(), { dx, dy });
          const pt = nodeAnchor(node);
          const ax = pt.readFloat(), ay = pt.add(4).readFloat();
          if (Math.abs(dx) > 0.5) nodeSetX(node, nodeGetX(node) + (0.5 - ax) * dx);
          if (Math.abs(dy) > 0.5) nodeSetY(node, nodeGetY(node) + (0.5 - ay) * dy);
          if (fitReports++ < 16)
            note('GACHA_ART_FIT src=' + srcW + 'x' + srcH + ' box=' + lcW.toFixed(0) + 'x' + lcH.toFixed(0) +
              ' fit=' + fitW.toFixed(1) + 'x' + fitH.toFixed(1));
        } catch (e) { note('GACHA_ART_FIT err ' + e); }
      }
    });
    attach('_ZN18GachaDetailScrlObj14updatePositionEff', {
      onEnter(a) { this.obj = a[0]; },
      onLeave() {
        try {
          if (!this.obj || this.obj.isNull()) return;
          const box = scrlOffsets.get(this.obj.toString());
          if (!box || Math.abs(box.dx) <= 0.5) return;
          const node = scrlGetBanner(this.obj);
          if (node.isNull()) return;
          const pt = nodeAnchor(node);
          nodeSetX(node, nodeGetX(node) + (0.5 - pt.readFloat()) * box.dx);
        } catch (e) {}
      }
    });
    attach('_ZN18GachaDetailScrlObjD1Ev', {
      onEnter(a) { scrlOffsets.delete(a[0].toString()); }
    });
  } catch (e) { note('GACHA_ART_FIT hook failed ' + e); }
  if (DEBUG) {
    // Read-only tracing while the JP flow is being brought up: scene construction/changes and login exit checks.
    let scenes = 0;
    for (const e of m.enumerateExports()) {
      if (e.type === 'function' && /^_ZN\d+\w*SceneC1Ev$/.test(e.name)) {
        try {
          Interceptor.attach(e.address, { onEnter() {
            const sn = e.name.replace(/^_ZN\d+/, '').replace(/C1Ev$/, '');
            if (sn === 'GateScene' || sn === 'GachaTopScene') { artMap = null; bySize = null; artDims = null; }
            note('SCENE_NEW ' + sn);
          } });
          scenes++;
        } catch (err) {}
      }
    }
    attach('_ZN10LoginScene15changeNextSceneEv', { onEnter() { artMap = null; bySize = null; artDims = null; rmFinal = false; note('LOGIN_EXIT'); } });
    attach('_ZN10LoginScene15isUpdatedPolicyEv', { onLeave(r) { note('CHECK isUpdatedPolicy -> ' + r.toInt32()); } });
    for (const n of ['_ZN8UserInfo13isTutoPlayingEv', '_ZN8UserInfo9existUserEv'])
      attach(n, { onLeave(r) { note('CHECK ' + n.replace(/^_ZN8UserInfo\d+/, '').replace(/Ev$/, '') + ' -> ' + r.toInt32()); } });
    attach('_ZN8UserInfo9setUserIDERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE', { onEnter(a) {
      const bt = Thread.backtrace(this.context, Backtracer.ACCURATE).slice(0, 6).map(p => { const s = DebugSymbol.fromAddress(p); return (s.name || p).toString().substring(0, 60); });
      note('SET_USER_ID [' + rstr(a[1]) + '] from ' + bt.join(' < ')); } });
    for (const e of m.enumerateExports())
      if (e.type === 'function' && /^_ZN14SuspendManager(\d+is|\d+exist)\w*Ev$/.test(e.name))
        try { Interceptor.attach(e.address, { onLeave(r) { if (r.toInt32() & 1) note('SUSPEND ' + e.name.replace(/^_ZN14SuspendManager\d+/, '').replace(/Ev$/, '') + ' -> 1'); } }); } catch (err) {}
    for (const n of ['_ZN12RbResumeInfo6sharedEv']) {}
    attach('_ZN11NoticeSceneC1Ev', { onEnter() {
      const bt = Thread.backtrace(this.context, Backtracer.FUZZY).slice(0, 10).map(p => { const s = DebugSymbol.fromAddress(p); return (s.name || p).toString().substring(0, 70); });
      note('NOTICE_FROM ' + bt.join(' < ')); } });
    note('DEBUG_TRACE scenes=' + scenes);
    if (TRACE_GACHA) {
      // Gacha list bring-up (2026-11-08): trace every call into the classes that build the summon top list,
      // so we can see which step drops the served banner. Count-limited per symbol.
      const GACHA_TRACE = /^_ZN[K]?\d+(GachaTopScene|GachaScheduleMst\w*|GachaBannerDownloader|GachaMstList|GachaMst|GachaDetailMstList|GachaUtil|ScrlGachaBanner\w*|GachaListObj\w*)\d/;
      const traced = [];
      for (const e of m.enumerateExports()) {
        if (e.type !== 'function' || !GACHA_TRACE.test(e.name) || /C[12]E|D[012]E/.test(e.name)) continue;
        let calls = 0;
        try {
          Interceptor.attach(e.address, {
            onEnter(a) { this.go = calls++ < 6; if (this.go && /createBanner/.test(e.name)) this.arg = rstr(a[0]); },
            onLeave(r) { if (this.go) note('GT ' + e.name.substring(0, 110) + (this.arg ? ' path=' + this.arg : '') + ' -> ' + r); }
          });
          traced.push(e.name);
        } catch (err) {}
      }
      note('GACHA_TRACE hooks=' + traced.length);
      // Which image names/paths does the list ask for while setListLayout runs?
      let inList = 0;
      attach('_ZN13GachaTopScene13setListLayoutEv', { onEnter() { inList++; }, onLeave() { inList--; } });
      const STR_ARG = /(FileUtils\w*(fullPathForFilename|isFileExist|getDataFromFile|getStringFromFile)|GameSprite\w*create\w*|SpriteUtil\w*|ResourceManager\w*|CriFsUtil\w*|ImageDownload\w*|BannerDownload\w*|TextureCache\d+add\w*)/;
      let fileHooks = 0;
      for (const e of m.enumerateExports()) {
        if (e.type !== 'function' || !STR_ARG.test(e.name) || !/basic_string/.test(e.name)) continue;
        let calls = 0;
        try {
          Interceptor.attach(e.address, {
            onEnter(a) {
              if (!inList || calls++ > 40) return;
              const s = [rstr(a[0]), rstr(a[1]), rstr(a[2])].filter(x => /png|jpg|gacha|banner/i.test(x));
              if (s.length) note('GL ' + e.name.substring(0, 90) + ' ' + s.join(' | '));
            }
          });
          fileHooks++;
        } catch (err) {}
      }
      note('GACHA_FILE_HOOKS ' + fileHooks);
      // Which loader functions run while the list builds (no string filter)?
      const LOADERS = /(initWithImage|getDataFromFile|getContents|CriFs|criFs|LoadFile|loadImage|ImageUtil|ResourceUtil|readFile|[Dd]ecrypt|Cipher|Crypt|Unpack|FileLoader|GameSprite\d+create)/;
      let loaderHooks = 0;
      for (const e of m.enumerateExports()) {
        if (e.type !== 'function' || !LOADERS.test(e.name) || /C[12]E|D[012]E/.test(e.name)) continue;
        let calls = 0;
        try {
          Interceptor.attach(e.address, { onEnter(a) {
            if (!inList || calls++ > 3) return;
            note('LD ' + e.name.substring(0, 120) + ' | ' + [rstr(a[0]), rstr(a[1]), rstr(a[2])].filter(x => x && x.length < 200 && /[a-z]/.test(x)).join(' | '));
          } });
          loaderHooks++;
        } catch (err) {}
      }
      note('LOADER_HOOKS ' + loaderHooks);
      let finds = 0;
      attach('criFsBinder_Find', { onEnter(a) {
        if (!inList || finds++ > 3) return;
        let p = ''; try { p = a[1].readUtf8String(); } catch (e) {}
        const bt = Thread.backtrace(this.context, Backtracer.ACCURATE).slice(0, 8).map(x => { const s = DebugSymbol.fromAddress(x); return (s.name || x).toString().substring(0, 70); });
        note('FIND ' + p + ' <= ' + bt.join(' < '));
      } });
    }
  }

  // ---- Summon banner art the JP CPKs do not have (Global banners, docs/plans/2026-11-08-jp-gacha-seasons.md) ----
  // JP draws banner art through CRI: criFsBinder_Find(name) -> CRI load -> cocos2d::Image::initWithImageData(bytes).
  // jp_banner_art.json (build/make_jp_banners.py; copied to files/exvius/ by the JP engine patch) maps stand-in JP
  // image names -> Global PNG path + the stand-in's byte size. Byte size is shared with unrelated files, so the
  // swap also verifies the decoded PNG's IHDR against jp_art_dims.json and the criFsBinder_Find file name.
  const FILES = '/data/data/com.exvius.jpkorean.app/files/';
  const libc = Process.getModuleByName('libc.so');
  const c_open = new NativeFunction(libc.getExportByName('open'), 'int', ['pointer', 'int']);
  const c_read = new NativeFunction(libc.getExportByName('read'), 'long', ['int', 'pointer', 'long']);
  const c_close = new NativeFunction(libc.getExportByName('close'), 'int', ['int']);
  function readFileBytes(path) {
    const fd = c_open(Memory.allocUtf8String(path), 0); if (fd < 0) return null;
    const chunks = []; let total = 0;
    for (;;) { const b = Memory.alloc(65536); const n = Number(c_read(fd, b, 65536)); if (n <= 0) break; chunks.push([b, n]); total += n; }
    c_close(fd); const out = Memory.alloc(total); let off = 0;
    for (const [b, n] of chunks) { Memory.copy(out.add(off), b, n); off += n; }
    return [out, total];
  }
  let artMap = null, bySize = null, artDims = null; const bytesCache = {};
  function loadArtMap() {
    if (artMap) return true;
    const f = readFileBytes(FILES + 'exvius/jp_banner_art.json'); if (!f) return false;
    const j = JSON.parse(f[0].readUtf8String(f[1]));
    artMap = j.art || {};
    bySize = {}; for (const k in artMap) { const a = artMap[k]; if (a && a.size) bySize[a.size] = { key: k, path: a.path }; }
    note('BANNER_ART map=' + Object.keys(artMap).length + ' stamp=' + (j.stamp || '-')); return true;
  }
  // jp_art_dims.json (build/make_jp_art_dims.py): the stand-in's real PNG size, {"dims":{name:{w,h}}, "by_size":{size:{w,h}}}.
  // Used to reject a same-byte-length image that is not the stand-in (build/out/summon_sprite/rain_lasswell.md).
  function loadArtDims() {
    if (artDims) return true;
    const f = readFileBytes(FILES + 'exvius/jp_art_dims.json'); if (!f) return false;
    artDims = {};
    let d = null; try { d = JSON.parse(f[0].readUtf8String(f[1])); } catch (e) { d = null; }
    const add = (k, v) => { if (!v || typeof v !== 'object') return; const w = v.w | 0, h = v.h | 0; if (w > 0 && h > 0) artDims[k] = [w, h]; };
    if (d) { for (const k in (d.dims || {})) add(k, d.dims[k]); for (const k in (d.by_size || {})) add(k, d.by_size[k]); }
    note('BANNER_ART dims=' + Object.keys(artDims).length); return true;
  }
  // loadArtMap() can run on splash images before Chaquopy starts and copies the updated jp_banner_art.json from app.imy;
  // invalidate cached art tables when leaving LoginScene so post-login scenes always read the current engine copy.
  attach('_ZN10LoginScene15changeNextSceneEv', { onEnter() { artMap = null; bySize = null; artDims = null; } });
  function pngSize(p, n) {  // PNG IHDR width/height; null when the decode is not a plain PNG
    try {
      if (n < 24) return null;
      const b = new Uint8Array(p.readByteArray(24));
      if (b[0] !== 0x89 || b[1] !== 0x50 || b[2] !== 0x4e || b[3] !== 0x47) return null;
      const w = ((b[16] << 24) | (b[17] << 16) | (b[18] << 8) | b[19]) >>> 0;
      const h = ((b[20] << 24) | (b[21] << 16) | (b[22] << 8) | b[23]) >>> 0;
      return (w > 0 && h > 0) ? [w, h] : null;
    } catch (e) { return null; }
  }
  // Every JP/Global gacha+event banner is 640 px wide (layout CSVs reserve 640x160 for the summon list row,
  // 640x240 for the spdungeon tiles, 640x392 for the detail art; every decrypted stand-in is 640 wide).
  const BANNER_W = 640;
  let findName = '', findTid = 0, findAt = 0, artFed = 0, artSkipped = 0;
  // JP-absent dungeon/area banner icons (F_ICON_MST names only the Global pack ships) -> the same area's
  // JP-shipped banner, at the CRI lookup itself so every loader of that name resolves (a batch-node-only swap
  // left GateDungeonScene's tile empty: device 2026-11-14, 711). Table: build/make_jp_icon_fallback.py.
  const iconRedirect = {};
  let iconRedirected = 0;
  attach('criFsBinder_Find', { onEnter(a) {
    try {
      let p = a[1].readUtf8String() || '';
      let s = p.lastIndexOf('/');
      const sub = (globalThis.__jpIconFallback || {})[s >= 0 ? p.substring(s + 1) : p];
      if (sub) {
        const np = p.substring(0, s + 1) + sub;
        let buf = iconRedirect[np];
        if (!buf) { buf = Memory.allocUtf8String(np); iconRedirect[np] = buf; }   // kept alive (GC)
        a[1] = buf;
        if (++iconRedirected <= 5 || (iconRedirected & (iconRedirected - 1)) === 0) note('ICON_REDIRECT ' + p + ' -> ' + np + ' n=' + iconRedirected);
        p = np; s = p.lastIndexOf('/');
      }
      findName = s >= 0 ? p.substring(s + 1) : p;
      findTid = Process.getCurrentThreadId(); findAt = Date.now();
    } catch (e) {}
  } });
  // Size alone is not an identity: unit_anime_100032817.png is exactly the same byte length as a stand-in banner
  // (118,699 B) and was swapped (14 accidental clashes over 11 units). Replace only when the decoded image is
  // provably that stand-in: its recorded IHDR size, or the file name criFsBinder_Find asked for (plus 640-wide,
  // since every banner is 640 wide and a sprite sheet is not).
  // Hi-res stand-ins: cocos draws a texture at 1 texel per point, so a 1280-wide banner would be twice the tile.
  // Sprite scaling does not stick (the game re-applies its own), so instead the texture reports the 640-wide size:
  // after Texture2D::initWithImage, rewrite _pixelsWide/_pixelsHigh (int pair) and _contentSize (float pair) to the
  // banner size. Texture coords are rect / pixelsWide, so the sprite still samples the whole 1280-wide GL texture.
  const hiresImg = new Map();
  let hiresFixed = 0;
  attach('_ZN7cocos2d9Texture2D13initWithImageEPNS_5ImageENS0_11PixelFormatE', {
    onEnter(a) { const k = a[1].toString(); this.d = hiresImg.get(k); if (this.d) hiresImg.delete(k); this.t = a[0]; },
    onLeave() {
      const d = this.d; if (!d) return;
      const [w, h] = d, nw = BANNER_W, nh = Math.round(h * BANNER_W / w);
      let ip = -1, fp = -1;
      for (let o = 8; o < 0x100 && (ip < 0 || fp < 0); o += 4) {
        const p = this.t.add(o);
        if (ip < 0 && p.readS32() === w && p.add(4).readS32() === h) ip = o;
        if (fp < 0 && p.readFloat() === w && p.add(4).readFloat() === h) fp = o;
      }
      if (ip < 0 || fp < 0) { note('BANNER_ART hires fields not found ip=' + ip + ' fp=' + fp); return; }
      this.t.add(ip).writeS32(nw); this.t.add(ip + 4).writeS32(nh);
      this.t.add(fp).writeFloat(nw); this.t.add(fp + 4).writeFloat(nh);
      if (++hiresFixed <= 5 || (hiresFixed & (hiresFixed - 1)) === 0)
        note('BANNER_ART hires ' + w + 'x' + h + '->' + nw + 'x' + nh + ' ip=0x' + ip.toString(16) + ' fp=0x' + fp.toString(16) + ' n=' + hiresFixed);
    } });
  attach('_ZN7cocos2d5ImageD2Ev', { onEnter(a) { if (hiresImg.size) hiresImg.delete(a[0].toString()); } });
  attach('_ZN7cocos2d5Image17initWithImageDataEPKhl', { onEnter(a) {
    const n = a[2].toInt32(); if (n < 4096 || !loadArtMap()) return;
    const hit = bySize[n]; if (!hit || !hit.path) return;
    const key = hit.key, rel = hit.path;
    const px = pngSize(a[1], n);
    loadArtDims();
    const want = artDims[key] || artDims[String(n)] || null;
    const named = (findTid === Process.getCurrentThreadId() && Date.now() - findAt < 500) ? findName : '';
    findAt = 0;  // one Find authorizes one decode; never let it license a later same-size load
    const dimsOk = !!want && !!px && px[0] === want[0] && px[1] === want[1];
    // exact name match plus banner-sized width (some JP banners are 637 wide; unit sheets are 1000+)
    const nameOk = !!named && named === key && !!px && px[0] >= 400 && px[0] < 1000;
    if (!(dimsOk || nameOk)) {  // size alone never swaps (a same-length sprite sheet is not the stand-in)
      if (artSkipped++ < 10) note('BANNER_ART skip n=' + n + ' px=' + (px ? px[0] + 'x' + px[1] : '?') +
        ' want=' + (want ? want[0] + 'x' + want[1] : '?') + ' name=' + (named || '-') + ' key=' + key);
      return;
    }
    let f = bytesCache[rel];
    if (!f && ART_DEV_OVERRIDE) {  // dev override: /data/local/tmp/ffbe/art/<basename> wins (lets a non-debuggable build test art)
      const ov = LOCAL + 'art/' + rel.substring(rel.lastIndexOf('/') + 1);
      // keep the buffer in bytesCache: an uncached Memory.alloc is GC-freed before cocos reads it (SIGSEGV in isCCZBuffer)
      if (c_access(Memory.allocUtf8String(ov), 0) === 0) { f = readFileBytes(ov); if (f) { bytesCache[rel] = f; note('BANNER_ART override ' + ov); } }
    }
    if (!f) { f = readFileBytes(FILES + rel); if (!f) { note('BANNER_ART missing ' + rel); return; } bytesCache[rel] = f; }
    a[1] = f[0]; a[2] = ptr(f[1]);
    const fpx = pngSize(f[0], f[1]);  // hi-res stand-in (e.g. 1280x480): draw it at the 640-wide banner size
    if (fpx && fpx[0] > BANNER_W) hiresImg.set(a[0].toString(), fpx);
    if (++artFed <= 5 || (artFed & (artFed - 1)) === 0) note('BANNER_ART fed ' + artFed + ' ' + rel + (nameOk ? ' name' : ' dims'));
  } });
  // ---- Rm (지도형 이벤트) 지역 전환 (2026-11-13) ----
  // GateScene::touchEnded: 0x1be0590 `ldr w23,[x20,#0x88]` = 터치한 타일 areaId,
  // 0x1be0594 `cmp w23,w26` (w26 = RmEventInfo::getAreaId) -- 같을 때만 0x1be059c RmEntryScene(13000).
  // RmEventInfo 는 싱글턴(+8 areaId, RmEventInfo::shared 0x1d13db8)이라 게이트 응답은 한 지역만 실을 수 있다.
  // 다른 Rm 지역 타일을 누르면 (a) 싱글턴 +8 에 그 지역을 쓰고 (b) x26 을 w23 과 같게 만들어 비교를 통과시킨 뒤
  // (c) 엔진이 RmEntry(wx5sg9ye)에서 읽을 지역 id 를 files/exvius/jp_rm_area.txt 에 남긴다.
  // 기간 문자열(+0x10/+0x28)은 건드리지 않는다. 목록은 jp_rm_areas.json(엔진과 같은 파일; build/make_jp_rm_areas.py).
  try {
    const rmShared = new NativeFunction(m.findExportByName('_ZN11RmEventInfo6sharedEv'), 'pointer', []);
    const c_write = new NativeFunction(libc.getExportByName('write'), 'long', ['int', 'pointer', 'long']);
    const c_open3 = new NativeFunction(libc.getExportByName('open'), 'int', ['pointer', 'int', '...', 'int']);
    const c_unlink = new NativeFunction(libc.getExportByName('unlink'), 'int', ['pointer']);
    const c_fchmod = new NativeFunction(libc.getExportByName('fchmod'), 'int', ['int', 'int']);
    const RM_FILE = FILES + 'exvius/jp_rm_area.txt';
    let rmAreas = { '5040': 1, '725': 1, '729': 1 }, rmFinal = false, rmHits = 0, rmListMiss = 0, rmWriteFail = 0;
    function loadRmAreas() {
      if (rmFinal) return rmAreas;
      const f = readFileBytes(FILES + 'exvius/jp_rm_areas.json');
      if (f) {
        try {
          const arr = JSON.parse(f[0].readUtf8String(f[1]));
          const map = { '725': 1, '729': 1 }; for (const a of arr) map[String(a)] = 1;
          rmAreas = map; rmFinal = true; note('RM_AREA list n=' + Object.keys(map).length);
        } catch (e) { note('RM_AREA list parse failed ' + e); }
      } else if (rmListMiss++ === 0) note('RM_AREA list missing, fallback 5040');
      return rmAreas;
    }
    function writeRmArea(area) {
      // open(2) with O_CREAT needs the mode argument: the 2-argument c_open left it to a garbage register, the
      // file came out unreadable and the engine kept the old area (2026-11-13 device: switch logged, map 5040).
      // Remove any such file first, then create it 0644.
      const pathPtr = Memory.allocUtf8String(RM_FILE);
      try { c_unlink(pathPtr); } catch (_) {}
      const fd = c_open3(pathPtr, 0x241, 0x1a4);   // O_WRONLY|O_CREAT|O_TRUNC, 0644
      if (fd < 0) { if (rmWriteFail++ < 3) note('RM_AREA write open failed ' + RM_FILE); return; }
      try {
        const text = area + '\n';
        c_fchmod(fd, 0x1a4);
        c_write(fd, Memory.allocUtf8String(text), text.length);
      } catch (e) { if (rmWriteFail++ < 3) note('RM_AREA write failed ' + e); }
      c_close(fd);
    }
    Interceptor.attach(m.base.add(0x1be0594), { onEnter() {
      try {
        const touched = this.context.x23.toInt32(), current = this.context.x26.toInt32();
        note('GATE_TAP area=' + touched + ' rmCurrent=' + current);   // 진단용: 누른 구역 id (2026-11-14)
        if (!loadRmAreas()[String(touched)]) return;
        // Always record the touched Rm area: when the gate reply already named this area (touched === current)
        // the file still held the PREVIOUS area and the engine served that map (2026-11-13 device: 861 map
        // after touching another event, correct only on the second entry).
        if (touched === current) { writeRmArea(touched); return; }
        const info = rmShared();
        if (info.isNull()) return;
        info.add(8).writeS32(touched);            // RmEventInfo+8 = areaId (getAreaId reads it)
        this.context.x26 = ptr(touched);          // w26 == w23 -> take the RmEntryScene branch
        writeRmArea(touched);
        if (++rmHits <= 5 || (rmHits & (rmHits - 1)) === 0)
          note('RM_AREA_SWITCH ' + current + ' -> ' + touched + ' n=' + rmHits);
      } catch (e) { note('RM_AREA_SWITCH failed ' + e); }
    } });
    // SealAreaListScene::touchEnded (0x19a1440): cmp w0 (touched areaId), w21 (RmEventInfo areaId)
    Interceptor.attach(m.base.add(0x19a1440), { onEnter() {
      try {
        const touched = this.context.x0.toInt32(), current = this.context.x21.toInt32();
        note('SEAL_TAP area=' + touched + ' rmCurrent=' + current);
        if (!loadRmAreas()[String(touched)]) return;
        if (touched === current) { writeRmArea(touched); return; }
        const info = rmShared();
        if (info.isNull()) return;
        info.add(8).writeS32(touched);
        this.context.x21 = ptr(touched);
        writeRmArea(touched);
        note('SEAL_RM_AREA_SWITCH ' + current + ' -> ' + touched);
      } catch (e) { note('SEAL_RM_AREA_SWITCH failed ' + e); }
    } });
    note('RM_AREA ready base=' + m.base + ' file=' + RM_FILE);
  } catch (e) { note('RM_AREA hook not installed ' + e); }

  // SealAreaListScene story episode back-navigation (2026-11-15):
  // Tab 0 (이야기) cards (5101..5291) carry RB8zTc9G="4,<bodyArea>" (5100..5290) and transition via
  // StoryEventEntryScene -> AreaScene(bodyArea). AreaScene::initialize (0x1a43fb8) checks
  // SealUtil::isSealMission(getFirstMissionId(bodyArea)) to set AreaScene+0x581 (m_isSealArea), and
  // AreaScene::backScene (0x1a46134) opens GateScene when +0x581 is 0 or SealAreaListScene(getTabIndex(areaId))
  // when +0x581 is 1. Because the seal rule row (10004) sits on the card area (5101..5291) rather than the
  // world-10 body area (5100..5290), +0x581 was 0 and getTabIndex(bodyArea) returned -1, sending Back to
  // GateScene instead of SealAreaListScene.
  try {
    let fromSealRoom = false;
    const SEAL_STORY_BODIES = new Set([
      5100, 5155, 5160, 5170, 5180, 5190, 5200, 5210, 5220, 5230, 5240, 5260, 5280, 5290
    ]);
    const sealTouch = m.findExportByName('_ZN17SealAreaListScene10touchEndedEPN7cocos2d5TouchEPNS0_5EventE');
    const gateInit = m.findExportByName('_ZN9GateScene10initializeEv');
    const areaInit = m.findExportByName('_ZN9AreaScene10initializeEv');
    const getTabIdx = m.findExportByName('_ZN8SealUtil11getTabIndexEi');
    if (sealTouch) Interceptor.attach(sealTouch, { onEnter() { fromSealRoom = true; } });
    if (gateInit) Interceptor.attach(gateInit, { onEnter() { fromSealRoom = false; } });
    if (areaInit) {
      Interceptor.attach(areaInit, {
        onEnter(a) { this.scene = a[0]; },
        onLeave() {
          try {
            if (!this.scene || this.scene.isNull()) return;
            const areaId = this.scene.add(0x548).readS32();
            if (fromSealRoom || SEAL_STORY_BODIES.has(areaId)) {
              this.scene.add(0x581).writeU8(1);
              note('SEAL_STORY_AREA_INIT area=' + areaId + ' -> m_isSealArea=1');
            }
          } catch (e) { note('SEAL_STORY_AREA_INIT err ' + e); }
        }
      });
    }
    if (getTabIdx) {
      Interceptor.attach(getTabIdx, {
        onEnter(a) { this.areaId = a[0].toInt32(); },
        onLeave(ret) {
          if (ret.toInt32() < 0 && (fromSealRoom || SEAL_STORY_BODIES.has(this.areaId))) {
            ret.replace(ptr(0));   // Tab 0 (이야기)
          }
        }
      });
    }
    note('SEAL_STORY_BACK hook ready');
  } catch (e) { note('SEAL_STORY_BACK hook failed ' + e); }

  if (typeof installJpRmNoscene === 'function') {
    try { installJpRmNoscene(m, note); } catch (e) { note('RM_NOSCENE_FAILED ' + e.stack); }
  }
  if (typeof installJpSummonMenu === 'function') {
    try { installJpSummonMenu(m, note); } catch (e) { note('JP_SUMMON_MENU_FAILED ' + e.stack); }
  }
  if (typeof installJpTitleMenu === 'function') {
    try { installJpTitleMenu(m, note, makeLocalBridge(m)); } catch (e) { note('JP_TITLE_MENU_FAILED ' + e.stack); }
  }
  note('JP_HOOK_READY libgame=' + m.base);
}
const DEBUG = true;
const ART_DEV_OVERRIDE = true;  // release bundle turns this off (art/ is a dev-only staging folder)
const TRACE_GACHA = false;  // summon-list bring-up tracing (GT/GL/LD/FIND logs), heavy: 700+ hooks
const HCAMX_RATE = 48000;    // 0이면 원래 44100 유지. 근거는 install()의 Sound 주석.
const TRACE_INSTALL = false; // 읽기 전용 로딩 추적. deploy --loading-trace에서만 활성화.

function installLoadingTrace(m) {
  const loadingThreads = new Set();
  const files = new Map();
  const seen = new Set();
  const libc = Process.getModuleByName('libc.so');
  // libc 표준 ABI: FILE* fopen(const char*,const char*), size_t fread(void*,size_t,size_t,FILE*), int fclose(FILE*).
  for (const e of libc.enumerateExports().filter(e => e.type === 'function' && /^(fopen|fopen64|fread|fclose)$/.test(e.name))) {
    if (seen.has(e.address.toString())) continue; seen.add(e.address.toString());
    Interceptor.attach(e.address, {
      onEnter(a) {
        this.t = Date.now(); this.fd = null;
        if (/^fopen/.test(e.name) && loadingThreads.has(Process.getCurrentThreadId())) {
          try { const p = a[0].readUtf8String(); if (/\.(dat|i)$/.test(p)) this.path = p; } catch (_) {}
        } else if (e.name === 'fread') this.fd = files.get(a[3].toString());
        else if (e.name === 'fclose') { this.handle = a[0].toString(); this.fd = files.get(this.handle); }
      },
      onLeave(r) {
        if (this.path && !r.isNull()) files.set(r.toString(), {path:this.path, opened:this.t, readMs:0, reads:0});
        if (!this.fd) return;
        if (e.name === 'fread') { this.fd.readMs += Date.now()-this.t; this.fd.reads++; }
        if (e.name === 'fclose') { note('MST_FILE_DIAG ' + JSON.stringify(Object.assign(this.fd, {ms:Date.now(), elapsed:Date.now()-this.fd.opened}))); files.delete(this.handle); }
      }
    });
  }
  const exports = m.enumerateExports().filter(e => e.type === 'function');
  const costs = new Map();
  for (const e of exports.filter(e => /MstFileUtil|CommonUtils.*(?:Local|Read)|Cipher|Crypto|[Dd]ecrypt|SeekableMstCacheList.*loadMst/.test(e.name))) {
    Interceptor.attach(e.address, {
      onEnter() { this.active = loadingThreads.has(Process.getCurrentThreadId()); if (this.active) this.t = Date.now(); },
      onLeave() { if (!this.active) return; const s = costs.get(e.name) || {name:e.name, calls:0, ms:0}; s.calls++; s.ms += Date.now()-this.t; costs.set(e.name,s); }
    });
  }
  const emit = (event, fields) => note('INSTALL_DIAG ' + JSON.stringify(Object.assign({event, ms: Date.now(), tid: Process.getCurrentThreadId()}, fields)));
  const bt = ctx => Thread.backtrace(ctx, Backtracer.ACCURATE).slice(0, 9).map(p => DebugSymbol.fromAddress(p).toString());
  for (const e of exports) {
    const n = e.name;
    const installer = /^_ZN16CriFileInstaller/.test(n) && !/C[12]Ev|D[012]Ev|6sharedEv|6updateEv/.test(n);
    const scene = /^_ZN20InitialDownloadScene/.test(n) && /initResources|setEndFlg|onSceneInvisible/.test(n);
    const save = /^_ZN9SaveUtils16(?:load|save)UserDefaults/.test(n);
    const mst = /^_ZN19DownloadMstFileList(?:3add|8loadMsts|11saveVersion|12needLoadMsts)/.test(n) || /^_ZN9GameScene15requestMstFiles/.test(n) || /^_ZN10LoginScene(?:\d+procState|11updateEventEv)/.test(n);
    if (!installer && !scene && !save && !mst && n !== 'criFsInstaller_Copy' && n !== 'criFsInstaller_GetStatus') continue;
    let count = 0, previous = '', loginState = null;
    emit('hook', {name:n, offset:e.address.sub(m.base).toString()});
    Interceptor.attach(e.address, {
      onEnter(a) {
        this.t = Date.now(); this.fields = {name:n}; this.enabled = true;
        if (n === '_ZN10LoginScene16procStateMstLoadEv') loadingThreads.add(Process.getCurrentThreadId());
        if (n === '_ZN10LoginScene11updateEventEv') {
          // 원본 updateEvent의 ldr [this,#0x544] 및 상태 분기에서 확인한 int.
          this.fields.state = a[0].add(0x544).readS32();
          if (loginState !== this.fields.state) { emit('login-state', this.fields); loginState = this.fields.state; }
        }
        if (save) {
          this.key = rstr(a[0]);
          this.enabled = /redownload|download|resource_version|mst_version/.test(this.key);
          if (!this.enabled) return;
          this.fields.key = this.key;
          if (n.includes('saveUser')) this.fields.value = rstr(a[1]);
        } else if (n.includes('addLoadFile')) {
          // mangled signature: this, std::string const& x3, int x3 (full overload).
          this.fields.dest = rstr(a[1]); this.fields.src = rstr(a[2]);
          if (n.endsWith('iii')) {
            this.fields.md5 = rstr(a[3]); this.fields.size = a[4].toInt32();
            this.fields.id = a[5].toInt32(); this.fields.mode = a[6].toInt32();
          }
          if (count < 4) this.fields.stack = bt(this.context);
        } else {
          // ABI 미확인 인자는 포인터만 기록하고 문자열로 해석하지 않는다.
          this.fields.args = [a[0],a[1],a[2],a[3]].map(String);
          if (/startEv|addLoadFailed|criFsInstaller_Copy|DownloadMstFileList3add|requestMstFiles/.test(n) && count < 4) this.fields.stack = bt(this.context);
          if (n.includes('DownloadMstFileList3addERK')) { this.fields.table = rstr(a[1]); this.fields.version=a[2].toInt32(); }
        }
        this.poll = /updateEv|updateEventEv|checkInstallEv|isFinishedEv|isErrorEv|isRunningEv|finishCountEv|criFsInstaller_GetStatus|needLoadMstsEv|procState.*Ev|getFileSize.*DownloadEv/.test(n);
        if (!this.poll) emit('enter', this.fields);
      },
      onLeave(r) {
        if (n === '_ZN10LoginScene16procStateMstLoadEv') {
          loadingThreads.delete(Process.getCurrentThreadId());
          if (Date.now()-this.t > 100) { note('MST_COST_DIAG ' + JSON.stringify(Array.from(costs.values()).sort((a,b)=>b.ms-a.ms).slice(0,20))); costs.clear(); }
        }
        if (!this.enabled) return;
        let value = r.toString();
        if (n === '_ZN10LoginScene11updateEventEv') value = 'void';
        if (save && n.includes('loadUser')) { try { value = r.isNull() ? null : r.readUtf8String(); } catch (_) { value = '<unreadable>'; } }
        const state = this.fields.name + ':' + value;
        if (!this.poll || previous !== state || Date.now()-this.t > 100) {
          emit('leave', Object.assign(this.fields, {ret:value, elapsed:Date.now()-this.t}));
          previous = state;
        }
        count++;
      }
    });
  }
}

note('JP_SCRIPT_START');
const wait = setInterval(() => { const m = Process.findModuleByName('libgame.so'); if (m) { clearInterval(wait); install(m); } }, 20);
