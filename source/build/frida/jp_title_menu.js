// JP title "New Game" (2026-11-09): the title's »info button becomes NEW GAME, the JP counterpart of the Global
// Offline exvius/title_menu.js. Global relabels text buttons (setBtnWithLocKey); JP 11.0.0 has no such function
// and draws image buttons (TitleScene::setBtn) with baked text, so the info label sprite itself is replaced (CPK).
//   tap info  -> TitleScene::onTouchInfoButton (replaced) -> the title's own exit confirmation (TitleScene::backScene,
//                ConfirmScene id 102) with its TITLE_CONFIRM_APP_EXIT text swapped for a New Game question
//   Yes       -> TitleScene::confirmAnswerYes(102) would end the app (Director::end); instead
//                LocalGameBridge.titleAction("new") (engine: offline_menu.new_game backs the save up to
//                state/backups/ and starts a fresh one; jp_offline_build.py re-grants the JP start-up switches),
//                then lets confirmAnswerYes(102) end the app as the original exit does. Starting the game in the
//                same process (TOUCH START, changeSceneWithSceneID(2)) kept the previous save's user lists in client
//                memory: an empty list (new save: no town quests) does not clear them, so the old 「비밀 수첩」 and
//                its completion still showed until the app was restarted (user, 2026-11-10). The user relaunches.
//   No / back -> unchanged (confirmAnswerNo clears +0x575).
// Offsets/ids from the JP libgame.so disassembly: backScene needs +0x576 != 0 and +0x575 == 0 and sets +0x575.
function installJpTitleMenu(m, note, bridge) {
  const exp = n => m.getExportByName(n);
  const fn = (n, r, a) => new NativeFunction(exp(n), r, a, {exceptions: 'propagate'});
  const CONFIRM_EXIT = 102, INFO_TAG = 100, DUMP_TITLE_IMAGES = false;
  // Game texts break lines with <br> (TITLE_CONFIRM_APP_EXIT bytes on device: "…します。<br>よろしいですか？");
  // a "\n" left the dialog text empty. Korean since the Korean game font (build/make_ko_font.py).
  const MESSAGE = '처음부터 새로 시작할까요?<br>지금 데이터는 백업되고 게임이 종료됩니다.<br>다시 실행해 주세요.';

  const stringData = [];  // the character buffers must outlive stdString(): JS frees unreferenced Memory.alloc blocks
  function stdString(text) {  // libc++ std::string (never freed: the game copies it)
    const data = Memory.allocUtf8String(text); stringData.push(data);
    const size = (() => { let n = 0; while (data.add(n).readU8() !== 0) n++; return n; })();
    const s = Memory.alloc(24);
    if (size <= 22) { s.writeU8(size << 1); Memory.copy(s.add(1), data, size + 1); }
    else { s.writeU64(uint64(((size + 16) & ~15) | 1)); s.add(8).writeU64(uint64(size)); s.add(16).writePointer(data); }
    return s;
  }
  const retained = [];
  const keep = x => { retained.push(x); return x; };

  const backScene = fn('_ZN10TitleScene9backSceneEv', 'void', ['pointer']);

  let pendingNew = false, askScene = null;
  // ask() runs inside a Frida callback (updateEvent), where neither listeners nor replacements fire for the game's
  // own nested calls, so getText cannot be hooked for backScene. Instead the text table entry itself is swapped:
  // GameScene::getText returns a reference to the stored std::string (long mode); its size and data pointer are
  // pointed at our text for the backScene call (which copies it into its ConfirmSceneSetting), then restored.
  const getText = fn('_ZN9GameScene7getTextERKNSt6__ndk112basic_stringIcNS0_11char_traitsIcEENS0_9allocatorIcEEEE', 'pointer', ['pointer', 'pointer']);
  const exitKey = keep(stdString('TITLE_CONFIRM_APP_EXIT'));
  function ask(self) {
    pendingNew = true;
    const entry = getText(self, exitKey), saved = entry.readByteArray(24);
    // Same shape as the original entry (its long-mode capacity kept), our text in a buffer made now.
    const text = Memory.allocUtf8String(MESSAGE); stringData.push(text);
    let len = 0; while (text.add(len).readU8() !== 0) len++;
    entry.add(8).writeU64(uint64(len)); entry.add(16).writePointer(text);
    try { backScene(self); } catch (e) { note('TITLE_NEW_GAME_DIALOG_ERROR ' + e); }
    finally { entry.writeByteArray(saved); }
    if (self.add(0x575).readU8() === 0) pendingNew = false;  // dialog not shown (title not ready / already open)
    note('TITLE_NEW_GAME_ASK shown=' + pendingNew);
  }
  // The info tap is decided in TitleScene::touchEnded (isTouchButton(100) -> +0x570 = 100 -> GetTitleInfo +
  // NoticeScene, which fails offline with 通信エラー). Like Global, report "not hit" for tag 100 and open the
  // New Game question on the next updateEvent instead.
  let titleTouch = 0;
  Interceptor.attach(exp('_ZN10TitleScene10touchEndedEPN7cocos2d5TouchEPNS0_5EventE'), {
    onEnter(a) { titleTouch++; this.self = a[0]; titleTouchScene = a[0]; }, onLeave() { titleTouch--; }
  });
  let titleTouchScene = null;
  Interceptor.attach(exp('_ZN9GameScene13isTouchButtonEiPN7cocos2d5TouchE'), {
    onEnter(a) { this.tag = titleTouch ? a[1].toInt32() : 0; },
    onLeave(r) {
      if (this.tag !== INFO_TAG || !(r.toInt32() & 1)) return;
      r.replace(ptr(0));
      askScene = titleTouchScene;
    }
  });
  Interceptor.replace(exp('_ZN10TitleScene17onTouchInfoButtonEv'), keep(new NativeCallback(self => ask(self), 'void', ['pointer'])));
  Interceptor.attach(exp('_ZN10TitleScene16confirmAnswerYesEi'), { onEnter(a) {
    if (!pendingNew || a[1].toInt32() !== CONFIRM_EXIT) return;
    pendingNew = false;
    try {
      bridge('titleAction', '(Ljava/lang/String;)Ljava/lang/String;', ['new']);
      note('TITLE_NEW_GAME done -> app exit');   // id stays 102: the original ends the app (Director::end)
    } catch (e) {
      a[1] = ptr(0);                     // not 102: the original returns without Director::end
      a[0].add(0x575).writeU8(0);        // what confirmAnswerNo would clear
      note('TITLE_NEW_GAME_ERROR ' + e);  // save unchanged; stay on the title
    }
  } });
  Interceptor.attach(exp('_ZN10TitleScene15confirmAnswerNoEi'), { onEnter(a) {
    if (pendingNew && a[1].toInt32() === CONFIRM_EXIT) pendingNew = false;
  } });
  Interceptor.attach(exp('_ZN10TitleScene11updateEventEv'), {
    onEnter(a) { this.t = a[0]; },
    onLeave() {
      if (askScene && askScene.equals(this.t)) { askScene = null; ask(this.t); }
    }
  });

  // ---- NEW GAME button art ----
  // The label is the title atlas frame titlebutton_label_info.png, redrawn by build/make_jp_title_art.py into
  // translations/ui-ko/sprites/custom/ and packed into common.cpk by build/apply_ko_ui.py (no runtime swap).
  const libc = Process.getModuleByName('libc.so');
  const readStd = p => { try { const b = p.readU8(); return (b & 1) ? p.add(16).readPointer().readUtf8String(p.add(8).readU64().toNumber()) : p.add(1).readUtf8String(b >> 1); } catch (e) { return '?'; } };
  // Developer aid (off): dump images decoded while the title builds, to files/exvius/title_dump/<n>_<bytes>.png.
  if (DUMP_TITLE_IMAGES) {
    const fopen = new NativeFunction(libc.getExportByName('fopen'), 'pointer', ['pointer', 'pointer']);
    const fwrite = new NativeFunction(libc.getExportByName('fwrite'), 'ulong', ['pointer', 'ulong', 'ulong', 'pointer']);
    const fclose = new NativeFunction(libc.getExportByName('fclose'), 'int', ['pointer']);
    const mkdir = new NativeFunction(libc.getExportByName('mkdir'), 'int', ['pointer', 'int']);
    const DIR = '/data/data/com.exvius.jpkorean.app/files/exvius/title_dump/';
    mkdir(Memory.allocUtf8String(DIR), 0x1ff);
    let dumped = 0, titleBuilt = false;
    Interceptor.attach(exp('_ZN10TitleScene6setBtnEPN7cocos2d15SpriteBatchNodeEiiNSt6__ndk112basic_stringIcNS3_11char_traitsIcEENS3_9allocatorIcEEEES9_S9_'),
      { onLeave() { titleBuilt = true; } });
    Interceptor.attach(exp('_ZN7cocos2d5Image17initWithImageDataEPKhl'), { onEnter(a) {
      const n = a[2].toInt32();
      if (titleBuilt || dumped >= 80 || n < 1024) return;
      const f = fopen(Memory.allocUtf8String(DIR + String(++dumped).padStart(3, '0') + '_' + n + '.png'), Memory.allocUtf8String('wb'));
      if (!f.isNull()) { fwrite(a[1], 1, n, f); fclose(f); }
    } });
  }
  note('JP_TITLE_MENU_READY');
}
