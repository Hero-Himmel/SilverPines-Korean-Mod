import copy
import struct
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tool import install
from tool.patch import (CompatibilityError, FILES, OUTPUT_ROLES, digest,
                        patch_catalog_entry, text_hash, translation_map, validate_text, write_json)


class TranslationTests(unittest.TestCase):
    def test_variables_can_move_but_cannot_disappear_or_duplicate(self):
        validate_text('Press {input_0}: {0}', '{0}: {input_0} 누르기')
        for translated in ('{0} 누르기', '{0} {input_0} {input_0}'):
            with self.assertRaises(CompatibilityError):
                validate_text('Press {input_0}: {0}', translated)

    def test_markup_and_percent_literal(self):
        validate_text('<b>50% Health</b>', '<b>체력 50%</b>')
        with self.assertRaises(CompatibilityError):
            validate_text('<color=white>Take {0}</color>', '획득 {0}')

    def test_old_source_and_duplicate_ids_rejected(self):
        source = {'entries': [{'table_id': '9007199254740993', 'entry_id': '5',
                              'english': 'Take {0}', 'source_sha256': text_hash('Take {0}')}]}
        row = {'table_id': '9007199254740993', 'entry_id': '5',
               'source_sha256': text_hash('Take {0}'), 'korean': '{0} 획득'}
        self.assertEqual(len(translation_map(source, {'format': 1, 'entries': [row]})), 1)
        with self.assertRaises(CompatibilityError):
            translation_map(source, {'format': 1, 'entries': [row, row]})
        stale = dict(row, source_sha256=text_hash('Different'))
        with self.assertRaises(CompatibilityError):
            translation_map(source, {'format': 1, 'entries': [stale]})


class CatalogTests(unittest.TestCase):
    def fixture(self, crc=0):
        data = bytearray(512)
        struct.pack_into('<II', data, 0, 0x0de38942, 2)
        data[32:43] = b'test.bundle'
        hash_id = 43
        data[hash_id:hash_id + 16] = b'1' * 16
        struct.pack_into('<I', data, hash_id + 16, 32)
        data[hash_id + 20:hash_id + 52] = b'a' * 32
        struct.pack_into('<5I', data, hash_id + 52, hash_id, hash_id + 20, crc, 1234, 450)
        struct.pack_into('<hhI', data, 450, 0, 32, 4)
        return data

    def test_disabled_crc_stays_disabled_and_uint32_size_updated(self):
        data = self.fixture()
        before = bytes(data)
        result = patch_catalog_entry(data, 'test.bundle', 123, 456, 1234, 5678)
        self.assertEqual(result['crc_after'], 0)
        self.assertEqual(struct.unpack_from('<II', data, result['offset'] + 8), (0, 5678))
        changed = {i for i, (a, b) in enumerate(zip(before, data)) if a != b}
        self.assertTrue(changed.issubset(set(range(result['offset'] + 12, result['offset'] + 16))))

    def test_enabled_crc_checked_and_updated(self):
        data = self.fixture(123)
        self.assertEqual(patch_catalog_entry(data, 'test.bundle', 123, 456, 1234, 5678)['crc_after'], 456)
        with self.assertRaises(CompatibilityError):
            patch_catalog_entry(self.fixture(999), 'test.bundle', 123, 456, 1234, 5678)

    def test_unknown_layout_fails_closed(self):
        data = self.fixture()
        struct.pack_into('<I', data, 4, 3)
        with self.assertRaises(CompatibilityError):
            patch_catalog_entry(data, 'test.bundle', 123, 456, 1234, 5678)
        with self.assertRaises(CompatibilityError):
            patch_catalog_entry(self.fixture(), 'test.bundle', 123, 456, 8888, 5678)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        temp_root = Path(__file__).resolve().parents[1] / 'artifacts/test-tmp'
        temp_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.game = self.root / 'game'
        self.output = self.root / 'patch'
        self.game.mkdir()
        (self.game / 'Carpenter.exe').write_bytes(b'fixture executable')
        self.inputs = {}
        self.outputs = {}
        for role, relative in FILES.items():
            target = self.game / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f'original {role}'.encode())
            self.inputs[relative.as_posix()] = digest(target.read_bytes())
        for role in OUTPUT_ROLES:
            target = self.output / FILES[role]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(f'patched {role}'.encode())
            self.outputs[FILES[role].as_posix()] = digest(target.read_bytes())
        self.report = {'format': 1, 'inputs': self.inputs, 'outputs': self.outputs}
        write_json(self.output / 'build-report.json', self.report)

    def assert_originals(self):
        for path, hash_value in self.inputs.items():
            self.assertEqual(digest((self.game / path).read_bytes()), hash_value)

    def test_dry_run_does_not_create_backup(self):
        self.assertEqual(len(install.install(self.game, self.output)), 4)
        self.assertFalse((self.game / install.BACKUP_NAME).exists())
        self.assert_originals()

    def test_install_and_restore_byte_for_byte(self):
        install.install(self.game, self.output, True)
        for path, value in self.outputs.items():
            self.assertEqual(digest((self.game / path).read_bytes()), value)
        install.restore(self.game, True)
        self.assert_originals()

    def test_failed_install_rolls_back(self):
        real_copy = install.atomic_copy
        calls = 0

        def fail_once(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('simulated locked game file')
            return real_copy(source, destination)

        with patch.object(install, 'atomic_copy', side_effect=fail_once):
            with self.assertRaises(OSError):
                install.install(self.game, self.output, True)
        self.assert_originals()

    def test_modified_patch_rejected_before_writing(self):
        (self.output / FILES['fonts']).write_bytes(b'corrupted')
        with self.assertRaises(CompatibilityError):
            install.install(self.game, self.output, True)
        self.assertFalse((self.game / install.BACKUP_NAME).exists())
        self.assert_originals()

    def test_game_update_blocks_restore(self):
        install.install(self.game, self.output, True)
        (self.game / FILES['fonts']).write_bytes(b'new game update')
        with self.assertRaises(CompatibilityError):
            install.restore(self.game, True)

    def make_next_version(self):
        for role in OUTPUT_ROLES:
            relative = FILES[role]
            target = self.output / relative
            target.write_bytes(f'next version {role}'.encode())
            self.report['outputs'][relative.as_posix()] = digest(target.read_bytes())
        write_json(self.output / 'build-report.json', self.report)

    def test_upgrade_preserves_original_backup_and_restores(self):
        install.install(self.game, self.output, True)
        self.make_next_version()
        install.install(self.game, self.output, True)
        for path, value in self.report['outputs'].items():
            self.assertEqual(digest((self.game / path).read_bytes()), value)
        install.restore(self.game, True)
        self.assert_originals()

    def test_failed_upgrade_returns_to_previous_patch(self):
        install.install(self.game, self.output, True)
        previous = {p: digest((self.game / p).read_bytes()) for p in self.outputs}
        self.make_next_version()
        real_copy = install.atomic_copy
        calls = 0

        def fail_once(source, destination):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError('simulated locked game file during upgrade')
            real_copy(source, destination)

        with patch.object(install, 'atomic_copy', side_effect=fail_once):
            with self.assertRaises(OSError):
                install.install(self.game, self.output, True)
        for path, value in previous.items():
            self.assertEqual(digest((self.game / path).read_bytes()), value)
        install.restore(self.game, True)
        self.assert_originals()

    def test_upgrade_rejects_changed_original_backup(self):
        install.install(self.game, self.output, True)
        (self.game / install.BACKUP_NAME / FILES['fonts']).write_bytes(b'corrupted original')
        self.make_next_version()
        with self.assertRaises(CompatibilityError):
            install.install(self.game, self.output, True)

    def test_interrupted_upgrade_can_restore_mixed_versions(self):
        install.install(self.game, self.output, True)
        previous = {p: digest((self.game / p).read_bytes()) for p in self.outputs}
        self.make_next_version()
        from tool.patch import read_json
        journal = self.game / install.BACKUP_NAME / 'state.json'
        state = read_json(journal)
        state.update(status='installing', previous_patched=previous,
                     patched=copy.deepcopy(self.report['outputs']))
        write_json(journal, state)
        first = FILES[OUTPUT_ROLES[0]]
        install.atomic_copy(self.output / first, self.game / first)
        install.restore(self.game, True)
        self.assert_originals()

    def test_unexpected_output_path_rejected(self):
        report = copy.deepcopy(self.report)
        report['outputs']['../outside'] = 'bad'
        write_json(self.output / 'build-report.json', report)
        with self.assertRaises(CompatibilityError):
            install.install(self.game, self.output, True)


if __name__ == '__main__':
    unittest.main()
