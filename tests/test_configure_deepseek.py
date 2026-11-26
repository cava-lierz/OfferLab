import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('configure_deepseek', Path(__file__).resolve().parents[1] / 'scripts/configure_deepseek.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class DeepSeekConfigTests(unittest.TestCase):
    def original(self):
        return {
            'gateway': {'auth': {'token': 'gateway-test-secret'}},
            'models': {'providers': {'sjtu': {'apiKey': 'school-test-secret'}}},
            'agents': {
                'defaults': {'model': {'primary': 'sjtu/deepseek-reasoner'}, 'models': {'sjtu/deepseek-reasoner': {}}},
                'list': [{'id': 'main'}, {'id': 'interviewer', 'model': {'primary': 'sjtu/deepseek-reasoner'}, 'tools': {'allow': ['read']}}],
            },
        }

    def test_interviewer_preserves_school_and_gateway_credentials(self):
        original = self.original()
        result = module.merge_config(original, 'personal-test-secret', 'https://api.deepseek.com', 'deepseek-flash', 'interviewer')
        self.assertEqual(original, self.original())
        self.assertEqual(result['gateway'], original['gateway'])
        self.assertEqual(result['models']['providers']['sjtu'], original['models']['providers']['sjtu'])
        self.assertEqual(result['agents']['defaults']['model'], original['agents']['defaults']['model'])
        self.assertEqual(result['agents']['list'][0], {'id': 'main'})
        self.assertEqual(result['agents']['list'][1]['tools'], {'allow': ['read']})
        self.assertIn('personal-deepseek/deepseek-flash', result['agents']['defaults']['models'])
        self.assertEqual(result['agents']['list'][1]['model']['fallbacks'], [])

    def test_default_switch(self):
        result = module.merge_config(self.original(), 'test', 'https://api.deepseek.com', 'deepseek-flash', 'defaults-and-interviewer')
        self.assertEqual(result['agents']['defaults']['model'], result['agents']['list'][1]['model'])

    def test_existing_provider_is_not_overwritten(self):
        original = self.original()
        original['models']['providers'][module.PROVIDER] = {'apiKey': 'existing-test-secret'}
        with self.assertRaises(ValueError):
            module.merge_config(original, 'test', 'https://api.deepseek.com', 'deepseek-flash', 'interviewer')

    def test_missing_agent_rejected(self):
        with self.assertRaises(ValueError):
            module.merge_config({}, 'test', 'https://api.deepseek.com', 'deepseek-flash', 'interviewer')

    def test_update_key_preserves_all_other_settings(self):
        original = module.merge_config(self.original(), 'old-test-key', 'https://api.deepseek.com', 'deepseek-flash', 'defaults-and-interviewer')
        result = module.update_key(original, 'new-test-key')
        self.assertEqual(result['models']['providers'][module.PROVIDER]['apiKey'], 'new-test-key')
        self.assertEqual(original['models']['providers'][module.PROVIDER]['apiKey'], 'old-test-key')
        result['models']['providers'][module.PROVIDER]['apiKey'] = 'old-test-key'
        self.assertEqual(result, original)

    def test_update_key_requires_existing_provider(self):
        with self.assertRaises(ValueError):
            module.update_key(self.original(), 'new-test-key')
