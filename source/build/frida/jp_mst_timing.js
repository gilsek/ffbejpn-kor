// jp_mst_timing.js — read-only timing of master loading at login (2026-11-10, diagnostic; deploy_jp_frida.py --mst-timing).
// Sums wall time and calls of the decode / parse functions on the game thread and logs the slowest files.
// Offsets: libgame.so sha256 54ef0fe9... (CommonUtils::* exports are 4-byte branch stubs, so hook their targets).
(function () {
  const TAG = 'MSTTIME';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  const FN = {
    procStateMstLoad: 0x1c3a004,
    decodeFile: 0x15a3754,
    decodeFileNew: 0x15a3900,
    decodeCString: 0x15a3ae4,
    decodeCStringNew: 0x15a3cc0,
    parseString: 0x15e62b8,
  };
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    const tot = {}, cnt = {}, files = [];
    let first = 0, last = 0, dirty = false;
    for (const [name, off] of Object.entries(FN)) {
      tot[name] = 0; cnt[name] = 0;
      Interceptor.attach(m.base.add(off), {
        onEnter(args) {
          this.t = Date.now();
          if (name.startsWith('decodeFile')) { try { this.path = args[0].readUtf8String(); } catch (e) { this.path = '?'; } }
        },
        onLeave() {
          const now = Date.now(), d = now - this.t;
          tot[name] += d; cnt[name] += 1; dirty = true;
          if (!first) first = this.t; last = now;
          if (this.path) files.push([d, this.path.split('/').pop()]);
        },
      });
    }
    setInterval(() => {
      if (!dirty || Date.now() - last < 2000) return;
      dirty = false;
      log('span ' + (last - first) + 'ms ' + Object.keys(FN).map(k => k + '=' + tot[k] + 'ms/' + cnt[k]).join(' '));
      files.sort((a, b) => b[0] - a[0]);
      log('slowest ' + files.slice(0, 15).map(f => f[1] + ':' + f[0]).join(' '));
      log('files ' + files.length + ' sum ' + files.reduce((s, f) => s + f[0], 0) + 'ms');
    }, 1000);
    log('hooks installed');
  }, 50);
})();
