// jp_profile_hangul.js — let Hangul through the profile name/comment filter (2026-11-11).
//
// TextInputUtils::filterText keeps a 3-byte UTF-8 char only when its lead byte passes
// `(lead + 0x1c) & 0xff < 6`, i.e. 0xE4..0xE9 (CJK kanji). Hangul syllables U+AC00..U+D7A3 use
// leads 0xEA..0xED, so typed Korean was silently dropped and UpdateUserInfoRequest carried only the
// gift id (device log: {"MZzST52W":[{"Utx8P1Qo":"10"}]}). Widen the range to 0xE4..0xED.
(function () {
  const TAG = 'HANGUL';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  // libgame.so sha256 54ef0fe9a5c160254654a741bd8a3791e83bac80f7ece8c806af589e8fa1184e (JP 11.0.0 arm64)
  const ANCHOR = ['_ZN14TextInputUtils10filterTextENSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEiNS_9TEXT_MODEE', 0x14c3b74];
  const PATCH = [[0x14c3ef4, 0x7100193f, 0x7100293f]];   // cmp w9,#6 -> cmp w9,#10
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    const a = m.findExportByName(ANCHOR[0]);
    if (!a || !a.equals(m.base.add(ANCHOR[1]))) { log('anchor mismatch, not patched'); return; }
    for (const [o, before] of PATCH) {
      const v = m.base.add(o).readU32();
      if (v !== before) { log('unexpected code at 0x' + o.toString(16) + ': 0x' + v.toString(16) + ', not patched'); return; }
    }
    for (const [o, , after] of PATCH) {
      Memory.patchCode(m.base.add(o), 4, (code) => { code.writeU32(after); });
    }
    log('filterText hangul range patched');
  }, 50);
})();
