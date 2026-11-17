// jp_hide_lump.js — hide 「데이터 일괄 다운로드」 in the menu (2026-11-10).
//
// The menu (MenuTopScene, below 훈장) has a button that opens LumpDownloadCheckScene and sends
// ResourceAllDownloadRequest. Every resource is already on the device, so it is useless here (the user asked to hide
// it). MenuTopScene::setLayout builds it with
//   setBtn(batch, batch, 2, 4, "menu_top_lump", "middlebutton_verylong_label_batchdownload.png",
//          "button_middle_verylong1.png", "button_middle_verylong2.png")
// (strings are libc++ std::string passed by reference; the return value is not used). Skip only that call.
(function () {
  const TAG = 'LUMP';
  const NAME = 'menu_top_lump';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  function str(p) {                          // libc++ std::string (short / long form)
    try {
      const b0 = p.readU8();
      if ((b0 & 1) === 0) return p.add(1).readUtf8String(b0 >> 1);
      return p.add(16).readPointer().readUtf8String(p.add(8).readU64().toNumber());
    } catch (e) { return null; }
  }
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    const sym = '_ZN12MenuTopScene6setBtnEPN7cocos2d15SpriteBatchNodeES2_iiNSt6__ndk112basic_stringIcNS3_11char_traitsIcEENS3_9allocatorIcEEEES9_S9_S9_';
    const p = m.findExportByName(sym);
    if (!p) { log('missing MenuTopScene::setBtn'); return; }
    const orig = new NativeFunction(p, 'void', ['pointer', 'pointer', 'pointer', 'int', 'int', 'pointer', 'pointer', 'pointer', 'pointer']);
    Interceptor.replace(p, new NativeCallback(function (self, b1, b2, x, y, s1, s2, s3, s4) {
      if (str(s1) === NAME) { log('hidden ' + NAME); return; }
      orig(self, b1, b2, x, y, s1, s2, s3, s4);
    }, 'void', ['pointer', 'pointer', 'pointer', 'int', 'int', 'pointer', 'pointer', 'pointer', 'pointer']));
    log('hook installed');
  }, 50);
})();
