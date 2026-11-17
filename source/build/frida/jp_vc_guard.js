// jp_vc_guard.js — 비전 카드 강화 시 UserVisionCardInfo 소멸 후 참조(SIGILL at _ZTSN7cocos2d3RefE) 방지.
//
// libgame.so sha256 54ef0fe9a5c160254654a741bd8a3791e83bac80f7ece8c806af589e8fa1184e (JP 11.0.0 arm64).
(function () {
  const TAG = 'VCGUARD';
  function log(s) {
    try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); }
  }

  const ANCHORS = [
    { name: 'shared', sym: '_ZN22UserVisionCardInfoList6sharedEv', off: 0x1d2fa10, word: 0xf81e0ff3 },
    { name: 'updateObject', sym: '_ZN22UserVisionCardInfoList12updateObjectEP18UserVisionCardInfo', off: 0x1d3023c, word: 0xf81d0ff5 },
    { name: 'addUserVcObject', sym: '_ZN22UserVisionCardInfoList15addUserVcObjectEP18UserVisionCardInfoRKNSt6__ndk112basic_stringIcNS2_11char_traitsIcEENS2_9allocatorIcEEEE', off: 0x1d3015c, word: 0xa9be4ff4 },
    { name: 'calcUserVcStatus', sym: '_ZN22UserVisionCardInfoList16calcUserVcStatusEP18UserVisionCardInfo', off: 0x1d3018c, word: 0xd10103ff },
    { name: 'objectForKey', sym: '_ZN7cocos2d12__Dictionary12objectForKeyERKNSt6__ndk112basic_stringIcNS1_11char_traitsIcEENS1_9allocatorIcEEEE', off: 0x21d3fdc, word: 0xa9bb67fa },
    { name: 'retain', sym: '_ZN7cocos2d3Ref6retainEv', off: 0x218ca7c, word: 0xb9400808 },
    { name: 'respC1', sym: '_ZN26UserVisionCardInfoResponseC1Ev', off: 0x1dc8f48, word: 0xf81e0ff3 },
    { name: 'setLayoutBaseCard', sym: '_ZN22VisionCardMixMainScene17setLayoutBaseCardEv', off: 0x197df44, word: 0xd10643ff },
  ];
  const VTABLE_SYM = '_ZTV18UserVisionCardInfo';
  const VTABLE_OFF = 0x2da4d88;

  const wait = setInterval(function () {
    const m = Process.findModuleByName('libgame.so');
    if (!m) return;
    clearInterval(wait);

    const addrs = {};
    for (let i = 0; i < ANCHORS.length; i++) {
      const a = ANCHORS[i];
      const p = m.findExportByName(a.sym);
      const expected = m.base.add(a.off);
      if (!p || !p.equals(expected) || p.readU32() !== a.word) {
        log('anchor mismatch on ' + a.name + ', not installed (' + p + ' vs ' + expected + ')');
        return;
      }
      addrs[a.name] = p;
    }

    const vtableAddr = m.findExportByName(VTABLE_SYM);
    const expectedVtable = m.base.add(VTABLE_OFF);
    if (!vtableAddr || !vtableAddr.equals(expectedVtable)) {
      log('anchor mismatch on vtable, not installed (' + vtableAddr + ' vs ' + expectedVtable + ')');
      return;
    }
    const expectedVptr = m.base.add(VTABLE_OFF + 0x10);

    const listShared = new NativeFunction(addrs.shared, 'pointer', []);
    const calcUserVcStatus = new NativeFunction(addrs.calcUserVcStatus, 'pointer', ['pointer', 'pointer']);
    const objectForKey = new NativeFunction(addrs.objectForKey, 'pointer', ['pointer', 'pointer']);
    const refRetain = new NativeFunction(addrs.retain, 'void', ['pointer']);

    // (A) UserVisionCardInfoList::updateObject: 제자리(in-place) 갱신으로 기존 객체 소멸 방지
    Interceptor.replace(addrs.updateObject, new NativeCallback(function (listPtr, newCard) {
      if (newCard.isNull()) return;
      calcUserVcStatus(listPtr, newCard);
      const key = newCard.add(0x28);
      const oldCard = objectForKey(listPtr, key);
      if (oldCard.isNull()) return;
      if (!oldCard.equals(newCard)) {
        if (!oldCard.readPointer().equals(expectedVptr)) {
          oldCard.writePointer(expectedVptr);
        }
        oldCard.add(0x24).writeU32(newCard.add(0x24).readU32());
        Memory.copy(oldCard.add(0x40), newCard.add(0x40), 0x41);
      }
    }, 'void', ['pointer', 'pointer']));

    // (B) UserVisionCardInfoList::addUserVcObject: 카드 객체 refcount 1회 추가 보호
    Interceptor.attach(addrs.addUserVcObject, {
      onEnter: function (args) {
        const card = args[1];
        if (!card.isNull()) {
          refRetain(card);
        }
      },
    });

    // (C) UserVisionCardInfoResponse::UserVisionCardInfoResponse(): m_mode=1로 강제해 removeAllObjects 방지
    Interceptor.attach(addrs.respC1, {
      onEnter: function (args) {
        this.self = args[0];
      },
      onLeave: function () {
        if (this.self && !this.self.isNull()) {
          this.self.add(0x24).writeS32(1);
        }
      },
    });

    // (D) VisionCardMixMainScene::setLayoutBaseCard: baseCard 포인터 및 vptr 검증/복구
    Interceptor.attach(addrs.setLayoutBaseCard, {
      onEnter: function (args) {
        const scene = args[0];
        if (scene.isNull()) return;
        const commonUi = scene.add(0x560).readPointer();
        if (commonUi.isNull()) return;
        let baseCard = commonUi.add(0x28).readPointer();
        if (baseCard.isNull()) return;

        const listPtr = listShared();
        if (!listPtr.isNull()) {
          const liveCard = objectForKey(listPtr, baseCard.add(0x28));
          if (!liveCard.isNull() && !liveCard.equals(baseCard)) {
            commonUi.add(0x28).writePointer(liveCard);
            log('rebound baseCard ' + baseCard + ' -> ' + liveCard);
            baseCard = liveCard;
          }
        }

        const vptr = baseCard.readPointer();
        if (!vptr.equals(expectedVptr)) {
          baseCard.writePointer(expectedVptr);
          log('restored baseCard vptr ' + vptr + ' -> ' + expectedVptr);
        }
      },
    });

    log('installed');
  }, 50);
})();
