// jp_clock.js — keep the client's server clock at the real time (2026-11-09).
//
// The JP client's "now" (time manager, singleton getter libgame+0x15e5bec, now() at +0x15e61bc) is
//     base(+0x08) + clock_gettime(CLOCK_BOOTTIME) - syncBoottime(+0x28)
// HeaderResponse::readParam (token dNrSy63V, the engine's time.time()) stores only base; syncBoottime stayed 0,
// so the client ran ahead by the tablet's whole uptime (probe 21:58: client 1803032275 vs device 1794229095,
// uptime 8803302 s). Quest periods then read as already ended ("남은 시간" blank) or 103 days short.
// Fix: whenever the header time is read, record the current CLOCK_BOOTTIME seconds at +0x28.
// Offsets are for the unchanged JP 11.0.0 libgame.so.
(function () {
  const TAG = 'CLOCK';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    try {
    const read = m.findExportByName('_ZN14HeaderResponse9readParamEiiPKcS1_b');
    if (!read) { log('missing HeaderResponse::readParam'); return; }
    const instance = new NativeFunction(m.base.add(0x15e5bec), 'pointer', []);
    const now = new NativeFunction(m.base.add(0x15e61bc), 'int64', ['pointer']);
    const clockGettime = new NativeFunction(Process.getModuleByName('libc.so').getExportByName('clock_gettime'), 'int', ['int', 'pointer']);
    const ts = Memory.alloc(16);
    let fixes = 0;
    Interceptor.attach(read, {
      onEnter(args) { this.isTime = !args[3].isNull() && args[3].readCString() === 'dNrSy63V'; },
      onLeave() {
        if (!this.isTime) return;
        if (clockGettime(7, ts) !== 0) return;          // 7 = CLOCK_BOOTTIME, the clock now() reads
        const inst = instance();
        inst.add(0x28).writeS64(ts.readS64());
        if (++fixes <= 3) log('server clock synced: client now=' + now(inst) + ' device=' + Math.floor(Date.now() / 1000));
      }
    });
    log('hook installed');
    } catch (e) { log('install failed ' + e); }
  }, 50);
})();
