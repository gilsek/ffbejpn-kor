// jp_cpk_dump.js — one-shot dump of the decrypted JP spdungeon CPK banners (2026-11-13). TEST USE ONLY.
//
// Appended to the Frida script only by `build/deploy_jp_frida.py --cpk-dump`, and even then it does nothing
// unless the list file /data/local/tmp/ffbe/dump_banners exists (push build/out/seal_room/banner_files.tsv there:
// "cpk<TAB>file<TAB>size" rows). Without both, no hook is installed and the game runs exactly as before.
//
// Why on the device: spdungeon1..9.cpk are encrypted on PC, but the game's CRI loader decrypts them. In JP 11.0.0
// (libgame.so sha256 54ef0fe9...) the texture path is
//   CriFileLoader::texture(name) 0x15dd6b0 -> CriFileLoader::load(const char*, size_t*) 0x15dceb0
//   -> TextureLoader::getTextureForBinary(key, bytes, len) -> cocos2d::Image::initWithImageData(bytes, len)
// with nothing in between, so the buffer load() returns is already the plain PNG. This script binds each
// spdungeon CPK on the shared CriFileLoader (same call jp_parade_res.js uses), then calls load() for every listed
// name on the GL thread (inside Director::mainLoop, a time budget per frame) and writes the bytes unchanged.
//
// Output: /sdcard/Android/data/com.exvius.jpkorean.app/files/cpk_dump/ (adb can pull it without run-as);
// if the app cannot create that, files/cpk_dump/ (needs a debuggable build + run-as). _log.tsv records every
// name (name, cpk, size, status); _done is written at the end. Files already present with the listed size are
// skipped, so a restart resumes. Collect with build/collect_cpk_banner_dump.py --pull.
(function () {
  const TAG = 'JP_CPK_DUMP';
  const LIST = '/data/local/tmp/ffbe/dump_banners';
  const FLAT = '/data/local/tmp/ffbe/';
  const PKG = 'com.exvius.jpkorean.app';
  // run 1: the app could not create its own Android/data dir (no Java getExternalFilesDir here), so it fell back to
  // files/cpk_dump (not pullable from a non-debuggable build). Pre-create the external dir with adb, and also try the
  // world-writable staging dir; the internal copy is removed after a successful dump elsewhere.
  const INTERNAL = '/data/data/' + PKG + '/files/cpk_dump/';
  const OUT_DIRS = ['/storage/emulated/0/Android/data/' + PKG + '/files/cpk_dump/', FLAT + 'cpk_dump/', INTERNAL];
  const FRAME_BUDGET_MS = 30, START_DELAY_FRAMES = 600, BIND_TIMEOUT_FRAMES = 600;
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }

  const g = n => Module.getGlobalExportByName(n);
  const c_access = new NativeFunction(g('access'), 'int', ['pointer', 'int']);
  // Cleanup mode (deploy_jp_frida.py --cpk-dump-clean): /data/local/tmp/ffbe/dump_cleanup present -> delete every
  // regular file in files/cpk_dump/ and the dir itself, then stop (no dump). Needed because a non-debuggable build
  // has no run-as, so adb cannot remove the app-private copy.
  if (c_access(Memory.allocUtf8String(FLAT + 'dump_cleanup'), 0) === 0) {
    try {
      const opendir = new NativeFunction(g('opendir'), 'pointer', ['pointer']);
      const readdir = new NativeFunction(g('readdir'), 'pointer', ['pointer']);
      const closedir = new NativeFunction(g('closedir'), 'int', ['pointer']);
      const unlink = new NativeFunction(g('unlink'), 'int', ['pointer']);
      const rmdir = new NativeFunction(g('rmdir'), 'int', ['pointer']);
      const d = opendir(Memory.allocUtf8String(INTERNAL));
      if (d.isNull()) { log('CLEANUP nothing (no ' + INTERNAL + ')'); return; }
      const names = [];
      for (;;) {  // bionic arm64 dirent: d_ino u64, d_off s64, d_reclen u16, d_type u8, d_name[256] at +19
        const e = readdir(d); if (e.isNull()) break;
        const name = e.add(19).readUtf8String();
        if (name !== '.' && name !== '..' && name.indexOf('/') < 0) names.push(name);
      }
      closedir(d);
      let ok = 0, fail = 0;
      for (const n of names) { if (unlink(Memory.allocUtf8String(INTERNAL + n)) === 0) ok++; else fail++; }
      const r = rmdir(Memory.allocUtf8String(INTERNAL));
      log('CLEANUP removed=' + ok + ' failed=' + fail + ' rmdir=' + r);
    } catch (e) { log('CLEANUP error ' + e.stack); }
    return;
  }
  if (c_access(Memory.allocUtf8String(LIST), 0) !== 0) return;  // dump mode off: install nothing

  const c_open = new NativeFunction(g('open'), 'int', ['pointer', 'int', 'int']);
  const c_read = new NativeFunction(g('read'), 'long', ['int', 'pointer', 'long']);
  const c_write = new NativeFunction(g('write'), 'long', ['int', 'pointer', 'long']);
  const c_close = new NativeFunction(g('close'), 'int', ['int']);
  const c_mkdir = new NativeFunction(g('mkdir'), 'int', ['pointer', 'int']);
  const c_stat_size = (function () {  // file size via open+lseek (no struct stat layout needed)
    const lseek = new NativeFunction(g('lseek'), 'long', ['int', 'long', 'int']);
    return function (path) {
      const fd = c_open(Memory.allocUtf8String(path), 0, 0); if (fd < 0) return -1;
      const n = Number(lseek(fd, 0, 2)); c_close(fd); return n;
    };
  })();
  const O_WR = 0x241;  // O_WRONLY | O_CREAT | O_TRUNC
  const O_APPEND_WR = 0x441;  // O_WRONLY | O_CREAT | O_APPEND
  function readText(path) {
    const fd = c_open(Memory.allocUtf8String(path), 0, 0); if (fd < 0) return null;
    const parts = [];
    for (;;) { const b = Memory.alloc(65536); const n = Number(c_read(fd, b, 65536)); if (n <= 0) break; parts.push(b.readUtf8String(n)); }
    c_close(fd); return parts.join('');
  }
  function writeAll(fd, p, n) {
    let off = 0;
    while (off < n) { const w = Number(c_write(fd, p.add(off), n - off)); if (w <= 0) return false; off += w; }
    return true;
  }
  function writeFile(path, p, n) {
    const fd = c_open(Memory.allocUtf8String(path), O_WR, 420); if (fd < 0) return false;
    const ok = writeAll(fd, p, n); c_close(fd); return ok;
  }
  function mkdirs(dir) {
    const parts = dir.split('/').filter(x => x); let cur = '';
    for (const p of parts) { cur += '/' + p; c_mkdir(Memory.allocUtf8String(cur), 493); }
  }
  const c_unlink = new NativeFunction(g('unlink'), 'int', ['pointer']);
  const c_rmdir = new NativeFunction(g('rmdir'), 'int', ['pointer']);
  function pickOutDir() {
    for (const d of OUT_DIRS) {
      mkdirs(d);
      const probe = d + '_probe';
      const b = Memory.allocUtf8String('ok');
      if (writeFile(probe, b, 2)) return d;
      log('out dir not writable ' + d);
    }
    return null;
  }
  // Export over adb reverse (run 2: neither Android/data nor /data/local/tmp is writable by the app, and a
  // non-debuggable build has no run-as). PC side: build/recv_cpk_dump.py listens on 127.0.0.1:EXPORT_PORT after
  // `adb reverse tcp:EXPORT_PORT tcp:EXPORT_PORT`. Stream: per file "F<TAB>name<TAB>size<LF>" + bytes, then "END<LF>".
  const EXPORT_PORT = 38917;
  function exportInternal() {
    try {
      const c_socket = new NativeFunction(g('socket'), 'int', ['int', 'int', 'int']);
      const c_connect = new NativeFunction(g('connect'), 'int', ['int', 'pointer', 'int']);
      const fd = c_socket(2, 1, 0); if (fd < 0) { log('export socket failed'); return; }
      const sa = Memory.alloc(16); sa.writeByteArray([2, 0, EXPORT_PORT >> 8, EXPORT_PORT & 255, 127, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]);
      if (c_connect(fd, sa, 16) !== 0) { log('export connect failed (adb reverse + recv_cpk_dump.py running?)'); c_close(fd); return; }
      const sendStr = function (t) { const b = Memory.allocUtf8String(t); let n = 0; while (b.add(n).readU8() !== 0) n++; return writeAll(fd, b, n); };
      let sent = 0, bytes = 0;
      const names = ['_log.tsv', '_done'];
      for (const k of order) for (const e of byCpk[k]) names.push(e.name);
      for (const name of names) {
        const fdi = c_open(Memory.allocUtf8String(INTERNAL + name), 0, 0); if (fdi < 0) continue;
        const parts = []; let size = 0;
        for (;;) { const b = Memory.alloc(262144); const n = Number(c_read(fdi, b, 262144)); if (n <= 0) break; parts.push([b, n]); size += n; }
        c_close(fdi);
        if (!sendStr('F'+'\t' + name + '\t' + size + '\n')) { log('export send failed at ' + name); c_close(fd); return; }
        for (const [b, n] of parts) if (!writeAll(fd, b, n)) { log('export send failed at ' + name); c_close(fd); return; }
        sent++; bytes += size;
      }
      sendStr('END\n'); c_close(fd);
      log('EXPORTED files=' + sent + ' bytes=' + bytes);
    } catch (e) { log('export error ' + e.stack); }
  }
  function removeInternal() {  // drop the run-1 copy once the dump landed somewhere pullable
    let n = 0;
    for (const k of order) for (const e of byCpk[k]) if (c_unlink(Memory.allocUtf8String(INTERNAL + e.name)) === 0) n++;
    for (const f of ['_log.tsv', '_probe', '_done']) c_unlink(Memory.allocUtf8String(INTERNAL + f));
    c_rmdir(Memory.allocUtf8String(INTERNAL));
    log('internal copy removed files=' + n);
  }

  // ---- list ----
  const text = readText(LIST);
  if (!text) { log('list unreadable ' + LIST); return; }
  // Optional 4th column "pin": the name also exists in another bound CPK (spdungeon3/4 share Chronicle_FF10_2;
  // spd_20200427_bn_top came back 924,418 B instead of spdungeon1's 525,276), so bind this CPK under a fresh key
  // with a raised CRI binder priority (CriFileLoader::bindCpk passes loader+0x38 to criFsBinder_SetPriority).
  const byCpk = {}, order = [], pinned = {};
  for (const line of text.split(/\r?\n/)) {
    const c = line.split('\t'); if (c.length < 3 || c[0] === 'cpk' || !/\.cpk$/.test(c[0])) continue;
    if (!byCpk[c[0]]) { byCpk[c[0]] = []; order.push(c[0]); }
    byCpk[c[0]].push({ name: c[1], size: parseInt(c[2], 10) || 0 });
    if (c[3] === 'pin') pinned[c[0]] = true;
  }
  order.sort((a, b) => (parseInt(a.replace(/\D/g, ''), 10) || 0) - (parseInt(b.replace(/\D/g, ''), 10) || 0));
  let total = 0; for (const k of order) total += byCpk[k].length;
  log('list ' + total + ' files in ' + order.length + ' cpk');

  // ---- libgame anchors (JP 11.0.0 sha256 54ef0fe9...) ----
  const OFF = { bindCpk: 0x15dc78c, mgrGet: 0x15a246c, isExist: 0x15ddafc, loaderSync: 0x15dc894, load: 0x15dceb0, freeBuf: 0x15d6210 };
  const WORDS = {
    0x15dc78c: [0xd101c3ff, 0xf9001bf7, 0xa90457f6, 0xa9054ff4, 0xa9067bfd, 0x910183fd, 0xd53bd056],  // CriFileLoader::bindCpk(std::string const&, int)
    0x15a246c: [0xa9bf7bfd, 0x910003fd, 0xf000c6e8, 0x9118a108, 0x8dffd08, 0x360000a8, 0xf000c6e0],    // holder accessor ([holder] = CriFileLoader*)
    0x15ddafc: [0xa9be4ff4, 0xa9017bfd, 0x910043fd, 0xaa0103f3, 0xaa0003f4, 0x97ffe159],              // CriFileLoader::isExist(char const*)
    0x15dc894: [0xa9be4ff4, 0xa9017bfd, 0x910043fd, 0xf9401414, 0x9100c013, 0xeb13029f],              // CriFileLoader::sync()
    0x15dceb0: [0xd10143ff, 0xf90013f5, 0xa9034ff4, 0xa9047bfd, 0x910103fd, 0xd53bd055, 0xf94016a8],  // CriFileLoader::load(char const*, size_t*) sync -> new[] buffer
    0x15d6210: [0xb4000040, 0x17ecd1d3],                                                              // buffer free (delete[] if non-null)
  };

  function stdString(str) {  // libc++ std::string (bindCpk takes std::string const&)
    const data = Memory.allocUtf8String(str); const len = str.length; const obj = Memory.alloc(24);
    if (len <= 22) { obj.writeU8(len << 1); Memory.copy(obj.add(1), data, len + 1); }
    else { obj.writeU64(uint64(len + 1).or(1)); obj.add(8).writeU64(len); obj.add(16).writePointer(data); }
    return { obj: obj, data: data };
  }

  const wait = setInterval(function () {
    const m = Process.findModuleByName('libgame.so'); if (!m) return;
    clearInterval(wait);
    for (const off in WORDS) {
      const w = WORDS[off];
      for (let i = 0; i < w.length; i++) {
        if (m.base.add(Number(off)).add(i * 4).readU32() !== w[i]) { log('ANCHOR MISMATCH 0x' + Number(off).toString(16) + ' (dump disabled)'); return; }
      }
    }
    const nf = (o, r, a) => new NativeFunction(m.base.add(o), r, a, { exceptions: 'propagate' });
    const bindCpk = nf(OFF.bindCpk, 'void', ['pointer', 'pointer', 'int']);
    const mgrGet = nf(OFF.mgrGet, 'pointer', []);
    const isExist = nf(OFF.isExist, 'bool', ['pointer', 'pointer']);
    const loaderSync = nf(OFF.loaderSync, 'void', ['pointer']);
    const load = nf(OFF.load, 'pointer', ['pointer', 'pointer', 'pointer']);
    const freeBuf = nf(OFF.freeBuf, 'void', ['pointer']);
    const mainLoop = m.findExportByName('_ZN7cocos2d8Director8mainLoopEv');
    if (!mainLoop) { log('Director::mainLoop missing (dump disabled)'); return; }

    let out = null, logFd = -1, frames = 0, loaderFrames = 0, state = 'wait', ci = 0, fi = 0, bindFrames = 0;
    const stat = { ok: 0, skip: 0, missing: 0, load_null: 0, write_fail: 0, size_diff: 0, error: 0 };
    const keep = [];  // keep NativeStrings alive while native code may hold them (GC -> SIGSEGV)
    let seenPrio = null;  // pinned binds only: criFsBinder_SetPriority(id, prio) calls made inside our bindCpk
    if (Object.keys(pinned).length) {
      const sp = m.findExportByName('criFsBinder_SetPriority');
      if (sp) Interceptor.attach(sp, { onEnter(a) { if (seenPrio) seenPrio.push([a[0].toInt32(), a[1].toInt32()]); } });
      else log('criFsBinder_SetPriority export missing (pin unverified)');
    }
    function rec(e, cpk, size, status) {
      if (logFd < 0) return;
      const s = Memory.allocUtf8String(e.name + '\t' + cpk + '\t' + size + '\t' + status + '\n');
      let n = 0; while (s.add(n).readU8() !== 0) n++;
      writeAll(logFd, s, n);
    }
    function getLoader() { try { const h = mgrGet(); if (h.isNull()) return null; const l = h.readPointer(); return l.isNull() ? null : l; } catch (e) { return null; } }
    function exists(loader, name) { try { return !!isExist(loader, Memory.allocUtf8String(name)); } catch (e) { return false; } }
    function stagedPath(cpk) {
      const p = FLAT + 'flat/' + cpk;
      return c_access(Memory.allocUtf8String(p), 0) === 0 ? p : null;
    }
    function bindNext(loader) {
      // Always bind: a first name visible through another CPK (spdungeon4 shares one name with spdungeon3)
      // does not mean this CPK is mounted (run 1: 163 spdungeon4 files missing). bindCpk skips a key already bound.
      const cpk = order[ci];
      const src = stagedPath(cpk) || cpk;  // bare name -> FileUtils::fullPathForFilename (installed files dir)
      if (pinned[cpk]) return bindPinned(loader, cpk, src);
      try { const ss = stdString(src); keep.push(ss); bindCpk(loader, ss.obj, 2); log('bind ' + cpk + ' <- ' + src); }
      catch (e) { log('bind failed ' + cpk + ' ' + e); }
      return false;
    }
    function bindPinned(loader, cpk, src) {
      // A key already in the loader's map is skipped by bindCpk, so try the plain name first and then "./" + name
      // (same file through FileUtils, different map key) until criFsBinder_SetPriority is seen for our bind.
      const prioPtr = loader.add(0x38), old = prioPtr.readS32();
      for (const key of (src[0] === '/' ? [src] : [src, './' + src])) {
        seenPrio = [];
        prioPtr.writeS32(old + 100);
        try { const ss = stdString(key); keep.push(ss); bindCpk(loader, ss.obj, 2); }
        catch (e) { log('pin bind failed ' + cpk + ' ' + e); }
        finally { prioPtr.writeS32(old); }
        log('pin bind ' + cpk + ' <- ' + key + ' prio ' + old + '+100 setPriority=' + JSON.stringify(seenPrio));
        if (seenPrio.length) break;
      }
      seenPrio = null;
      return false;
    }
    function dumpOne(loader, cpk, e) {
      const dst = out + e.name;
      if (e.size > 0 && c_stat_size(dst) === e.size) { stat.skip++; return; }
      if (!exists(loader, e.name)) { stat.missing++; rec(e, cpk, 0, 'missing'); return; }
      const cname = Memory.allocUtf8String(e.name), sz = Memory.alloc(8); sz.writeU64(0);
      let buf;
      try { buf = load(loader, cname, sz); } catch (err) { stat.error++; rec(e, cpk, 0, 'error'); log('load error ' + e.name + ' ' + err); return; }
      if (!buf || buf.isNull()) { stat.load_null++; rec(e, cpk, 0, 'load_null'); return; }
      const n = sz.readU64().toNumber();
      const ok = n > 0 && writeFile(dst, buf, n);
      try { freeBuf(buf); } catch (err) {}
      if (!ok) { stat.write_fail++; rec(e, cpk, n, 'write_fail'); return; }
      const st = (e.size && n !== e.size) ? 'size_diff' : 'ok';
      stat[st]++; rec(e, cpk, n, st);
    }

    Interceptor.attach(mainLoop, { onEnter() {
      if (state === 'done') return;
      frames++;
      try {
        const loader = getLoader(); if (!loader) return;
        if (state === 'wait') {
          if (++loaderFrames < START_DELAY_FRAMES) return;
          out = pickOutDir();
          if (!out) { log('no writable output dir (dump disabled)'); state = 'done'; return; }
          logFd = c_open(Memory.allocUtf8String(out + '_log.tsv'), O_APPEND_WR, 420);
          log('start out=' + out + ' frame=' + frames);
          state = 'bind'; ci = 0; bindFrames = 0;
        }
        if (state === 'bind') {
          if (ci >= order.length) { state = 'finish'; }
          else {
            const cpk = order[ci];
            if (bindFrames === 0 && bindNext(loader)) { state = 'dump'; fi = 0; }
            else {
              try { loaderSync(loader); } catch (e) {}
              bindFrames++;
              if (exists(loader, byCpk[cpk][0].name)) { log('ready ' + cpk + ' after ' + bindFrames + ' frames'); state = 'dump'; fi = 0; }
              else if (bindFrames > BIND_TIMEOUT_FRAMES) { log('bind timeout ' + cpk + ' (dumping what is visible)'); state = 'dump'; fi = 0; }
            }
          }
        }
        if (state === 'dump') {
          const cpk = order[ci], list = byCpk[cpk], t0 = Date.now();
          while (fi < list.length && Date.now() - t0 < FRAME_BUDGET_MS) dumpOne(loader, cpk, list[fi++]);
          if (fi >= list.length) {
            log('cpk ' + cpk + ' done ' + JSON.stringify(stat));
            ci++; bindFrames = 0; state = 'bind';
          }
        }
        if (state === 'finish') {
          state = 'done';
          const s = Memory.allocUtf8String(JSON.stringify(stat)); let n = 0; while (s.add(n).readU8() !== 0) n++;
          writeFile(out + '_done', s, n);
          if (logFd >= 0) c_close(logFd);
          log('DONE ' + JSON.stringify(stat) + ' total=' + total + ' out=' + out);
          if (out !== INTERNAL && stat.ok > 0) removeInternal();
          else if (out === INTERNAL) setTimeout(exportInternal, 100);  // Frida's own thread, not the GL thread
        }
      } catch (e) { log('frame error ' + e.stack); state = 'done'; }
    } });
    log('armed (mainLoop hook, start after ' + START_DELAY_FRAMES + ' loader frames)');
  }, 20);
})();
