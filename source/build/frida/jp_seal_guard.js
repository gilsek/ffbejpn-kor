// jp_seal_guard.js — 봉인의 방 → 뒤로(GateScene 재구성) 크래시 회피 + 원인 기록 (2026-11-12).
//
// 크래시 3건 공통(build/out/seal_crash/notes.md): libgame.so+0x218CA7C cocos2d::Ref::retain (this=null)
//   <- +0x21D489C cocos2d::__Dictionary::setObjectUnSafe(obj=null, key) <- __Dictionary::setObject <- UI 캐시.
// null 객체를 사전에 넣으려는 호출만 건너뛴다(그 키는 사전에 없게 됨 = getObject miss). 건너뛸 때마다
// 키와 호출 경로를 EXVIUS_JP 로그에 남겨 근본 원인(어떤 UI 리소스가 없는지)을 찾는다.
// libgame.so sha256 54ef0fe9a5c160254654a741bd8a3791e83bac80f7ece8c806af589e8fa1184e (JP 11.0.0 arm64).
(function () {
  const TAG = 'SEALGUARD';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }

  const UNSAFE_SYM = '_ZN7cocos2d12__Dictionary15setObjectUnSafeEPNS_3RefERKNSt6__ndk112basic_stringIcNS3_11char_traitsIcEENS3_9allocatorIcEEEE';
  const A_UNSAFE = 0x21D4874;
  const B_UNSAFE = 0xf81b0ff9;   // str x25,[sp,#-0x50]!
  let skipped = 0;

  function readStdString(p) {
    try {
      if (p.isNull()) return '<null>';
      const b = p.readU8();
      if (b & 1) {
        const size = p.add(8).readU64().toNumber();
        const data = p.add(16).readPointer();
        if (data.isNull() || size > 4096) return '<bad>';
        return data.readUtf8String(Math.min(size, 256));
      }
      return p.add(1).readUtf8String(Math.min(b >> 1, 22));
    } catch (e) { return '<err>'; }
  }

  const wait = setInterval(function () {
    const m = Process.findModuleByName('libgame.so');
    if (!m) return;
    clearInterval(wait);
    const unsafe = m.findExportByName(UNSAFE_SYM);
    if (!unsafe || !unsafe.equals(m.base.add(A_UNSAFE)) || unsafe.readU32() !== B_UNSAFE) {
      log('anchor mismatch, not installed (' + unsafe + ')');
      return;
    }
    const orig = new NativeFunction(unsafe, 'void', ['pointer', 'pointer', 'pointer']);
    Interceptor.replace(unsafe, new NativeCallback(function (dict, obj, key) {
      if (!obj.isNull()) { orig(dict, obj, key); return; }
      skipped++;
      if (skipped <= 40) {
        let bt = '';
        try {
          bt = Thread.backtrace(this.context, Backtracer.FUZZY).slice(0, 10).map(function (p) {
            const off = p.sub(m.base);
            const s = DebugSymbol.fromAddress(p);
            return (s.name ? s.name.substring(0, 60) : '?') + '+' + off;
          }).join(' < ');
        } catch (e) { bt = '<bt err>'; }
        log('null insert skipped #' + skipped + ' key="' + readStdString(key) + '" ret=' + this.returnAddress.sub(m.base) + ' bt: ' + bt);
      }
    }, 'void', ['pointer', 'pointer', 'pointer']));
    log('null-insert guard on __Dictionary::setObjectUnSafe');
  }, 50);
})();
