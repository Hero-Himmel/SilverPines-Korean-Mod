"""Verify ZIP contents, embedded resources, and the frozen patcher's startup."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .release_config import (ROOT, EXE_NAME, RESOURCE_FILES, PACKAGE_FILES, load_version,
                             release_name, resource_hashes)


def verify_executable(executable: Path) -> None:
    from PyInstaller.archive.readers import CArchiveReader

    reader = CArchiveReader(str(executable))
    names = {name.replace('\\', '/'): name for name in reader.toc}
    embedded = {n.removeprefix('resource/') for n in names if n.startswith('resource/')}
    if embedded != set(RESOURCE_FILES):
        raise RuntimeError(f'EXE 내장 리소스 구성이 다릅니다: {embedded}')
    expected = resource_hashes()
    for name in RESOURCE_FILES:
        data = reader.extract(names['resource/' + name])
        if hashlib.sha256(data).hexdigest() != expected[name]:
            raise RuntimeError(f'EXE 내장 리소스 해시 불일치: {name}')
    forbidden = {'carpenter.exe', 'global-metadata.dat', 'gameassembly.dll', 'unityplayer.dll', 'english.json'}
    for name in names:
        lower = name.lower()
        if (Path(lower).name in forbidden or lower.endswith(('.bundle', '.assets', '.ress'))
                or lower.startswith(('inputs/', 'artifacts/'))):
            raise RuntimeError(f'EXE에 게임 파일 또는 로컬 입력이 포함되었습니다: {name}')


def verify(output_root: Path, *, smoke_test: bool = True) -> dict:
    version = load_version()
    archive = output_root.resolve() / f'{release_name(version)}.zip'
    expected_checksum = archive.with_suffix('.zip.sha256').read_text(encoding='ascii').strip()
    actual_checksum = f'{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}'
    if expected_checksum != actual_checksum:
        raise RuntimeError('배포 ZIP 체크섬 불일치')
    # Keep all extraction and executable temp files under the chosen output root.
    with tempfile.TemporaryDirectory(prefix='silverpines-verify-', dir=output_root) as temporary:
        directory = Path(temporary)
        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
            if len(names) != len(PACKAGE_FILES) or set(names) != PACKAGE_FILES or z.testzip() is not None:
                raise RuntimeError('배포 ZIP에 예상하지 않은 파일이 있거나 손상되었습니다.')
            manifest = json.loads(z.read('release-manifest.json'))
            if (manifest.get('release') != version['release'] or manifest.get('platform') != 'windows'
                    or manifest.get('executable') != EXE_NAME
                    or manifest.get('resources') != resource_hashes()
                    or set(manifest.get('files', {})) != PACKAGE_FILES - {'release-manifest.json'}):
                raise RuntimeError('배포 manifest 구성이 다릅니다.')
            for name, value in manifest['files'].items():
                if hashlib.sha256(z.read(name)).hexdigest() != value:
                    raise RuntimeError(f'ZIP 파일 해시 불일치: {name}')
            if z.read('OFL.txt') != (ROOT / 'resource/fonts/OFL.txt').read_bytes():
                raise RuntimeError('폰트 라이선스 불일치')
            executable = directory / EXE_NAME
            executable.write_bytes(z.read(EXE_NAME))
        verify_executable(executable)
        if smoke_test:
            environment = os.environ.copy()
            temporary_root = directory / 'temp'
            temporary_root.mkdir()
            environment.update(TEMP=str(temporary_root), TMP=str(temporary_root))
            completed = subprocess.run([str(executable), '--self-test'], check=True,
                                       capture_output=True, text=True, encoding='utf-8',
                                       errors='replace', timeout=120, env=environment, cwd=directory)
            summary = json.loads(completed.stdout)
            if (summary['release'] != version['release'] or summary['resources'] != resource_hashes()
                    or summary.get('texture_backend_verified') is not True):
                raise RuntimeError('실행형 패처 자체 검사 결과 불일치')
    result = {'release': version['release'], 'archive_verified': True,
              'embedded_resources_verified': True, 'runtime_smoke_test': smoke_test}
    print(json.dumps(result, ensure_ascii=False))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output-root', type=Path, default=ROOT / 'artifacts/release')
    args = parser.parse_args()
    verify(args.output_root)
