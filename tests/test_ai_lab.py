import copy
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TARGET = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ai_lab_v2', TARGET / 'ai_lab.py')
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)

class ModelLabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cfg = json.loads((TARGET/'models.json').read_text(encoding='utf8'))
        self.paths = []
        for p in self.cfg['models']:
            if p.get('path'):
                relative = p['path']
            elif p['id'] == 'blend-q5':
                relative = 'models/jetbrains-blend-Q5_K_M.gguf'
            else:
                relative = 'models/Devstral-Small-2-Q4_K_M.gguf'
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fake gguf')
            self.paths.append(path)
            if p.get('mmproj'):
                mm = self.root / p['mmproj']; mm.parent.mkdir(parents=True, exist_ok=True); mm.write_bytes(b'fake mmproj')
        self.env = patch.dict(os.environ, {'AI_LAB_MODEL_ROOT':str(self.root), 'AI_LAB_SERVER_BIN':sys.executable})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_unique_models(self):
        ids = [m['id'] for m in self.cfg['models']]
        self.assertEqual(len(ids), 7)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('coder-30b-ud', ids)

    def test_all_models_build_commands(self):
        for profile in self.cfg['models']:
            with self.subTest(model=profile['id']):
                cmd, gguf = lab.build_command(self.cfg, profile)
                self.assertTrue(gguf.is_file())
                self.assertIn('--alias', cmd)
                self.assertEqual(cmd[cmd.index('--alias')+1], profile['id'])
                self.assertEqual(cmd[cmd.index('-c')+1], str(profile['context']))
                self.assertIn('--no-kv-offload', cmd)
                self.assertIn('--metrics', cmd)
                self.assertIn('--cache-type-k', cmd)
                if profile['id'] == 'qwen3-vl-30b':
                    self.assertIn('--mmproj', cmd)
                if profile['id'] == 'coder-30b-ud':
                    self.assertIn('--n-cpu-moe', cmd)
                if profile['id'] in ('blend-q4','qwen38-27b'):
                    self.assertIn('--chat-template-kwargs', cmd)

    def test_process_identity_requires_matching_start(self):
        meta = {'tag':'llama','pid':os.getpid(), 'start_ticks':lab.process_start_ticks(os.getpid()),
                'exe':str(Path('/proc/self/exe').resolve())}
        self.assertTrue(lab.process_owned(meta, 'llama'))
        self.assertFalse(lab.process_owned({**meta,'start_ticks':meta['start_ticks']+1}, 'llama'))
        self.assertFalse(lab.process_owned(meta, 'comfy'))

    def test_stop_only_verified_owned_process(self):
        import subprocess
        proc = subprocess.Popen(['/bin/sleep', '40'], start_new_session=True)
        saved = lab.SERVER_STATE
        lab.SERVER_STATE = self.root/'llama.json'
        try:
            meta = lab.proc_meta(proc, 'llama', Path('/bin/sleep'), alias='test')
            lab.atomic_json(lab.SERVER_STATE, meta)
            self.assertTrue(lab.process_owned(meta, 'llama'))
            self.assertTrue(lab.stop_owned(lab.SERVER_STATE, 'llama'))
            self.assertIsNotNone(proc.wait(timeout=5))
        finally:
            lab.SERVER_STATE = saved
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)

    def test_exact_override_ambiguous_is_error(self):
        extra = self.root/'x/other-blend-Q5_K_M.gguf'
        extra.parent.mkdir(parents=True,exist_ok=True); extra.write_bytes(b'test')
        p = next(x for x in self.cfg['models'] if x['id']=='blend-q5')
        with self.assertRaises(RuntimeError):
            lab.choose_file(self.cfg,p)

# Additional UI/service tests are defined in a separate class so existing
# v2 tests remain unmodified. No real subprocess/service is launched.
class V21MenusTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((TARGET/'models.json').read_text(encoding='utf8'))

    def test_purposes_even_with_old_installed_config(self):
        for p in self.cfg['models']:
            old = dict(p)
            old.pop('purpose', None)
            self.assertTrue(lab.purpose(old))
            self.assertTrue(lab.purpose(p))

    def test_after_model_routes_into_both_submenus(self):
        from unittest.mock import patch
        with patch.object(lab, 'current_model_alias', return_value='blend-q4'), \
             patch('builtins.input', side_effect=['5','6','0']), \
             patch.object(lab, 'tests_menu') as tests, \
             patch.object(lab, 'management_menu') as management:
            lab.menu_after_model(self.cfg, 'blend-q4')
        tests.assert_called_once_with(self.cfg)
        management.assert_called_once_with(self.cfg)

    def test_management_individual_webui_stop_only(self):
        from unittest.mock import patch
        with patch('builtins.input', side_effect=['5','0']), \
             patch.object(lab, 'stop_webui') as stop_webui, \
             patch.object(lab, 'stop_owned') as stop_owned, \
             patch.object(lab, 'stop_office') as stop_office:
            lab.management_menu(self.cfg)
        stop_webui.assert_called_once_with()
        stop_owned.assert_not_called()
        stop_office.assert_not_called()

    def test_management_test_entry_does_not_stop_server(self):
        from unittest.mock import patch
        with patch('builtins.input', side_effect=['t','m','0']), \
             patch.object(lab, 'tests_menu') as tests, \
             patch.object(lab, 'management_menu') as manager, \
             patch.object(lab, 'stop_all') as stopall:
            lab.main_menu(self.cfg)
        tests.assert_called_once_with(self.cfg)
        manager.assert_called_once_with(self.cfg)
        stopall.assert_not_called()

    def test_unsupported_benchmark_model_cannot_run(self):
        from unittest.mock import patch
        with patch.object(lab, 'current_model_alias', return_value='qwen3-vl-30b'), \
             patch.object(lab.subprocess, 'run') as run:
            self.assertFalse(lab.run_android_benchmark('P1'))
            run.assert_not_called()

    def test_benchmark_context_mismatch_blocks_launch(self):
        from unittest.mock import patch
        pi = {'providers':{'local-lab':{'models':[{'id':'blend-q4','contextWindow':16384}]}}}
        with tempfile.TemporaryDirectory() as directory:
            benchmark = Path(directory) / 'run-LP-01A-comparison.fish'
            benchmark.touch()
            saved = lab.BENCH_SCRIPT
            lab.BENCH_SCRIPT = benchmark
            original_read = lab.read_json
            try:
                with patch.object(lab, 'current_model_alias', return_value='blend-q4'), \
                     patch.object(lab, 'http_json', return_value={'default_generation_settings':{'n_ctx':131072}}), \
                     patch.object(lab, 'read_json', return_value=pi), \
                     patch.object(lab.shutil, 'which', return_value='/usr/bin/fish'), \
                     patch.object(lab.subprocess, 'run') as run:
                    self.assertFalse(lab.run_android_benchmark('P1'))
                    run.assert_not_called()
            finally:
                lab.BENCH_SCRIPT = saved

if __name__ == '__main__':
    unittest.main()
