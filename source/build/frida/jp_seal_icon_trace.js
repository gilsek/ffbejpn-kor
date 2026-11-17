// jp_seal_icon_trace.js — 봉인의 방 아이콘 경로 진단(읽기 전용, 2026-11-12).
// export 이름으로 찾은 함수만 attach. 아이콘 이름 생성/아이템 정보 갱신이 불리는지와 반환값 기록.
(function () {
  const TAG = 'SEALICON';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  function stdstr(p) {
    try { const b = p.readU8();
      if (b & 1) { const n = p.add(8).readU64().toNumber(); return n > 300 ? '<big>' : p.add(16).readPointer().readUtf8String(n); }
      return p.add(1).readUtf8String(b >> 1); } catch (e) { return '<err>'; }
  }
  const wait = setInterval(function () {
    const m = Process.findModuleByName('libgame.so');
    if (!m) return;
    clearInterval(wait);
    const want = ['getItemIconImageName', 'setLayoutItemInfo', 'getRequiredItemIdWithTabIndex', 'SealAreaListScene'];
    let n = 0;
    m.enumerateExports().forEach(function (e) {
      if (e.type !== 'function') return;
      const nm = e.name;
      if (nm.indexOf('getItemIconImageName') >= 0) {
        Interceptor.attach(e.address, {
          onEnter: function (a) { this.sret = this.context.x8; this.a = [a[0].toInt32(), a[1].toInt32(), a[2].toInt32()]; },
          onLeave: function () { log('getItemIconImageName(' + this.a.join(',') + ') = "' + stdstr(this.sret) + '" [' + nm + ']'); }
        }); n++;
      } else if (nm.indexOf('getRequiredItemIdWithTabIndex') >= 0) {
        Interceptor.attach(e.address, {
          onEnter: function (a) { this.t = a[0].toInt32(); },
          onLeave: function (r) { log('getRequiredItemIdWithTabIndex(' + this.t + ') -> ' + r.toInt32()); }
        }); n++;
      } else if (nm.indexOf('SealAreaListScene') >= 0 && /setLayout|update|Item|Tab/.test(nm)) {
        let c = 0; Interceptor.attach(e.address, { onEnter: function () { if (++c > 20) return; log('call ' + nm + ' @' + e.address.sub(m.base)); } }); n++;
      }
    });
    log('icon trace hooks=' + n);
  }, 50);
})();
