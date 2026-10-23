"""Materialize hash-verified build inputs without uninstalling the active patch."""
import argparse
import shutil
from pathlib import Path

from .patch import ROOT, FILES, CompatibilityError, game_root, read_json, digest, verify_sources


def materialize(game: Path, output: Path, manifest: Path, *, quiet: bool = False):
    game = game_root(game)
    output = output.resolve()
    if output == game or game in output.parents or output in game.parents:
        raise CompatibilityError('원본 입력 사본은 게임 설치 폴더와 분리해야 합니다.')
    if output.exists() and any(output.iterdir()):
        raise CompatibilityError('새 원본 입력 폴더를 지정하세요.')
    expected = read_json(manifest)
    if set(expected.get('files', {})) != {p.as_posix() for p in FILES.values()}:
        raise CompatibilityError('원본 manifest 구성이 다릅니다.')
    sources = {}
    for relative in FILES.values():
        wanted = expected['files'][relative.as_posix()]
        source = game / relative
        if digest(source.read_bytes()) != wanted:
            source = game / '.silverpines-ko-backup' / relative
            if not source.is_file() or digest(source.read_bytes()) != wanted:
                raise CompatibilityError(f'설치본과 백업에서 원본을 찾지 못했습니다: {relative}')
        sources[relative] = source
    output.mkdir(parents=True, exist_ok=True)
    shutil.copy2(game / 'Carpenter.exe', output / 'Carpenter.exe')
    for relative, source in sources.items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    verify_sources(output, expected)
    if not quiet:
        print(f'원본 입력 사본 생성 완료: {output}')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--game', type=Path, required=True)
    p.add_argument('--output', type=Path, default=ROOT / 'inputs/pristine-game')
    p.add_argument('--manifest', type=Path, default=ROOT / 'resource/source-manifest.json')
    a = p.parse_args()
    materialize(a.game, a.output, a.manifest)
