"""Interactive, self-contained Windows patcher used by the packaged EXE."""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from . import install as installer
from .patch import ROOT, CompatibilityError, build, game_root
from .pristine import materialize
from .release_config import load_version, validate_resources
from .console_ui import (ProgressTimer, configure_console, format_duration,
                         set_warning_color, restore_console_color, read_confirmation)


def show_intro(release: str) -> None:
    print(f'Silver Pines 한국어 패치 {release}\n')
    color = set_warning_color()
    try:
        print('[주의 사항]')
        print('이 MOD는 비공식 한글 패치입니다.')
        print('게임을 종료한 뒤 진행해 주세요.')
        print('원본은 백업하며, 원본 복구 메뉴로 되돌릴 수 있습니다.')
        print('번역은 AI를 활용했습니다.')
        print('- 오역, 문제는 Issue에 올려주세요.')
        print('by. Himmel\n')
    finally:
        restore_console_color(color)


def show_menu() -> None:
    print('\n1. 한국어 패치 설치 / 업데이트')
    print('2. 원본 파일 복구')
    print('0. 종료\n')


def steam_installations() -> list[Path]:
    roots = []
    if sys.platform == 'win32':
        import winreg
        for hive, key, value in (
            (winreg.HKEY_CURRENT_USER, r'Software\Valve\Steam', 'SteamPath'),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Valve\Steam', 'InstallPath'),
        ):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    roots.append(Path(winreg.QueryValueEx(handle, value)[0]))
            except OSError:
                pass
    for variable in ('ProgramFiles(x86)', 'ProgramFiles'):
        base = os.environ.get(variable)
        if base:
            roots.append(Path(base) / 'Steam')
    return list(dict.fromkeys(roots))


def steam_libraries(roots: list[Path]) -> list[Path]:
    result = list(roots)
    for root in roots:
        path = root / 'steamapps/libraryfolders.vdf'
        if not path.is_file():
            continue
        try:
            contents = path.read_text(encoding='utf-8-sig')
        except OSError:
            continue
        for value in re.findall(r'"path"\s*"((?:\\.|[^"\\])*)"', contents):
            try:
                result.append(Path(json.loads('"' + value + '"')))
            except (ValueError, OSError):
                continue
    return list(dict.fromkeys(result))


def find_game() -> Path | None:
    for root in steam_libraries(steam_installations()):
        candidate = root / 'steamapps/common/Silver Pines'
        if (candidate / 'Carpenter.exe').is_file():
            return candidate
    return None


def normalize_game(path: Path) -> Path:
    if path.name.casefold() == 'carpenter.exe':
        path = path.parent
    return game_root(path)


def check_game_closed() -> None:
    if sys.platform != 'win32':
        raise CompatibilityError('이 패처는 Windows 전용입니다.')
    result = subprocess.run(
        ['tasklist.exe', '/FI', 'IMAGENAME eq Carpenter.exe', '/FO', 'CSV', '/NH'],
        capture_output=True, text=True, encoding='utf-8', errors='replace',
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if result.returncode:
        raise CompatibilityError('게임 실행 여부를 확인하지 못했습니다. 작업 관리자를 확인해 주세요.')
    for row in csv.reader(io.StringIO(result.stdout)):
        if row and row[0].casefold() == 'carpenter.exe':
            raise CompatibilityError('Silver Pines가 실행 중입니다. 게임을 종료하고 다시 실행하세요.')


def run_patch(game: Path, *, apply: bool, temporary_root: Path | None = None) -> dict:
    if apply:
        check_game_closed()
    resource = ROOT / 'resource'
    summary = validate_resources(resource)
    # Originals are read from the game or its verified backup. No original
    # game bytes or generated Unity assets are shipped in this application.
    progress = ProgressTimer()
    progress.start()
    try:
        with tempfile.TemporaryDirectory(prefix='silverpines-ko-', dir=temporary_root) as temporary:
            base = Path(temporary)
            progress.stage('[1/4] 게임 원본과 패치 호환성을 확인하는 중...')
            materialize(game, base / 'source', resource / 'source-manifest.json', quiet=True)
            progress.stage('[2/4] 한글 문장과 폰트로 패치 파일을 생성하는 중...')
            report = build(base / 'source', base / 'patch', resource / 'translations.json',
                           resource / 'source-manifest.json', resource / 'fonts')
            progress.stage('[3/4] 한글 패치를 게임 폴더에 적용하는 중...' if apply
                           else '[3/4] 생성된 패치 파일을 검증하는 중...')
            installer.install(game, base / 'patch', apply=apply)
            progress.stage('[4/4] 임시 파일을 정리하는 중...')
    finally:
        elapsed = progress.stop()
    return {'applied': apply, 'files': len(report['outputs']),
            'release': summary['release'], 'translation_summary': report['translation_summary'],
            'elapsed': elapsed}


def self_test() -> dict:
    from PIL import Image
    from UnityPy.export import Texture2DConverter

    summary = validate_resources()
    # This import/conversion also exercises UnityPy's native dependencies.
    # Resource JSON validation alone cannot detect missing frozen DLLs.
    data, texture_format = Texture2DConverter.image_to_texture2d(
        Image.new('RGBA', (2, 2), (255, 255, 255, 0)), 1)
    if int(texture_format) != 1 or bytes(data) != bytes(4):
        raise RuntimeError('폰트 아틀라스 변환 백엔드 검사 실패')
    summary['texture_backend_verified'] = True
    return summary


def main(argv: list[str] | None = None) -> int:
    configure_console()
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    version = load_version()
    parser = argparse.ArgumentParser(description='Silver Pines 한국어 패처')
    parser.add_argument('--version', action='version', version=version['release'])
    parser.add_argument('--game', type=Path, help='Carpenter.exe가 있는 폴더 또는 실행 파일 경로')
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--self-test', action='store_true', help='게임 없이 내장 리소스 검사')
    modes.add_argument('--check', action='store_true', help='패치를 생성하고 검증 (설치하지 않음)')
    modes.add_argument('--restore', action='store_true', help='원본 게임 파일로 복구')
    modes.add_argument('--apply', action='store_true', help='확인 질문 없이 패치 적용')
    modes.add_argument('--preview', action='store_true', help='게임 변경 없이 예상 화면 표시')
    args = parser.parse_args(argv)
    interactive = not any((args.self_test, args.check, args.restore, args.apply, args.preview))
    result = 1
    try:
        if args.self_test:
            print(json.dumps(self_test(), ensure_ascii=False))
            return 0
        if args.preview:
            show_intro(version['release'])
            print('계속하시겠습니까?  1. Yes  2. No : 1')
            print('\n기본 게임 경로 확인 완료.')
            show_menu()
            print('선택 [1]: 1\n')
            for stage in ('[1/4] 게임 원본과 패치 호환성을 확인하는 중...',
                          '[2/4] 한글 문장과 폰트로 패치 파일을 생성하는 중...',
                          '[3/4] 한글 패치를 게임 폴더에 적용하는 중...',
                          '[4/4] 임시 파일을 정리하는 중...'):
                print(stage)
            print('진행 시간: 00:08')
            print('Done. 한글 패치 완료. (총 소요 시간: 00:08)')
            print('게임 언어 설정에서 한국어를 선택하세요.\n')
            print('계속하려면 Enter를 누르세요 . . .')
            return 0
        if interactive:
            show_intro(version['release'])
            if read_confirmation() != '1':
                print('패치를 취소했습니다.')
                return 0
            print()
        else:
            print(f'Silver Pines 한국어 패치 {version["release"]}')
        game = args.game or find_game()
        if game is None and interactive:
            value = input('Carpenter.exe가 있는 게임 폴더를 입력하세요: ').strip().strip('"')
            if not value:
                raise CompatibilityError('게임 경로를 입력하지 않았습니다.')
            game = Path(value)
        if game is None:
            raise CompatibilityError('게임을 찾지 못했습니다. --game으로 설치 폴더를 지정하세요.')
        game = normalize_game(game)
        print('게임 경로 확인 완료.' if args.game else '기본 게임 경로 확인 완료.')
        if interactive:
            show_menu()
            choice = input('선택 [1]: ').strip() or '1'
            if choice == '0':
                return 0
            if choice not in ('1', '2'):
                raise CompatibilityError('1, 2, 0 중 하나를 선택하세요.')
            args.restore = choice == '2'
        if args.restore:
            check_game_closed()
            progress = ProgressTimer()
            progress.start()
            try:
                progress.stage('[1/2] 원본 백업과 게임 파일을 확인하는 중...')
                installer.restore(game, apply=False)
                progress.stage('[2/2] 게임 원본을 복구하는 중...')
                installer.restore(game, apply=True)
            finally:
                elapsed = progress.stop()
            print(f'Done. 원본 복구 완료. (총 소요 시간: {format_duration(elapsed)})')
        else:
            report = run_patch(game, apply=not args.check)
            if args.check:
                print('검사 완료. 게임 파일은 변경하지 않았습니다.')
            else:
                print(f'Done. 한글 패치 완료. (총 소요 시간: {format_duration(report["elapsed"])})')
                print('게임 언어 설정에서 한국어를 선택하세요.')
        result = 0
    except PermissionError as error:
        print(f'파일 접근 오류: {error}', file=sys.stderr)
        if getattr(error, 'winerror', None) in (32, 33):
            print('다른 프로세스가 파일을 사용 중입니다. 게임을 종료하고 다시 실행해 주세요.', file=sys.stderr)
        else:
            print('표시된 경로의 접근 권한을 확인해 주세요. 게임 설치 폴더의 쓰기 권한 문제라면 관리자 권한으로 실행해 주세요.', file=sys.stderr)
    except (CompatibilityError, OSError, ValueError, RuntimeError) as error:
        print(f'오류: {error}', file=sys.stderr)
    finally:
        if interactive:
            try:
                input('계속하려면 Enter를 누르세요 . . .')
            except (EOFError, KeyboardInterrupt):
                pass
    return result
