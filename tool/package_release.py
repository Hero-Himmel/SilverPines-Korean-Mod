"""Build a Windows one-file patcher from code, translations, and licensed fonts."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from .release_config import (ROOT, EXE_NAME, RESOURCE_FILES, load_version,
                             release_name, resource_hashes, validate_resources)


def build_executable(build_root: Path) -> Path:
    if sys.platform != 'win32':
        raise RuntimeError('Windows EXE는 Windows에서 빌드해야 합니다.')
    command = [sys.executable, '-B', '-m', 'PyInstaller', '--noconfirm', '--clean',
               '--log-level', 'WARN', '--onefile', '--console', '--noupx',
               '--name', Path(EXE_NAME).stem, '--paths', str(ROOT),
               '--collect-all', 'UnityPy', '--collect-all', 'archspec',
               '--collect-all', 'fmod_toolkit',
               '--distpath', str(build_root / 'dist'),
               '--workpath', str(build_root / 'work'), '--specpath', str(build_root / 'spec')]
    # Explicit allowlist: never bundle inputs/, artifacts/, or the whole repo.
    for name in RESOURCE_FILES:
        source = ROOT / 'resource' / name
        destination = (Path('resource') / name).parent.as_posix()
        command.extend(['--add-data', f'{source}{os.pathsep}{destination}'])
    command.append(str(ROOT / 'patcher.py'))
    environment = os.environ.copy()
    environment['PYTHONHASHSEED'] = '0'
    environment['PYINSTALLER_CONFIG_DIR'] = str(build_root / 'cache')
    subprocess.run(command, check=True, cwd=ROOT, env=environment)
    executable = build_root / 'dist' / EXE_NAME
    if not executable.is_file():
        raise RuntimeError('PyInstaller가 실행 파일을 생성하지 않았습니다.')
    return executable


def package(output_root: Path) -> Path:
    version = load_version()
    summary = validate_resources()
    output_root = output_root.resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    name = release_name(version)
    archive = output_root / f'{name}.zip'
    checksum = archive.with_suffix('.zip.sha256')
    if archive.exists() or checksum.exists():
        raise RuntimeError(f'같은 릴리스가 이미 있습니다. 새 출력 폴더 또는 버전을 사용하세요: {archive}')
    with tempfile.TemporaryDirectory(prefix='silverpines-release-', dir=output_root) as temporary:
        staging = Path(temporary)
        payload = staging / 'payload'
        payload.mkdir()
        executable = build_executable(staging / 'build')
        shutil.copy2(executable, payload / EXE_NAME)
        shutil.copy2(ROOT / 'resource/fonts/OFL.txt', payload / 'OFL.txt')
        instructions = (
            f'Silver Pines 한국어 패치 {version["release"]} (Windows)\n\n'
            f'1. 게임을 종료하고 {EXE_NAME}를 실행하세요.\n'
            '2. Steam 설치 경로를 자동으로 찾습니다. 못 찾으면 게임 폴더를 입력하세요.\n'
            '3. 설치 / 업데이트를 선택한 뒤, 게임 언어에서 한국어를 선택하세요.\n'
            '4. 제거하려면 같은 패처를 실행하고 원본 복구를 선택하세요.\n\n'
            f'전체 {summary["total"]}행 처리, 한국어 {summary["korean"]}행, 원문 유지 {summary["keep_english"]}행.\n'
            '번역 초안이며 전체 진행 검수는 남아 있습니다. Windows 전용입니다.\n'
            '지원 여부는 원본 파일 SHA-256으로 확인하며, 다른 게임 빌드에는 적용하지 않습니다.\n'
            '설치 권한 오류가 나면 패처를 관리자 권한으로 실행하세요.\n'
            'Python 설치와 게임 파일 다운로드는 필요하지 않습니다.\n'
            'Noto Sans KR 폰트 라이선스는 함께 제공되는 OFL.txt를 확인하세요.\n'
        )
        (payload / 'README.txt').write_text(instructions, encoding='utf-8-sig')
        manifest = {'format': 1, 'release': version['release'], 'platform': 'windows',
                    'executable': EXE_NAME, 'resources': resource_hashes(),
                    'files': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted(payload.iterdir())}}
        commit = os.environ.get('GITHUB_SHA', '')
        if commit:
            manifest['commit'] = commit
        (payload / 'release-manifest.json').write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        # Only finalized archives are placed in the upload directory.
        staged_zip = staging / archive.name
        with zipfile.ZipFile(staged_zip, 'w', compression=zipfile.ZIP_DEFLATED) as z:
            for path in sorted(payload.iterdir()):
                z.write(path, path.name)
        staged_zip.replace(archive)
    checksum.write_text(f'{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n', encoding='ascii')
    print(f'Release: {archive}')
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-root', type=Path, default=ROOT / 'artifacts/release')
    args = parser.parse_args()
    package(args.output_root)
