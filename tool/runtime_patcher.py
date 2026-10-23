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
    with tempfile.TemporaryDirectory(prefix='silverpines-ko-', dir=temporary_root) as temporary:
        base = Path(temporary)
        print('원본 파일과 백업을 확인하고 있습니다...', flush=True)
        materialize(game, base / 'source', resource / 'source-manifest.json')
        print('한국어 문자열과 폰트를 생성하고 있습니다...', flush=True)
        report = build(base / 'source', base / 'patch', resource / 'translations.json',
                       resource / 'source-manifest.json', resource / 'fonts')
        installer.install(game, base / 'patch', apply=apply)
    return {'applied': apply, 'files': len(report['outputs']),
            'release': summary['release'], 'translation_summary': report['translation_summary']}


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
    args = parser.parse_args(argv)
    interactive = not any((args.self_test, args.check, args.restore, args.apply))
    result = 1
    try:
        if args.self_test:
            print(json.dumps(self_test(), ensure_ascii=False))
            return 0
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
        if interactive:
            print(f'게임 폴더: {game}')
            print('1. 한국어 패치 설치 / 업데이트')
            print('2. 원본 파일 복구')
            print('0. 종료')
            choice = input('선택 [1]: ').strip() or '1'
            if choice == '0':
                return 0
            if choice not in ('1', '2'):
                raise CompatibilityError('1, 2, 0 중 하나를 선택하세요.')
            args.restore = choice == '2'
        if args.restore:
            check_game_closed()
            files = installer.restore(game, apply=True)
            print(f'원본 복구 완료: {len(files)}개 파일')
        else:
            report = run_patch(game, apply=not args.check)
            print(json.dumps(report, ensure_ascii=False))
            if args.check:
                print('검사 완료. 게임 파일은 변경하지 않았습니다.')
            else:
                print('패치 적용 완료. 게임 언어에서 한국어를 선택하세요.')
        result = 0
    except PermissionError:
        print('게임 폴더에 쓸 권한이 없습니다. 패처를 관리자 권한으로 실행해 주세요.', file=sys.stderr)
    except (CompatibilityError, OSError, ValueError, RuntimeError) as error:
        print(f'오류: {error}', file=sys.stderr)
    finally:
        if interactive:
            try:
                input('Enter를 누르면 종료합니다...')
            except (EOFError, KeyboardInterrupt):
                pass
    return result
