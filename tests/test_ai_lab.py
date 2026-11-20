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

if __name__ == '__main__':
    unittest.main()
