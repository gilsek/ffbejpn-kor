// jp_hide_explore.js — hide the home "Explore" (chocobo) icon (2026-11-09).
//
// JP 11.0.0 has an Explore feature (ExploreTopScene/ExplorePartyListScene, requests ExploreEntry/Start/RewardGet/
// Retire/Setting...). The offline engine is the Global server, which has no Explore: tapping the icon sent
// mr6DnTQV, got an empty reply and the client showed "로컬 게임 데이터를 불러올 수 없습니다". The icon appears once the
// player unlocks it (switch 10000501 granted 16:01:34 on the test tablet).
// (A crash at 16:06 right after this hook went in was the mail list -- see jp_mail.py -- not this hook.)
// HomeScene::setExploreIcon() starts with `if (!isDispExploreIcon()) return;`, so returning false hides the icon.
(function () {
  const TAG = 'EXPLORE';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    const p = m.findExportByName('_ZN9HomeScene17isDispExploreIconEv');
    if (!p) { log('missing isDispExploreIcon'); return; }
    let calls = 0;
    Interceptor.replace(p, new NativeCallback(function () {
      if (++calls <= 3) log('isDispExploreIcon -> 0 (hidden)');
      return 0;
    }, 'bool', ['pointer']));
    log('hook installed');
  }, 50);
})();
