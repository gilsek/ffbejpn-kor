// 읽기 전용 사운드 진단 (2026-11-09). deploy_jp_frida.py --sound-trace 일 때만 jp_offline.js 뒤에 붙는다.
// 인자·반환값을 기록만 하고 바꾸지 않는다. 태그 EXVIUS_SND.
// 가설: BGM·가챠 효과음 acb는 EncodeType 6(HCA-MX로 추정), 잘 나는 SE는 EncodeType 2(HCA).
// HCA-MX 초기화·보이스 풀·재생 시작 결과와 CRI 오류 메시지를 본다.
(function () {
  const logw = new NativeFunction(Module.getGlobalExportByName('__android_log_write'), 'int', ['int', 'pointer', 'pointer']);
  const TAG = Memory.allocUtf8String('EXVIUS_SND');
  const say = s => logw(4, TAG, Memory.allocUtf8String(String(s)));
  const cstr = p => { try { return p.isNull() ? '(null)' : p.readUtf8String(300); } catch (e) { return '(bad)'; } };
  const words = (p, n) => { try { const a = []; for (let i = 0; i < n; i++) a.push(p.add(i * 4).readS32()); return a.join(','); } catch (e) { return '(bad)'; } };
  const floatAt = (p, o) => { try { return p.add(o).readFloat().toFixed(1); } catch (e) { return '?'; } };

  function go(m) {
    const at = (name, cb) => {
      const a = m.findExportByName(name);
      if (!a) { say('NO_SYMBOL ' + name); return; }
      try { Interceptor.attach(a, cb); } catch (e) { say('HOOK_FAILED ' + name + ' ' + e); }
    };
    // CRI 오류·경고 메시지(포맷 문자열 + 정수 인자).
    for (const n of ['criErr_Notify', 'criErr_Notify1', 'criErr_Notify2', 'criErr_NotifyGeneric', 'criErr_NotifyErrorSimple', 'criErr_NotifyWarningSimple']) {
      let c = 0;
      at(n, { onEnter(a) { if (c++ < 200) say('CRI_ERR ' + n + ' level=' + a[0].toInt32() + ' msg=' + cstr(a[1]) + ' p=' + a[2].toInt32() + ',' + a[3].toInt32()); } });
    }
    // HCA-MX / HCA 초기화와 보이스 풀.
    at('criAtomExHcaMx_Initialize', { onEnter(a) {
      // CriAtomExHcaMxConfig: server_frequency(float), num_mixers, max_voices, max_input_channels, max_sampling_rate, output_channels, output_sampling_rate, sound_renderer_type
      say('HCAMX_INIT cfg=' + a[0] + ' server_hz=' + floatAt(a[0], 0) + ' ints=' + words(a[0].add(4), 7) + ' work=' + a[1] + ' size=' + a[2].toInt32());
    }, onLeave() { say('HCAMX_INIT done'); } });
    at('criAtomExHcaMx_CalculateWorkSize', { onEnter(a) { this.c = a[0]; }, onLeave(r) { say('HCAMX_WORKSIZE -> ' + r.toInt32() + (this.c.isNull() ? ' (default cfg)' : ' ints=' + words(this.c.add(4), 7))); } });
    at('criAtomHcaMx_Initialize', { onLeave() { say('ATOM_HCAMX_INIT done'); } });
    for (const n of ['criAtomExVoicePool_AllocateHcaMxVoicePool', 'criAtomExVoicePool_AllocateHcaVoicePool', 'criAtomExVoicePool_AllocateStandardVoicePool', 'criAtomExVoicePool_AllocateRawPcmVoicePool']) {
      at(n, { onEnter(a) { this.c = a[0]; }, onLeave(r) { say('VOICEPOOL ' + n.replace('criAtomExVoicePool_Allocate', '') + ' -> ' + r + (this.c.isNull() ? ' (default cfg)' : ' cfg=' + words(this.c, 10))); } });
    }
    at('criAtomEx_Initialize_ANDROID', { onEnter(a) { say('ATOMEX_INIT_ANDROID cfg=' + a[0]); }, onLeave() { say('ATOMEX_INIT_ANDROID done'); } });
    for (const n of ['criAtomEx_RegisterAcfFile', 'criAtomEx_RegisterAcfData', 'criAtomEx_RegisterAcfConfig']) {
      at(n, { onEnter(a) { this.p = n === 'criAtomEx_RegisterAcfFile' ? cstr(a[1]) : ''; }, onLeave(r) { say('ACF ' + n + ' ' + this.p + ' -> ' + r); } });
    }
    // ACB 로드와 재생.
    let loads = 0;
    at('criAtomExAcb_LoadAcbFile', { onEnter(a) { this.p = cstr(a[1]); this.w = cstr(a[3]); }, onLeave(r) { if (loads++ < 300) say('ACB_LOAD ' + this.p + ' awb=' + this.w + ' -> ' + r); } });
    at('criAtomExAcb_LoadAcbData', { onEnter(a) { this.n = a[1].toInt32(); }, onLeave(r) { if (loads++ < 300) say('ACB_LOAD_DATA size=' + this.n + ' -> ' + r); } });
    let cues = 0;
    at('criAtomExPlayer_SetCueName', { onEnter(a) { if (cues++ < 400) say('CUE_NAME player=' + a[0] + ' acb=' + a[1] + ' ' + cstr(a[2])); } });
    at('criAtomExPlayer_SetCueId', { onEnter(a) { if (cues++ < 400) say('CUE_ID player=' + a[0] + ' acb=' + a[1] + ' id=' + a[2].toInt32()); } });
    let starts = 0;
    const getStatus = (() => { const a = m.findExportByName('criAtomExPlayer_GetStatus'); return a ? new NativeFunction(a, 'int', ['pointer']) : null; })();
    at('criAtomExPlayer_Start', { onEnter(a) { this.pl = a[0]; }, onLeave(r) {
      if (starts++ >= 400) return;
      const pl = this.pl, id = r.toInt32();
      say('START player=' + pl + ' -> playback ' + id + (getStatus ? ' status=' + getStatus(pl) : ''));
      // 200ms 뒤 상태: 0 STOP, 1 PREP, 2 PLAYING, 3 PLAYEND, 4 ERROR
      if (getStatus) setTimeout(() => { try { say('STATUS+200ms player=' + pl + ' playback ' + id + ' = ' + getStatus(pl)); } catch (e) {} }, 200);
    } });
    // 볼륨은 float 인자라 s0 레지스터에 있다.
    const s0 = ctx => { try { return Number(ctx.s0).toFixed(2); } catch (e) { return '?'; } };
    at('criAtomExCategory_SetVolumeByName', { onEnter(a) { say('CATEGORY_VOL ' + cstr(a[0]) + ' = ' + s0(this.context)); } });
    at('criAtomExCategory_SetVolume', { onEnter(a) { say('CATEGORY_VOL id=' + a[0].toInt32() + ' = ' + s0(this.context)); } });
    at('criAtomExCategory_SetVolumeById', { onEnter(a) { say('CATEGORY_VOL id=' + a[0].toInt32() + ' = ' + s0(this.context)); } });
    say('SOUND_TRACE_READY libgame=' + m.base);
  }
  const t = setInterval(() => { const m = Process.findModuleByName('libgame.so'); if (m) { clearInterval(t); go(m); } }, 5);
})();
