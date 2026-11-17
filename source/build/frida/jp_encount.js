// jp_encount.js — exploration random encounters (2026-11-10), with jp_compat.install_encount.
//
// MapManager::checkEncountFiled(field) asks EncountInfoList::checkEnable(field, group, n) with
// n = EncountLogList::getEncountNum(field, group) = how many times this group was met in this mission. The real
// tables listed a row per n; the engine sends one row (h4Sjf96p = 0) per field and group, so n is pinned to 0
// and a group can be met again.
(function () {
  const TAG = 'ENCOUNT';
  function log(s) { try { note(TAG + ' ' + s); } catch (e) { console.log(TAG + ' ' + s); } }
  const wait = setInterval(() => {
    const m = Process.findModuleByName('libgame.so'); if (!m) return; clearInterval(wait);
    const p = m.findExportByName('_ZN14EncountLogList13getEncountNumEii');
    if (!p) { log('missing EncountLogList::getEncountNum'); return; }
    let calls = 0;
    Interceptor.replace(p, new NativeCallback(function (self, field, group) {
      if (++calls <= 3) log('getEncountNum(' + field + ',' + group + ') -> 0');
      return 0;
    }, 'int', ['pointer', 'int', 'int']));
    log('hook installed');
  }, 50);
})();
