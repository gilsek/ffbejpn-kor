// jp_find_miss.js — read-only diagnostic (2026-11-15): log every file name criFsBinder_Find does NOT find, once
// per name. A null-texture crash (Texture2D::getContentSize, fault addr 0x3c) follows a failed find, so the last
// FINDMISS lines before the crash name the missing image. Added by build/deploy_jp_frida.py --find-miss only.
(function () {
  const TAG = 'FINDMISS';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  const wait = setInterval(function () {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    const find = m.findExportByName('criFsBinder_Find');
    if (!find) { log('criFsBinder_Find missing'); return; }
    const seen = new Set();
    Interceptor.attach(find, {
      onEnter(a) { this.n = null; this.ex = a[3]; try { this.n = a[1].readUtf8String(); } catch (e) {} },
      onLeave(r) {
        try {
          if (!this.n || seen.has(this.n)) return;
          const found = this.ex.isNull() ? (r.toInt32() === 0) : (this.ex.readS32() !== 0);
          if (!found) { seen.add(this.n); if (seen.size <= 4000) log(this.n); }
        } catch (e) {}
      }
    });
    // Null-texture caller: Texture2D::getContentSize(this=null) is the crash site; log who called it (no exception
    // handler -- Process.setExceptionHandler broke ART's own fault handling and the app could not start).
    const gcs = m.findExportByName('_ZNK7cocos2d9Texture2D14getContentSizeEv');
    if (gcs) {
      Interceptor.attach(gcs, { onEnter(a) {
        if (!a[0].isNull()) return;
        try {
          const rel = p => { try { return '0x' + ptr(p).sub(m.base).toString(16); } catch (e) { return '?'; } };
          log('NULLTEX lr=' + rel(this.context.lr) + ' bt ' + Thread.backtrace(this.context, Backtracer.ACCURATE).slice(0, 12).map(rel).join(' < '));
          log('NULLTEX fuz ' + Thread.backtrace(this.context, Backtracer.FUZZY).slice(0, 20).map(rel).join(' < '));
        } catch (e) { log('NULLTEX bt failed ' + e); }
      } });
    }
    log('installed');
  }, 50);
})();
