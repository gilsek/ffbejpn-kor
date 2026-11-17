// JP summon season chooser: the summon-only part of the Global Offline exvius/summon_menu.js (+ native_bridge.js),
// ported to JP 11.0.0 (every symbol below verified in the JP libgame.so export table, 2026-11-08).
// A button in the summon header opens a list of the engine's archive groups (standard, season1-5, collab);
// choosing one asks LocalGameBridge.summonArchive(<group>) (engine: android_game.summon_archive ->
// gacha_archive.menu, which stores the choice) and re-opens the summon list so the engine serves that group.
// Device script = cat jp_summon_menu.js jp_offline.js > build/out/jp_offline/frida_script.js (pushed to /data/local/tmp).
// ---- JNI bridge to com.exvius.local.LocalGameBridge (Global native_bridge.js); shared with jp_title_menu.js ----
// Static String methods only: bridge('summonArchive', '(Ljava/lang/String;)Ljava/lang/String;', ['season1']).
function makeLocalBridge(m) {
  const methodInfo = new NativeFunction(m.getExportByName('_ZN7cocos2d9JniHelper19getStaticMethodInfoERNS_14JniMethodInfo_EPKcS4_S4_'),
    'bool', ['pointer', 'pointer', 'pointer', 'pointer'], {exceptions: 'propagate'});
  const className = Memory.allocUtf8String('com/exvius/local/LocalGameBridge');
  return function bridge(method, signature, args) {
    const info = Memory.alloc(Process.pointerSize * 3);
    if (!methodInfo(info, className, Memory.allocUtf8String(method), Memory.allocUtf8String(signature)))
      throw new Error('Local method is unavailable: ' + method);
    const env = info.readPointer(), cls = info.add(Process.pointerSize).readPointer();
    const methodId = info.add(Process.pointerSize * 2).readPointer(), table = env.readPointer();
    const jni = (i, t, p) => new NativeFunction(table.add(i * Process.pointerSize).readPointer(), t, p, {exceptions: 'propagate'});
    const newString = jni(167, 'pointer', ['pointer', 'pointer']), invoke = jni(116, 'pointer', ['pointer', 'pointer', 'pointer', 'pointer']);
    const getChars = jni(169, 'pointer', ['pointer', 'pointer', 'pointer']), releaseChars = jni(170, 'void', ['pointer', 'pointer', 'pointer']);
    const deleteRef = jni(23, 'void', ['pointer', 'pointer']), hasException = jni(228, 'bool', ['pointer']), clearException = jni(17, 'void', ['pointer']);
    const refs = [cls], values = Memory.alloc(Math.max(8, args.length * 8));
    let output = ptr(0), text = ptr(0);
    const check = () => { if (hasException(env)) { clearException(env); throw new Error('Local method failed: ' + method); } };
    try {
      args.forEach((v, i) => { const s = newString(env, Memory.allocUtf8String(v)); check(); refs.push(s); values.add(i * 8).writePointer(s); });
      output = invoke(env, cls, methodId, values); check();
      if (output.isNull()) throw new Error('Local method returned no text');
      refs.push(output); text = getChars(env, output, ptr(0)); check();
      return text.readUtf8String();
    } finally {
      if (!text.isNull()) releaseChars(env, output, text);
      for (const r of refs.reverse()) if (!r.isNull()) deleteRef(env, r);
    }
  };
}

function installJpSummonMenu(m, note) {
  const exp = n => m.getExportByName(n);
  const fn = (n, r, a) => new NativeFunction(exp(n), r, a, {exceptions: 'propagate'});
  const strType = 'RKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE';
  const bridge = makeLocalBridge(m);
  const bannerNames = {};
  const readMenu = (selection = '') => {
    const result = JSON.parse(bridge('summonArchive', '(Ljava/lang/String;)Ljava/lang/String;', [selection]));
    Object.assign(bannerNames, result.names || {});
    return result;
  };

  // ---- drawing (Global summon_menu.js) ----
  const makeSprite = fn('_ZN16GameScale9Sprite25createWithSpriteFrameNameE' + strType + 'RKN7cocos2d4RectE', 'pointer', ['pointer', 'pointer']);
  const spriteSize = fn('_ZN16GameScale9Sprite7setSizeEff', 'void', ['pointer', 'float', 'float']);
  const setPosition = fn('_ZN7cocos2d4Node11setPositionEff', 'void', ['pointer', 'float', 'float']);
  const setAnchor = fn('_ZN7cocos2d4Node14setAnchorPointERKNS_4Vec2E', 'void', ['pointer', 'pointer']);
  const frameCache = fn('_ZN7cocos2d16SpriteFrameCache11getInstanceEv', 'pointer', []);
  const findFrame = fn('_ZN7cocos2d16SpriteFrameCache20getSpriteFrameByNameERKNSt6__ndk112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE', 'pointer', ['pointer', 'pointer']);
  const makeLabel = fn('_ZN9GameScene14setStringLabelEi' + strType + 'ffRKN7cocos2d7Color3BEiii', 'pointer',
    ['pointer', 'int', 'pointer', 'float', 'float', 'pointer', 'int', 'int', 'int']);
  const layer = fn('_ZN9GameLayer6sharedEv', 'pointer', []);
  const addChild = fn('_ZN9GameLayer8addChildEiiPN7cocos2d4NodeE', 'void', ['pointer', 'int', 'int', 'pointer']);
  const removeChild = fn('_ZN9GameLayer11removeChildEiPN7cocos2d4NodeE', 'void', ['pointer', 'int', 'pointer']);
  const touchEnabled = fn('_ZN9GameScene13isTouchEnableEv', 'bool', ['pointer']);
  const sceneState = fn('_ZNK13GachaTopScene13getSceneStateEv', 'int', ['pointer']);
  const setTab = fn('_ZN13GachaTopScene6setTabENS_9GACHA_TABE', 'void', ['pointer', 'int']);
  const scrollPosition = fn('_ZN9LayerUtil13setScrollPosYEiiii', 'void', ['int', 'int', 'int', 'int']);
  const refresh = fn('_ZN9GameScene24onCheckTouchFooterSummonEv', 'void', ['pointer']);
  const width = fn('_ZN11CommonUtils11getWinWidthEv', 'int', []), height = fn('_ZN11CommonUtils12getWinHeightEv', 'int', []);
  const rectangle = fn('_ZN12GraphicUtils8fillRectEiffffRKN7cocos2d7Color3BEiib', 'pointer',
    ['int', 'float', 'float', 'float', 'float', 'pointer', 'int', 'int', 'bool']);
  const color = (r, g, b) => Memory.alloc(3).writeByteArray([r, g, b]);
  const white = color(255, 255, 255), black = color(0, 0, 0);
  const popupBackground = color(0, 17, 38), popupBorder = color(90, 135, 180), popupSelected = color(22, 64, 105);
  const caps = Memory.alloc(16).writeByteArray(new Uint8Array(16));
  const centre = Memory.alloc(8); centre.writeFloat(0.5); centre.add(4).writeFloat(0.5);
  const scenes = new Map(), layerId = 101, z = 29000, rowH = 34;
  // Header row (戻る / 召喚): the empty right side. Design units, y from the top.
  const headerX = () => width() - 110, headerY = () => 188, headerW = 200, headerH = 50;
  // JP draws these nodes lower than the touch point's design y (TB373FU, run32 screenshots vs adb taps):
  // sprites/labels ~+48, GraphicUtils::fillRect boxes ~+35 design units. Hit boxes follow what is drawn.
  const DY_SPRITE = 48, DY_RECT = 35;
  let skin;
  function withString(value, action) {
    const length = Array.from(value).reduce((n, c) => n + (c.codePointAt(0) < 128 ? 1 : c.codePointAt(0) < 2048 ? 2 : c.codePointAt(0) < 65536 ? 3 : 4), 0);
    const s = Memory.alloc(24); s.writeByteArray(new Uint8Array(24));
    let buffer;
    if (length <= 22) { s.writeU8(length * 2); s.add(1).writeUtf8String(value); }
    else {
      const capacity = Math.ceil((length + 1) / 16) * 16; buffer = Memory.alloc(capacity); buffer.writeUtf8String(value);
      s.writeU64(capacity | 1); s.add(8).writeU64(length); s.add(16).writePointer(buffer);
    }
    const r = action(s); if (buffer) buffer.isNull(); return r;
  }
  // Unlike GL's MST_GACHA_NAME TextManager lookup, JP initSubHeader copies GachaMst+0x28
  // directly (0x1ad468c..0x1ad4698). Frida HEADER trace: id=9, name="". Populate that
  // owned C++ string using its setter; the same name is then available to the confirm dialog.
  const gachaId = fn('_ZNK8GachaMst10getGachaIdEv', 'int', ['pointer']);
  const detailName = fn('_ZNK14GachaDetailMst12getGachaNameEv', 'pointer', ['pointer']);
  const setGachaName = fn('_ZN8GachaMst12setGachaNameENSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE',
    'void', ['pointer', 'pointer']);
  for (const [symbol, masterOffset, detailOffset] of [
    ['_ZN19GachaPayDetailScene13initSubHeaderEv', 0x5a0, 0x5b0],
    // JP setSingleButtonLayout 0x1afb7c0 reads the primary detail at +0x558.
    ['_ZN16GachaDetailScene13initSubHeaderEv', 0x550, 0x558],
    // JP setGachaDate at 0x1aed8d0 stores master/detail at +0x558/+0x560;
    // box initSubHeader at 0x1aed6c0 copies that master's name.
    ['_ZN19GachaBoxDetailScene13initSubHeaderEv', 0x558, 0x560],
    // Ticket confirm popup stores master/detail at +0x548/+0x550.
    ['_ZN23GachaTicketConfirmScene13initSubHeaderEv', 0x548, 0x550]
  ]) Interceptor.attach(exp(symbol), {
    onEnter(a) {
      try {
        const mst = a[0].add(masterOffset).readPointer();
        if (mst.isNull()) return;
        const id = String(gachaId(mst));
        let detail = a[0].add(detailOffset).readPointer();
        if (detail.isNull()) detail = a[0].add(detailOffset + 8).readPointer();
        // The engine already sends G4L0YIB2 on the DETAIL row. GL's missing-text list
        // omits shipped GL ids such as 9, even though JP has no corresponding text.
        let name = detail.isNull() ? '' : rstr(detailName(detail));
        if (!name) { if (!bannerNames[id]) readMenu(''); name = bannerNames[id]; }
        if (!name) { note('JP_GACHA_TITLE_MISSING id=' + id); return; }
        withString(name, s => setGachaName(mst, s));
        note('JP_GACHA_TITLE id=' + id + ' name=' + name);
      } catch (e) { note('JP_GACHA_TITLE_ERROR ' + e); }
    }
  });
  // Mark TagString::parse calls inside the narrow subheader bar so jp_talk_wrap fits long titles onto one line.
  const titleCallbacks = [];
  for (const cls of ['19GachaPayDetailScene', '16GachaDetailScene', '17GachaConfirmScene', '23GachaTicketConfirmScene']) {
    let originalTitle;
    const callback = new NativeCallback((scene, title, layerId) => {
      globalThis.__inGachaSubHeader = true;
      try {
        return originalTitle(scene, title, layerId);
      } finally {
        globalThis.__inGachaSubHeader = false;
      }
    }, 'void', ['pointer', 'pointer', 'int']);
    titleCallbacks.push(callback);
    originalTitle = new NativeFunction(Interceptor.replaceFast(exp('_ZN' + cls + '19setSubHeaderUiLabelE' + strType.slice(2) + 'i'), callback),
      'void', ['pointer', 'pointer', 'int']);
  }
  function label(ui, key, text, x, y, size = 18, depth = z + 4) {
    const prev = ui.labels.get(key); if (prev) removeChild(layer(), layerId, prev);
    if (!text) { ui.labels.delete(key); return; }
    ui.labels.set(key, withString(text, s => makeLabel(ui.scene, layerId, s, x, y, white, 1, size, depth)));
  }
  function chooseSkin() {
    const loaded = ['tab_off.png', 'common_tab_bg.png', 'sort_btn_mini_1.png', 'sort_btn5_1.png', 'common_btn_mini_oldui_off.png',
      'common_btn_gdsquare_blue.png', 'common_btn_gdsquare_off.png', 'gacha_tab_free_1.png', 'common_tab_bg_black.png']
      .filter(n => !withString(n, s => findFrame(frameCache(), s)).isNull());
    note('JP_SUMMON_GROUP_SKINS ' + loaded.join(','));
    return loaded[0] || null;
  }
  function panel(ui, x, y, w, h, depth) {
    let node;
    if (skin) {
      node = withString(skin, s => makeSprite(s, caps));
      spriteSize(node, w, h); setAnchor(node, centre); setPosition(node, x, height() - y); addChild(layer(), layerId, depth, node);
    } else node = rectangle(layerId, x - w / 2, y - h / 2, w, h, black, depth, 220, 0);
    ui.nodes.push(node); return {x, y, w, h};
  }
  const hit = (b, p) => b && Math.abs(p.x - b.x) <= b.w / 2 && Math.abs(p.y - b.y) <= b.h / 2;
  const touchPoint = t => ({x: t.add(0x34).readFloat(), y: t.add(0x38).readFloat()});   // cocos2d::Touch::_point
  function clear(ui) {
    for (const n of ui.nodes) removeChild(layer(), layerId, n);
    ui.nodes = []; for (const k of Array.from(ui.labels.keys())) label(ui, k, '', 0, 0);
  }
  function drawHeader(ui) {
    ui.header = panel(ui, headerX(), headerY(), headerW, headerH, z + 5);
    ui.header = {x: ui.header.x, y: ui.header.y + DY_SPRITE, w: ui.header.w + 20, h: ui.header.h + 30};
    label(ui, 'header', ui.menu.selected.label + '  ▼', headerX() - headerW / 2 + 16, headerY(), 20, z + 6);
  }
  function close(ui) { ui.open = false; ui.rows = []; clear(ui); drawHeader(ui); }
  function open(ui) {
    clear(ui); ui.open = true;
    ui.nodes.push(rectangle(layerId, 0, 0, width(), height(), black, z, 150, 0));
    drawHeader(ui);
    const left = headerX() - headerW / 2, top = headerY() + headerH / 2, listH = ui.menu.groups.length * rowH;
    ui.nodes.push(rectangle(layerId, left - 1, top - 1, headerW + 2, listH + 2, popupBorder, z + 2, 255, 0));
    ui.nodes.push(rectangle(layerId, left, top, headerW, listH, popupBackground, z + 3, 255, 0));
    ui.rows = ui.menu.groups.map((g, i) => {
      const y = top + rowH * (i + 0.5);
      if (g.id === ui.menu.selected.id) ui.nodes.push(rectangle(layerId, left, top + rowH * i, headerW, rowH, popupSelected, z + 3, 255, 0));
      label(ui, 'choice' + i, (g.id === ui.menu.selected.id ? '▶ ' : '') + g.label + ' (' + g.count + ')', left + 12, y - 12, 17);
      return {box: {x: headerX(), y: y + DY_RECT, w: headerW, h: rowH}, group: g};
    });
  }
  function choose(ui, group) {
    ui.menu = readMenu(group.id);
    close(ui);
    setTab(ui.scene, 0);                       // JP: every lapis banner is on the pay tab (有料召喚)
    for (let tab = 0; tab < 3; tab++) scrollPosition(700, tab, 0, 0);
    refresh(ui.scene);                         // the original summon entry request reloads the chosen group
    note('JP_SUMMON_GROUP_SELECTED ' + group.id);
  }
  Interceptor.attach(exp('_ZN13GachaTopScene13initSubHeaderEv'), {
    onLeave() {
      try {
        if (Object.keys(bannerNames).length === 0) {
          const menu = readMenu('');
          note('JP_SUMMON_3TAB_READY count=' + Object.keys(bannerNames).length + ' win=' + width() + 'x' + height() + ' selected=' + menu.selected.id);
        }
      } catch (e) { note('JP_SUMMON_GROUP_ERROR ' + e.stack); }
    }
  });
  // ---- modal touches (Global summon_menu.js: claim the gesture before GameScene dispatches it) ----
  const claims = (scene, touch) => { const ui = scenes.get(scene.toString()); return ui && (ui.open || hit(ui.header, touchPoint(touch))) ? ui : null; };
  const owned = new Map(), tk = (s, t) => s.toString() + ':' + t.toString();
  const stopTouch = e => { if (!e.isNull()) e.add(0x28).writeU8(1); };     // cocos2d::Event::_isStopped
  let touchEnded, touchBegan, touchMoved, touchCancelled;
  const endGesture = (scene, touch, event) => {
    const g = owned.get(tk(scene, touch)); if (!g) return touchEnded(scene, touch, event);
    stopTouch(event); if (g.ended) return 1; g.ended = true;
    const ui = scenes.get(scene.toString()); if (!ui || !touchEnabled(scene) || sceneState(scene) !== 2) return 1;
    try {
      const p = touchPoint(touch);
      if (!ui.open && hit(ui.header, p)) { ui.menu = readMenu(''); open(ui); }
      else if (ui.open) { const row = ui.rows.find(r => hit(r.box, p)); if (row) choose(ui, row.group); else close(ui); }
    } catch (e) { note('JP_SUMMON_GROUP_ERROR ' + e); close(ui); }
    return 1;
  };
  const claimGesture = (scene, touch, event) => {
    owned.delete(tk(scene, touch));
    try { if (claims(scene, touch)) { owned.set(tk(scene, touch), {ended: false}); stopTouch(event); return true; } }
    catch (e) { note('JP_SUMMON_GROUP_ERROR ' + e); }
    return false;
  };
  const sig = ['pointer', 'pointer', 'pointer'];
  const keep = [];
  const replace = (name, cb, ret) => { const c = new NativeCallback(cb, ret, sig); keep.push(c);
    return new NativeFunction(Interceptor.replaceFast(exp(name), c), ret, sig, {exceptions: 'propagate'}); };
  touchEnded = replace('_ZN9GameScene12onTouchEndedEPN7cocos2d5TouchEPNS0_5EventE', endGesture, 'bool');
  touchBegan = replace('_ZN9GameScene12onTouchBeganEPN7cocos2d5TouchEPNS0_5EventE',
    (s, t, e) => claimGesture(s, t, e) ? 1 : touchBegan(s, t, e), 'bool');
  touchMoved = replace('_ZN9GameScene12onTouchMovedEPN7cocos2d5TouchEPNS0_5EventE',
    (s, t, e) => { if (owned.has(tk(s, t))) { stopTouch(e); return 1; } return touchMoved(s, t, e); }, 'bool');
  touchCancelled = replace('_ZN9GameScene16onTouchCancelledEPN7cocos2d5TouchEPNS0_5EventE',
    (s, t, e) => { if (owned.has(tk(s, t))) { owned.delete(tk(s, t)); stopTouch(e); return; } touchCancelled(s, t, e); }, 'void');
  const vectorSuffix = 'ERKNSt6__ndk16vectorIPN7cocos2d5TouchENS0_9allocatorIS4_EEEEPNS2_5EventE';
  const vectorTouches = v => { const f = v.readPointer(), l = v.add(8).readPointer(), n = l.sub(f).toInt32();
    if (n < 0 || n > 128 || n % 8) return []; const out = []; for (let o = 0; o < n; o += 8) out.push(f.add(o).readPointer()); return out; };
  for (const [method, phase] of [['onTouchesBegan', 'begin'], ['onTouchesMoved', 'move'], ['onTouchesEnded', 'end']]) {
    let original;
    const cb = new NativeCallback((scene, vector, event) => {
      const touches = vectorTouches(vector);
      if (phase === 'begin') { let c = false; for (const t of touches) c = claimGesture(scene, t, event) || c; if (c) return; }
      else { const mine = touches.filter(t => owned.has(tk(scene, t)));
        if (mine.length) { stopTouch(event); if (phase === 'end') for (const t of mine) endGesture(scene, t, event); return; } }
      original(scene, vector, event);
    }, 'void', sig);
    keep.push(cb);
    original = new NativeFunction(Interceptor.replaceFast(exp('_ZN9GameScene14' + method + vectorSuffix), cb), 'void', sig, {exceptions: 'propagate'});
  }
  Interceptor.attach(exp('_ZN13GachaTopScene16onSceneInvisibleEv'), { onEnter(a) {
    const key = a[0].toString(), ui = scenes.get(key);
    for (const g of owned.keys()) if (g.startsWith(key + ':')) owned.delete(g);
    if (ui) { clear(ui); scenes.delete(key); }
  } });
  Interceptor.attach(exp('_ZN13GachaTopSceneD1Ev'), { onEnter(a) { scenes.delete(a[0].toString()); } });
  globalThis.__jpSummonMenuKeep = keep;
  note('JP_SUMMON_MENU_READY');
}
