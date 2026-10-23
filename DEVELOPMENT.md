# Silver Pines 한국어 패치 개발 안내

사용자의 게임 원본을 읽어 한글화 파일을 생성하는 Windows용 패치 프로젝트입니다.
현재는 **전체 텍스트 번역 초안**입니다. 전체 3,469행 중 3,406행을 한국어로 번역하고,
객실 기호·제품명·엔딩명·빈 항목·개발용 자리표시자 등 63행은 원문을 유지합니다. 미처리 행은 없습니다.
대사 1,188행, 아이템 728행, 조사 문구 326행, 문서 160행을 포함한 24개 테이블을 모두 처리했습니다.
기본 한글 표시와 폰트 동작은 플레이에서 확인했습니다. 전체 진행을 통한 문맥·줄바꿈·퍼즐 검수는 남아 있습니다.

## 배포판 설치

GitHub Release의 `SilverPines-Korean-<버전>-windows.zip`을 받아 압축을 풀고
`SilverPinesKoreanPatcher.exe`를 실행합니다. Python 설치는 필요하지 않습니다.

1. 게임을 종료합니다.
2. 패처가 Steam 라이브러리의 게임 폴더를 찾습니다. 못 찾으면 `Carpenter.exe`가 있는 폴더를 입력합니다.
3. `한국어 패치 설치 / 업데이트`를 선택합니다.
4. 게임 언어에서 `한국어`를 선택합니다. 자체 언어명이 남아 있는 화면에서는 번체 중국어 항목을 선택합니다.

원본으로 되돌리려면 같은 EXE를 실행하고 `원본 파일 복구`를 선택합니다.
원본 백업은 게임 폴더의 `.silverpines-ko-backup`에 보관합니다.

명령줄에서도 사용할 수 있습니다.

```powershell
.\SilverPinesKoreanPatcher.exe --game '게임 폴더' --check
.\SilverPinesKoreanPatcher.exe --game '게임 폴더' --apply
.\SilverPinesKoreanPatcher.exe --game '게임 폴더' --restore
```

`--check`는 원본 확인과 패치 생성·검증만 수행하고 게임을 변경하지 않습니다.
지원 여부는 원본 파일 SHA-256으로 판단하며, 검증하지 않은 게임 빌드에는 적용하지 않습니다.

## 구성과 동작

- 번체 중국어(`zh-Hant`) 슬롯을 한국어로 활용합니다. 이 슬롯의 폰트 번들에 원본 Font 객체가 포함되어 있어 로컬 참조를 유지할 수 있습니다.
- Noto Sans KR Regular/Bold를 넣고 TextMeshPro 폰트를 Dynamic SDF로 전환합니다. 기존 중국어 글리프·문자·커닝·아틀라스 데이터는 초기화하고 multi-atlas를 활성화합니다.
- 게임 실행 시 필요한 문자를 원본 OTF에서 생성하는 방식입니다. 기본 동작을 확인했으며, 전체 번역의 장문 레이아웃과 성능은 플레이 검수가 필요합니다.
- 시계·키패드·버튼 기호 폰트는 수정하지 않습니다. 특수 폰트가 쓰이는 화면과 번역문은 플레이 검수에서 대조해야 합니다.
- 영문 테이블의 ID와 메타데이터를 기준으로 번역을 주입합니다. 원문 유지 항목은 이유를 기록합니다. 향후 새 문장이 추가되면 영어로 표시하며, 현재 기준 미처리 문장은 없습니다.
- 빈 대상 테이블에도 영문 행을 넣으며, Smart String의 관리 참조 타입과 메타데이터를 보존합니다.
- Addressables 2.9.1 binary catalog v2의 번들 요청 옵션을 확인해 크기를 수정합니다. CRC가 켜져 있으면 갱신하고, 원본에서 꺼져 있으면 그대로 유지합니다.
- 현재 로컬 카탈로그의 `catalog.hash`는 버전 토큰으로 유지합니다. 원격 카탈로그·로컬 UnityWebRequest 설정은 지원하지 않습니다.

`Carpenter.exe`가 있는 게임 폴더와 별도 출력 폴더를 사용합니다. 생성 단계는 게임 설치본을 수정하지 않습니다.

## 현재 PC에서 실행

프로젝트 폴더에서 PowerShell로 실행합니다. `run.ps1`은 프로젝트 가상환경, 사용 가능한 로컬 Python 런타임 순서로 찾으며, 로컬 `.tools/pydeps`가 있으면 사용합니다.

```powershell
# 원문 추출: inputs/english.json
.\run.ps1 extract

# 번역 ID, 원문 변경, 변수, 서식 태그 검사
.\run.ps1 validate

# 패치가 적용된 설치본에서도 원본 백업을 이용해 빌드 입력을 준비할 수 있음
# 아래 '원본 입력 사본' 절 참고

# 새 출력 폴더에 패치 생성 (비어 있지 않은 폴더에는 생성하지 않음)
.\run.ps1 build -GamePath .\inputs\pristine-game -OutputPath .\artifacts\full-ko-v2

# 기본 생성물의 원본/출력 해시 검사 (게임 변경 없음)
.\run.ps1 check

# 테스트
.\run.ps1 test
```

기본 게임 경로는 `C:\Program Files (x86)\Steam\steamapps\common\Silver Pines`입니다.
다른 경로에서는 `-GamePath '게임 폴더'`를 지정하세요.

## 번역 초안 설치와 복구

**게임을 종료한 상태에서** 실행합니다. 설치/복구도 기본 동작은 검사이며 `-Apply`를 지정해야 실제로 교체합니다.

```powershell
# 검사만
.\run.ps1 install

# 실제 설치
.\run.ps1 install -Apply

# 복구 검사 / 실제 복구
.\run.ps1 restore
.\run.ps1 restore -Apply
```

기본 출력은 `artifacts/full-ko-v1`입니다. 다른 생성물은 `-OutputPath`로 지정하세요.

게임 언어 설정에서 한국어 또는 기존 번체 중국어(Traditional Chinese) 항목을 선택합니다.
Locale 표시 이름은 한국어로 바꾸지만 게임이 자체 언어명을 사용하는 화면은 여전히 번체 중국어로 표시될 수 있습니다.
내부 언어 코드는 `zh-Hant`를 유지합니다.

설치기는 게임 폴더의 `.silverpines-ko-backup`에 원본과 복구 기록을 보관한 후 4개 파일을 교체합니다.
파일 교체 오류 시 자동 롤백합니다. 비정상 종료 시에도 기록과 백업으로 복구할 수 있습니다.
게임이 업데이트되거나 다른 수정이 감지되면 덮어쓰기를 중단합니다.
기존 테스트판이 설치돼 있어도 동일한 원본 버전이면 바로 업데이트할 수 있습니다.
업데이트 시 게임 원본 백업은 유지하고, 실패하면 업데이트 직전 패치로 되돌립니다.
업데이트가 중단된 경우 복구 명령으로 게임 원본을 복원할 수 있습니다. 복구 후에도 백업은 남습니다.

## 원본 입력 사본

`tool.pristine`은 설치본과 원본 백업의 SHA-256을 확인해 빌드에 필요한 파일만 로컬에 복사합니다.
게임에 적용된 패치를 제거하거나 진행 중인 플레이에 영향을 주지 않습니다.
현재 PC에서는 `inputs/pristine-game`에 준비돼 있습니다.

개발 환경의 Python에서 다음 명령을 사용할 수 있습니다.

```powershell
python -m tool.pristine --game 'C:\Program Files (x86)\Steam\steamapps\common\Silver Pines'
```

## 새 개발 환경

Python 3.10 이상을 설치하고 아래 명령을 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`resource/source-manifest.json`은 현재 분석한 설치본의 파일 SHA-256을 지정합니다.
게임 업데이트 후에는 새 원본을 분석하고 테이블·카탈로그·폰트 호환성을 검증한 다음 갱신해야 합니다.
단순히 새 해시만 등록해 호환성 검사를 우회하지 마세요.

## 번역과 배포

- `resource/translations.json`: 전체 원문에 대응하는 번역/원문 유지 사유, 원문 SHA-256, 테이블/문자열 ID, 키. JSON ID는 정밀도 손실을 피하도록 문자열로 저장합니다.
- `resource/translation-guide.md`: 인물명·지명·용어와 번역 톤, 퍼즐 단서 보존 원칙.
- `inputs/english.json`: 로컬에서 추출한 전체 원문. Git 및 배포에서 제외합니다.
- `artifacts/`: 로컬 생성물과 보고서. 게임 에셋이 포함되므로 배포하지 않습니다.
- `tool/patch.py`: 추출·검증·문자열·폰트·카탈로그 변환.
- `tool/install.py`: 해시 검사·백업·파일 교체·복구.
- `tool/pristine.py`: 설치된 패치를 유지한 채 원본 백업에서 빌드 입력 준비.
- `tool/translation_workflow.py`: 원문 export 해시를 검증하고 번역 배치를 안정적인 ID로 병합.
- `test/`: 변수/태그, binary catalog, 설치 실패 롤백, 업데이트 감지 테스트.

## GitHub Actions 자동 배포

`.github/workflows/release.yml`에서 Windows 실행형 패처를 빌드하고 Release에 게시합니다.

- `main` 푸시: 테스트 → EXE 생성 → ZIP/체크섬 검증 → GitHub Release 생성 또는 배포 파일 갱신.
- `v*` 태그 푸시: 같은 과정으로 배포. 태그는 버전 파일과 정확히 일치해야 합니다.
- `workflow_dispatch`: Actions 탭에서 수동 실행. `main`에서 실행하면 Release까지 게시합니다.
- Pull Request: 테스트와 EXE/ZIP 빌드·검증 후 Actions 아티팩트만 생성합니다.

버전의 단일 기준은 `resource/version.json`입니다. 현재 패치 버전은 `26.10.16-a`이고,
번역 검수 중인 버전이므로 `prerelease: true`로 설정되어 있습니다. 버전은 게임 업데이트 날짜를 기준으로 한 `YY.MM.DD-차수` 형식이며, 게임의 공식 버전 번호와는 별개입니다.
`release`를 바꾸면 ZIP 이름과 Release 태그가 함께 바뀝니다. 예를 들어 다음 태그가 대응합니다.

```text
resource/version.json: "release": "26.10.16-a"
Git tag: v26.10.16-a
```

GitHub 저장소의 기본 브랜치를 `main`으로 두고 이 프로젝트를 푸시하면 실행됩니다.
게시에는 워크플로의 `contents: write` 권한을 사용하므로 별도 개인 액세스 토큰은 필요하지 않습니다.
조직 정책에서 Actions의 쓰기 권한을 제한했다면 저장소 관리자가 허용해야 합니다.

배포 파일:

```text
SilverPines-Korean-26.10.16-a-windows.zip
SilverPines-Korean-26.10.16-a-windows.zip.sha256
```

ZIP에는 EXE, 사용법, 폰트 라이선스, 배포 manifest만 포함됩니다.
EXE에는 코드·번역·원본 체크섬·허용된 폰트만 넣습니다. 원문 전체 추출 파일이나 게임 에셋을 넣지 않습니다.
게임 원본과 변환 결과는 사용자의 설치본에서 실행 시 임시 생성합니다.
CI는 게임 파일 없이 실행되며, ZIP 파일 목록·해시·EXE 내부 리소스·`--self-test` 실행까지 검사합니다.

로컬 배포 빌드도 동일한 명령을 사용합니다. Windows의 개발 환경에서 실행하세요.

```powershell
python -m pip install -r requirements-release.txt
python -m unittest discover -s test -v
python -m tool.package_release
python -m tool.verify_release
```

출력은 `artifacts/release`입니다. 같은 버전을 다시 빌드하려면 새 `--output-root`를 지정하거나
이전에 생성한 해당 ZIP과 체크섬을 옮긴 뒤 빌드하세요. 개발 환경의 `inputs/`, `.tools/`, 게임 에셋이 든
`artifacts/full-ko-v1` 등은 저장소와 Release에 포함하지 않습니다.

Noto Sans KR 원본 OTF는 수정하지 않고 임베드합니다. 폰트는 [SIL Open Font License 1.1](resource/fonts/OFL.txt)을 따릅니다.
폰트 원본: https://github.com/notofonts/noto-cjk/tree/main/Sans/SubsetOTF/KR
