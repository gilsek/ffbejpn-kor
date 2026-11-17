// jp_mst_slice.js — load masters over several frames so the login loading animation keeps moving (2026-11-10).
//
// LoginScene::procStateMstLoad runs once per frame: updateLoadingAnime(), count down [this+0x548], then (when
// CommonUtils::needsDownload() and not [this+0x57a] skip) calls the hidden loader 0x1da9df0(manager 0x1da8a24()).
// That walks a std::map<string, Loader*> (179 loaders) and for each one calls vf+0x28 (gate) and vf+0x10 (load,
// 0 = ok), then runs 6 post steps (GateUtil/SealUtil exchange lists, VisionCardUtils status). All of it takes
// ~6 s inside one frame, so the chocobo freezes (device 2026-11-10, gate 163/179, gate result unchanged after load).
// Here the gated loads run ~30 ms per frame with updateLoadingAnime() in between; then the original
// procStateMstLoad runs once with the gate (call site 0x1da9eac, loader in x21) forced off for loaders already
// loaded, so it only does the post steps, error handling for anything that failed, and the state change.
// Of the post steps only GateUtil (0.24 s) and SealUtil::setExchangeGachaIdList (0.58 s) cost anything; each runs in
// its own frame first (they only read masters) and is skipped inside that final call. Remaining single-frame cost:
// AbilityMstList's own load, ~1.75 s.
// NativeFunction must use exceptions:'propagate': the loaders call into Java, and Android 15 ART's implicit suspend
// checks fault on purpose; Frida's default 'steal' swallowed that and ART aborted ("Transitioning to Runnable with
// checkpoint flag"). CModule is not an option here: its pages were not executable on this device (2026-11-10).
// A single loader can still take long (AbilityMstList: 41,207 cocos Refs, ~1.3 s of parsing). While a load is in
// progress, every ~33 ms (checked on cocos2d::Ref::Ref and on per-line decode calls) the loading ss::Player
// ([LoginScene+0x570]) is advanced by the elapsed time and the scene is drawn with the Director paused
// (Director+0x150, so the scheduler does not run again) and shown with eglSwapBuffers (GLViewImpl::swapBuffers is
// empty on Android; GLSurfaceView normally swaps after onDrawFrame). Loading in another thread is not safe: the
// loaders autorelease every row into cocos' shared pool, which the GL thread clears each frame.
// The big Java decodes are taken off the GL thread by FastDecode.prefetch (build/patch_jp_fast_decode.py).
// Offsets: libgame.so sha256 54ef0fe9... (JP 11.0.0 arm64).
(function () {
  const TAG = 'MSTSLICE';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  const PROC = 0x1c3a004, MGR = 0x1da8a24, GATE_SITE = 0x1da9eac, BUDGET_MS = 30;
  const OPT = { exceptions: 'propagate' };
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    const anchor = m.findExportByName('_ZN10LoginScene16procStateMstLoadEv');
    if (!anchor || !anchor.equals(m.base.add(PROC)) || m.base.add(GATE_SITE).readU32() !== 0x360006a0) {
      log('code mismatch, not installed'); return;
    }
    const nf = (p, ret, args) => new NativeFunction(p, ret, args, OPT);
    const anime = nf(m.findExportByName('_ZN10LoginScene18updateLoadingAnimeEv'), 'void', ['pointer']);
    const needs = nf(m.findExportByName('_ZN11CommonUtils13needsDownloadEv'), 'bool', []);
    const mgr = nf(m.base.add(MGR), 'pointer', []);
    const orig = nf(m.base.add(PROC), 'void', ['pointer']);
    const fns = new Map();                   // vtable slot -> NativeFunction
    function vf(o, off, ret) {
      const p = o.readPointer().add(off).readPointer(), k = p.toString() + ret;
      let f = fns.get(k); if (!f) fns.set(k, f = nf(p, ret, ['pointer']));
      return f;
    }
    function next(n) {                       // libc++ __tree_next
      let r = n.add(8).readPointer();
      if (!r.isNull()) { while (!r.readPointer().isNull()) r = r.readPointer(); return r; }
      while (true) { const p = n.add(0x10).readPointer(); if (p.readPointer().equals(n)) return p; n = p; }
    }
    function loaders(g) {
      const out = [], end = g.add(0x10);
      for (let n = g.add(8).readPointer(); !n.equals(end); n = next(n)) out.push(n.add(0x38).readPointer());
      return out;
    }
    const director = nf(m.findExportByName('_ZN7cocos2d8Director11getInstanceEv'), 'pointer', []);
    const drawScene = nf(m.findExportByName('_ZN7cocos2d8Director9drawSceneEv'), 'void', ['pointer']);
    const calcDelta = nf(m.findExportByName('_ZN7cocos2d8Director18calculateDeltaTimeEv'), 'void', ['pointer']);
    const getDelta = nf(m.findExportByName('_ZNK7cocos2d8Director12getDeltaTimeEv'), 'float', ['pointer']);
    const ssUpdate = nf(m.findExportByName('_ZN2ss6Player6updateEf'), 'void', ['pointer', 'float']);
    const egl = Process.getModuleByName('libEGL.so');
    const eglDpy = nf(egl.getExportByName('eglGetCurrentDisplay'), 'pointer', []);
    const eglSurf = nf(egl.getExportByName('eglGetCurrentSurface'), 'pointer', ['int']);
    const eglSwap = nf(egl.getExportByName('eglSwapBuffers'), 'int', ['pointer', 'pointer']);
    function players(top) {                  // top ss::Player and nested ones (same vtable), children at Node+0x178
      const vt = top.readPointer(), out = [];
      (function walk(n, d) {
        if (n.readPointer().equals(vt)) out.push(n);
        if (d > 4) return;
        const b = n.add(0x178).readPointer(), k = n.add(0x180).readPointer().sub(b).toInt32() / 8;
        for (let i = 0; i < k && i < 64; i++) walk(b.add(8 * i).readPointer(), d + 1);
      })(top, 0);
      return out;
    }
    let scene = null, plist = [], drawing = false, lastShown = 0, maxGap = 0, redraws = 0;
    function shown() { const n = Date.now(); if (lastShown) maxGap = Math.max(maxGap, n - lastShown); lastShown = n; }
    function tick() {
      if (drawing || !scene || Date.now() - lastShown < 33) return;
      drawing = true;
      try {
        const d = director(), paused = d.add(0x150).readU8();
        calcDelta(d);
        // ss::Player::updateFrame steps one animation frame per call (Director+0x120 animationInterval, frame skip
        // off), so step as many times as frames have passed.
        const dt = getDelta(d), iv = d.add(0x120).readFloat() || 1 / 60;
        const steps = Math.max(1, Math.min(8, Math.round(dt / iv)));
        for (let s = 0; s < steps; s++) for (const p of plist) ssUpdate(p, iv);
        d.add(0x150).writeU8(1);
        try { drawScene(d); } finally { d.add(0x150).writeU8(paused); }
        eglSwap(eglDpy(), eglSurf(0x3059));   // EGL_DRAW
        redraws++;
        shown();
      } finally { drawing = false; }
    }
    let ticks = [];
    function startTicks() {
      ticks = [m.findExportByName('_ZN7cocos2d3RefC2Ev'), m.base.add(0x15a3cc0)].map(p => Interceptor.attach(p, { onEnter: tick }));
    }
    function stopTicks() { ticks.forEach(x => x.detach()); ticks = []; scene = null; }
    const POST = ['_ZN8GateUtil22setExchangeGachaIdListEv', '_ZN8SealUtil22setExchangeGachaIdListEv'].map(s => {
      const p = m.findExportByName(s), f = nf(p, 'void', []);
      Interceptor.replace(p, new NativeCallback(() => { if (!force) f(); }, 'void', []));
      return f;
    });
    let phase = 0, list = [], idx = 0, frames = 0, t0 = 0, failed = 0, force = false, worst = 0, slow = [];
    const loaded = new Set();
    Interceptor.attach(m.base.add(GATE_SITE), {
      onEnter() { if (force && loaded.has(this.context.x21.toString())) this.context.x0 = ptr(0); },
    });
    Interceptor.replace(m.base.add(PROC), new NativeCallback(function (self) {
      if (phase === 1) {
        anime(self);
        frames++;
        shown();
        const t = Date.now();
        while (idx < list.length && Date.now() - t < BUDGET_MS) {
          const l = list[idx++];
          if (!vf(l, 0x28, 'bool')(l)) continue;
          const tl = Date.now();
          if (vf(l, 0x10, 'int')(l) === 0) loaded.add(l.toString()); else failed++;
          if (Date.now() - tl > 100) slow.push((idx - 1) + ':' + (() => { try { return l.readPointer().sub(8).readPointer().add(8).readPointer().readCString(); } catch (e) { return l.readPointer().sub(m.base); } })() + '@' + l.readPointer().add(0x10).readPointer().sub(m.base) + '=' + (Date.now() - tl));
        }
        worst = Math.max(worst, Date.now() - t);
        if (idx < list.length) return;
        phase = 2;
        return;
      }
      if (phase === 2 || phase === 3) {
        anime(self);
        frames++;
        shown();
        const t = Date.now();
        POST[phase - 2]();
        worst = Math.max(worst, Date.now() - t);
        phase++;
        return;
      }
      if (phase === 4) {
        stopTicks();
        const t1 = Date.now();
        force = true;
        try { orig(self); } finally { force = false; }
        log('loaded ' + loaded.size + '/' + list.length + ' failed ' + failed + ' frames ' + frames +
            ' total ' + (Date.now() - t0) + 'ms, worst frame ' + worst + 'ms, finish ' + (Date.now() - t1) + 'ms, redraws ' + redraws + ' players ' + plist.length + ', longest still ' + maxGap + 'ms, slow ' + slow.join(' '));
        phase = 0; loaded.clear(); list = [];
        return;
      }
      if (self.add(0x548).readS32() - 1 <= 0 && self.add(0x57a).readU8() === 0 && needs()) {
        anime(self);
        list = loaders(mgr()); idx = 0; frames = 0; failed = 0; worst = 0; slow = []; t0 = Date.now(); phase = 1;
        const top = self.add(0x570).readPointer();
        plist = top.isNull() ? [] : players(top);
        scene = self; lastShown = 0; maxGap = 0; redraws = 0;
        startTicks();
        return;
      }
      orig(self);
    }, 'void', ['pointer']));
    log('hook installed');
  }, 50);
})();
