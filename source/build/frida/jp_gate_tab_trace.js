// 읽기 전용 진단: 차원의 틈새(GateScene::setLayoutList) 탭 필터가 비교하는 값을 기록한다.
// 0x1bdd904: `ldr w9,[sp,#0xb0]; cmp w9,w8` -- [sp+0xb0] = 현재 탭의 필터 값, w8 = 행의 qnUhs32P(+0x28).
// 0x1bdd6d8: `ldr w9,[x21]` -- x21 = 선택된 메인 탭 인덱스 포인터.
// libgame.so sha256 54ef0fe9a5c16025... 기준 오프셋. 로그 태그는 jp_offline.js의 note()를 쓴다.
(function () {
  const seen = {};
  let flushAt = 0;
  function flush(force) {
    const now = Date.now();
    if (!force && now < flushAt) return;
    flushAt = now + 1500;
    const keys = Object.keys(seen);
    if (keys.length === 0) return;
    note('GATE_TAB_TRACE ' + keys.map(k => k + 'x' + seen[k]).join(' '));
    for (const k of keys) delete seen[k];
  }
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so');
    if (!m) return;
    clearInterval(wait);
    Interceptor.attach(m.base.add(0x1bdd6d8), function () {
      try { const idx = this.context.x21.readS32(); const k = 'main=' + idx; seen[k] = (seen[k] || 0) + 1; } catch (e) {}
    });
    // 0x1bdd810: x25 = AreaMst of the area entering the loop, areaId at +0x88 (GateScene::touchEnded reads the same).
    const WATCH = { 5040: 1, 5050: 1, 5060: 1, 6080: 1, 4821: 1 };
    let entered = 0;
    Interceptor.attach(m.base.add(0x1bdd810), function () {
      try {
        const x25 = this.context.x25; if (x25.isNull()) { seen['area=null'] = (seen['area=null'] || 0) + 1; return; }
        const area = x25.add(0x88).readS32(); entered++;
        if (WATCH[area]) { const k = 'in=' + area; seen[k] = (seen[k] || 0) + 1; }
      } catch (e) {}
    });
    // 0x1bdd904: x27 = SpDungeonCondMst (null -> row tab 0), w8 = its qnUhs32P (+0x28), [sp+0xb0] = tab filter.
    Interceptor.attach(m.base.add(0x1bdd904), function () {
      try {
        const want = this.context.sp.add(0xb0).readS32();
        const row = this.context.x8.toInt32();
        const area = this.context.x25.add(0x88).readS32();
        const k = 'want=' + want + '/row=' + row;
        seen[k] = (seen[k] || 0) + 1;
        if (WATCH[area]) { const k2 = 'cmp' + area + ':cond=' + (this.context.x27.isNull() ? 'null' : 'ok') + ',row=' + row + ',want=' + want; seen[k2] = (seen[k2] || 0) + 1; }
      } catch (e) {}
      flush(false);
    });
    setInterval(() => { if (entered) { note('GATE_TAB_TRACE entered ' + entered); entered = 0; } }, 3000);
    // 시험용(2026-11-13): RmAreaScene 크래시(Texture2D::getContentSize this=null) 원인 그림 찾기.
    function stdStr(p) {  // libc++ std::string
      try { const f = p.readU8(); if ((f & 1) === 0) return p.add(1).readUtf8String(f >> 1);
        return p.add(16).readPointer().readUtf8String(p.add(8).readU64().toNumber()); } catch (e) { return '?'; }
    }
    const recent = [];
    function remember(t) { recent.push(t); if (recent.length > 12) recent.shift(); }
    function sym(n) { try { return m.findExportByName(n); } catch (e) { note('IMG_TRACE no export ' + n); return null; } }
    const tcAdd = sym('_ZN7cocos2d12TextureCache8addImageERKNSt6__ndk112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE');
    if (tcAdd) Interceptor.attach(tcAdd, { onEnter(a) { this.n = stdStr(a[1]); }, onLeave(r) {
      if (r.isNull()) { note('IMG_MISS addImage ' + this.n); remember('miss:' + this.n); } else remember(this.n); } });
    const batch = sym('_ZN11LayoutUtils26getOrCreateSpriteBatchNodeERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEiij');
    if (batch) Interceptor.attach(batch, { onEnter(a) { this.n = stdStr(a[0]); }, onLeave(r) {
      if (r.isNull()) { note('IMG_MISS batch ' + this.n); remember('bmiss:' + this.n); } else remember('b:' + this.n); } });
    const frame = sym('_ZN7cocos2d16SpriteFrameCache20getSpriteFrameByNameERKNSt6__ndk112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE');
    if (frame) Interceptor.attach(frame, { onEnter(a) { this.n = stdStr(a[1]); }, onLeave(r) {
      if (r.isNull()) { note('IMG_MISS frame ' + this.n); remember('fmiss:' + this.n); } } });
    // 지도 그림 로더(이름 없음 0x15a2794: CRI 래퍼, x1=std::string 파일명)와 setLayoutAreaMap의 구역 id(+0x9c).
    Interceptor.attach(m.base.add(0x15a2794), { onEnter(a) { this.n = stdStr(a[1]); }, onLeave(r) {
      remember('L:' + this.n + (r.isNull() ? '=NULL' : ''));
      if (r.isNull()) note('IMG_MISS loader ' + this.n); } });
    Interceptor.attach(m.base.add(0x1a41a38), { onEnter(a) { try { note('AREAMAP setLayoutAreaMap area=' + a[0].add(0x9c).readS32()); } catch (e) {} } });
    const gcs = sym('_ZNK7cocos2d9Texture2D14getContentSizeEv');
    if (gcs) Interceptor.attach(gcs, { onEnter(a) {
      if (!a[0].isNull()) return;
      const bt = Thread.backtrace(this.context, Backtracer.ACCURATE).slice(0, 8).map(x => '0x' + x.sub(m.base).toString(16)).join(',');
      note('IMG_NULL_TEXTURE bt=' + bt + ' recent=' + recent.join(' | '));
    } });
    setInterval(() => flush(true), 3000);
    note('GATE_TAB_TRACE ready base=' + m.base);
  }, 50);
})();
