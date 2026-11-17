// jp_lb_index.js — limit burst level index count to 4 bytes (2026-11-10).
//
// files/0EvyjKh8.i (index of F_LIMITBURST_LV_MST) was rebuilt on every launch (~20 s from Ver1001_0EvyjKh8.dat).
// The index is: u32 0xFFBE0000, u32 version, u16 count, count x 16-byte entries, u32 0xFFBE.
// F_LIMITBURST_LV_MST has 96,776 rows, so the u16 count wraps to 31,240, the reader stops early, finds entry bytes
// where the trailer should be, the check fails and the index is rebuilt.
// SeekableMstCacheList<pair<int,int>, LimitBurstLvMst> body reader (vtable+0x78, 0x1c5caac) and writer
// (vtable+0x80, 0x1c5cbf4) are used only by LimitBurstLvMstList vtables; switch both to a u32 count.
// The old u16 index fails the check once and is rewritten in the new form.
(function () {
  const TAG = 'LBINDEX';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  // libgame.so sha256 54ef0fe9a5c160254654a741bd8a3791e83bac80f7ece8c806af589e8fa1184e (JP 11.0.0 arm64)
  const ANCHOR = ['_ZN19LimitBurstLvMstList10getMstNameEv', 0x1c5c54c];
  const PATCH = [            // [offset, original, new]
    [0x1c5cadc, 0x52800042, 0x52800082],   // read:  mov w2,#2           -> mov w2,#4
    [0x1c5cae8, 0x79002bff, 0xb90017ff],   //        strh wzr,[sp,#0x14] -> str wzr,[sp,#0x14]
    [0x1c5caf8, 0xf100091f, 0xf100111f],   //        cmp x8,#2           -> cmp x8,#4
    [0x1c5cb00, 0x79402be8, 0xb94017e8],   //        ldrh w8,[sp,#0x14]  -> ldr w8,[sp,#0x14]
    [0x1c5cba8, 0x79402be8, 0xb94017e8],   //        ldrh w8,[sp,#0x14]  -> ldr w8,[sp,#0x14]
    [0x1c5cbb0, 0x6b38211f, 0x6b18011f],   //        cmp w8,w24,uxth     -> cmp w8,w24
    [0x1c5cc24, 0x52800042, 0x52800082],   // write: mov w2,#2           -> mov w2,#4
    [0x1c5cc30, 0x79000be8, 0xb90007e8],   //        strh w8,[sp,#4]     -> str w8,[sp,#4]
  ];
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
    log('u32 count patched (' + PATCH.length + ')');
  }, 50);
})();
