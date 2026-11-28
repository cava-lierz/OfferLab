import copy
import importlib.util
import json
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


installer = load('offerlab_installer', ROOT / 'openclaw/install_interviewer.py')
packager = load('offerlab_packager', ROOT / 'scripts/package_interviewer.py')


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / '.openclaw'
        self.state.mkdir()
        self.remote = Path('/home/idekube/.openclaw')
        self.config = {
            'meta': {'lastTouchedVersion': '2026.5.22'},
            'agents': {'defaults': {'workspace': '/school/custom-main', 'model': {'primary': 'sjtu/deepseek-reasoner'}}},
            'gateway': {'auth': {'token': 'test-gateway-secret'}, 'http': {'endpoints': {'chatCompletions': {'enabled': True}}}},
            'models': {'providers': {'sjtu': {'apiKey': 'test-model-secret'}}},
            'tools': {'profile': 'coding', 'alsoAllow': ['feishu_chat']},
            'plugins': {'entries': {'existing': {'enabled': True}}},
        }
        self.path = self.state / 'openclaw.json'
        self.path.write_text(json.dumps(self.config))

    def test_merge_preserves_provider_credentials_gateway_and_implicit_main(self):
        original = copy.deepcopy(self.config)
        merged = installer.merge_config(self.config, self.remote)
        self.assertEqual(self.config, original)
        for key in ('gateway', 'models', 'tools', 'plugins', 'meta'):
            self.assertEqual(merged[key], original[key])
        self.assertEqual(merged['agents']['defaults'], original['agents']['defaults'])
        main, interviewer = merged['agents']['list']
        self.assertEqual(main, {'id': 'main', 'default': True, 'workspace': '/school/custom-main'})
        self.assertEqual(interviewer['id'], 'interviewer')
        self.assertEqual(interviewer['tools']['allow'], ['read', 'web_search', 'web_fetch'])
        self.assertTrue(interviewer['tools']['fs']['workspaceOnly'])
        self.assertEqual(interviewer['skills'], ['offerlab-interviewer'])

    def test_existing_agents_and_default_are_preserved(self):
        entries = [{'id': 'main', 'workspace': '/old'}, {'id': 'course', 'default': True, 'model': 'sjtu/glm'}]
        self.config['agents']['list'] = entries
        merged = installer.merge_config(self.config, self.remote)
        self.assertEqual(merged['agents']['list'][:2], entries)
        self.assertNotIn('default', merged['agents']['list'][-1])

    def test_copy_install_creates_backup_and_can_be_repeated(self):
        original_bytes = self.path.read_bytes()
        result = installer.install(self.state, self.remote)
        self.assertFalse(result['validated_by_openclaw'])
        self.assertEqual((Path(result['backup']) / 'openclaw.json').read_bytes(), original_bytes)
        workspace = self.state / 'workspace-interviewer'
        self.assertTrue((workspace / 'skills/offerlab-interviewer/SKILL.md').is_file())
        (workspace / 'local-note.txt').write_text('preserved')
        first = json.loads(self.path.read_text())
        installer.install(self.state, self.remote)
        self.assertEqual(json.loads(self.path.read_text()), first)
        self.assertEqual((workspace / 'local-note.txt').read_text(), 'preserved')
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertFalse((self.state / '.offerlab-install.lock').exists())

    def test_validator_failure_changes_nothing(self):
        original = self.path.read_bytes()
        def reject(candidate, state):
            self.assertEqual(state, self.state)
            self.assertEqual(self.path.read_bytes(), original)
            self.assertTrue(candidate.exists())
            raise ValueError('unsupported field')
        with self.assertRaises(ValueError):
            installer.install(self.state, self.remote, reject)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.state / 'workspace-interviewer').exists())
        self.assertFalse((self.state / '.offerlab-install.lock').exists())

    def test_reinstall_preserves_personal_model_and_provider(self):
        installer.install(self.state, self.remote)
        config = json.loads(self.path.read_text())
        model = {'primary': 'personal-deepseek/custom-model', 'fallbacks': []}
        provider = {'apiKey': 'personal-test-key', 'models': [{'id': 'custom-model'}]}
        config['agents']['list'][1]['model'] = model
        config['models']['providers']['personal-deepseek'] = provider
        self.path.write_text(json.dumps(config))
        installer.install(self.state, self.remote)
        updated = json.loads(self.path.read_text())
        self.assertEqual(updated['agents']['list'][1]['model'], model)
        self.assertEqual(updated['models'], config['models'])
        self.assertEqual(updated['agents']['defaults'], config['agents']['defaults'])
        self.assertEqual(updated['gateway'], config['gateway'])

    def test_existing_string_model_does_not_require_default_model(self):
        del self.config['agents']['defaults']['model']
        self.config['agents']['list'] = [{'id': 'interviewer', 'model': 'personal-deepseek/custom-model'}]
        merged = installer.merge_config(self.config, self.remote)
        self.assertEqual(merged['agents']['list'][0]['model'], 'personal-deepseek/custom-model')

    def test_concurrent_configuration_edit_is_not_overwritten(self):
        updated = json.dumps(self.config | {'new': 'concurrent-setting'})
        def concurrent(candidate, state):
            self.path.write_text(updated)
        with self.assertRaises(ValueError):
            installer.install(self.state, self.remote, concurrent)
        self.assertEqual(self.path.read_text(), updated)
        self.assertFalse((self.state / 'workspace-interviewer').exists())

    def test_commit_failure_rolls_back_config_and_new_workspace(self):
        original = self.path.read_bytes()
        write = installer.atomic_write
        def fail_config(path, content, mode=0o600):
            if path == self.path and content != original:
                raise OSError('simulated disk failure')
            return write(path, content, mode)
        with patch.object(installer, 'atomic_write', side_effect=fail_config):
            with self.assertRaises(OSError):
                installer.install(self.state, self.remote)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse((self.state / 'workspace-interviewer').exists())

    def test_unmanaged_interviewer_is_not_overwritten(self):
        workspace = self.state / 'workspace-interviewer'
        workspace.mkdir()
        (workspace / 'important.txt').write_text('keep')
        with self.assertRaises(ValueError):
            installer.install(self.state, self.remote)
        self.assertEqual((workspace / 'important.txt').read_text(), 'keep')

    def test_different_config_version_is_rejected(self):
        self.config['meta']['lastTouchedVersion'] = 'different'
        self.path.write_text(json.dumps(self.config))
        with self.assertRaises(ValueError):
            installer.install(self.state, self.remote)

    def test_nested_symlink_cannot_redirect_workspace_writes(self):
        installer.install(self.state, self.remote)
        workspace = self.state / 'workspace-interviewer'
        destination = workspace / 'SOUL.md'
        destination.unlink()
        outside = Path(self.temp.name) / 'outside.txt'
        outside.write_text('do not overwrite')
        destination.symlink_to(outside)
        original = self.path.read_bytes()
        with self.assertRaises(ValueError):
            installer.install(self.state, self.remote)
        self.assertEqual(outside.read_text(), 'do not overwrite')
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(destination.is_symlink())

    def test_archive_contains_only_declared_source_files(self):
        path = Path(self.temp.name) / 'agent.tar.gz'
        count = packager.package(path)
        with tarfile.open(path) as archive:
            names = archive.getnames()
            self.assertEqual(len(names), count)
            self.assertEqual(count, len(installer.FILES) + 2)
            self.assertTrue(all(name.startswith('offerlab-interviewer/') for name in names))
            self.assertFalse(any('.openclaw' in name or '.env' in name or 'openclaw.json' in name for name in names))
            for entry in archive:
                self.assertTrue(entry.isfile())
                self.assertNotIn(b'test-gateway-secret', archive.extractfile(entry).read())


if __name__ == '__main__':
    unittest.main()
