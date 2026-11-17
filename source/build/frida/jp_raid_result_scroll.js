// jp_raid_result_scroll.js — raid result list scrolls to the last row in repeat (周回) results (2026-11-17).
//
// Raid repeat result (「1주년 고마워 쿠포·특급 x10周」) list stopped ~1 row past the top: more items below were unreachable.
// The list's scroll length comes from getDropItemCount (virtual). ResultSummaryScene::getDropItemCount counts the
// scene's own result info (ResultBaseScene::getMissionResultInfo, the summed repeat result), but the override
// RaidResultSummaryScene::getDropItemCount counts MissionResultInfo::shared() (one battle) instead.
// Return the larger of the two: a single battle gives the same count, a repeat summary gets its full length.
(function () {
  const TAG = 'RAIDSCROLL';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  const RAID = '_ZN22RaidResultSummaryScene16getDropItemCountEv';
  const BASE = '_ZN18ResultSummaryScene16getDropItemCountEv';
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    const raidP = m.findExportByName(RAID), baseP = m.findExportByName(BASE);
    if (!raidP || !baseP) { log('symbol missing, not installed'); return; }
    const raid = new NativeFunction(raidP, 'int', ['pointer']);
    const base = new NativeFunction(baseP, 'int', ['pointer']);
    let logged = 0;
    Interceptor.replace(raidP, new NativeCallback(function (self) {
      const r = raid(self);
      let b = r;
      try { b = base(self); } catch (e) { log('base ERR ' + e); }
      if (logged < 20 && (b !== r || logged < 3)) { logged++; log('raid=' + r + ' summary=' + b); }
      return b > r ? b : r;
    }, 'int', ['pointer']));
    log('installed');
  }, 50);
})();
