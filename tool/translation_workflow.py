"""Apply human-authored indexed translation batches to stable table/entry IDs."""
import argparse
from pathlib import Path

from .patch import ROOT, CompatibilityError, read_json, validate_text, write_json, digest


def apply_batch(path: Path, replace=False):
    export = read_json(ROOT / 'inputs/english.json')['entries']
    document = read_json(ROOT / 'resource/translations.json')
    rows = {(r['table_id'], r['entry_id']): r for r in document['entries']}
    seen = set()
    updates = []
    lines = path.read_text(encoding='utf-8-sig').splitlines()
    expected_header = '#export-sha256:' + digest((ROOT / 'inputs/english.json').read_bytes())
    if not lines or lines[0] != expected_header:
        raise CompatibilityError('번역 배치의 원문 export SHA-256이 다릅니다.')
    for line in lines:
        if not line or line.startswith('#'):
            continue
        index, text = line.split('\t', 1)
        index = int(index)
        if index < 0 or index >= len(export):
            raise CompatibilityError(f'배치 인덱스 범위 오류: {index}')
        if index in seen:
            raise CompatibilityError(f'배치 중복 인덱스: {index}')
        seen.add(index)
        source = export[index]
        identity = (source['table_id'], source['entry_id'])
        if identity in rows and not replace:
            raise CompatibilityError(f'이미 번역한 항목: {index}')
        base = {k: source[k] for k in ('table', 'table_id', 'entry_id', 'key', 'source_sha256')}
        if text.startswith('@KEEP:'):
            if not text[6:].strip():
                raise CompatibilityError(f'영문 유지 사유가 없습니다: {index}')
            base.update(keep_english=True, reason=text[6:].strip(), status='reviewed')
        else:
            # TSV uses explicit escapes for newlines; all other backslashes survive.
            translated = text.replace('\\r', '\r').replace('\\n', '\n').replace('\\t', '\t')
            validate_text(source['english'], translated)
            base.update(korean=translated, status='draft')
        updates.append((identity, base))
    for identity, row in updates:
        rows[identity] = row
    document['entries'] = sorted(rows.values(), key=lambda r: (r['table'], int(r['entry_id'])))
    write_json(ROOT / 'resource/translations.json', document)
    print(f'{len(updates)}행 반영, 누적 {len(rows)}/{len(export)}행')


def main():
    p = argparse.ArgumentParser()
    p.add_argument('batch', type=Path)
    p.add_argument('--replace', action='store_true')
    a = p.parse_args()
    apply_batch(a.batch, a.replace)


if __name__ == '__main__':
    main()
