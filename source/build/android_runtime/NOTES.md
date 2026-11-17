# android_runtime — 배포용 다운로더 (2026-11-17)

JP 11.0.0 오프라인 앱의 첫 실행 데이터 다운로드/설치 런타임. 영문 Exvius Offline의
`com.exvius.local` 구조를 본뜨되 Android `DownloadManager` 대신 앱 프로세스 안의
`HttpURLConnection` 다운로더를 쓴다.

## 파일
- `src/com/exvius/local/DataUpdates.java` — 상태/매니페스트 검증/HTTP 전송(리다이렉트·Range 이어받기·
  3회 지수 재시도·크기·SHA-256·`.verified`)/설치 저널/공간 검사/APK 업데이트.
- `src/com/exvius/local/DataDownloadService.java` — 같은 프로세스 포그라운드 서비스
  (`foregroundServiceType="dataSync"`), 진행률 알림 채널, WifiLock + 부분 WakeLock.
- `src/com/exvius/local/DataDownloadActivity.java` — 런처(배포 빌드), 한국어 UI, 재시도 버튼,
  POST_NOTIFICATIONS 요청.
- `src/com/exvius/local/DataPack.java` — 팩 엔트리 → 설치 경로, 경로 탈출·중복 목적지·엔트리 수·
  unpackedSize 검사, `.installing` 원자 교체.
- `tools/DexToSmali.java` — apktool_3.0.3.jar의 smali/dexlib2(cli 없음)로 dex→smali 변환.

## 빌드 연결
`build/jp_offline_build.py`가 `install_runtime()`에서 javac(--release 8, android-36) →
d8(--min-api 21) → DexToSmali → `work/smali_classes5/com/exvius/local/`로 넣는다.
같은 패키지의 옛 `DataUpdates*`·`DataPack*`·`DataDownloadActivity*` smali는 merge_runtime()에서
지운다(GameAssets·Local* 는 영문 빌드 그대로 유지, JP에서는 미사용).
`--release`가 배포 모드: 런처 전환, debuggable 제거, versionCode 200/versionName 0.1.0,
Frida 묶음 내장(상대 경로 config), `pageSizeCompat="enabled"`, FileProvider, 서비스/권한 선언.
`--manifest-url`/`--assets-prefix`는 DataUpdates 상수 두 줄만 치환하는 시험용.
개발 빌드에서는 `REQUIRE_INSTALLED` 상수를 false로 바꿔 컴파일한다(개발 데이터는 adb/run-as로
복사해 `exvius/data/installed.json`이 없으므로 ready()가 마스터 파일만 검사하던 예전 동작 유지).

## 팩 배치 (기기 실험 2026-11-17 반영)
- `static/..` → `files/exvius/data/static/..`
- `metadata/registry.json` → `files/exvius/data/registry.json` (keyF_* → SharedPreferences `gamedata` 유지)
- `ui_ko/..` → `files/exvius/ui_ko/..`
- `res/flat/<파일명>`, `res/mst/<하위>/<파일명>` → `files/<파일명>` (평면화, 같은 파일명 중복 거부)
- 그 밖은 거부. 설치 후 `files/` 바로 아래 `*.i` 삭제.

## 배포 빌드/검사
```
set EXVIUS_KR_KS_PASS=...   (없으면 -debugkey 시험본)
python -I -X utf8 build/build_release_apk.py
산출물 build/out/release_apk/v0.1.0/*.apk (base + split 3개, install-multiple)
```
검사: dex/so/xml에 `/data/local/tmp` 0건, debuggable 없음, libgame.so 원본 해시, 내장 js.so가
deploy_jp_frida.build_bundle(release=True)와 바이트 일치, 런처 DataDownloadActivity, versionCode/Name.

## 의심/미확인
- `libexviustest.so`(Frida/V8 gadget)에 개발 경로 문자열 1개가 있어 배포 split에서 같은 길이
  `/data/local/tmx`로 덮었다(V8 기본 폴백 경로, 미사용). 다른 경로 의미는 없음.
- 배포 키 서명은 비밀번호가 없어 실행하지 못함(`EXVIUS_KR_KS_PASS` 필요). 디버그 키 시험본만 통과.
- 기기 미실행: 실제 GitHub 리다이렉트/이어받기, 포그라운드 서비스 생존, FileProvider APK 설치,
  `pageSizeCompat` 동작. stage 0(클라이언트 addLoadFile 스킵) 결과는 main 보고 기준.
