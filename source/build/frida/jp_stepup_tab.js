// jp_stepup_tab.js — 소환 화면 세 번째 탭(교환소)을 스텝업 탭으로 쓴다 (2026-11-16, 사용자 결정).
//
// JP 클라이언트는 GachaMst+0xbc(타입) 하나로 탭을 정한다(libgame.so 11.0.0 역어셈블,
// build/out/jp_offline/gacha_jp/stepup_tab/disasm*.txt):
//   isFreeType     0x1cd2ad8: type 0·7          -> 탭 1(무료/Standard)
//   isExchangeType 0x1cd2af4: type 6·8          -> 탭 2(교환소)
//   isPayType      0x1cd2aa8: 0·7·6·8 이 아님   -> 탭 0(유료)
// 이 둘을 부르는 곳은 GachaTopScene::setListLayout/isRefresh(탭별 목록 필터), GachaEntryScene::updateEvent,
// Gacha(Pay)DetailScene::closeScene(돌아갈 탭)뿐이다. 스텝업 상세 화면은 isNewStepUpGacha(type 5 && +0xcc==2)를
// 따로 쓰므로 영향이 없다. 그래서 타입 5(엔진 gacha_archive.wire_type의 steps 배너)를 교환 탭 쪽으로 옮긴다.
// 선택 교환(6)·교환(8) 판정 isExchange/judgeExeSelectGacha는 건드리지 않는다.
// 탭 그림 gacha_tab_exchange_{1,2}.png는 build/make_stepup_tab_label.py가 'Step-Up Summon'으로 다시 그린다.
(function () {
  const TAG = 'STEPUP_TAB';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  const STEP = 5;
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    const pay = m.findExportByName('_ZN8GachaMst9isPayTypeEv');
    const free = m.findExportByName('_ZN8GachaMst10isFreeTypeEv');
    const exch = m.findExportByName('_ZN8GachaMst14isExchangeTypeEv');
    if (!pay || !free || !exch) { log('missing export ' + pay + ' ' + free + ' ' + exch); return; }
    const type = self => self.add(0xbc).readS32();
    const payListTicketRet = m.base.add(0x1ab49d8);
    const freeListTicketRet = m.base.add(0x1ab4c50);
    const listBadgeRet = m.base.add(0x1ab5254);
    Interceptor.replace(pay, new NativeCallback(function (self) {
      if (this.returnAddress.equals(payListTicketRet)) return 0;
      return type(self) === 1 ? 1 : 0;
    }, 'int', ['pointer']));
    Interceptor.replace(free, new NativeCallback(function (self) {
      if (this.returnAddress.equals(freeListTicketRet)) return 0;
      const t = type(self);
      return (t === 2 || t === 0 || t === 7) ? 1 : 0;
    }, 'int', ['pointer']));
    Interceptor.replace(exch, new NativeCallback(function (self) {
      if (this.returnAddress.equals(listBadgeRet)) return 0;
      const t = type(self);
      return (t === 3 || t === STEP || t === 6 || t === 8) ? 1 : 0;
    }, 'int', ['pointer']));
    const ticketBtnHookAt = m.base.add(0x1ad89e4);
    const rightBtnStr = m.base.add(0x25e0bc4); // 'gacha_pay_summon_right_btn'
    Interceptor.attach(ticketBtnHookAt, function () {
      this.context.x1 = rightBtnStr;
    });
    const ticketOnly = m.findExportByName('_ZN14GachaDetailMst17isTicketOnlyGachaEv');
    const getDefInt = m.findExportByName('_ZN9DefineMst11getIntValueEPKc');
    const ticketSetLayoutRet = m.base.add(0x1b03a84);
    if (ticketOnly) {
      Interceptor.attach(ticketOnly, {
        onEnter() {
          this.fromTicketConfirm = this.returnAddress.equals(ticketSetLayoutRet);
        },
        onLeave(retval) {
          if (this.fromTicketConfirm) retval.replace(1);
        }
      });
    }
    if (getDefInt) {
      Interceptor.attach(getDefInt, {
        onEnter(args) {
          this.isExLimit = !args[1].isNull() && args[1].readUtf8String() === 'GACHA_EX_TICKET_USE_LIMIT';
        },
        onLeave(retval) {
          if (this.isExLimit) retval.replace(11);
        }
      });
    }
    const uiFooterUpdateBadge = m.findExportByName('_ZN8UIFooter11updateBadgeEii');
    const uiFooterNeedBadge = m.findExportByName('_ZN8UIFooter15needUpdateBadgeEii');
    for (const fn of [uiFooterUpdateBadge, uiFooterNeedBadge]) {
      if (fn) {
        Interceptor.attach(fn, {
          onEnter(args) {
            args[1] = ptr(0);
          }
        });
      }
    }
    log('hook installed (1->FFBE, 2/0/7->FF_SERIES, 3/5/6/8->COLLAB + no list ticket box + no footer gacha badge + ticket 11x)');
  }, 50);
})();
