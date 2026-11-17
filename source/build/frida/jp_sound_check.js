// 빠진 소리 기록 (2026-11-09). deploy_jp_frida.py --sound-check 일 때만 jp_offline.js 뒤에 붙는다. 읽기 전용.
// 재생을 시작한 cue마다 250ms 뒤 상태를 보고, 처음 본 cue와 실패한 cue를 앱 폴더 파일에 남긴다(logcat은 금방 밀려 사라짐).
//   files/exvius/sound_check.log  (탭 구분: 시각, 판정, acb 크기, cue id, cue 이름, cue 길이 ms, 플레이어 상태, 재생 상태)
// 판정: FAIL_ERROR = 플레이어 상태 4(ERROR). FAIL_EARLY = 250ms 안에 재생이 끝났는데 cue 길이가 600ms 넘거나 루프(-1).
//       OK = 그 밖. 분석: python -I tools/sound_check_report.py
(function () {
  const OUT = '/data/data/com.exvius.jpkorean.app/files/exvius/sound_check.log';
  const libc = Process.getModuleByName('libc.so');
  const fopen = new NativeFunction(libc.getExportByName('fopen'), 'pointer', ['pointer', 'pointer']);
  const fputs = new NativeFunction(libc.getExportByName('fputs'), 'int', ['pointer', 'pointer']);
  const fflush = new NativeFunction(libc.getExportByName('fflush'), 'int', ['pointer']);
  let fp = null;
  function write(line) {
    if (!fp) { fp = fopen(Memory.allocUtf8String(OUT), Memory.allocUtf8String('a')); if (fp.isNull()) { fp = null; return; } }
    fputs(Memory.allocUtf8String(line + '\n'), fp); fflush(fp);
  }
  const stamp = () => new Date().toISOString().substring(11, 23);
  const cstr = p => { try { return p.isNull() ? '' : p.readUtf8String(120); } catch (e) { return ''; } };

  function go(m) {
    const fn = (n, ret, args) => { const a = m.findExportByName(n); return a ? new NativeFunction(a, ret, args) : null; };
    const playerStatus = fn('criAtomExPlayer_GetStatus', 'int', ['pointer']);
    const playbackStatus = fn('criAtomExPlayback_GetStatus', 'int', ['uint32']);
    const cueNameById = fn('criAtomExAcb_GetCueNameById', 'pointer', ['pointer', 'int']);
    const cueInfoById = fn('criAtomExAcb_GetCueInfoById', 'int', ['pointer', 'int', 'pointer']);
    const info = Memory.alloc(1024);
    const at = (n, cb) => { const a = m.findExportByName(n); if (a) Interceptor.attach(a, cb); else write(stamp() + '\tNO_SYMBOL\t' + n); };

    const acbSize = new Map();   // handle -> data size (파일 이름은 분석 스크립트가 크기로 찾는다)
    const cueOf = new Map();     // player -> {acb, id, name}
    const seen = new Map();      // acb|cue -> 마지막 판정
    at('criAtomExAcb_LoadAcbData', { onEnter(a) { this.n = a[1].toInt32(); }, onLeave(r) { if (!r.isNull()) acbSize.set(r.toString(), this.n); } });
    at('criAtomExPlayer_SetCueId', { onEnter(a) { cueOf.set(a[0].toString(), { acb: a[1], id: a[2].toInt32(), name: null }); } });
    at('criAtomExPlayer_SetCueName', { onEnter(a) { cueOf.set(a[0].toString(), { acb: a[1], id: null, name: cstr(a[2]) }); } });
    at('criAtomExPlayer_SetCueIndex', { onEnter(a) { cueOf.set(a[0].toString(), { acb: a[1], id: null, name: 'index:' + a[2].toInt32() }); } });
    at('criAtomExPlayer_Start', { onEnter(a) { this.pl = a[0]; }, onLeave(r) {
      const pl = this.pl, pb = r.toUInt32(), cue = cueOf.get(pl.toString());
      if (!cue) return;
      let name = cue.name || '', length = '?';
      try {
        if (cue.id !== null) {
          if (cueNameById) name = cstr(cueNameById(cue.acb, cue.id));
          if (cueInfoById && cueInfoById(cue.acb, cue.id, info)) length = info.add(24).readS64().toString();
        }
      } catch (e) {}
      const size = acbSize.get(cue.acb.toString()) || 'file';
      setTimeout(() => {
        let ps = -1, bs = -1;
        try { ps = playerStatus ? playerStatus(pl) : -1; bs = playbackStatus ? playbackStatus(pb) : -1; } catch (e) {}
        const len = Number(length);
        let verdict = 'OK';
        if (ps === 4) verdict = 'FAIL_ERROR';
        else if (bs === 3 && (len === -1 || len > 600)) verdict = 'FAIL_EARLY';  // 3 = REMOVED(끝남)
        const key = size + '|' + (cue.id !== null ? cue.id : name);
        if (verdict === 'OK' && seen.get(key) === 'OK') return;  // 성공은 cue마다 한 번만
        seen.set(key, verdict);
        write([stamp(), verdict, size, cue.id === null ? '-' : cue.id, name, length, ps, bs].join('\t'));
      }, 250);
    } });
    let errs = 0;
    for (const n of ['criErr_Notify', 'criErr_Notify1', 'criErr_Notify2'])
      at(n, { onEnter(a) { if (errs++ < 500) write(stamp() + '\tCRI_ERR\t' + n + '\tlevel=' + a[0].toInt32() + '\tp=' + a[2].toInt32() + ',' + a[3].toInt32()); } });
    write(stamp() + '\tSTART\tsound_check ready libgame=' + m.base);
  }
  const t = setInterval(() => { const m = Process.findModuleByName('libgame.so'); if (m) { clearInterval(t); go(m); } }, 5);
})();
