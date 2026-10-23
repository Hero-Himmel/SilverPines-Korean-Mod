<p align="center">
  <img src="resource/images/header.jpg" alt="Silver Pines" width="460">
</p>

# Silver Pines 한국어 MOD

Silver Pines를 한국어로 플레이할 수 있도록 제작한 비공식 한글 패치입니다. **Windows Steam판**을 지원합니다.

현재 패치 버전은 **26.10.16-c**입니다. 게임 업데이트 날짜를 기준으로 한 `YY.MM.DD-차수` 표기를 사용하며, 게임의 공식 버전 번호와는 별개입니다.

## 설치 방법

1. 게임을 종료합니다.
2. 이 저장소의 Releases에서 `SilverPines-Korean-<버전>-windows.zip`을 내려받아 압축을 풉니다.
3. `SilverPinesKoreanPatcher.exe`를 실행합니다. Python을 별도로 설치할 필요는 없습니다.
4. 패처가 Steam 라이브러리의 게임 경로를 자동으로 찾습니다. 찾지 못하면 `Carpenter.exe`가 있는 게임 폴더를 입력합니다.
5. `한국어 패치 설치 / 업데이트`를 선택합니다.
6. 게임 언어 설정에서 `한국어`를 선택합니다.

일반적인 Steam 설치 경로는 다음과 같습니다.

```text
C:\Program Files (x86)\Steam\steamapps\common\Silver Pines
```

패처는 사용자의 게임 원본을 읽어 번역과 폰트를 적용한 파일을 생성합니다. 게임 원본 파일은 배포 파일에 포함하지 않습니다. 지원 여부는 원본 파일의 SHA-256으로 확인하며, 검증하지 않은 게임 빌드에는 패치를 적용하지 않습니다.

## 패치 제거 및 복구

게임을 종료한 뒤 `SilverPinesKoreanPatcher.exe`를 다시 실행하고 `원본 파일 복구`를 선택하세요.

원본 백업은 게임 폴더의 `.silverpines-ko-backup`에 보관합니다. 복구에 필요하므로 삭제하지 마세요. 같은 원본 버전에 패치를 업데이트하면 최초 원본 백업을 유지하며, 설치 도중 오류가 발생하면 교체 전 상태로 되돌립니다.

게임 업데이트 후 호환되지 않거나 백업으로 복구할 수 없다면 [Steam 게임 파일 무결성 검사 안내](https://help.steampowered.com/ko/faqs/view/0C48-FCBD-DA71-93EB)에 따라 게임 파일을 복구하세요. 이후 해당 게임 버전을 지원하는 패치를 적용하세요.

## 폴더 구조

- `resource/translations.json` — 번역문과 원문 유지 사유
- `resource/translation-guide.md` — 인물명·지명·용어 및 번역 원칙
- `resource/source-manifest.json` — 지원하는 게임 원본 파일의 체크섬
- `resource/version.json` — 패치 버전과 배포 설정
- `resource/fonts/` — Noto Sans KR Regular/Bold와 폰트 라이선스
- `tool/patch.py` — 문자열·폰트·카탈로그 변환
- `tool/install.py` — 원본 검사·백업·파일 교체·복구
- `tool/runtime_patcher.py` — Windows 실행형 패처
- `tool/package_release.py` — EXE와 배포 ZIP 생성
- `tool/verify_release.py` — 배포 파일 구성과 무결성 검사
- `.github/workflows/release.yml` — GitHub Actions 빌드 및 Release 게시

개발 환경 설정, 명령줄 사용법, 빌드·배포 절차는 [개발 안내](DEVELOPMENT.md)를 참고하세요.

## OFL

이 패치에는 Noto Sans KR 폰트가 포함되어 있으며, 해당 폰트는 [SIL Open Font License 1.1](resource/fonts/OFL.txt)에 따라 배포됩니다.

시계·키패드·버튼 기호에 쓰이는 특수 폰트는 유지합니다.

## 제작자

- 한국어 MOD 제작: [@himmel_dev](https://x.com/himmel_dev)

## 피드백

오역, 문장 잘림, 퍼즐 단서 또는 패치 오류는 이 저장소의 Issues에 올려 주세요. 문제가 발생한 화면과 상황, 패치 버전을 함께 적어 주시면 확인에 도움이 됩니다.

## 주의 사항

이 MOD는 비공식입니다. 사용에 따른 책임은 사용자 본인에게 있습니다.

게임 본체의 원문과 각종 소재에 대한 권리는 각각의 권리자에게 있습니다.

번역은 AI를 활용했습니다. 번역 데이터를 다른 MOD에 포함해 재배포하거나, 직접 만든 번역인 것처럼 배포하는 행위는 삼가 주세요.
