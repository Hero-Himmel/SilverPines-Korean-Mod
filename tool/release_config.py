"""Release identity and explicit resource allowlist; metadata uses stdlib only."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXE_NAME = 'SilverPinesKoreanPatcher.exe'
RESOURCE_FILES = (
    'version.json', 'translations.json', 'source-manifest.json',
    'fonts/NotoSansKR-Regular.otf', 'fonts/NotoSansKR-Bold.otf', 'fonts/OFL.txt',
)
PACKAGE_FILES = {EXE_NAME, 'README.txt', 'OFL.txt', 'release-manifest.json'}


def load_version(resource: Path | None = None) -> dict:
    resource = resource or ROOT / 'resource'
    version = json.loads((resource / 'version.json').read_text(encoding='utf-8'))
    if (version.get('format') != 1 or version.get('game') != 'Silver Pines'
            or version.get('platform') != 'windows'
            or not isinstance(version.get('release'), str)
            or not re.fullmatch(r'\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?', version['release'])
            or type(version.get('prerelease')) is not bool
            or type(version.get('entry_count')) is not int or version['entry_count'] <= 0):
        raise RuntimeError('resource/version.json의 릴리스 정보가 잘못되었습니다.')
    return version


def release_name(version: dict) -> str:
    return f'SilverPines-Korean-{version["release"]}-windows'


def resource_hashes(resource: Path | None = None) -> dict[str, str]:
    resource = resource or ROOT / 'resource'
    return {name: hashlib.sha256((resource / name).read_bytes()).hexdigest() for name in RESOURCE_FILES}


def validate_resources(resource: Path | None = None) -> dict:
    from .patch import FILES

    resource = resource or ROOT / 'resource'
    version = load_version(resource)
    translations = json.loads((resource / 'translations.json').read_text(encoding='utf-8'))
    if translations.get('format') != 1 or not isinstance(translations.get('entries'), list):
        raise RuntimeError('번역 리소스 형식이 잘못되었습니다.')
    entries = translations['entries']
    if len(entries) != version['entry_count']:
        raise RuntimeError('버전 파일의 문자열 수와 번역 리소스 수가 다릅니다.')
    seen = set()
    korean = kept = 0
    for row in entries:
        for key in ('table_id', 'entry_id'):
            if not isinstance(row.get(key), str) or not re.fullmatch(r'-?\d+', row[key]):
                raise RuntimeError('번역 ID는 정밀도를 보존하는 문자열이어야 합니다.')
        identity = (row['table_id'], row['entry_id'])
        if identity in seen:
            raise RuntimeError(f'중복 번역 ID: {identity}')
        seen.add(identity)
        if not re.fullmatch(r'[0-9a-f]{64}', row.get('source_sha256', '')):
            raise RuntimeError(f'원문 SHA-256이 잘못되었습니다: {identity}')
        if row.get('keep_english') is True:
            if 'korean' in row or not isinstance(row.get('reason'), str) or not row['reason'].strip():
                raise RuntimeError(f'원문 유지 사유 또는 번역 지정이 잘못되었습니다: {identity}')
            kept += 1
        elif isinstance(row.get('korean'), str) and row['korean'].strip():
            korean += 1
        else:
            raise RuntimeError(f'번역문이 비어 있습니다: {identity}')
    manifest = json.loads((resource / 'source-manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 1 or set(manifest.get('files', {})) != {p.as_posix() for p in FILES.values()}:
        raise RuntimeError('원본 manifest 파일 구성이 다릅니다.')
    if any(not isinstance(h, str) or not re.fullmatch(r'[0-9a-f]{64}', h) for h in manifest['files'].values()):
        raise RuntimeError('원본 manifest SHA-256이 잘못되었습니다.')
    for weight in ('Regular', 'Bold'):
        if (resource / f'fonts/NotoSansKR-{weight}.otf').read_bytes()[:4] != b'OTTO':
            raise RuntimeError(f'Noto Sans KR {weight} OTF가 없습니다.')
    if 'SIL OPEN FONT LICENSE' not in (resource / 'fonts/OFL.txt').read_text(encoding='utf-8'):
        raise RuntimeError('폰트 라이선스가 없습니다.')
    return {'release': version['release'], 'total': len(entries), 'korean': korean,
            'keep_english': kept, 'resources': resource_hashes(resource)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--validate', action='store_true')
    parser.add_argument('--github-output', type=Path)
    args = parser.parse_args()
    version = load_version()
    if args.github_output:
        with args.github_output.open('a', encoding='utf-8') as output:
            output.write(f'release={version["release"]}\n')
            output.write(f'prerelease={str(version["prerelease"]).lower()}\n')
    print(json.dumps(validate_resources() if args.validate else version, ensure_ascii=False))


if __name__ == '__main__':
    main()
