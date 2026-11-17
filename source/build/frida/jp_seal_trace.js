// jp_seal_trace.js — 봉인의 방 진단(읽기 전용, 2026-11-12). 코드 패치 없음, 인자/반환값만 기록.
// 1) GateScene 재구성 때 "common" 배치노드가 null이 되는 원인: getOrCreateSpriteBatchNode(key, file, ..., loader)
//    와 TextureCache::addImage 실패를 기록.
// 2) 하얀 신정석 아이콘: createGameSpriteByImage(const char* file, ...) 호출 파일명과 반환값 기록.
(function () {
  const TAG = 'SEALTRACE';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  function stdstr(p) {
    try {
      if (p.isNull()) return '<null>';
      const b = p.readU8();
      if (b & 1) { const n = p.add(8).readU64().toNumber(); const d = p.add(16).readPointer(); return n > 512 ? '<big>' : d.readUtf8String(n); }
      return p.add(1).readUtf8String(b >> 1);
    } catch (e) { return '<err>'; }
  }
  function cstr(p) { try { return p.isNull() ? '<null>' : p.readUtf8String(); } catch (e) { return '<err>'; } }
  const SYMS = {
    batch: ['_ZN11LayoutUtils26getOrCreateSpriteBatchNodeERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEPKciijP13CriFileLoader', 0x154717c],
    addImage: ['_ZN7cocos2d12TextureCache8addImageERKNSt6__ndk112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE', 0x21cb324],
    byImage: ['_ZN11LayoutUtils23createGameSpriteByImageEPKciffffiRKN7cocos2d4Vec2E', 0x1547c18],
  };
  const wait = setInterval(function () {
    const m = Process.findModuleByName('libgame.so');
    if (!m) return;
    clearInterval(wait);
    let n = 0;
    function hook(name, onEnter, onLeave) {
      const s = SYMS[name];
      const a = m.findExportByName(s[0]);
      if (!a || !a.equals(m.base.add(s[1]))) { log('anchor mismatch ' + name); return; }
      Interceptor.attach(a, { onEnter: onEnter, onLeave: onLeave });
      n++;
    }
    hook('batch', function (args) { this.k = stdstr(args[0]); this.f = cstr(args[1]); },
      function (ret) { if (ret.isNull() || this.k === 'common') log('batch key="' + this.k + '" file="' + this.f + '" -> ' + ret); });
    hook('addImage', function (args) { this.p = stdstr(args[1]); },
      function (ret) { if (ret.isNull() || this.p.indexOf('item_') >= 0) log('addImage "' + this.p + '" -> ' + ret); });
    hook('byImage', function (args) { this.f = cstr(args[0]); },
      function (ret) { if (ret.isNull() || this.f.indexOf('item_') >= 0) log('byImage "' + this.f + '" -> ' + ret); });
    log('trace hooks=' + n);
  }, 50);
})();
