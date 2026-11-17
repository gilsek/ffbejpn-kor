# Exvius KR 소스 (v0.1.0 기준)

v0.1.0 배포판(APK·데이터 팩)을 만든 코드입니다. 이 폴더만으로는 빌드되지 않습니다. 아래 "들어 있지 않은 것"이 따로 필요합니다.

## 구조
| 경로 | 내용 |
|---|---|
| `build/frida/` | 게임 본체(`libgame.so`)는 원본 그대로 두고 동작을 바꾸는 Frida 후킹 스크립트. `build/deploy_jp_frida.py`가 하나로 묶습니다(배포판은 `RELEASE_EXCLUDE` 제외). |
| `build/engine_overlay/` | 오프라인 엔진(Chaquopy 파이썬)에 얹는 일본판 대응 코드와 표 데이터. `jp_compat.py`의 `install()`이 시작점입니다. |
| `build/android_runtime/` | 첫 실행 때 GitHub 릴리스에서 데이터 팩을 받는 다운로더(Java). |
| `build/java/` | 마스터 데이터 빠른 복호화(`FastDecode`). |
| `build/*.py` | APK 조립(`jp_offline_build.py`, `build_release_apk.py`), 데이터 팩(`build_release_data_jp.py`), 한국어 적용(`apply_ko_*.py`), 배너·상점·가챠 표 생성(`make_jp_*.py`), 검사(`validate_*`, `test_*`). |
| `tools/` | CPK·마스터 데이터 리더, 감사·점검 스크립트, UI 그림 작업 도구. |
| `translations/` | 번역 파이프라인(GalTransl 입력 생성, 수동 보정, 기계 점검)과 용어집(`chapter1-ko/Dict/gpt_dict.txt`, `monster-skills-ko/canonical_terms.json`). |
| `scripts/` | 일본판 데이터 아카이브 받기·검증. |

## 들어 있지 않은 것
- 오프라인 엔진 원본: [Elvlin/exvius-offline](https://github.com/Elvlin/exvius-offline). 라이선스가 명시돼 있지 않아 복사하지 않았습니다. 일부 스크립트가 `tools/upstream_ref/`(엔진 저장소의 참조 파일)를 불러오는데, 이 폴더도 엔진 저장소에서 가져와야 합니다.
- 게임 데이터·APK·Frida Gadget 바이너리·번역 결과물(대량 산출물)·서명 키.
- 개발 기기 경로는 `C:\Users\USER\...`, `<tablet-ip>` 같은 자리표시자로 바꿨습니다. 쓰려면 자기 환경에 맞게 고쳐야 합니다.

## 라이선스
이 폴더의 코드와 용어집은 MIT입니다([`LICENSE`](LICENSE)). 게임 데이터와 상위 엔진, 영문판 클래스를 따른 다운로더 일부는 해당하지 않습니다.
