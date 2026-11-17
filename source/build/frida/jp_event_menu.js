// JP 次元の狭間 (Vortex / GateScene) season chooser — the JP port of the archive picker in the Global
// exvius/summon_menu.js (event part). A box in the gate sub-header shows the chosen season; tapping it drops a
// list of the groups that LocalGameBridge.eventArchive serves, and choosing one stores it and re-requests the
// gate rows so the server's new selection reaches GateScene::setLayoutList.
//
// JP 11.0.0 libgame.so (sha256 54ef0fe9…): GateScene has no setListLayout/setTab/refreshLayout (Global-only),
// so nothing here filters a client array. Instead:
//   * initSubHeader 0x1bdf2e8 / setLayoutSubHeaderArea 0x1bdc980  -> draw and anchor the box
//   * todo: GateScene::setLayoutList 0x1bdd4a8 -> marks the re-request as consumed
//   * refresh = what GateScene::checkRoutineConnect (0x1bdfda8) does: _Znwm(0x30) -> RoutineWorldUpdateRequest
//     ctor (0x1e14db4) -> GameScene::accessPhp (0x1a2c2e8). The engine's own updateEvent (0x1bdf524) rebuilds
//     the list when scene+0x548 == 1 (verified: clearLayoutList -> setLayoutList -> slideInListLayer).
//   * touch: GameScene::onTouchBegan/Ended/onTouches* are already replaced by jp_summon_menu.js, so this script
//     does NOT replace them. It replaces GateScene's own touchBegan/Moved/Ended (reached through the original;
//     a claimed touch skips GateScene's handlers) and GameScene::buttonTouchEnded (untouched by other scripts)
//     so a claimed gesture cannot switch a tab or open a banner underneath the box or the dropdown.
// Device script = python build/deploy_jp_frida.py (concatenates jp_event_menu.js with the other hooks).
// ---- JNI bridge to com.exvius.local.LocalGameBridge (same as jp_summon_menu.js, kept local so this file can
// load on its own) ----
function makeEventBridge(m) {
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

function installJpEventMenu(m, note) {
  if (globalThis.__jpEventMenuInstalled) return;
  globalThis.__jpEventMenuInstalled = true;
  const exp = n => m.getExportByName(n);
  const fn = (n, r, a) => new NativeFunction(exp(n), r, a, {exceptions: 'propagate'});
  const strType = 'RKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE';
  const bridge = makeEventBridge(m);

  // ---- drawing (same helpers as jp_summon_menu.js) ----
  const makeLabel = fn('_ZN9GameScene14setStringLabelEi' + strType + 'ffRKN7cocos2d7Color3BEiii', 'pointer',
    ['pointer', 'int', 'pointer', 'float', 'float', 'pointer', 'int', 'int', 'int']);
  const layer = fn('_ZN9GameLayer6sharedEv', 'pointer', []);
  const addChild = fn('_ZN9GameLayer8addChildEiiPN7cocos2d4NodeE', 'void', ['pointer', 'int', 'int', 'pointer']);
  const removeChild = fn('_ZN9GameLayer11removeChildEiPN7cocos2d4NodeE', 'void', ['pointer', 'int', 'pointer']);
  const touchEnabled = fn('_ZN9GameScene13isTouchEnableEv', 'bool', ['pointer']);
  const width = fn('_ZN11CommonUtils11getWinWidthEv', 'int', []), height = fn('_ZN11CommonUtils12getWinHeightEv', 'int', []);
  const rectangle = fn('_ZN12GraphicUtils8fillRectEiffffRKN7cocos2d7Color3BEiib', 'pointer',
    ['int', 'float', 'float', 'float', 'float', 'pointer', 'int', 'int', 'bool']);
  const color = (r, g, b) => Memory.alloc(3).writeByteArray([r, g, b]);
  const white = color(255, 255, 255), black = color(0, 0, 0);
  const popupBackground = color(0, 17, 38), popupBorder = color(90, 135, 180), popupSelected = color(22, 64, 105);
  const centre = Memory.alloc(8); centre.writeFloat(0.5); centre.add(4).writeFloat(0.5);
  const scenes = new Map(), anchors = new Map(), layerId = 101, z = 29000, rowH = 28;
  // JP renders these nodes lower than the touch point's design y (jp_summon_menu.js measured on TB373FU):
  // sprites/labels ~+48, fillRect boxes ~+35 design units. Hit boxes follow what is drawn.
  const DY_SPRITE = 48, DY_RECT = 35;
  const HEADER_W = 92, HEADER_H = 28, LIST_W = 150;
  // Title bar (gate sub-header) ends ~166 design units left of the seal icon centre; the box sits inside the
  // bar's empty right end, after the '차원의 틈새' title, clear of the icon (TB373FU screenshot 2026-11-12).
  const BAR_END_FROM_ICON = 166;

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
  function label(ui, key, text, x, y, size = 17, depth = z + 6) {
    const prev = ui.labels.get(key); if (prev) removeChild(layer(), layerId, prev);
    if (!text) { ui.labels.delete(key); return; }
    ui.labels.set(key, withString(text, s => makeLabel(ui.scene, layerId, s, x, y, white, 1, size, depth)));
  }
  const hit = (b, p) => b && Math.abs(p.x - b.x) <= b.w / 2 && Math.abs(p.y - b.y) <= b.h / 2;
  const touchPoint = t => ({x: t.add(0x34).readFloat(), y: t.add(0x38).readFloat()});   // cocos2d::Touch::_point
  const stopTouch = e => { if (e.compare(ptr(0x10000)) > 0) e.add(0x28).writeU8(1); };   // skip null/garbage                  // cocos2d::Event::_isStopped
  function clear(ui) {
    for (const n of ui.nodes) removeChild(layer(), layerId, n);
    ui.nodes = []; for (const k of Array.from(ui.labels.keys())) label(ui, k, '', 0, 0);
  }
  // The sub-header anchor is the gate_seal_area_icon layout centre (setLayoutSubHeaderArea). The season box is
  // placed to its LEFT so the seal-room icon stays tappable. Fallback: top-right of the design area.
  function headerBox(ui) {
    const a = anchors.get(ui.key);
    // Right edge stops 6 units left of the seal-room icon (its layout width), so the icon is never covered.
    const cx = a ? a.x - BAR_END_FROM_ICON - 4 - HEADER_W / 2 : width() - 120;
    const cy = a ? a.y - 4 : 80;
    return {x: cx, y: cy, w: HEADER_W, h: HEADER_H};
  }
  function drawHeader(ui) {
    ui.header = headerBox(ui);
    const b = ui.header;
    ui.nodes.push(rectangle(layerId, b.x - b.w / 2, b.y - b.h / 2, b.w, b.h, popupBackground, z + 5, 230, 0));
    // One line, vertically centred on the box (labels draw DY_SPRITE lower, boxes DY_RECT lower).
    label(ui, 'pick', (ui.menu && ui.menu.selected ? ui.menu.selected.label : '시즌 1') + ' ▼',
      b.x - b.w / 2 + 10, b.y - (DY_SPRITE - DY_RECT), 17, z + 6);
    ui.hit = {x: b.x, y: b.y + DY_RECT, w: b.w + 16, h: b.h + 24};
  }
  function readMenu(selection = '') {
    return JSON.parse(bridge('eventArchive', '(Ljava/lang/String;)Ljava/lang/String;', [selection]));
  }
  function close(ui) { ui.open = false; ui.rows = []; clear(ui); drawHeader(ui); }
  function open(ui) {
    clear(ui); ui.open = true;
    ui.nodes.push(rectangle(layerId, 0, 0, width(), height(), black, z, 150, 0));
    drawHeader(ui);
    const b = ui.header, groups = (ui.menu && ui.menu.groups) || [];
    const selectedId = ui.menu && ui.menu.selected ? ui.menu.selected.id : '';
    const left = b.x - b.w / 2, top = b.y + b.h / 2 + 4, listH = Math.max(rowH, groups.length * rowH);
    ui.nodes.push(rectangle(layerId, left - 1, top - 1, LIST_W + 2, listH + 2, popupBorder, z + 2, 255, 0));
    ui.nodes.push(rectangle(layerId, left, top, LIST_W, listH, popupBackground, z + 3, 255, 0));
    ui.rows = groups.map((g, i) => {
      const y = top + rowH * (i + 0.5);
      if (g.id === selectedId) ui.nodes.push(rectangle(layerId, left, top + rowH * i, LIST_W, rowH, popupSelected, z + 3, 255, 0));
      label(ui, 'choice' + i, (g.id === selectedId ? '▶ ' : '') + g.label + ' (' + g.count + ')', left + 10, y - 10, 15);
      return {box: {x: left + LIST_W / 2, y: y + DY_RECT, w: LIST_W, h: rowH + 4}, group: g};
    });
    note('JP_EVENT_MENU_OPEN x=' + b.x + ' y=' + b.y + ' rows=' + groups.length);
  }

  // ---- gate re-request (same calls as GateScene::checkRoutineConnect) ----
  // Resolved lazily: if one of these symbols is missing, the menu and label still work and only the refresh
  // degrades (logged), instead of failing the whole installer.
  let refreshApi = null;
  function api() {
    if (refreshApi) return refreshApi;
    refreshApi = {
      znew: new NativeFunction(Module.getGlobalExportByName('_Znwm'), 'pointer', ['size_t'], {exceptions: 'propagate'}),
      ctor: fn('_ZN25RoutineWorldUpdateRequestC1Ev', 'void', ['pointer']),
      access: fn('_ZN9GameScene9accessPhpEP11RequestData', 'void', ['pointer', 'pointer']),
      update: fn('_ZN9GateScene11updateEventEv', 'void', ['pointer'])
    };
    return refreshApi;
  }
  const pending = new Map();
  function refreshGate(scene) {
    pending.set(scene.toString(), {scene, until: Date.now() + 4000});
    try {
      const f = api(), request = f.znew(0x30);
      f.ctor(request);
      f.access(scene, request);
      note('JP_EVENT_REFRESH_SENT scene=' + scene);
    } catch (e) {
      pending.delete(scene.toString());
      note('JP_EVENT_REFRESH_ERROR ' + e.stack);
    }
  }
  // The response normally flips scene+0x548 and the scene's own update loop rebuilds the list. If no rebuild
  // arrived within 4 s, force the same flag and call updateEvent once (verified state offset/actions above).
  setInterval(() => {
    for (const [key, item] of Array.from(pending.entries())) {
      if (Date.now() < item.until) continue;
      pending.delete(key);
      if (!scenes.has(key)) continue;
      try {
        // Only raise the flag; the scene's own update loop rebuilds on the game thread (calling updateEvent
        // from this timer thread was not thread-safe).
        item.scene.add(0x54c).writeU8(1);
        note('JP_EVENT_REFRESH_FORCED scene=' + key);
      } catch (e) { note('JP_EVENT_REFRESH_FORCE_ERROR ' + e); }
    }
  }, 500);
  // First visit after launch showed an empty list (device trace 2026-11-12): GateScene sets scene+0x548=1 and
  // rebuilds the list (setLayoutList) right after it SENDS the routine request, i.e. from the data it had before
  // the reply; checkConnectResult then stores the reply but never asks for another rebuild. Later visits looked
  // fine only because the first reply was cached by then. Raising the same flag after the reply makes the
  // scene's own update loop (game thread) rebuild from the fresh rows.
  const relistAt = new Map();
  Interceptor.attach(exp('_ZN9GateScene18checkConnectResultEv'), {
    onEnter(a) {
      this.scene = a[0];
      this.wasZero = !this.scene.isNull() && this.scene.add(0x544).readS32() === 0;
    },
    onLeave(ret) {
      // 0x548 only re-runs setLayoutList over the old area array (1 tile on first visit). scene+0x54c (bool)
      // makes the next updateEvent run updateLayoutList -> getInSessionAreaList, i.e. recompute the area
      // array from the fresh rows (first_entry_and_art.md §3.2/§5).
      try {
        if (!this.wasZero || ret.isNull() || ret.toInt32() === 0) return;
        const k = this.scene.toString(), now = Date.now();
        if (now - (relistAt.get(k) || 0) < 1500) return;
        relistAt.set(k, now);
        this.scene.add(0x54c).writeU8(1);
        note('JP_EVENT_RELIST_AFTER_REPLY scene=' + this.scene);
      } catch (e) { note('JP_EVENT_RELIST_ERROR ' + e); }
    }
  });
  // Suppress automatic GateScene / SealAreaListScene routine polling once SpDungeonCondMstList is populated
  // (2026-11-15): GateScene::checkRoutineConnect (0x1bdfda8) runs every frame, sends RoutineWorldUpdateRequest
  // + RoutineEventUpdateRequest back-to-back, and prematurely sets scene+0x54c=1 before the reply arrives,
  // showing an unnecessary loading spinner on entry and tangling slideInListLayer rebuilds.
  try {
    const spCondShared = fn('_ZN20SpDungeonCondMstList6sharedEv', 'pointer', []);
    const refreshWaitPtr = m.findExportByName('_ZN9GateScene13m_refreshWaitE');
    function hasGateRows() {
      try {
        const list = spCondShared();
        if (list.isNull()) return false;
        const arr = list.add(0x30).readPointer();
        return !arr.isNull() && arr.readS32() > 10;
      } catch (e) { return false; }
    }
    const gateRoutineCb = new NativeCallback(function (scene) {
      try {
        if (refreshWaitPtr && !refreshWaitPtr.isNull()) refreshWaitPtr.writeS32(0x7fffffff);
        if (hasGateRows()) return;
        const key = scene.toString();
        if (!pending.has(key)) refreshGate(scene);
      } catch (e) { note('JP_GATE_ROUTINE_SKIP_ERR ' + e); }
    }, 'void', ['pointer']);
    Interceptor.replace(exp('_ZN9GateScene19checkRoutineConnectEv'), gateRoutineCb);
    globalThis.__jpEventMenuRoutineKeep = [gateRoutineCb];
    const sealRoutine = m.findExportByName('_ZN17SealAreaListScene19checkRoutineConnectEv');
    if (sealRoutine) {
      const origSealRoutine = new NativeFunction(sealRoutine, 'void', ['pointer']);
      const sealRoutineCb = new NativeCallback(function (scene) {
        try {
          if (hasGateRows()) return;
          origSealRoutine(scene);
        } catch (e) { note('JP_SEAL_ROUTINE_SKIP_ERR ' + e); }
      }, 'void', ['pointer']);
      Interceptor.replace(sealRoutine, sealRoutineCb);
      globalThis.__jpEventMenuRoutineKeep.push(sealRoutineCb);
    }
    note('JP_GATE_ROUTINE_SUPPRESS ready');
  } catch (e) { note('JP_GATE_ROUTINE_SUPPRESS failed ' + e); }
  Interceptor.attach(exp('_ZN9GateScene13setLayoutListEv'), {
    onEnter(a) {
      const key = a[0].toString();
      if (pending.delete(key)) note('JP_EVENT_REFRESH_LIST scene=' + key);
    }
  });

  function choose(ui, group) {
    let menu;
    try { menu = readMenu(group.id); }
    catch (e) { note('JP_EVENT_SELECT_ERROR id=' + group.id + ' ' + e.stack); return; }
    ui.menu = menu;
    close(ui);
    refreshGate(ui.scene);
    note('JP_EVENT_SEASON_SELECTED id=' + group.id + ' count=' + group.count
      + ' selected=' + (menu.selected ? menu.selected.id : '?'));
  }

  // ---- sub-header anchor + header draw ----
  const getLayouts = fn('_ZN9GameScene18getLayoutCacheListEv', 'pointer', ['pointer']);
  const getLayout = fn('_ZN15LayoutCacheList9getObjectE' + strType, 'pointer', ['pointer', 'pointer']);
  const layoutX = fn('_ZNK13LayoutControl4getXEv', 'float', ['pointer']);
  const layoutY = fn('_ZNK13LayoutControl4getYEv', 'float', ['pointer']);
  const layoutW = fn('_ZNK13LayoutControl8getWidthEv', 'float', ['pointer']);
  const layoutH = fn('_ZNK13LayoutControl9getHeightEv', 'float', ['pointer']);
  const headers = [];
  Interceptor.attach(exp('_ZN9GateScene22setLayoutSubHeaderAreaEv'), {
    onEnter(a) { headers.push(a[0]); },
    onLeave() {
      const scene = headers.pop();
      try {
        const key = scene.toString(), layouts = getLayouts(scene);
        if (!layouts.isNull()) {
          for (const name of ['gate_seal_area_icon', 'gate_another_world_icon']) {
            const layout = withString(name, s => getLayout(layouts, s));
            if (layout.isNull()) continue;
            const x = layoutX(layout) + layoutW(layout) / 2, y = layoutY(layout) + layoutH(layout) / 2;
            if (isFinite(x) && isFinite(y) && x > 0 && y >= 0) {
              const w = layoutW(layout);
              anchors.set(key, {x, y, w: isFinite(w) && w > 0 && w < 200 ? w : 64});
              note('JP_EVENT_ANCHOR ' + name + ' x=' + x.toFixed(0) + ' y=' + y.toFixed(0) + ' w=' + w.toFixed(0));
              break;
            }
          }
        }
        const ui = scenes.get(key);
        if (ui) drawHeader(ui);
      } catch (e) { note('JP_EVENT_ANCHOR_ERROR ' + e); }
    }
  });
  Interceptor.attach(exp('_ZN9GateScene13initSubHeaderEv'), {
    onEnter(a) { this.scene = a[0]; },
    onLeave() {
      try {
        const key = this.scene.toString();
        let ui = scenes.get(key);
        if (!ui) { ui = {key, scene: this.scene, labels: new Map(), nodes: [], rows: [], open: false, menu: null}; scenes.set(key, ui); }
        ui.menu = readMenu('');
        close(ui);
        note('JP_EVENT_MENU_READY selected=' + (ui.menu.selected ? ui.menu.selected.id : '?')
          + ' groups=' + ui.menu.groups.map(g => g.id + ':' + g.count).join(',')
          + ' win=' + width() + 'x' + height());
      } catch (e) { note('JP_EVENT_MENU_ERROR ' + e.stack); }
    }
  });

  // ---- gestures ----
  // Only GateScene's own handlers are hooked (GameScene's are owned by jp_summon_menu.js). A claimed touch is
  // remembered so GameScene::buttonTouchEnded can be suppressed for that release.
  const owned = new Map(), tk = (s, t) => s.toString() + ':' + t.toString();
  const claims = (scene, touch) => {
    const ui = scenes.get(scene.toString());
    if (!ui) return null;
    return ui.open || hit(ui.hit, touchPoint(touch)) ? ui : null;
  };
  // A claimed touch must NOT reach GateScene's own handlers: touchBegan (0x1bdff00) starts the list scroll /
  // button press and touchEnded (0x1bdff80, 3.4 KB) switches main/sub tabs and opens banners, so merely
  // stopping the event let a tap on the box or a dropdown row also hit the tab/banner underneath (tablet
  // 2026-11-13). The three handlers are replaced; unclaimed touches go to the originals unchanged.
  // touchBegan returns true for a claimed touch so GameScene keeps delivering its moves/release.
  const sig = n => '_ZN9GateScene' + n + 'EPN7cocos2d5TouchEPNS0_5EventE';
  let gateBegan, gateMoved, gateEnded;
  const gateBeganCb = new NativeCallback((scene, touch, event) => {
    try {
      const key = tk(scene, touch);
      owned.delete(key);            // a reused Touch pointer: drop any claim left by an unobserved release
      if (claims(scene, touch)) { owned.set(key, {ui: scenes.get(scene.toString())}); stopTouch(event); return 1; }
    } catch (e) { note('JP_EVENT_TOUCH_ERROR ' + e); }
    return gateBegan(scene, touch, event) ? 1 : 0;
  }, 'bool', ['pointer', 'pointer', 'pointer']);
  const gateMovedCb = new NativeCallback((scene, touch, event) => {
    try { if (owned.get(tk(scene, touch))) { stopTouch(event); return; } }
    catch (e) { note('JP_EVENT_TOUCH_ERROR ' + e); }
    gateMoved(scene, touch, event);
  }, 'void', ['pointer', 'pointer', 'pointer']);
  const gateEndedCb = new NativeCallback((scene, touch, event) => {
    let rec = null;
    try { rec = owned.get(tk(scene, touch)); } catch (e) { note('JP_EVENT_TOUCH_ERROR ' + e); }
    if (!rec) { gateEnded(scene, touch, event); return; }
    try {
      stopTouch(event);
      const ui = rec.ui;
      if (!ui || !touchEnabled(scene)) return;
      const p = touchPoint(touch);
      if (!ui.open && hit(ui.hit, p)) { ui.menu = readMenu(''); open(ui); }
      else if (ui.open) { const row = ui.rows.find(r => hit(r.box, p)); if (row) choose(ui, row.group); else close(ui); }
    } catch (e) { note('JP_EVENT_TOUCH_ERROR ' + e); }
  }, 'void', ['pointer', 'pointer', 'pointer']);
  gateBegan = new NativeFunction(Interceptor.replaceFast(exp(sig('10touchBegan')), gateBeganCb),
    'bool', ['pointer', 'pointer', 'pointer'], {exceptions: 'propagate'});
  gateMoved = new NativeFunction(Interceptor.replaceFast(exp(sig('10touchMoved')), gateMovedCb),
    'void', ['pointer', 'pointer', 'pointer'], {exceptions: 'propagate'});
  gateEnded = new NativeFunction(Interceptor.replaceFast(exp(sig('10touchEnded')), gateEndedCb),
    'void', ['pointer', 'pointer', 'pointer'], {exceptions: 'propagate'});
  let buttonEnded;
  const buttonEndedCallback = new NativeCallback((scene, touch, event, flag) => {
    try {
      const key = tk(scene, touch);
      if (owned.delete(key)) { stopTouch(event); return 1; }
    } catch (e) { note('JP_EVENT_TOUCH_ERROR ' + e); }
    return buttonEnded(scene, touch, event, flag) ? 1 : 0;
  }, 'bool', ['pointer', 'pointer', 'pointer', 'bool']);
  buttonEnded = new NativeFunction(Interceptor.replaceFast(
    exp('_ZN9GameScene16buttonTouchEndedEPN7cocos2d5TouchEPNS0_5EventEb'), buttonEndedCallback),
    'bool', ['pointer', 'pointer', 'pointer', 'bool'], {exceptions: 'propagate'});
  // Drop stale claims on a new touch / scene exit so a cancelled gesture cannot eat the next tap.
  const forget = scene => {
    const key = scene.toString();
    for (const k of owned.keys()) if (k.startsWith(key + ':')) owned.delete(k);
    const ui = scenes.get(key);
    if (ui) { clear(ui); scenes.delete(key); }
    anchors.delete(key);
  };
  Interceptor.attach(exp('_ZN9GateScene16onSceneInvisibleEv'), { onEnter(a) { forget(a[0]); } });
  Interceptor.attach(exp('_ZN9GateSceneD1Ev'), { onEnter(a) { forget(a[0]); } });
  // ---- raid menu: ask the server on EVERY raid entry (2026-11-14) ----
  // GateMissionScene::initConnect (0x1bc46fc): for a raid scene (+0x610 == 1) it sends
  // RoutineRaidMenuUpdateRequest(dungeon = [+0x558]+0x24) only when the scene flag +0x69c
  // (setRaidMenuUpdateRequestFlg, 0x199c5c0) is set or UpdateInfo::isNeedRaidMenuUpdate() is true. Live JP had
  // one raid at a time, so after the first reply the RaidMenuInfo singleton (title/HP/level/background) was
  // reused for every other raid: opening 6070 after 6260 showed 6260's title and art. Setting the flag makes
  // each raid entry fetch its own menu info.
  try {
    Interceptor.attach(exp('_ZN16GateMissionScene11initConnectEv'), {
      onEnter(a) {
        try { if (a[0].add(0x610).readS32() === 1) a[0].add(0x69c).writeU8(1); } catch (e) {}
      }
    });
  } catch (e) { note('JP_RAID_MENU_REFRESH_FAILED ' + e); }
  globalThis.__jpEventMenuKeep = [buttonEndedCallback, gateBeganCb, gateMovedCb, gateEndedCb];
  // ---- JP-absent tile art: crash guard + diagnosis (build/out/vortex_season/crash_analysis.md 4.2/4.3) ----
  // Gate rows can carry `event_<area>.png` (the GL raid archive's menu_background). JP ships none of them:
  // LayoutUtils::getOrCreateSpriteBatchNode then returns a null SpriteBatchNode and GameLayer::addChild
  // forwards it to Node::addChildHelper, whose Ref::retain(child) reads child+8 -> SIGSEGV. jp_compat now
  // rewrites those names (registered stand-ins / the default plate), but a null child must never kill the
  // scene through any path. Symbols are JP 11.0.0 dynsym entries (see the report's addresses).
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
  const nullChildren = new Set();
  let addChildOrig;
  try {
    // replaceFast returns a trampoline for the original (same pattern as GameScene::buttonTouchEnded above);
    // Interceptor.replace would make addChildOrig re-enter the replacement.
    addChildOrig = new NativeFunction(Interceptor.replaceFast(
      exp('_ZN9GameLayer8addChildEiiPN7cocos2d4NodeE'),
      new NativeCallback(function (layer, id, depth, node) {
        try {
          if (!node.isNull()) { addChildOrig(layer, id, depth, node); return; }
          const k = id + ':' + depth;
          if (!nullChildren.has(k)) { nullChildren.add(k); note('JP_EVENT_NULL_CHILD layer=' + id + ' depth=' + depth); }
        } catch (e) { note('JP_EVENT_ADDCHILD_ERROR ' + e); }
      }, 'void', ['pointer', 'int', 'int', 'pointer'])), 'void',
      ['pointer', 'int', 'int', 'pointer'], {exceptions: 'propagate'});
  } catch (e) { note('JP_EVENT_NULL_GUARD_FAILED ' + e.stack); }
  // ---- empty / JP-absent tile art: make getOrCreateSpriteBatchNode never return null ----
  // GateDungeonScene::setListLayout+0x38c/+0x3b0 (0x1bc03ec/0x1bc040c) calls the 5-parameter overload
  //   LayoutUtils::getOrCreateSpriteBatchNode(string const&, CriFileLoader*, int, int, unsigned)   0x154709c
  // with IconMstList::getFileName(DungeonMst.iconId). JP F_DUNGEON_MST has 16 rows with 0HUPxDf1="0" and
  // F_ICON_MST has no id 0, so getFileName returns "" (0x1cafec0), the texture load fails, and the body hands
  // a null node to GameLayer::addChild(2,3,null) (Ref::retain(null) = SIGSEGV) and to createGameSpriteByImage
  // at 0x1bc0570, so suppressing addChild only delays the crash. Replacing the return value is the only guard
  // that holds: normal art is untouched (only null results are substituted) and every caller funnels through
  // this overload (the 4-arg one at 0x1547050 tail-calls it). The old diagnostic was attached to that 4-arg
  // symbol and could never fire for this scene, so it moved here (build/out/vortex_season/dungeon_crash.md).
  const GOSBN6 = '_ZN11LayoutUtils26getOrCreateSpriteBatchNodeERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEEP13CriFileLoaderiij';
  const FALLBACK_NAME = 'image/ui/common/common.png';   // this same scene loads it at 0x1bc00cc (layer 2, depth 5)
  // libc++ (__ndk1) std::string long form: [0..7] capacity (bit 0 set = long), [8..15] size, [16..23] data.
  function longString(name) {
    const cap = name.length % 2 === 0 ? name.length + 1 : name.length + 2;   // odd and >= size+1
    const data = Memory.alloc(cap);
    data.writeUtf8String(name);
    const buf = Memory.alloc(24);
    buf.writeU64(cap);
    buf.add(8).writeU64(name.length);
    buf.add(16).writePointer(data);
    globalThis.__jpEventMenuKeep.push(data, buf);
    return buf;
  }
  const fallbackName = longString(FALLBACK_NAME);
  // The UICacheList key is always "common", so the engine's own log cannot name the missing image; this does.
  const artMiss = new Set();
  const iconSubs = new Map(), iconSubNoted = new Set();
  let gosbn6;
  try {
    const guard = new NativeCallback(function (key, loader, layer, depth, flag) {
      try {
        const name = readStdString(key);
        if (name !== '' && name !== '<null>' && name !== '<bad>' && name !== '<err>') {
          const node = gosbn6(key, loader, layer, depth, flag);
          if (!node.isNull()) return node;
        }
        // JP-absent dungeon/area banner icon -> the same area's JP-shipped banner (build/make_jp_icon_fallback.py).
        // A common.png stand-in avoided the crash but left the whole GateDungeonScene list blank (711, 2026-11-14).
        const sub = (globalThis.__jpIconFallback || {})[name];
        if (sub) {
          let subKey = iconSubs.get(sub);
          if (!subKey) { subKey = longString(sub); iconSubs.set(sub, subKey); }
          const node = gosbn6(subKey, loader, layer, depth, flag);
          if (!iconSubNoted.has(name)) { iconSubNoted.add(name); note('JP_EVENT_ICON_SUB "' + name + '" -> "' + sub + '" node=' + (node.isNull() ? 'null' : 'ok')); }
          if (!node.isNull()) return node;
        }
        let fresh = false;
        if (!artMiss.has(name)) { artMiss.add(name); fresh = true; note('JP_EVENT_ART_MISS "' + name + '" layer=' + layer + ' depth=' + depth); }
        const alt = gosbn6(fallbackName, loader, layer, depth, flag);
        if (fresh) note('JP_EVENT_BATCH_FALLBACK "' + name + '" -> ' + FALLBACK_NAME + ' node=' + (alt.isNull() ? 'null' : 'ok'));
        return alt;
      } catch (e) { note('JP_EVENT_BATCH_GUARD_ERROR ' + e); return ptr(0); }
    }, 'pointer', ['pointer', 'pointer', 'int', 'int', 'uint']);
    gosbn6 = new NativeFunction(Interceptor.replaceFast(exp(GOSBN6), guard),
                                'pointer', ['pointer', 'pointer', 'int', 'int', 'uint'],
                                {exceptions: 'propagate'});
    globalThis.__jpEventMenuKeep.push(guard);
  } catch (e) {
    note('JP_EVENT_BATCH_GUARD_FAILED ' + e.stack);
    // Diagnostic-only path (no replacement): the same 5-parameter symbol, with layer/depth.
    try {
      Interceptor.attach(exp(GOSBN6), {
        onEnter(a) { this.key = a[0]; this.layer = a[2].toInt32(); this.depth = a[3].toInt32(); },
        onLeave(r) {
          if (!r.isNull()) return;
          const name = readStdString(this.key);
          if (artMiss.has(name)) return;
          artMiss.add(name);
          note('JP_EVENT_ART_MISS "' + name + '" layer=' + this.layer + ' depth=' + this.depth);
        }
      });
    } catch (e2) { note('JP_EVENT_ART_TRACE_FAILED ' + e2.stack); }
  }
  // Suppress the meaningless '99 attempts remaining' Moogle overlay on Fragment Trial tiles
  // (GateScene::setLayoutList 0x1bddcc4: tbz w0, #0, #0x1bdde3c after isBrokenPieceMission;
  // leaves GateScene::touchEnded 0x1be0768 untouched so entry still works).
  try {
    Interceptor.attach(m.base.add(0x1bddcc4), {
      onEnter() {
        this.context.x0 = ptr(0);
      }
    });
  } catch (e) { note('JP_BROKEN_PIECE_OVERLAY_SKIP_FAILED ' + e); }
  note('JP_EVENT_MENU_INSTALLED');
}

// Self-install: jp_offline.js only calls the installers it knows, and it must not be edited for this feature.
// Running the wait here mirrors jp_seal_guard.js.
(function () {
  const TAG = 'JPEVENT';
  if (globalThis.__jpEventMenuBooted) return;
  globalThis.__jpEventMenuBooted = true;
  const log = s => { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } };
  let tries = 0;
  const timer = setInterval(function () {
    if (globalThis.__jpEventMenuInstalled) { clearInterval(timer); return; }
    const m = Process.findModuleByName('libgame.so');
    if (!m) { if (++tries > 1200) { clearInterval(timer); log('NO_LIBGAME'); } return; }
    clearInterval(timer);
    try { installJpEventMenu(m, log); } catch (e) { log('INSTALL_FAILED ' + e.stack); }
  }, 50);
})();
