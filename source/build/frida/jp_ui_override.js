// jp_ui_override.js — Korean replacements for single UI images inside downloaded CPKs (2026-11-10).
//
// Images such as homeBanner_02.png (home bottom "ワールド" banner) are not in the APK atlases: the client finds them by
// bare name with criFsBinder_Find in a downloaded CPK (files/campaign_ui.cpk, copied from /data/local/tmp/ffbe/flat/)
// where every file is encrypted with its own key stream (same length as the PNG). Instead of re-encrypting the CPK,
// the decoded PNG is swapped at cocos2d::Image::initWithImageData: when criFsBinder_Find resolves a name listed in
// /data/local/tmp/ffbe/ui_ko/index.txt, its extract size is remembered, and the next decode of exactly that many bytes
// gets /data/local/tmp/ffbe/ui_ko/<name> instead (device check 2026-11-10: the decode follows the find directly,
// decoded length == CriFsBinderFileInfo.extract_size). Files: translations/ui-ko/sprites/campaign_ui/, pushed by
// build/deploy_ko_ui_override.py.
// When replacing homeBanner_02.png, check the story world number (1, 3, 4, 5, 6, 7) recorded in the app state
// file world_icon.txt (written by jp_mission.py). If present, prefer homeBanner_02_w<N>.png; otherwise fall back
// to the default homeBanner_02.png.
(function () {
  const TAG = 'UIKO';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  const DIR = '/data/local/tmp/ffbe/ui_ko/';
  const WORLD_FILE = '/data/data/com.exvius.jpkorean.app/files/exvius/state/world_icon.txt';
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    const libc = Process.getModuleByName('libc.so');
    const c_open = new NativeFunction(libc.getExportByName('open'), 'int', ['pointer', 'int']);
    const c_read = new NativeFunction(libc.getExportByName('read'), 'long', ['int', 'pointer', 'long']);
    const c_close = new NativeFunction(libc.getExportByName('close'), 'int', ['int']);
    function readAll(path) {
      const fd = c_open(Memory.allocUtf8String(path), 0); if (fd < 0) return null;
      const chunks = []; let total = 0;
      for (;;) { const b = Memory.alloc(65536); const n = Number(c_read(fd, b, 65536)); if (n <= 0) break; chunks.push([b, n]); total += n; }
      c_close(fd); const out = Memory.alloc(total); let off = 0;
      for (const [b, n] of chunks) { Memory.copy(out.add(off), b, n); off += n; }
      return [out, total];
    }
    const idx = readAll(DIR + 'index.txt');
    if (!idx) { log('no index, not installed'); return; }
    const names = new Set(idx[0].readUtf8String(idx[1]).split(/\r?\n/).map(s => s.trim()).filter(Boolean));
    const find = m.findExportByName('criFsBinder_Find');
    const init = m.findExportByName('_ZN7cocos2d5Image17initWithImageDataEPKhl');
    if (!find || !init) { log('symbols missing, not installed'); return; }
    const cache = {}, pending = new Map();   // extract size -> name
    let fed = 0;
    Interceptor.attach(find, {
      onEnter(a) {
        this.n = null;
        try { const s = a[1].readUtf8String(); const b = s.substring(s.lastIndexOf('/') + 1); if (names.has(b)) { this.n = b; this.info = a[2]; } } catch (e) {}
      },
      onLeave() {
        if (!this.n || this.info.isNull()) return;
        const ext = this.info.add(32).readS64().toNumber();
        if (ext > 0) pending.set(ext, this.n);
      },
    });
    // Picks the file name to feed: homeBanner_02.png -> homeBanner_02_w<N>.png when world_icon.txt holds a story world
    // and that file exists; any failure keeps the default name silently.
    function pickName(n) {
      if (n !== 'homeBanner_02.png') return n;
      try {
        const res = readAll(WORLD_FILE);
        // no record yet (no story mission started since this feature) -> season 1 (user decision 2026-11-14)
        const val = res && res[1] > 0 ? res[0].readUtf8String(res[1]).trim() : '1';
        if (['1', '3', '4', '5', '6', '7'].indexOf(val) !== -1) {
          const cand = 'homeBanner_02_w' + val + '.png';
          if (readAll(DIR + cand)) return cand;
        }
      } catch (e) {}
      return 'homeBanner_02.png';
    }
    Interceptor.attach(init, { onEnter(a) {
      if (!pending.size) return;
      const len = a[2].toInt32(), n = pending.get(len); if (!n) return;
      pending.delete(len);
      const want = pickName(n);
      let f = cache[want];
      if (!f) { f = readAll(DIR + want); if (!f) { log('missing ' + want); return; } cache[want] = f; }
      a[1] = f[0]; a[2] = ptr(f[1]);
      if (++fed <= 5 || (fed & (fed - 1)) === 0) log('fed ' + fed + ' ' + want);
    } });
    log('hook installed, images ' + names.size);
  }, 50);
})();
