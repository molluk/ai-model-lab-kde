"""Offline tests for model-to-client routing without starting any real agent."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import client_launcher as client
import core

INFO = {'alias': 'blend-q4', 'name': 'Blend Q4', 'port': 8081,
        'context': 131072, 'url': 'http://127.0.0.1:8081/v1', 'mmproj': False}


class TestClients(unittest.TestCase):
    def test_v1_config_points_to_selected_port(self):
        cfg = client.opencode_v1_config(INFO)
        entry = cfg['provider']['ai-model-lab']
        self.assertEqual(entry['options']['baseURL'], INFO['url'])
        self.assertIn('blend-q4', entry['models'])
        self.assertEqual(entry['models']['blend-q4']['limit']['context'], 131072)

    def test_v2_config_points_to_selected_port(self):
        cfg = client.opencode_v2_config(INFO)
        entry = cfg['providers']['ai-model-lab']
        self.assertEqual(entry['settings']['baseURL'], INFO['url'])
        self.assertEqual(cfg['model'], 'ai-model-lab/blend-q4')

    def test_opencode_versions(self):
        for version in (1, 2):
            with mock.patch.object(client, 'opencode_major', return_value=version):
                argv, env, label = client.build_command(INFO, 'opencode', '/tmp/opencode')
            self.assertEqual(env.get('OPENCODE_CONFIG_CONTENT') is not None, True)
            self.assertEqual(argv[-1], 'ai-model-lab/blend-q4')
            self.assertEqual('--standalone' in argv, version == 2)

    def test_pi_isolation_does_not_write_user_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            before = core.MODELS
            original_data = core.DATA
            original_models = core.MODELS
            original_settings = core.SETTINGS
            try:
                core.DATA = Path(tmp) / 'data'
                core.LOGS = core.DATA / 'logs'
                core.REPORTS = core.DATA / 'reports'
                core.MODELS = Path(tmp) / 'models.json'
                core.SETTINGS = Path(tmp) / 'settings.json'
                with mock.patch.object(client, 'pi_global_matches', return_value=False):
                    argv, env, _ = client.build_command(INFO, 'pi', '/tmp/pi')
                self.assertEqual(argv[-1], 'off')
                self.assertEqual(argv[2], 'ai-model-lab')
                path = Path(env['PI_CODING_AGENT_DIR']) / 'models.json'
                self.assertTrue(path.is_file())
                loaded = core.load_json(path)
                provider = loaded['providers']['ai-model-lab']
                self.assertEqual(provider['baseUrl'], INFO['url'])
                self.assertEqual(provider['models'][0]['maxTokens'], 8192)
                self.assertFalse((Path(tmp) / 'models.json').exists())
            finally:
                core.DATA = original_data
                core.LOGS = original_data / 'logs'
                core.REPORTS = original_data / 'reports'
                core.MODELS = original_models
                core.SETTINGS = original_settings

    def test_pi_reuses_matching_global_provider(self):
        with mock.patch.object(client, 'pi_global_matches', return_value=True):
            argv, env, _ = client.build_command(INFO, 'pi', '/tmp/pi')
        self.assertEqual(argv[2], 'local-lab')
        self.assertNotIn('PI_CODING_AGENT_DIR', env) if 'PI_CODING_AGENT_DIR' not in os.environ else None

    def test_ready_alias_verified_against_props(self):
        instance = {'managed': True, 'state': 'running', 'port': 8081, 'context': 131072}
        p = {'id': 'blend-q4', 'name': 'Blend Q4', 'context': 131072}
        with mock.patch.object(client.multi, 'inspect', return_value=instance), \
                mock.patch.object(client.multi, 'profile_by_id', return_value=p), \
                mock.patch.object(client.core, 'json_api', return_value={
                    'model_alias': 'not-blend', 'default_generation_settings': {'n_ctx': 131072}}):
            with self.assertRaises(RuntimeError):
                client.effective_instance('blend-q4')

    def test_ready_uses_live_port(self):
        instance = {'managed': True, 'state': 'running', 'port': 8082, 'context': 32768}
        p = {'id': 'model-copy', 'name': 'Copy', 'context': 131072}
        with mock.patch.object(client.multi, 'inspect', return_value=instance), \
                mock.patch.object(client.multi, 'profile_by_id', return_value=p), \
                mock.patch.object(client.core, 'json_api', return_value={
                    'model_alias': 'model-copy', 'default_generation_settings': {'n_ctx': 32768}}):
            info = client.effective_instance('model-copy')
        self.assertEqual(info['url'], 'http://127.0.0.1:8082/v1')
        self.assertEqual(info['context'], 32768)

if __name__ == '__main__':
    unittest.main()
