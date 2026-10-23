"""Build Korean assets from a user's own Silver Pines installation.

No game files are edited by this module. IDs are strings in interchange JSON.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import struct
import tempfile
import zlib
from collections import Counter
from pathlib import Path

import UnityPy
from PIL import Image
from UnityPy.enums import ArchiveFlags
from UnityPy.streams import EndianBinaryReader

ROOT = Path(__file__).resolve().parents[1]
DATA = Path('Carpenter_Data')
AA = DATA / 'StreamingAssets/aa'
BUNDLES = AA / 'StandaloneWindows64'
LOCALE = 'zh-Hant'
FILES = {
    'english': BUNDLES / 'localization-string-tables-english(en)_assets_all.bundle',
    'shared': BUNDLES / 'localization-assets-shared_assets_all.bundle',
    'strings': BUNDLES / 'localization-string-tables-chinese(traditional)(zh-hant)_assets_all.bundle',
    'fonts': BUNDLES / 'fonts-traditional-chinese_assets_all.bundle',
    'locales': BUNDLES / 'localization-locales_assets_all.bundle',
    'font_table': BUNDLES / 'localization-asset-tables-chinese(traditional)(zh-hant)_assets_all.bundle',
    'catalog': AA / 'catalog.bin',
    'catalog_hash': AA / 'catalog.hash',
    'settings': AA / 'settings.json',
}
OUTPUT_ROLES = ('strings', 'fonts', 'locales', 'catalog')


class CompatibilityError(RuntimeError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def text_hash(text: str) -> str:
    return digest(text.encode('utf-8'))


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.ko-json-', delete=False) as handle:
        temporary = Path(handle.name)
        try:
            handle.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        except Exception:
            handle.close()
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def game_root(path: Path) -> Path:
    path = path.expanduser().resolve()
    if not (path / 'Carpenter.exe').is_file():
        raise CompatibilityError(f'Carpenter.exe가 없습니다: {path}')
    for role, relative in FILES.items():
        if not (path / relative).is_file():
            raise CompatibilityError(f'필수 파일이 없습니다 ({role}): {relative}')
    return path


def object_trees(path: Path):
    env = UnityPy.load(str(path))
    for obj in env.objects:
        if obj.type.name == 'MonoBehaviour':
            # Do not silently skip unreadable localization objects.
            yield obj, obj.read_typetree()


def tables(path: Path):
    result = {}
    for obj, tree in object_trees(path):
        if 'm_TableData' not in tree or 'm_SharedData' not in tree:
            continue
        table_id = str(tree['m_SharedData']['m_PathID'])
        if table_id in result:
            raise CompatibilityError(f'중복 테이블 ID: {table_id}')
        result[table_id] = (obj, tree)
    if not result:
        raise CompatibilityError(f'문자열 테이블이 없습니다: {path}')
    return result


def extract(game: Path) -> dict:
    shared = {}
    for obj, tree in object_trees(game / FILES['shared']):
        if 'm_Entries' in tree and 'm_TableCollectionName' in tree:
            shared[str(obj.path_id)] = tree
    entries = []
    for table_id, (_, tree) in tables(game / FILES['english']).items():
        if table_id not in shared:
            raise CompatibilityError(f'Shared Table을 찾지 못했습니다: {table_id}')
        definition = shared[table_id]
        keys = {str(row['m_Id']): row['m_Key'] for row in definition['m_Entries']}
        seen = set()
        for row in tree['m_TableData']:
            entry_id = str(row['m_Id'])
            if entry_id in seen:
                raise CompatibilityError(f'중복 문자열 ID: {table_id}/{entry_id}')
            seen.add(entry_id)
            if entry_id not in keys:
                raise CompatibilityError(f'Shared Key가 없습니다: {table_id}/{entry_id}')
            entries.append({
                'table': definition['m_TableCollectionName'], 'table_id': table_id,
                'entry_id': entry_id, 'key': keys[entry_id],
                'english': row['m_Localized'], 'source_sha256': text_hash(row['m_Localized']),
            })
    return {'format': 1, 'entries': sorted(entries, key=lambda x: (x['table'], int(x['entry_id'])))}


def source_manifest(game: Path) -> dict:
    return {'format': 1, 'files': {
        str(relative.as_posix()): digest((game / relative).read_bytes())
        for relative in FILES.values()
    }}


def verify_sources(game: Path, manifest: dict) -> None:
    expected = {p.as_posix() for p in FILES.values()}
    if manifest.get('format') != 1 or set(manifest.get('files', {})) != expected:
        raise CompatibilityError('지원 버전 manifest 파일 구성이 다릅니다.')
    for relative, expected_hash in manifest['files'].items():
        if digest((game / relative).read_bytes()) != expected_hash:
            raise CompatibilityError(f'원본 SHA-256 불일치 (업데이트 또는 패치 여부 확인): {relative}')


# Preserve multiplicity, including repeated runtime input placeholders.
TOKEN = re.compile(r'(?<!\{)\{[^{}\r\n]+\}(?!\})|%(?:\d+\$)?[-+0 #]*\d*(?:\.\d+)?[sdif]')
TAG = re.compile(r'</?[A-Za-z][^>]*>')


def validate_text(source: str, translated: str) -> None:
    if not isinstance(translated, str) or not translated.strip():
        raise CompatibilityError('번역문이 비어 있습니다.')
    if Counter(TOKEN.findall(source)) != Counter(TOKEN.findall(translated)):
        raise CompatibilityError('변수/입력 토큰이 원문과 다릅니다.')
    if Counter(TAG.findall(source)) != Counter(TAG.findall(translated)):
        raise CompatibilityError('서식 태그가 원문과 다릅니다.')


def translation_map(export: dict, translations: dict) -> dict:
    if translations.get('format') != 1:
        raise CompatibilityError('지원하지 않는 번역 형식입니다.')
    current = {(r['table_id'], r['entry_id']): r for r in export['entries']}
    result = {}
    for row in translations['entries']:
        identity = (row['table_id'], row['entry_id'])
        if identity in result:
            raise CompatibilityError(f'중복 번역 ID: {identity}')
        if identity not in current:
            raise CompatibilityError(f'삭제되었거나 잘못된 번역 ID: {identity}')
        original = current[identity]
        if row['source_sha256'] != original['source_sha256']:
            raise CompatibilityError(f'원문이 변경되었습니다: {identity}')
        if row.get('keep_english') is True:
            if row.get('korean'):
                raise CompatibilityError(f'영문 유지와 번역이 동시에 지정되었습니다: {identity}')
            result[identity] = original['english']
        else:
            validate_text(original['english'], row['korean'])
            result[identity] = row['korean']
    return result


def bundle_root(env):
    roots = list(env.files.values())
    if len(roots) != 1 or roots[0].__class__.__name__ != 'BundleFile':
        raise CompatibilityError('단일 Unity AssetBundle을 예상했습니다.')
    return roots[0]


def save_bundle(env, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(bundle_root(env).save(packer='lz4'))


def build_strings(game: Path, output: Path, overrides: dict) -> dict:
    source_tables = tables(game / FILES['english'])
    env = UnityPy.load(str(game / FILES['strings']))
    targets = {}
    for obj in env.objects:
        if obj.type.name != 'MonoBehaviour':
            continue
        tree = obj.read_typetree()
        if 'm_TableData' in tree and 'm_SharedData' in tree:
            identity = str(tree['m_SharedData']['m_PathID'])
            if identity in targets:
                raise CompatibilityError(f'중복 대상 테이블: {identity}')
            targets[identity] = (obj, tree)
    if set(targets) != set(source_tables):
        raise CompatibilityError('영문/대상 언어의 테이블 ID 구성이 다릅니다.')
    expected = {}
    for table_id, (obj, tree) in targets.items():
        # Copy English rows, including their Smart String managed metadata.
        # This also supports target tables with zero rows (e.g. Save).
        source_tree = source_tables[table_id][1]
        source_file = source_tables[table_id][0].assets_file
        target_file = obj.assets_file
        existing = {(r.m_ClassName, r.m_NameSpace, r.m_AssemblyName) for r in target_file.ref_types or []}
        for ref_type in source_file.ref_types or []:
            signature = (ref_type.m_ClassName, ref_type.m_NameSpace, ref_type.m_AssemblyName)
            if signature not in existing:
                if target_file.ref_types is None:
                    target_file.ref_types = []
                target_file.ref_types.append(copy.copy(ref_type))
                existing.add(signature)
        tree['m_TableData'] = copy.deepcopy(source_tree['m_TableData'])
        tree['m_Metadata'] = copy.deepcopy(source_tree['m_Metadata'])
        tree['references'] = copy.deepcopy(source_tree['references'])
        for row in tree['m_TableData']:
            identity = (table_id, str(row['m_Id']))
            row['m_Localized'] = overrides.get(identity, row['m_Localized'])
            expected[identity] = copy.deepcopy(row)
        obj.save_typetree(tree)
    save_bundle(env, output)
    actual = {}
    for table_id, (_, tree) in tables(output).items():
        if tree['m_LocaleId']['m_Code'] != LOCALE:
            raise CompatibilityError('생성한 번들의 언어 코드가 다릅니다.')
        for row in tree['m_TableData']:
            identity = (table_id, str(row['m_Id']))
            if identity in actual:
                raise CompatibilityError(f'생성 결과에 중복 ID: {identity}')
            actual[identity] = row
    if actual != expected:
        raise CompatibilityError('생성한 문자열/메타데이터 재검증 실패')
    return {'rows': len(actual), 'overrides': len(overrides)}


def build_fonts(game: Path, output: Path, font_dir: Path) -> dict:
    env = UnityPy.load(str(game / FILES['fonts']))
    font_ids, tmp_fonts, atlas_ids = {}, {}, set()
    font_hashes = {}
    for obj in env.objects:
        if obj.type.name == 'Font':
            tree = obj.read_typetree()
            for weight in ('Regular', 'Bold'):
                if tree['m_Name'] == f'NotoSansTC-{weight}':
                    data = (font_dir / f'NotoSansKR-{weight}.otf').read_bytes()
                    if data[:4] != b'OTTO':
                        raise CompatibilityError(f'잘못된 OTF 폰트: {weight}')
                    tree['m_FontData'] = data
                    tree['m_Name'] = f'NotoSansKR-{weight}'
                    tree['m_FontNames'] = ['Noto Sans KR']
                    obj.save_typetree(tree)
                    font_ids[int(obj.path_id)] = weight
                    font_hashes[weight] = digest(data)
        elif obj.type.name == 'MonoBehaviour':
            tree = obj.read_typetree()
            if 'm_CharacterTable' in tree:
                tmp_fonts[int(obj.path_id)] = (obj, tree)
    if sorted(font_ids.values()) != ['Bold', 'Regular'] or len(tmp_fonts) != 2:
        raise CompatibilityError('Regular/Bold 원본 폰트 쌍을 식별하지 못했습니다.')
    for obj, tree in tmp_fonts.values():
        pointer = tree['m_SourceFontFile']
        if pointer['m_FileID'] != 0 or pointer['m_PathID'] not in font_ids:
            raise CompatibilityError('TMP 원본 폰트 참조가 예상과 다릅니다.')
        weight = font_ids[pointer['m_PathID']]
        tree['m_Name'] = f'NotoSansKR-{weight} SDF'
        tree['m_FaceInfo']['m_FamilyName'] = 'Noto Sans KR'
        tree['m_AtlasPopulationMode'] = 1  # Dynamic: Unity TextCore generates SDFs.
        tree['m_IsMultiAtlasTexturesEnabled'] = 1
        tree['m_ClearDynamicDataOnBuild'] = 0
        tree['m_GlyphTable'] = []
        tree['m_CharacterTable'] = []
        tree['m_UsedGlyphRects'] = []
        tree['m_FreeGlyphRects'] = [{
            'm_X': 0, 'm_Y': 0,
            'm_Width': tree['m_AtlasWidth'] - 1, 'm_Height': tree['m_AtlasHeight'] - 1,
        }]
        tree['m_AtlasTextureIndex'] = 0
        for records in tree['m_FontFeatureTable'].values():
            if not isinstance(records, list):
                raise CompatibilityError('알 수 없는 폰트 feature 형식입니다.')
            records.clear()
        tree['m_ShouldReimportFontFeatures'] = 0
        tree['m_GetFontFeatures'] = 0
        tree['m_glyphInfoList'] = []
        tree['m_KerningTable']['kerningPairs'] = []
        tree['m_CreationSettings']['characterSequence'] = ''
        tree['m_CreationSettings']['sourceFontFileName'] = f'NotoSansKR-{weight}.otf'
        for atlas in tree['m_AtlasTextures']:
            if atlas['m_FileID'] != 0:
                raise CompatibilityError('외부 아틀라스 참조는 지원하지 않습니다.')
            atlas_ids.add(int(atlas['m_PathID']))
        obj.save_typetree(tree)
    changed_atlases = set()
    for obj in env.objects:
        if obj.type.name == 'Texture2D' and int(obj.path_id) in atlas_ids:
            tex = obj.read()
            tex.set_image(Image.new('RGBA', (tex.m_Width, tex.m_Height), (255, 255, 255, 0)))
            tex.m_IsReadable = True
            tex.save()
            changed_atlases.add(int(obj.path_id))
    if changed_atlases != atlas_ids or len(atlas_ids) != 2:
        raise CompatibilityError('SDF 아틀라스 쌍을 식별하지 못했습니다.')
    save_bundle(env, output)
    verified_fonts, verified_tmp, verified_atlases = set(), 0, 0
    check = UnityPy.load(str(output))
    for obj in check.objects:
        if obj.type.name == 'Font' and int(obj.path_id) in font_ids:
            tree = obj.read_typetree()
            weight = font_ids[int(obj.path_id)]
            if digest(bytes(tree['m_FontData'])) != font_hashes[weight]:
                raise CompatibilityError('OTF 재검증 실패')
            verified_fonts.add(weight)
        elif obj.type.name == 'MonoBehaviour' and int(obj.path_id) in tmp_fonts:
            tree = obj.read_typetree()
            if tree['m_AtlasPopulationMode'] != 1 or tree['m_CharacterTable'] or tree['m_GlyphTable']:
                raise CompatibilityError('동적 SDF 설정 재검증 실패')
            if not tree['m_IsMultiAtlasTexturesEnabled'] or not tree['m_FreeGlyphRects']:
                raise CompatibilityError('동적 SDF 아틀라스 설정 재검증 실패')
            verified_tmp += 1
        elif obj.type.name == 'Texture2D' and int(obj.path_id) in atlas_ids:
            tex = obj.read()
            if not tex.m_IsReadable or any(tex.get_image_data()):
                raise CompatibilityError('아틀라스 초기화 재검증 실패')
            verified_atlases += 1
    if verified_fonts != {'Regular', 'Bold'} or verified_tmp != 2 or verified_atlases != 2:
        raise CompatibilityError('폰트 재검증 개수가 다릅니다.')
    return {'family': 'Noto Sans KR', 'mode': 'dynamic', 'fonts': font_hashes, 'runtime_verified': False}


def build_locales(game: Path, output: Path) -> None:
    env = UnityPy.load(str(game / FILES['locales']))
    count = 0
    for obj in env.objects:
        if obj.type.name != 'MonoBehaviour':
            continue
        tree = obj.read_typetree()
        if tree.get('m_Identifier', {}).get('m_Code') == LOCALE:
            tree['m_LocaleName'] = '한국어'
            # Retain m_Name / identifier to preserve Addressables and save settings.
            obj.save_typetree(tree)
            count += 1
    if count != 1:
        raise CompatibilityError('대상 Locale을 유일하게 식별하지 못했습니다.')
    save_bundle(env, output)
    names = [t['m_LocaleName'] for _, t in object_trees(output)
             if t.get('m_Identifier', {}).get('m_Code') == LOCALE]
    if names != ['한국어']:
        raise CompatibilityError('Locale 재검증 실패')


def bundle_crc(path: Path) -> int:
    raw = path.read_bytes()
    bundle = bundle_root(UnityPy.load(raw))
    reader = EndianBinaryReader(raw)
    reader.read_string_to_null()
    reader.read_u_int()
    reader.read_string_to_null()
    reader.read_string_to_null()
    reader.read_long()
    packed_size, unpacked_size = reader.read_u_int(), reader.read_u_int()
    reader.read_u_int()
    if bundle._uses_block_alignment:
        reader.align_stream(16)
    start = reader.Position
    if int(bundle.dataflags) & int(ArchiveFlags.BlocksInfoAtTheEnd):
        reader.Position = reader.Length - packed_size
        packed_info = reader.read_bytes(packed_size)
        data_start = start
    else:
        packed_info = reader.read_bytes(packed_size)
        if int(bundle.dataflags) & 0x200:
            reader.align_stream(16)
        data_start = reader.Position
    info = EndianBinaryReader(bundle.decompress_data(packed_info, unpacked_size, bundle.dataflags))
    info.read_bytes(16)
    blocks = [(info.read_u_int(), info.read_u_int(), info.read_u_short()) for _ in range(info.read_int())]
    reader.Position = data_start
    crc = 0
    for index, (size, packed, flags) in enumerate(blocks):
        crc = zlib.crc32(bundle.decompress_data(reader.read_bytes(packed), size, flags, index), crc)
    return crc & 0xffffffff


def patch_catalog_entry(data: bytearray, name: str, old_crc: int, new_crc: int,
                        old_size: int, new_size: int) -> dict:
    if struct.unpack_from('<II', data) != (0x0de38942, 2):
        raise CompatibilityError('지원하지 않는 binary catalog 버전입니다.')
    encoded = name.encode('ascii')
    if data.count(encoded) != 1:
        raise CompatibilityError(f'카탈로그에서 번들을 유일하게 식별할 수 없습니다: {name}')
    hash_id = data.index(encoded) + len(encoded)
    # Addressables 2.9.1 AssetBundleRequestOptionsSerializationAdapter:
    # uint hashId, bundleNameId, crc, bundleSize, commonId.
    # Validate both pointers, never search for a non-unique zero CRC.
    candidates = []
    for position in range(hash_id, min(len(data) - 20, hash_id + 256)):
        h, n, crc, size, common = struct.unpack_from('<5I', data, position)
        if h != hash_id or size != old_size or n < 4 or n + 32 > len(data):
            continue
        if struct.unpack_from('<I', data, n - 4)[0] != 32:
            continue
        if not re.fullmatch(b'[0-9a-f]{32}', data[n:n + 32]) or common + 8 > len(data):
            continue
        candidates.append((position, crc, common))
    if len(candidates) != 1:
        raise CompatibilityError(f'카탈로그 request options 식별 실패: {name} ({len(candidates)})')
    position, crc, common = candidates[0]
    if crc not in (0, old_crc):
        raise CompatibilityError(f'카탈로그 CRC가 원본과 다릅니다: {name}')
    flags = struct.unpack_from('<I', data, common + 4)[0]
    if flags & 8:
        raise CompatibilityError('로컬 번들 UnityWebRequest/캐시 경로는 아직 지원하지 않습니다.')
    updated_crc = 0 if crc == 0 else new_crc
    struct.pack_into('<II', data, position + 8, updated_crc, new_size)
    if struct.unpack_from('<II', data, position + 8) != (updated_crc, new_size):
        raise CompatibilityError('카탈로그 재검증 실패')
    return {'offset': position, 'crc_before': crc, 'crc_after': updated_crc,
            'size_before': old_size, 'size_after': new_size}


def build(game: Path, output: Path, translations_path: Path, manifest_path: Path, font_dir: Path) -> dict:
    game = game_root(game)
    output = output.resolve()
    if output == game or game in output.parents or output in game.parents:
        raise CompatibilityError('출력 폴더는 게임 설치 폴더와 분리해야 합니다.')
    if output.exists() and any(output.iterdir()):
        raise CompatibilityError('출력 폴더가 비어 있지 않습니다. 새 출력 경로를 사용하세요.')
    verify_sources(game, read_json(manifest_path))
    settings = read_json(game / FILES['settings'])
    locations = settings.get('m_CatalogLocations', [])
    expected_location = '{UnityEngine.AddressableAssets.Addressables.RuntimePath}/catalog.bin'
    if len(locations) != 1 or locations[0].get('m_InternalId') != expected_location or locations[0].get('m_Dependencies'):
        raise CompatibilityError('검증되지 않은 원격/추가 카탈로그 구성이 있습니다.')
    export = extract(game)
    translations = read_json(translations_path)
    overrides = translation_map(export, translations)
    output.mkdir(parents=True, exist_ok=True)
    strings = build_strings(game, output / FILES['strings'], overrides)
    fonts = build_fonts(game, output / FILES['fonts'], font_dir)
    build_locales(game, output / FILES['locales'])
    catalog = bytearray((game / FILES['catalog']).read_bytes())
    catalog_report = {}
    for role in ('strings', 'fonts', 'locales'):
        original, modified = game / FILES[role], output / FILES[role]
        catalog_report[role] = patch_catalog_entry(catalog, original.name,
            bundle_crc(original), bundle_crc(modified), original.stat().st_size, modified.stat().st_size)
    (output / FILES['catalog']).write_bytes(catalog)
    # Keep catalog.hash unchanged: it is a content-version token, not a checksum
    # of catalog.bin. This catalog is local-only (settings has no remote location).
    report = {
        'format': 1, 'stage': 'translation-draft' if len(overrides) == len(export['entries']) else 'prototype',
        'locale': LOCALE, 'runtime_verified': False,
        'strings': strings, 'fonts': fonts, 'catalog': catalog_report,
        'translation_summary': {
            'total': len(export['entries']),
            'korean': sum('korean' in r for r in translations['entries']),
            'keep_english': sum(r.get('keep_english', False) for r in translations['entries']),
            'unassigned': len(export['entries']) - len(overrides),
        },
        'inputs': source_manifest(game)['files'],
        'outputs': {FILES[role].as_posix(): digest((output / FILES[role]).read_bytes()) for role in OUTPUT_ROLES},
    }
    write_json(output / 'build-report.json', report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description='Silver Pines 한국어 패치 (원본 변경 없이 생성)')
    parser.add_argument('command', choices=('extract', 'validate', 'build'))
    parser.add_argument('--game', type=Path, default=Path(r'C:\Program Files (x86)\Steam\steamapps\common\Silver Pines'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--translations', type=Path, default=ROOT / 'resource/translations.json')
    parser.add_argument('--manifest', type=Path, default=ROOT / 'resource/source-manifest.json')
    parser.add_argument('--fonts', type=Path, default=ROOT / 'resource/fonts')
    args = parser.parse_args()
    game = game_root(args.game)
    if args.command == 'extract':
        target = args.output or ROOT / 'inputs/english.json'
        write_json(target, extract(game))
        print(f'문자열 추출 완료: {target}')
    elif args.command == 'validate':
        export = extract(game)
        overrides = translation_map(export, read_json(args.translations))
        print(f'검증 완료: {len(overrides)}/{len(export["entries"])}행 지정')
    else:
        if args.output is None:
            parser.error('build에는 --output 새 폴더가 필요합니다.')
        report = build(game, args.output, args.translations, args.manifest, args.fonts)
        print(json.dumps({'output': str(args.output.resolve()), 'strings': report['strings'],
                          'runtime_verified': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
