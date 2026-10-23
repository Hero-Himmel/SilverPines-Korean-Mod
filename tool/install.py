"""Explicit prototype installation / rollback; dry run unless --apply is given."""
from __future__ import annotations

import argparse
import os
import shutil
import tempfile
from pathlib import Path

from .patch import CompatibilityError, FILES, OUTPUT_ROLES, digest, game_root, read_json, write_json

BACKUP_NAME = '.silverpines-ko-backup'


def checked_files(game: Path, patch: Path, state: dict | None = None) -> tuple[dict, list[str]]:
    report = read_json(patch / 'build-report.json')
    expected = {FILES[role].as_posix() for role in OUTPUT_ROLES}
    if report.get('format') != 1 or set(report.get('outputs', {})) != expected:
        raise CompatibilityError('패치 보고서 파일 구성이 다릅니다.')
    if set(report.get('inputs', {})) != {p.as_posix() for p in FILES.values()}:
        raise CompatibilityError('패치 보고서의 원본 해시 파일 구성이 다릅니다.')
    files = sorted(expected)
    for relative, expected_hash in report['inputs'].items():
        allowed = {expected_hash}
        if state and relative in expected:
            if state['originals'][relative] != expected_hash:
                raise CompatibilityError(f'이전 패치와 새 패치의 원본 버전이 다릅니다: {relative}')
            allowed.add(state['patched'][relative])
        if digest((game / relative).read_bytes()) not in allowed:
            raise CompatibilityError(f'게임 원본이 다릅니다: {relative}')
    for relative in files:
        if digest((patch / relative).read_bytes()) != report['outputs'][relative]:
            raise CompatibilityError(f'생성된 패치 파일이 변경되었습니다: {relative}')
    return report, files


def atomic_copy(source: Path, destination: Path) -> None:
    with tempfile.NamedTemporaryFile(dir=destination.parent, prefix='.ko-', delete=False) as handle:
        temporary = Path(handle.name)
    try:
        shutil.copy2(source, temporary)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def install(game: Path, patch: Path, apply: bool = False) -> list[str]:
    game = game_root(game)
    patch = patch.resolve()
    backup = game / BACKUP_NAME
    prior_state = None
    if backup.exists():
        prior_state = read_json(backup / 'state.json')
        validate_state(prior_state)
        if prior_state['status'] not in ('installed', 'restored', 'rolled-back'):
            raise CompatibilityError('이전 작업이 중단된 기록입니다. 먼저 복구하세요.')
        for relative, value in prior_state['originals'].items():
            if digest((backup / relative).read_bytes()) != value:
                raise CompatibilityError(f'기존 원본 백업이 변경되었습니다: {relative}')
    report, files = checked_files(game, patch, prior_state)
    if not apply:
        return files
    # Backups and a journal are durable before the first original is replaced.
    # A process crash leaves sufficient information for --restore.
    backup.mkdir(exist_ok=True)
    state = {'format': 1, 'status': 'preparing', 'files': files,
             'originals': {p: report['inputs'][p] for p in files}, 'patched': report['outputs']}
    if not prior_state:
        write_json(backup / 'state.json', state)
        try:
            for relative in files:
                destination = backup / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(game / relative, destination)
                if digest(destination.read_bytes()) != state['originals'][relative]:
                    raise CompatibilityError('백업 검증 실패')
        except Exception:
            state['status'] = 'backup-failed'
            write_json(backup / 'state.json', state)
            raise
    # Preserve the current patch for rollback on an update, while retaining
    # the immutable game originals for eventual uninstall.
    before = {p: digest((game / p).read_bytes()) for p in files}
    previous = backup / 'previous-version'
    for relative in files:
        destination = previous / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(game / relative, destination)
        if digest(destination.read_bytes()) != before[relative]:
            raise CompatibilityError('이전 버전 사본 검증 실패')
    state['previous_patched'] = before
    state['status'] = 'installing'
    write_json(backup / 'state.json', state)
    changed = []
    try:
        for relative in files:
            if digest((game / relative).read_bytes()) != before[relative]:
                raise CompatibilityError(f'설치 중 원본이 변경되었습니다: {relative}')
            # Include this file before replacement, including post-copy failures.
            changed.append(relative)
            atomic_copy(patch / relative, game / relative)
            if digest((game / relative).read_bytes()) != state['patched'][relative]:
                raise CompatibilityError('설치 후 파일 검증 실패')
    except Exception:
        for relative in reversed(changed):
            atomic_copy(previous / relative, game / relative)
        if prior_state:
            write_json(backup / 'state.json', prior_state)
        else:
            state['status'] = 'rolled-back'
            write_json(backup / 'state.json', state)
        raise
    state['status'] = 'installed'
    write_json(backup / 'state.json', state)
    return files


def validate_state(state: dict) -> None:
    expected = {FILES[role].as_posix() for role in OUTPUT_ROLES}
    if (state.get('format') != 1 or set(state.get('files', [])) != expected
            or set(state.get('originals', {})) != expected or set(state.get('patched', {})) != expected):
        raise CompatibilityError('복구 기록 파일 구성이 다릅니다.')
    if 'previous_patched' in state and set(state['previous_patched']) != expected:
        raise CompatibilityError('이전 패치 기록 파일 구성이 다릅니다.')


def restore(game: Path, apply: bool = False) -> list[str]:
    game = game_root(game)
    backup = game / BACKUP_NAME
    state = read_json(backup / 'state.json')
    validate_state(state)
    for relative in state['files']:
        if digest((backup / relative).read_bytes()) != state['originals'][relative]:
            raise CompatibilityError(f'백업이 변경되었거나 없습니다: {relative}')
        current = digest((game / relative).read_bytes())
        if current not in (state['originals'][relative], state['patched'][relative],
                           state.get('previous_patched', {}).get(relative)):
            raise CompatibilityError(f'게임 업데이트 또는 다른 수정이 감지되었습니다: {relative}')
    if apply:
        for relative in state['files']:
            atomic_copy(backup / relative, game / relative)
            if digest((game / relative).read_bytes()) != state['originals'][relative]:
                raise CompatibilityError(f'복구 검증 실패: {relative}')
        state['status'] = 'restored'
        write_json(backup / 'state.json', state)
        # Retain verified backups for manual recovery and future patch updates.
    return state['files']


def main() -> None:
    parser = argparse.ArgumentParser(description='Silver Pines 패치 설치/복구 (기본: 변경 없이 검사)')
    parser.add_argument('--game', type=Path, required=True)
    parser.add_argument('--patch', type=Path)
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--apply', action='store_true', help='실제로 파일을 교체합니다. 게임을 먼저 종료하세요.')
    args = parser.parse_args()
    if args.restore:
        files = restore(args.game, args.apply)
    elif args.patch:
        files = install(args.game, args.patch, args.apply)
    else:
        parser.error('--patch 또는 --restore가 필요합니다.')
    print(('완료' if args.apply else '검사 완료 (변경 없음)') + f': {len(files)}개 파일')


if __name__ == '__main__':
    main()
