// 장면 자료가 없는 Rm 스토리 노드(build/engine_overlay/jp_rm_noscene.json): 들어가면 클리어.
// 이 노드들은 지도만 뜨고 미션을 끝낼 장면 스크립트가 없다. 지도 화면이 뜬 뒤 미션 종료 화면
// (GameSceneFactory::createGameScene case 13009 = RmMissionEndScene, RmEndRequest를 보냄)으로 넘긴다.
// 미션 id는 UserState+0x118 (RmBattleScene::exitRmWaveResult가 같은 값을 읽는다).
// 목록은 deploy_jp_frida.py가 아래 배열에 채운다.
const JP_RM_NOSCENE = /*__RM_NOSCENE__*/[];
function installJpRmNoscene(m, note) {
  const ids = new Set(JP_RM_NOSCENE.map(Number));
  if (!ids.size) { note('RM_NOSCENE list empty; hook not installed'); return; }
  const userState = new NativeFunction(m.getExportByName('_ZN9UserState6sharedEv'), 'pointer', []);
  const changeById = new NativeFunction(m.getExportByName('_ZN9GameScene22changeSceneWithSceneIDEib'), 'void', ['pointer', 'int', 'bool']);
  const SCENE_RM_MISSION_END = 13009, WAIT_FRAMES = 45;
  let scene = null, frames = 0, done = false;
  Interceptor.attach(m.getExportByName('_ZN8MapSceneC1Ev'), { onEnter(a) { scene = a[0]; frames = 0; done = false; } });
  Interceptor.attach(m.getExportByName('_ZN8MapScene11updateEventEv'), {
    onEnter(a) { this.t = a[0]; },
    onLeave() {
      if (done || scene === null || !this.t.equals(scene)) return;
      if (++frames < WAIT_FRAMES) return;
      done = true;
      try {
        const mission = userState().add(0x118).readS32();
        if (!ids.has(mission)) return;
        note('RM_NOSCENE_CLEAR ' + mission);
        changeById(this.t, SCENE_RM_MISSION_END, 0);
      } catch (e) { note('RM_NOSCENE_CLEAR failed ' + e); }
    } });
  note('RM_NOSCENE ready n=' + ids.size);
}
