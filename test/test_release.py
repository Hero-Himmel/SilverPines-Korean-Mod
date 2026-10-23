import copy
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tool import release_config, runtime_patcher
from tool.patch import ROOT, CompatibilityError


class ReleaseResourceTests(unittest.TestCase):
    def setUp(self):
        root = ROOT / 'artifacts/test-tmp'
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=root)
        self.addCleanup(self.temp.cleanup)
        self.resource = Path(self.temp.name)
        for name in release_config.RESOURCE_FILES:
            target = self.resource / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if name.endswith('.otf'):
                target.write_bytes(b'OTTO' + bytes(64))
            else:
                target.write_bytes((ROOT / 'resource' / name).read_bytes())

    def read(self, name):
        return json.loads((self.resource / name).read_text(encoding='utf-8'))

    def write(self, name, value):
        (self.resource / name).write_text(json.dumps(value), encoding='utf-8')

    def test_release_resources_validate_without_game_or_export(self):
        result = release_config.validate_resources()
        self.assertEqual(result['total'], result['korean'] + result['keep_english'])
        self.assertEqual(set(result['resources']), set(release_config.RESOURCE_FILES))
        self.assertFalse(any('inputs' in p or '.bundle' in p for p in result['resources']))

    def test_release_identity_cannot_escape_output_folder(self):
        version = self.read('version.json')
        version['release'] = '../../outside'
        self.write('version.json', version)
        with self.assertRaises(RuntimeError):
            release_config.load_version(self.resource)

    def test_duplicate_translation_is_rejected(self):
        translations = self.read('translations.json')
        translations['entries'][1] = copy.deepcopy(translations['entries'][0])
        self.write('translations.json', translations)
        with self.assertRaises(RuntimeError):
            release_config.validate_resources(self.resource)

    def test_missing_font_or_license_prevents_release(self):
        (self.resource / 'fonts/OFL.txt').write_text('missing license', encoding='utf-8')
        with self.assertRaises(RuntimeError):
            release_config.validate_resources(self.resource)

    def test_wrong_entry_count_prevents_release(self):
        version = self.read('version.json')
        version['entry_count'] += 1
        self.write('version.json', version)
        with self.assertRaises(RuntimeError):
            release_config.validate_resources(self.resource)

    def test_keep_english_requires_reason(self):
        translations = self.read('translations.json')
        next(r for r in translations['entries'] if r.get('keep_english'))['reason'] = ''
        self.write('translations.json', translations)
        with self.assertRaises(RuntimeError):
            release_config.validate_resources(self.resource)


class RuntimePatcherTests(unittest.TestCase):
    def test_preview_never_searches_or_modifies_game(self):
        with patch.object(runtime_patcher, 'find_game') as find, \
                patch.object(runtime_patcher, 'run_patch') as run, \
                patch('sys.stdout', new_callable=io.StringIO) as output:
            self.assertEqual(runtime_patcher.main(['--preview']), 0)
            find.assert_not_called()
            run.assert_not_called()
            self.assertIn('[4/4]', output.getvalue())

    def test_declining_intro_never_starts_install(self):
        with patch.object(runtime_patcher, 'read_confirmation', return_value='2'), \
                patch.object(runtime_patcher, 'find_game') as find, \
                patch.object(runtime_patcher, 'run_patch') as run, \
                patch('builtins.input', return_value=''), \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(runtime_patcher.main([]), 0)
            find.assert_not_called()
            run.assert_not_called()

    def test_restore_menu_only_restores(self):
        with patch.object(runtime_patcher, 'read_confirmation', return_value='1'), \
                patch.object(runtime_patcher, 'normalize_game', return_value=Path('game')), \
                patch.object(runtime_patcher, 'check_game_closed'), \
                patch.object(runtime_patcher.installer, 'restore') as restore, \
                patch.object(runtime_patcher, 'run_patch') as run, \
                patch('builtins.input', side_effect=['2', '']), \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(runtime_patcher.main(['--game', 'game']), 0)
            self.assertEqual(restore.call_args_list[0].kwargs, {'apply': False})
            self.assertEqual(restore.call_args_list[1].kwargs, {'apply': True})
            run.assert_not_called()

    def test_permission_error_reports_the_actual_path(self):
        error = PermissionError(13, 'Access denied', 'temporary-source.bundle')
        with patch.object(runtime_patcher, 'normalize_game', return_value=Path('game')), \
                patch.object(runtime_patcher, 'run_patch', side_effect=error), \
                patch('sys.stderr', new_callable=io.StringIO) as stderr, \
                patch('sys.stdout', new_callable=io.StringIO):
            self.assertEqual(runtime_patcher.main(['--game', 'game', '--check']), 1)
            self.assertIn('temporary-source.bundle', stderr.getvalue())

    def test_file_lock_is_not_reported_as_missing_admin_rights(self):
        error = PermissionError(13, 'Sharing violation', 'temporary-source.bundle')
        error.winerror = 32
        with patch.object(runtime_patcher, 'normalize_game', return_value=Path('game')), \
                patch.object(runtime_patcher, 'run_patch', side_effect=error), \
                patch('sys.stderr', new_callable=io.StringIO) as stderr:
            self.assertEqual(runtime_patcher.main(['--game', 'game', '--check']), 1)
            self.assertIn('다른 프로세스', stderr.getvalue())
            self.assertNotIn('관리자 권한', stderr.getvalue())

    def test_steam_library_vdf_paths_and_deduplication(self):
        root = ROOT / 'artifacts/test-tmp'
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=root) as temp:
            steam = Path(temp)
            (steam / 'steamapps').mkdir()
            library = r'D:\Steam Library'
            escaped = json.dumps(library)
            (steam / 'steamapps/libraryfolders.vdf').write_text(
                '"libraryfolders" { "1" { "path" ' + escaped + ' } "2" { "path" ' + escaped + ' } }',
                encoding='utf-8')
            paths = runtime_patcher.steam_libraries([steam])
            self.assertEqual(paths, [steam, Path(library)])

    def test_check_mode_never_requests_install(self):
        with patch.object(runtime_patcher, 'normalize_game', return_value=Path('game')), \
                patch.object(runtime_patcher, 'run_patch', return_value={'applied': False}) as run, \
                patch('builtins.print'):
            self.assertEqual(runtime_patcher.main(['--game', 'game', '--check']), 0)
            run.assert_called_once_with(Path('game'), apply=False)

    def test_apply_stops_before_reading_sources_when_game_runs(self):
        with patch.object(runtime_patcher, 'check_game_closed', side_effect=CompatibilityError('running')), \
                patch.object(runtime_patcher, 'materialize') as materialize:
            with self.assertRaises(CompatibilityError):
                runtime_patcher.run_patch(Path('game'), apply=True)
            materialize.assert_not_called()

    def test_self_test_does_not_search_for_a_game(self):
        with patch.object(runtime_patcher, 'find_game') as find, patch('builtins.print'):
            self.assertEqual(runtime_patcher.main(['--self-test']), 0)
            find.assert_not_called()


if __name__ == '__main__':
    unittest.main()
