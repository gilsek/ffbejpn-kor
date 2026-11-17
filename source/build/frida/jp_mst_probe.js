// jp_mst_probe.js — read-only probe of the master loader list (2026-11-10, diagnostic).
// 0x1da9df0(manager) walks a std::map<string, Loader*> (begin [this+8], end node this+0x10, value at node+0x38) and for
// each loader calls vf+0x28 (gate) then vf+0x10 (load, 0 = ok). Logs how many pass the gate before and after.
(function () {
  const TAG = 'MSTPROBE';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    function next(n) {                       // libc++ __tree_next
      let r = n.add(8).readPointer();
      if (!r.isNull()) { while (!r.readPointer().isNull()) r = r.readPointer(); return r; }
      while (true) { const p = n.add(0x10).readPointer(); if (p.readPointer().equals(n)) return p; n = p; }
    }
    function loaders(mgr) {
      const out = [], end = mgr.add(0x10);
      for (let n = mgr.add(8).readPointer(); !n.equals(end); n = next(n)) out.push(n.add(0x38).readPointer());
      return out;
    }
    function vf(o, off) { return o.readPointer().add(off).readPointer(); }
    function gate(ls) {
      let c = 0;
      for (const l of ls) if (new NativeFunction(vf(l, 0x28), 'bool', ['pointer'])(l)) c++;
      return c;
    }
    Interceptor.attach(m.base.add(0x1da9df0), {
      onEnter(args) {
        this.mgr = args[0];
        const ls = loaders(this.mgr);
        const vt = {};
        for (const l of ls) { const k = l.readPointer().sub(m.base).toString(); vt[k] = (vt[k] || 0) + 1; }
        log('enter loaders=' + ls.length + ' gate=' + gate(ls) + ' vtables=' + Object.keys(vt).length);
        const l = ls[0];
        log('sample vt=' + l.readPointer().sub(m.base) + ' f10=' + vf(l, 0x10).sub(m.base) + ' f28=' + vf(l, 0x28).sub(m.base) +
            ' f30=' + vf(l, 0x30).sub(m.base) + ' f38=' + vf(l, 0x38).sub(m.base));
        this.t = Date.now();
      },
      onLeave(r) {
        const ls = loaders(this.mgr);
        log('leave ret=' + r + ' ms=' + (Date.now() - this.t) + ' gate=' + gate(ls) + ' tid=' + Process.getCurrentThreadId());
      },
    });
    log('hook installed');
  }, 50);
})();
