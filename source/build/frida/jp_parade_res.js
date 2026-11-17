// jp_parade_res.js — mount the parade area's resource CPK before the parade map draws (2026-11-12).
//
// Crash this fixes: 봉인의 방 → "Battle at Visectrum's Peak" (area 954, Dark Visions area, F_AREA_MST
// q4f9IdMs="108600,400716"). ParadeEntryRequest enters area 954 outside the normal area/gate flow, so the
// client never runs the area's download/version check and the area pack is not mounted. The first map draw
// asks CriFileLoader::texture("map954_1.jpg") (loaderFetch 0x15dcf54) -> 0x0 -> existsWrap 0x15d711c -> 0 ->
// Texture2D::getContentSize(this=null) = SIGSEGV at libgame 0x21c49d4 from AreaMapManager::setLayoutAreaMap+0x1a0.
//
// How the normal area path mounts that pack (libgame.orig.so, JP 11.0.0 sha256 54ef0fe9...):
//   AreaScene::initialize+0x158 -> AreaMapManager::bindAreaMapCpkAsync(AreaMst*) 0x1a43838 (only caller):
//   AreaMst::getFileInfo() (member +0x28, comma separated resource ids) -> split "," -> for each id
//   ResourceMapMstList lookup -> the resource's file list -> entries ending ".cpk" ->
//   CriFileLoader::bindCpk(name, 2) 0x15dc78c
//       = cocos2d FileUtils::fullPathForFilename(name)            (0x113dd40 + vtable[0x118])
//       + criFsBinder_BindCpk(loader->binder, .., path, .., 2)    (0x15d6360 -> PLT criFsBinder_BindCpk)
//       + insert into the loader's bound-file map                 (0x15dc98c)
//   with loader = *CriFileLoader holder (holder = static accessor 0x15a246c, first field = loader).
// Parade route: ParadeAreaScene::initialize skips that block when a mission is already selected
// (+0x5d8 != 0, the entry case) and calls onSelectedDungeon -> ParadeDungeonScene -> DungeonScene::setLayout
// -> AreaMapManager::setLayoutAreaMap, i.e. it draws before/without the area bind. ParadeAreaScene::
// initialize's own bind block (only on the no-mission path) binds the "battlebg"/"spdungeon" groups and
// RmResourceCommon::bindMapResourceCpk(this+0x598); ParadeDungeonScene::loadFiles binds the groups and
// RmResourceCommon::bindMapResourceCpk(this+0x548).
//
// This hook repeats the area bind at the two parade entry points, from the staged release folder
// (/data/local/tmp/ffbe/{flat_ko,flat}, the same files jp_offline.js's localize() feeds CriFileInstaller),
// so it mounts the pack whether or not the installer already copied it into the app's files dir. The
// id -> cpk name table is build/engine_overlay/area_resource_cpk.json (build/make_area_resource_cpk_map.py,
// from F_RESOURCE_MAP_MST) copied to files/exvius/ by build/jp_offline_build.py.
//
// Light by design: 5 exports + 3 local offsets (each verified by its first instruction words), no export
// enumeration — jp_offline.js's HCA-MX 48000 patch must not be delayed.
(function () {
  const TAG = 'JP_PARADE_RES';
  const FLAT = '/data/local/tmp/ffbe/';
  const APP_FILES = '/data/data/com.exvius.jpkorean.app/files/';
  const MAP_FILES = ['/data/data/com.exvius.jpkorean.app/files/exvius/area_resource_cpk.json',
                     '/data/local/tmp/ffbe/exvius/area_resource_cpk.json'];
  // Local functions (no export). Verified by ANCHOR words below before any use.
  const OFF = { bindCpk: 0x15dc78c, mgrGet: 0x15a246c, isExist: 0x15ddafc, loaderSync: 0x15dc894 };
  const WORDS = {
    // CriFileLoader::bindCpk(std::string const&, int)
    0x15dc78c: [0xd101c3ff, 0xf9001bf7, 0xa90457f6, 0xa9054ff4, 0xa9067bfd, 0x910183fd, 0xd53bd056],
    // CriFileLoader holder accessor (returns &holder; [holder] = CriFileLoader*)
    0x15a246c: [0xa9bf7bfd, 0x910003fd, 0xf000c6e8, 0x9118a108, 0x8dffd08, 0x360000a8, 0xf000c6e0],
    // CriFileLoader::isExist(char const*) -> bool (binder find on loader->binder)
    0x15ddafc: [0xa9be4ff4, 0xa9017bfd, 0x910043fd, 0xaa0103f3, 0xaa0003f4, 0x97ffe159],
    // CriFileLoader::sync() — for each bound cpk: criFs_ExecuteMain + criFsBinder_GetStatus
    0x15dc894: [0xa9be4ff4, 0xa9017bfd, 0x910043fd, 0xf9401414, 0x9100c013, 0xeb13029f],
  };
  let hooks = 0, map = null, mapTried = false;
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  function stdstr(p) {  // libc++ std::string
    try {
      if (!p || p.isNull()) return '';
      const b = p.readU8();
      if (b & 1) { const n = p.add(8).readU64().toNumber(); return n > 4096 ? '' : p.add(16).readPointer().readUtf8String(n); }
      return p.add(1).readUtf8String(b >> 1);
    } catch (e) { return ''; }
  }
  const c_access = new NativeFunction(Module.getGlobalExportByName('access'), 'int', ['pointer', 'int']);
  const c_open = new NativeFunction(Module.getGlobalExportByName('open'), 'int', ['pointer', 'int']);
  const c_read = new NativeFunction(Module.getGlobalExportByName('read'), 'long', ['int', 'pointer', 'long']);
  const c_close = new NativeFunction(Module.getGlobalExportByName('close'), 'int', ['int']);
  const cpkPathPool = {};
  function pooledCstr(str) {
    let p = cpkPathPool[str];
    if (!p) { p = Memory.allocUtf8String(str); cpkPathPool[str] = p; }
    return p;
  }
  // libc++(arm64) std::string 을 만든다. bindCpk 는 name 을 std::string const& 로 받는다(char* 를 넘기면 bad_alloc).
  // long 모드: [0]=cap|1, [8]=size, [16]=data. short 모드: [0]=size<<1, [1..]=data(최대 22).
  function stdString(str) {
    const data = pooledCstr(str);
    const len = (function () { let i = 0; while (data.add(i).readU8() !== 0) i++; return i; })();
    const obj = Memory.alloc(24);
    if (len <= 22) {
      obj.writeU8(len << 1);
      Memory.copy(obj.add(1), data, len + 1);
    } else {
      obj.writeU64(uint64(len + 1).or(1));
      obj.add(8).writeU64(len);
      obj.add(16).writePointer(data);
    }
    return { obj: obj, data: data };
  }
  function exists(path) { try { return c_access(Memory.allocUtf8String(path), 0) === 0; } catch (e) { return false; } }
  function readText(path) {
    const fd = c_open(Memory.allocUtf8String(path), 0);
    if (fd < 0) return null;
    const parts = [];
    for (;;) {
      const buf = Memory.alloc(65536);
      const n = Number(c_read(fd, buf, 65536));
      if (n <= 0) break;
      parts.push(buf.readUtf8String(n));
    }
    c_close(fd);
    return parts.join('');
  }
  function stagedPath(name) {  // jp_offline.js prefers the Korean rebuild beside the original
    for (const dir of ['flat_ko/', 'flat/']) {
      const p = FLAT + dir + name;
      if (exists(p)) return p;
    }
    // Release data packs unpack every map cpk (Korean already merged) straight into files/ (DataPack.destination),
    // so files/ffbe/flat/ holds nothing there (2026-11-17).
    const installed = APP_FILES + name;
    if (exists(installed)) return installed;
    return null;
  }
  function loadMap() {
    if (map) return map;
    for (const path of MAP_FILES) {
      const text = readText(path);
      if (!text) continue;
      try { map = JSON.parse(text); log('map=' + Object.keys(map.areas || {}).length + ' areas from ' + path); return map; } catch (e) { log('map parse failed ' + path + ' ' + e); }
    }
    if (!mapTried) { mapTried = true; log('map file absent (' + MAP_FILES.join(' | ') + ') -> fallback AreaMapManager::bindAreaMapCpkAsync'); }
    return null;
  }

  const wait = setInterval(function () {
    const m = Process.findModuleByName('libgame.so');
    if (!m) return;
    clearInterval(wait);
    for (const off in WORDS) {
      const w = WORDS[off];
      try {
        for (let i = 0; i < w.length; i++) {
          if (m.base.add(Number(off)).add(i * 4).readU32() !== w[i]) { log('ANCHOR MISMATCH 0x' + Number(off).toString(16)); return; }
        }
      } catch (e) { log('ANCHOR read failed 0x' + Number(off).toString(16) + ' ' + e); return; }
    }
    const exp = n => m.findExportByName(n);
    const nGetNowArea = exp('_ZN10ParadeUtil13getNowAreaMstEv');
    const nBindAreaMap = exp('_ZN14AreaMapManager19bindAreaMapCpkAsyncEP7AreaMst');
    const nAreaMgr = exp('_ZN14AreaMapManager6sharedEv');
    if (!nGetNowArea) { log('ANCHOR MISSING ParadeUtil::getNowAreaMst'); return; }
    const getNowAreaMst = new NativeFunction(nGetNowArea, 'pointer', [], { exceptions: 'propagate' });
    const areaMapManager = nAreaMgr ? new NativeFunction(nAreaMgr, 'pointer', [], { exceptions: 'propagate' }) : null;
    const bindAreaMap = nBindAreaMap ? new NativeFunction(nBindAreaMap, 'void', ['pointer', 'pointer'], { exceptions: 'propagate' }) : null;
    const bindCpk = new NativeFunction(m.base.add(OFF.bindCpk), 'void', ['pointer', 'pointer', 'int'], { exceptions: 'propagate' });
    const mgrGet = new NativeFunction(m.base.add(OFF.mgrGet), 'pointer', [], { exceptions: 'propagate' });
    const isExist = new NativeFunction(m.base.add(OFF.isExist), 'bool', ['pointer', 'pointer'], { exceptions: 'propagate' });
    const loaderSync = new NativeFunction(m.base.add(OFF.loaderSync), 'void', ['pointer'], { exceptions: 'propagate' });
    const sync = function (loader) { try { loaderSync(loader); } catch (e) { log('sync failed ' + e); } };

    function mount(site) {
      try { mountInner(site); } catch (e) { log(site + ' mount failed ' + e); }
    }
    function mountInner(site) {
      let area = null;
      try { area = getNowAreaMst(); } catch (e) { log(site + ' getNowAreaMst failed ' + e); return; }
      if (!area || area.isNull()) { log(site + ' area mst=null (skip)'); return; }
      const areaId = area.add(0x88).readS32();  // AreaMst area id (read at 0x188fb70 in initialize)
      const table = loadMap();
      // 1) the area's own resource ids, exactly like AreaMapManager::bindAreaMapCpkAsync
      const info = area.add(0x28).readPointer();
      const ids = stdstr(info).split(',').map(s => s.trim()).filter(s => s.length);
      const names = [];
      if (table) {
        const res = table.resources || {};
        for (const id of ids) { const n = res[id]; if (n && !names.includes(n)) names.push(n); }
        const byArea = (areaId > 0 && (table.areas || {})[String(areaId)]) || null;
        if (byArea) for (const n of byArea.cpks) if (!names.includes(n)) names.push(n);
      }
      const mapName = (table && (table.areas || {})[String(areaId)] || {}).map || '';
      if (!names.length) {
        // Fallback (map file absent): the client's own area bind, AreaScene::initialize+0x158's call:
        // AreaMapManager::shared()->bindAreaMapCpkAsync(areaMst), then the loader sync at +0x180.
        if (bindAreaMap && areaMapManager) {
          try {
            bindAreaMap(areaMapManager(), area);
            let loader = null;
            try { const holder = mgrGet(); loader = holder.isNull() ? null : holder.readPointer(); } catch (e) {}
            if (loader && !loader.isNull()) sync(loader);
            log(site + ' area=' + areaId + ' fallback bindAreaMapCpkAsync done (ids=' + ids.join(',') + ')');
          } catch (e) { log(site + ' fallback bind failed ' + e); }
        } else log(site + ' area=' + areaId + ' ids=' + ids.join(',') + ' no cpk in map (and no fallback)');
        return;
      }
      let loader = null, bound = 0;
      try { const holder = mgrGet(); loader = holder.isNull() ? null : holder.readPointer(); } catch (e) { log(site + ' loader lookup failed ' + e); }
      if (!loader || loader.isNull()) { log(site + ' loader=null (skip)'); return; }
      // Already mounted (the client's own AreaScene path or an earlier hook call): nothing to do.
      if (mapName) {
        try { if (isExist(loader, Memory.allocUtf8String(mapName))) { log(site + ' area=' + areaId + ' already mounted (' + mapName + ')'); return; } } catch (e) {}
      }
      for (const name of names) {
        const src = stagedPath(name);
        if (!src) { log(site + ' MISSING staged ' + name); continue; }
        try { const ss = stdString(src); bindCpk(loader, ss.obj, 2); bound++; log(site + ' bind ' + name + ' <- ' + src); }
        catch (e) { log(site + ' bind failed ' + name + ' ' + e); }
      }
      if (bound) sync(loader);  // same pass AreaScene::initialize runs after its area bind
      let seen = '', visible = false;
      const check = function () {
        if (!mapName) return '';
        try { visible = isExist(loader, Memory.allocUtf8String(mapName)); return ' isExist(' + mapName + ')=' + (visible ? 1 : 0); }
        catch (e) { return ' isExist failed'; }
      };
      seen = check();
      if (mapName && !visible && bindAreaMap && areaMapManager) {
        // The staged path did not reach the binder (e.g. the app cannot open /data/local/tmp): bind again
        // through the client's own area bind, which resolves the cpk from the installed files dir.
        try {
          bindAreaMap(areaMapManager(), area);
          sync(loader);
          log(site + ' area=' + areaId + ' staged bind not visible -> bindAreaMapCpkAsync');
          seen = check();
        } catch (e) { log(site + ' fallback bind failed ' + e); }
      }
      log(site + ' area=' + areaId + ' ids=' + ids.join(',') + ' cpk=' + bound + '/' + names.length + seen);
    }

    for (const [sym, site] of [['_ZN15ParadeAreaScene10initializeEv', 'ParadeAreaScene::initialize'],
                               ['_ZN18ParadeDungeonScene9loadFilesEv', 'ParadeDungeonScene::loadFiles'],
                               ['_ZN18ParadeDungeonScene10initializeEv', 'ParadeDungeonScene::initialize']]) {
      const a = exp(sym);
      if (!a) { log('ANCHOR MISSING ' + sym); continue; }
      try { Interceptor.attach(a, { onEnter() { mount(site); } }); hooks++; } catch (e) { log('hook failed ' + site + ' ' + e); }
    }
    // Area packs the master forgot (2026-11-15, 봉인의 방 story card -> body crashed with the same null texture):
    // F_AREA_MST 5155 「集められし者たち」 / 5220 「時を超えた約束」 (and their world-2 originals 725 / 729) list
    // map725_*.jpg / map729_*.jpg but their q4f9IdMs is empty, and F_RESOURCE_MAP_MST has no row for the packs
    // that hold those images (area_ex_mG73tpLd.cpk / area_ex2_4pIfNrj3.cpk; TOC check over every staged area*.cpk:
    // build/out/seal_story/area_cpk_files.json; 866 「非情は七色」 lists 108529 but map796_1.jpg is in area_ex15).
    const AREA_EXTRA = { 5155: ['area_ex_mG73tpLd.cpk'], 725: ['area_ex_mG73tpLd.cpk'],
                         5220: ['area_ex2_4pIfNrj3.cpk'], 729: ['area_ex2_4pIfNrj3.cpk'],
                         866: ['area_ex15_Kgd7Ni5y.cpk'], 1599: ['area37_32IGc6S0.cpk'],
                         1000: ['area_bt1.cpk'], 1001: ['area_bt1.cpk'], 1002: ['area_bt1.cpk'], 1003: ['area_bt1.cpk'],
                         1004: ['area_bt1.cpk'], 1005: ['area_bt1.cpk'], 1006: ['area_bt1.cpk'], 1007: ['area_bt1.cpk'] };
    const AREA_EXTRA_MAP = { 5155: 'map725_1.jpg', 725: 'map725_1.jpg',
                             5220: 'map729_1.jpg', 729: 'map729_1.jpg',
                             866: 'map796_1.jpg', 1599: 'map99_1.jpg',
                             1000: 'map9850_1.jpg', 1001: 'map9850_1.jpg', 1002: 'map9850_1.jpg', 1003: 'map9850_1.jpg',
                             1004: 'map9850_1.jpg', 1005: 'map9850_1.jpg', 1006: 'map9850_1.jpg', 1007: 'map9850_1.jpg' };
    function ensureAreaMounted(site, areaId, areaPtr, syncFirst) {
      try {
        if (!areaId || areaId <= 0) return;
        const table = loadMap();
        const byArea = (table && (table.areas || {})[String(areaId)]) || null;
        const names = [];
        if (AREA_EXTRA[areaId]) for (const n of AREA_EXTRA[areaId]) if (!names.includes(n)) names.push(n);
        if (byArea && byArea.cpks) for (const n of byArea.cpks) if (!names.includes(n)) names.push(n);
        if (areaPtr && !areaPtr.isNull() && table && table.resources) {
          const ids = stdstr(areaPtr.add(0x28).readPointer()).split(',').map(s => s.trim()).filter(s => s.length);
          for (const id of ids) { const n = table.resources[id]; if (n && !names.includes(n)) names.push(n); }
        }
        if (!names.length) return;
        const holder = mgrGet();
        const loader = holder.isNull() ? null : holder.readPointer();
        if (!loader || loader.isNull()) return;
        if (syncFirst) sync(loader);
        const rawMap = AREA_EXTRA_MAP[areaId] || (byArea && byArea.map) || '';
        const firstMap = rawMap.split(',')[0].trim();
        if (firstMap) {
          try { if (isExist(loader, pooledCstr(firstMap))) return; } catch (e) {}
        }
        let bound = 0;
        for (const name of names) {
          const src = stagedPath(name);
          if (!src) { log(site + ' MISSING staged ' + name); continue; }
          const ss = stdString(src); bindCpk(loader, ss.obj, 2); bound++;
          log(site + ' area=' + areaId + ' bind ' + name + ' <- ' + src);
        }
        if (bound) sync(loader);
      } catch (e) { log(site + ' ensureAreaMounted failed ' + e); }
    }
    if (nBindAreaMap) {
      try {
        Interceptor.attach(nBindAreaMap, {
          onEnter(args) { this.area = args[1]; },
          onLeave() {
            const area = this.area;
            if (!area || area.isNull()) return;
            ensureAreaMounted('bindAreaMapCpkAsync', area.add(0x88).readS32(), area, true);
          }
        });
        hooks++;
      } catch (e) { log('hook failed bindAreaMapCpkAsync ' + e); }
    }
    const nSetLayoutAreaMap = exp('_ZN14AreaMapManager16setLayoutAreaMapEP9GameScene');
    if (nSetLayoutAreaMap) {
      try {
        Interceptor.attach(nSetLayoutAreaMap, {
          onEnter(args) {
            const mgr = args[0];
            if (!mgr || mgr.isNull() || mgr.add(0x50).readU8() !== 0) return;
            ensureAreaMounted('setLayoutAreaMap', mgr.add(0x9c).readS32(), null, false);
          }
        });
        hooks++;
      } catch (e) { log('hook failed setLayoutAreaMap ' + e); }
    }
    // Redirect any un-installed CPK bind (e.g. AreaMapManager::bindAreaMapCpkAsync / RmResourceCommon::bindMapResourceCpk
    // passing /data/user/0/.../files/<name>.cpk when StoryEventEntryScene skipped InitialDownloadScene) to /data/local/tmp/ffbe/{flat_ko,flat}/<name>.cpk
    const nCriBindCpk = exp('criFsBinder_BindCpk');
    if (nCriBindCpk) {
      try {
        Interceptor.attach(nCriBindCpk, {
          onEnter(args) {
            try {
              const p = args[2];
              if (!p || p.isNull()) return;
              const orig = p.readUtf8String();
              if (!orig) return;
              const slash = orig.lastIndexOf('/');
              const base = slash >= 0 ? orig.substring(slash + 1) : orig;
              if (!base.endsWith('.cpk')) return;
              const ko = FLAT + 'flat_ko/' + base;
              let target = null;
              if (exists(ko)) target = ko;
              else if (!exists(orig)) {
                const fl = FLAT + 'flat/' + base;
                if (exists(fl)) target = fl;
              }
              if (target && target !== orig) {
                args[2] = pooledCstr(target);
                log('criFsBinder_BindCpk ' + base + ' -> ' + target);
              }
            } catch (e) {}
          }
        });
        hooks++;
      } catch (e) { log('hook failed criFsBinder_BindCpk ' + e); }
    }
    const nGetCpkPath = exp('_ZN8CriUtils22getCpkPathWithFileNameERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE');
    const nStrAssign = exp('_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEE6assignEPKcm');
    if (nGetCpkPath && nStrAssign) {
      const strAssign = new NativeFunction(nStrAssign, 'pointer', ['pointer', 'pointer', 'ulong'], { exceptions: 'propagate' });
      try {
        Interceptor.attach(nGetCpkPath, {
          onEnter(args) { this.sret = this.context.x8; this.name = stdstr(args[0]); },
          onLeave() {
            try {
              if (!this.sret || this.sret.isNull() || !this.name) return;
              if (stdstr(this.sret).length > 0) return;
              const src = stagedPath(this.name);
              if (!src) return;
              strAssign(this.sret, pooledCstr(src), src.length);
              log('getCpkPathWithFileName ' + this.name + ' -> ' + src);
            } catch (e) {}
          }
        });
        hooks++;
      } catch (e) { log('hook failed getCpkPathWithFileName ' + e); }
    }
    // Current-event pick (2026-11-14, gate tile 965 drew 954's map and crashed): every parade scene finds
    // "the" event with ParadeEventInfoList::getObjectWithEventSubType(UserState+0x1f0) (0x1d29a40), a
    // first-match scan on the row's RdV4nK8w (+0xf8). The list is never cleared (onReadStarted is a bare
    // ret; updateObject 0x1d299b0 replaces by area +0xf4 or appends), and the offline gate serves one row
    // per parade tile, all RdV4nK8w '1' (the value the client's ParadeUtil logo/banner code expects for a
    // normal parade; 2 = Royal Parade), so the first row (954) always won. Every entry (gate, home banner,
    // seal room, result return) goes through ParadeEntryScene::setAreaMst(AreaMst*): move the row of that
    // area to index 0 so the sub-type scan returns it. Pointer swap inside the ccArray only (no retain).
    const nListShared = exp('_ZN19ParadeEventInfoList6sharedEv');
    const nEntryArea = exp('_ZN16ParadeEntryScene10setAreaMstEP7AreaMst');
    if (nListShared && nEntryArea) {
      const listShared = new NativeFunction(nListShared, 'pointer', [], { exceptions: 'propagate' });
      Interceptor.attach(nEntryArea, {
        onEnter(args) {
          try {
            const area = args[1];
            if (area.isNull()) return;
            const areaId = area.add(0x88).readS32();
            const arr = listShared().add(0x30).readPointer();   // ccArray {num, max, Ref **arr}
            if (arr.isNull()) return;
            const num = arr.readS64().toNumber ? arr.readS64().toNumber() : Number(arr.readS64());
            const items = arr.add(0x10).readPointer();
            for (let i = 0; i < num; i++) {
              const row = items.add(i * 8).readPointer();
              if (row.isNull() || row.add(0xf4).readS32() !== areaId) continue;
              if (i > 0) { items.add(i * 8).writePointer(items.readPointer()); items.writePointer(row); }
              log('entry area=' + areaId + ' row ' + i + '->0 of ' + num + ' subtype=' + row.add(0xf8).readS32());
              return;
            }
            log('entry area=' + areaId + ' no row in ' + num);
          } catch (e) { log('entry reorder failed ' + e); }
        }
      });
      hooks++;
    } else log('ANCHOR MISSING ParadeEventInfoList::shared / ParadeEntryScene::setAreaMst');
    log('ready hooks=' + hooks + ' base=' + m.base);
  }, 50);
})();
