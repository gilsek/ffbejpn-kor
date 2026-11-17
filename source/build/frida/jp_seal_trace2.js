// trace2.js — 봉인의 방 → GateScene 재진입 크래시 확정용 읽기 전용 훅 초안 (2026-11-12)
// 코드/메모리 수정 없음. jp_seal_trace.js와 같은 형식(note(TAG+...), 앵커 확인).
// 확인하려는 것:
//  1) 0x154717c(6인자)에서 배치노드 생성이 어떤 키/파일로 실패하는지
//  2) 전역 CriFileLoader*(0x2e810620) 경로: vtable[0x30]=0x15dd2bc → 0x15dcf54의 어느 단계에서 null이 되는지
//     (existsFile 0x15d711c / getFileSize 0x15d700c / 텍스처 생성 0x15d6910)
//  3) 봉인의 방 loadFiles(0x199e578)가 호출하는 manager→0x15dc894(로더 캐시 정리)와 0x15a27b4(등록) 순서
//  4) isExist 경로: 0x15a2874 → CriFileLoader::isExist 0x15ddafc → 0x15d711c, 그리고 아이콘 이름 문자열
//  5) null child가 addChildHelper로 들어오는지(크래시 직전)
(function () {
  const TAG = 'SEALTRACE2';
  let armed = false;
  function log(s) { if (!armed && !/^(trace2|ANCHOR|hook fail|SealAreaListScene)/.test(s) && s.indexOf('item_') < 0) return; try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  function stdstr(p) {
    try {
      if (p.isNull()) return '<null>';
      const b = p.readU8();
      if (b & 1) { const n = p.add(8).readU64().toNumber(); const d = p.add(16).readPointer(); return n > 300 ? '<big:' + n + '>' : d.readUtf8String(n); }
      return p.add(1).readUtf8String(b >> 1);
    } catch (e) { return '<err>'; }
  }
  function cstr(p) { try { return p.isNull() ? '<null>' : p.readUtf8String(); } catch (e) { return '<err>'; } }
  function hx(p) { try { return p.toString(); } catch (e) { return '?'; } }

  // libgame 원본 오프셋(빌드마다 base만 이동). 앵커는 export로 검증.
  const OFF = {
    batch6: 0x154717c, batch5: 0x154709c, batch4: 0x1547050,
    createWT: 0x2135c00, initWT: 0x2135ce0,
    loaderGetTex: 0x15dd2bc, loaderFetch: 0x15dcf54,
    existsWrap: 0x15d711c, fileSize: 0x15d700c, mkTex: 0x15d6910,
    loaderClear: 0x15dc894, mgrClear: 0x15a2758, mgrAdd: 0x15a27b4, mgrGet: 0x15a246c,
    isExistWrap: 0x15a2874, isExist: 0x15ddafc,
    sealLoadFiles: 0x199e578, sealBack: 0x19a0e28, sealInvisible: 0x199e558, sealDtor: 0x199e3fc,
    itemInfo: 0x199ee88,
    addChildHelper: 0x2122e48, addChild1: 0x2123120,
  };
  const ANCHORS = [
    ['_ZN11LayoutUtils26getOrCreateSpriteBatchNodeERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEPKciijP13CriFileLoader', OFF.batch6],
    ['_ZN11LayoutUtils26getOrCreateSpriteBatchNodeERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEP13CriFileLoaderiij', OFF.batch5],
    ['_ZN7cocos2d15SpriteBatchNode17createWithTextureEPNS_9Texture2DEl', OFF.createWT],
    ['_ZN17SealAreaListScene9loadFilesEv', OFF.sealLoadFiles],
    ['_ZN7cocos2d4Node14addChildHelperEPS0_iiRKNSt6__ndk112basic_stringIcNS2_11char_traitsIcEENS2_9allocatorIcEEEEb', OFF.addChildHelper],
  ];

  const wait = setInterval(function () {
    const m = Process.findModuleByName('libgame.so');
    if (!m) return;
    clearInterval(wait);
    for (const [sym, off] of ANCHORS) {
      const a = m.findExportByName(sym);
      if (!a || !a.equals(m.base.add(off))) { log('ANCHOR MISMATCH ' + sym + ' off=0x' + off.toString(16)); return; }
    }
    let n = 0;
    function at(off) { return m.base.add(off); }
    function hook(off, name, onEnter, onLeave) {
      try { Interceptor.attach(at(off), { onEnter: onEnter, onLeave: onLeave }); n++; }
      catch (e) { log('hook fail ' + name + ' ' + e); }
    }

    // 1) 배치노드 생성 계층
    hook(OFF.batch4, 'batch4', function (args) { this.k = stdstr(args[0]); },
      function (r) { log('batch4 key="' + this.k + '" -> ' + hx(r)); });
    hook(OFF.batch5, 'batch5', function (args) { this.k = stdstr(args[0]); this.l = args[1]; },
      function (r) { log('batch5 key="' + this.k + '" loader=' + hx(this.l) + ' -> ' + hx(r)); });
    hook(OFF.batch6, 'batch6',
      function (args) { this.k = stdstr(args[0]); this.f = cstr(args[1]); this.w = [args[2].toInt32(), args[3].toInt32(), args[4].toInt32()]; this.l = args[5]; },
      function (r) {
        log('batch6 key="' + this.k + '" file="' + this.f + '" w=' + this.w.join(',') + ' loader=' + hx(this.l) + ' -> ' + hx(r));
      });
    // getBatchNode 결과(0x15471b8 직후) / createWithTexture 결과(0x15471ec 직후)

    // 2) CriFileLoader 텍스처 취득 경로
    hook(OFF.loaderGetTex, 'loaderGetTex',
      function (args) { this.name = cstr(args[1]); },
      function (r) { log('loaderGetTex name="' + this.name + '" -> ' + hx(r)); });
    hook(OFF.loaderFetch, 'loaderFetch',
      function (args) { this.s = stdstr(args[1]); this.name = cstr(args[4]); this.w2 = args[2].toInt32(); this.w3 = args[3].toInt32(); },
      function (r) { log('loaderFetch prefix="' + this.s + '" file="' + this.name + '" w2=' + this.w2 + ' w3=' + this.w3 + ' -> ' + hx(r)); });
    // 존재 확인 직후(0x15dcfb4: exists 반환값 비교 전) / 실패 분기들
    hook(OFF.existsWrap, 'existsWrap',
      function (args) { this.b = args[0]; this.p = cstr(args[1]); },
      function (r) { log('existsWrap binder=' + hx(this.b) + ' path="' + this.p + '" -> ' + r.toInt32()); });
    hook(OFF.fileSize, 'fileSize',
      function (args) { this.p = cstr(args[1]); },
      function (r) { log('fileSize path="' + this.p + '" -> ' + r.toInt32()); });
    hook(OFF.mkTex, 'mkTex', function (args) { this.name = cstr(args[4]); },
      function (r) { log('mkTex file="' + this.name + '" -> ' + hx(r)); });

    // 3) 봉인의 방에서 전역 로더 캐시 건드리는 지점
    hook(OFF.mgrGet, 'mgrGet', null, function (r) { log('mgrGet -> ' + hx(r)); });
    hook(OFF.mgrClear, 'mgrClear(0x15dc894)', function (args) { this.l = args[0]; },
      function () { log('mgrClear(0x15dc894) loader=' + hx(this.l) + ' done'); });
    hook(OFF.loaderClear, 'loaderClear', function (args) { log('loaderClear this=' + hx(args[0])); },
      function () { log('loaderClear done'); });
    let mgrAddN = 0;
    hook(OFF.mgrAdd, 'mgrAdd(0x15a27b4)',
      function (args) {
        const a = stdstr(args[1]), b = stdstr(args[2]);
        if (mgrAddN < 5 || a.indexOf('item_') >= 0 || b.indexOf('item_') >= 0 || a.indexOf('spd_bn') >= 0 || b.indexOf('spd_bn') >= 0 || a.indexOf('common') >= 0 || b.indexOf('common') >= 0) {
          log('mgrAdd("' + a + '","' + b + '")');
        }
        mgrAddN++;
      });
    // 4) 봉인의 방 흐름
    function sceneHook(off, name) {
      hook(off, name, function () { log(name + ' enter this=' + hx(this.context.x0)); },
        function () { log(name + ' leave'); });
    }
    hook(OFF.sealLoadFiles, 'loadFiles', function () { armed = true; log('SealAreaListScene::loadFiles enter (logging armed)'); }, function () { log('SealAreaListScene::loadFiles leave'); });
    sceneHook(OFF.sealBack, 'SealAreaListScene::backScene');
    sceneHook(OFF.sealInvisible, 'SealAreaListScene::onSceneInvisible');
    sceneHook(OFF.sealDtor, 'SealAreaListScene::~SealAreaListScene');

    // 5) isExist(아이콘) 경로
    hook(OFF.isExistWrap, 'isExistWrap',
      function (args) { this.l = args[0]; this.s = stdstr(args[1]); },
      function (r) { log('isExistWrap loader=' + hx(this.l) + ' name="' + this.s + '" -> ' + r.toInt32()); });
    // 0x15a2874가 std::string을 c_str로 바꿔 0x15ddafc(loader, char const*)로 꼬리호출한다.
    hook(OFF.isExist, 'CriFileLoader::isExist', function (args) { this.s = cstr(args[1]); },
      function (r) { log('isExist path="' + this.s + '" -> ' + r.toInt32()); });

    // 6) 크래시 직전 null child 확인
    hook(OFF.addChildHelper, 'addChildHelper',
      function (args) {
        const child = args[1];
        if (child.isNull()) {
          log('NULL CHILD addChildHelper parent=' + hx(args[0]) + ' lr=' + hx(this.returnAddress));
          try { log('  bt: ' + Thread.backtrace(this.context, Backtracer.ACCURATE).map(function (a) { return DebugSymbol.fromAddress(a).toString(); }).join(' | ')); } catch (e) {}
        }
      });
    hook(OFF.addChild1, 'addChild(Node*)', function (args) {
      if (args[1].isNull()) log('NULL CHILD addChild(Node*) parent=' + hx(args[0]) + ' lr=' + hx(this.returnAddress));
    });

    log('trace2 hooks=' + n + ' base=' + hx(m.base));
  }, 50);
})();
