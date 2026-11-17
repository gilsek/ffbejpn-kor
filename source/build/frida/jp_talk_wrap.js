// jp_talk_wrap.js — auto line break: 26 characters per old 24-character width, punctuation not counted (2026-11-14).
//
// TagString::parse (libgame.so) does not measure glyphs. For each UTF-8 character it adds the nominal font size
// (multi-byte: Hangul, kanji, '…') or half of it (1 byte: ASCII, space, '.') to the running line width s12 and
// breaks when s12 > TagString::width (+0x68):
//   0x1542e1c fcsel s13, s9, s8, eq    ; s13 = advance (half if 1 byte)
//   0x1542e20 fadd  s12, s12, s13      ; <- hooked here
//   0x1542e2c fcmp  s12, s0 / b.le     ; break when over the width
// The Korean font was scaled to 0.90 (build/make_ko_font.py SIZE), so the old rule left empty space at line ends.
// Here every advance is multiplied by 24/26 (26 full-width characters fit where 24 did) and punctuation gets 0
// (user request). The width itself is not touched: parse also uses it for centre/right alignment.
// Word wrap (user request): a word that does not fit moves to the next line whole (see the hook body).
// Battle dialogue is pre-split with the same rule in build/ko_line_fit.py (WIDTH 26, punctuation excluded).
// At 0x1542e20: x8 = begin of the per-character std::string vector (24-byte entries), x24 = index, x22 = byte length.
(function () {
  const TAG = 'TEXTWRAP';
  const SCALE = 24 / 26;
  const HOOK_OFF = 0x1542e20;
  const PUNCT = new Set(Array.from('.,!?…‥~～・、。，．！？：；:;\'"“”‘’「」『』()（）[]［］-－—–'));
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  function ch(entry) {                       // libc++ std::string, one UTF-8 character
    const b0 = entry.readU8();
    if ((b0 & 1) === 0) return entry.add(1).readUtf8String(b0 >> 1);
    return entry.add(16).readPointer().readUtf8String(entry.add(8).readU64().toNumber());
  }
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    const parse = m.findExportByName('_ZN9TagString5parseEv');
    const at = m.base.add(HOOK_OFF);
    // guard: the function and the hooked instruction must be the ones this was written against (JP 11.0.0)
    let insn = null;
    try { insn = Instruction.parse(at); } catch (e) { }
    if (!parse || !parse.equals(m.base.add(0x15429b8)) || !insn || insn.mnemonic !== 'fadd' ||
        insn.opStr.replace(/\s/g, '') !== 's12,s12,s13') {
      log('layout differs, not installed (' + (insn ? insn.mnemonic + ' ' + insn.opStr : 'no insn') + ')');
      return;
    }
    let errors = 0, wrapped = 0, fitted = 0, fitBegin = null, fitScale = 1;
    const NAME_WIDTH = 315;
    function info(entry) {                   // [text, byte length]
      const b0 = entry.readU8();
      if ((b0 & 1) === 0) return [entry.add(1).readUtf8String(b0 >> 1), b0 >> 1];
      const n = entry.add(8).readU64().toNumber();
      return [entry.add(16).readPointer().readUtf8String(n), n];
    }
    function advance(t, n, full, half) {     // adjusted advance of one character
      if (PUNCT.has(t)) return 0;
      return (n === 1 ? half : full) * SCALE;
    }
    Interceptor.attach(at, function () {
      const c = this.context;
      try {
        const adv = c.s13;
        if (typeof adv !== 'number' || !(adv > 0)) return;
        const begin = c.x8, i = c.x24.toUInt32();
        const [t, n] = info(begin.add(i * 24));
        const full = c.s8, half = c.s9;
        const a = advance(t, n, full, half);
        c.s13 = a;
        // Summon field unit name or detail/confirm subheader: stay on 1 line and squeeze width instead of wrapping.
        if (i === 0) {
          fitBegin = null;
          if (Math.abs(c.s0 - NAME_WIDTH) < 0.5 || globalThis.__inGachaSubHeader) {
            const cnt = c.sp.add(0xa0).readPointer().sub(begin).toUInt32() / 24;
            let tot = 0, nl = false;
            for (let j = 0; j < cnt; j++) {
              const [tj, nj] = info(begin.add(j * 24));
              if (tj === '<' || tj === String.fromCharCode(10)) { nl = true; break; }
              tot += advance(tj, nj, full, half);
            }
            if (!nl && tot > c.s0) {
              fitBegin = begin.toString(); fitScale = (c.s0 / tot) * 0.995;
              if (fitted++ < 5) log('name fit width ' + c.s0 + ' text ' + tot.toFixed(1));
            }
          }
        }
        if (fitBegin !== null && begin.toString() === fitBegin) { c.s13 = a * fitScale; return; }
        // word wrap: at the first character of a word (previous character is a space), measure the whole word;
        // if it does not fit on this line, break here. Forcing s12 to the width makes s12 + s13 exceed it; the
        // engine then inserts <br> before this character and starts the new line at s13 (the real advance).
        const s12 = c.s12, width = c.s0;
        if (i === 0 || t === ' ' || !(s12 > 0) || !(width > 0)) return;
        if (info(begin.add((i - 1) * 24))[0] !== ' ') return;
        const end = c.sp.add(0xa0).readPointer();
        const count = end.sub(begin).toUInt32() / 24;
        let w = a;
        for (let j = i + 1; j < count && s12 + w <= width; j++) {
          const [tj, nj] = info(begin.add(j * 24));
          if (tj === ' ' || tj === '<' || tj === String.fromCharCode(10)) break;
          w += advance(tj, nj, full, half);
        }
        if (s12 + w > width && w <= width) {
          c.s12 = width + 0.01;
          if (wrapped++ < 2) log('word wrap at ' + JSON.stringify(t) + ' line ' + s12.toFixed(1) + ' word ' + w.toFixed(1) + ' width ' + width);
        }
      } catch (e) {
        if (errors++ < 3) log('error ' + e);
      }
    });
    log('hook installed scale=' + SCALE.toFixed(4));

    // Separate UI font (TT_RodinCattleya-B.ttf = NotoSansKR UI) vs Script/Talk font (FOT-SkipStd-E.otf = Binggrae).
    const uiFont = m.base.add(0x25704b7);
    const scriptFont = m.base.add(0x257f7db);
    const slInit = m.findExportByName('_ZN11StringLabel4initEiPKcffffRKN7cocos2d7Color3BEiS1_i');
    const clCreate = m.findExportByName('_ZN14CustomLabelTTF6createEiRKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEPKcfRKN7cocos2d4RectEi');
    let okRoute = false;
    try {
      okRoute = uiFont.readUtf8String() === 'font/TT_RodinCattleya-B.ttf' &&
                scriptFont.readUtf8String() === 'font/FOT-SkipStd-E.otf' &&
                slInit && slInit.equals(m.base.add(0x15ba654)) &&
                clCreate && clCreate.equals(m.base.add(0x15bb018));
    } catch (e) { okRoute = false; }
    if (!okRoute) {
      log('FONTROUTE layout differs, not installed');
      return;
    }
    let scriptDepth = 0;
    const scriptOffs = [
      0x155e680, // MapScriptManager::initialize
      0x155ed70, // MapScriptManager::initializeForStorySummary
      0x155f35c, // MapScriptManager::createShowTextListForStorySummary
      0x155f9d8, // MapScriptManager::initializeChoice
      0x155fd1c, // MapScriptManager::proc
      0x1561458, // MapScriptManager::procChoice
      0x1561b80, // MapScriptManager::changeText
      0x1562368, // MapScriptManager::remakeSummaryForNextPage
      0x1620af8, // BattleScene::setTalkWindow
      0x1a5507c, // StoreMessageWindow::initialize
      0x1a55438, // StoreMessageWindow::changeString
    ];
    for (const off of scriptOffs) {
      Interceptor.attach(m.base.add(off), {
        onEnter() { scriptDepth++; },
        onLeave() { if (scriptDepth > 0) scriptDepth--; },
      });
    }
    Interceptor.attach(slInit, {
      onEnter() { this.context.x4 = scriptDepth > 0 ? scriptFont : uiFont; },
    });
    Interceptor.attach(clCreate, {
      onEnter() { this.context.x2 = scriptDepth > 0 ? scriptFont : uiFont; },
    });

    // Align and style the dynamic "<frame>프레임 간격" repeat button label to match adjacent sprite buttons.
    const createSLL = m.findExportByName('_ZN11LayoutUtils21createStringLabelListEiRKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEffffPKcRKN7cocos2d7Color3BEiiibibi');
    const addObjSLL = m.findExportByName('_ZN15StringLabelList9addObjectEP11StringLabel');
    const enableOutline = m.findExportByName('_ZN7cocos2d5Label13enableOutlineERKNS_7Color4BEi');
    if (createSLL && createSLL.equals(m.base.add(0x1548aa8)) &&
        addObjSLL && addObjSLL.equals(m.base.add(0x14c47c0)) &&
        enableOutline && enableOutline.equals(m.base.add(0x21143d8))) {
      const callEnableOutline = new NativeFunction(enableOutline, 'void', ['pointer', 'pointer', 'int']);
      const outlineColor = Memory.alloc(4);
      outlineColor.writeByteArray([8, 18, 36, 255]);
      const repeatBtnLists = new Set();
      let repeatBtnDepth = 0;
      let loggedRepeat = false;
      Interceptor.attach(createSLL, {
        onEnter() {
          const callerOff = this.returnAddress.sub(m.base).toUInt32();
          this._isRepeatBtn = (callerOff === 0x1bace4c || callerOff === 0x16c38e8);
          if (!this._isRepeatBtn) return;
          repeatBtnDepth++;
          this.context.x5 = ptr(22);
          if (typeof this.context.s1 === 'number') this.context.s1 = this.context.s1 + 1.5;
        },
        onLeave(retval) {
          if (this._isRepeatBtn) {
            if (repeatBtnDepth > 0) repeatBtnDepth--;
            if (!retval.isNull()) {
              repeatBtnLists.add(retval.toString());
              if (!loggedRepeat) {
                loggedRepeat = true;
                log('REPEATBTN styled list=' + retval);
              }
            }
          } else if (!retval.isNull()) {
            repeatBtnLists.delete(retval.toString());
          }
        },
      });
      Interceptor.attach(addObjSLL, {
        onEnter() {
          const listPtr = this.context.x0;
          if (repeatBtnDepth > 0 || repeatBtnLists.has(listPtr.toString())) {
            listPtr.add(0x324).writeU8(0);
            callEnableOutline(this.context.x1, outlineColor, 2);
          }
        },
      });
      log('REPEATBTN hook installed');
    } else {
      log('REPEATBTN layout differs, not installed');
    }
    log('FONTROUTE installed (UI=NotoSansKR, Script=Binggrae)');
  }, 50);
})();
