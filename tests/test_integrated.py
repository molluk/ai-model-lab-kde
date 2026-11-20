import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import core
import bench

class TestIntegrated(unittest.TestCase):
    def test_unique_profiles_and_context(self):
        obj=core.load_json(core.ROOT / 'models.example.json', {})
        profiles=obj['models']
        self.assertGreaterEqual(len(profiles), 1)
        aliases=[x['id'] for x in profiles]
        self.assertEqual(len(aliases),len(set(aliases)))
        expected={'blend-q4': 131072, 'qwen38-27b': 131072,
                  'coder-30b': 131072, 'coder-30b-ud': 98304}
        for alias, context in expected.items():
            profile = next((p for p in profiles if p['id'] == alias), None)
            if profile is not None:
                self.assertEqual(profile['context'], context)
        self.assertTrue(all(x.get('purpose') for x in profiles))

    def test_server_command_aliases_and_kv(self):
        with tempfile.TemporaryDirectory() as td:
            exe=Path(td)/'llama-server';exe.touch(mode=0o755)
            gguf=Path(td)/'model.gguf';gguf.write_text('placeholder')
            examples=core.load_json(core.ROOT / 'models.example.json', {})
            for profile in examples.get('models', [])[:3]:
                alias = profile['id']
                with mock.patch.object(core,'server_exe',return_value=exe), mock.patch.object(core,'resolve_gguf',return_value=gguf):
                    args=core.server_command(profile)
                self.assertEqual(args[args.index('--alias')+1],alias)
                self.assertEqual(args[args.index('-c')+1],str(profile['context']))
                self.assertIn('--no-kv-offload',args)
                self.assertEqual(args[args.index('--cache-type-k')+1],'q8_0')
                self.assertEqual(args[args.index('--cache-type-v')+1],'q8_0')
                self.assertIn('--metrics',args)
            profile=next((p for p in examples['models'] if p['id']=='qwen3-vl-30b'), None)
            if profile:
                with mock.patch.object(core,'server_exe',return_value=exe), mock.patch.object(core,'resolve_gguf',return_value=gguf),mock.patch.object(core,'model_root',return_value=Path(td)):
                    (Path(td)/profile['mmproj']).parent.mkdir(parents=True,exist_ok=True)
                    (Path(td)/profile['mmproj']).touch()
                    self.assertIn('--mmproj',core.server_command(profile))

    def test_context_markers(self):
        text=bench.generate_context(8192)
        for value in ('ROUTE_SAFFRON_38','VALIDATE_COBALT_62','localConfiguration.uri.toString()'):
            self.assertEqual(text.count(value),1)
        places=[text.index(x)/len(text) for x in ('route_key=ROUTE_','validation_key=VALIDATE_','requested_fix=localConfiguration')]
        for got,expected in zip(places,(.05,.5,.95)):
            self.assertAlmostEqual(got,expected,delta=.03)

    def test_fingerprint_changes_when_source_changes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); (root/'app').mkdir()
            (root/'app'/'Main.kt').write_text('class Foo {}')
            a=bench.source_digest(root)
            (root/'app'/'Main.kt').write_text('class Foo { val a = 5 }')
            b=bench.source_digest(root)
            self.assertNotEqual(a['sha256'],b['sha256'])
            (root/'build').mkdir();(root/'build'/'Generated.java').write_text('ignore')
            self.assertEqual(b['sha256'],bench.source_digest(root)['sha256'])
            self.assertEqual(b['files'],1)

    def test_pi_event_parser(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'events.jsonl'
            msgs=[{'type':'tool_execution_end','toolName':'read','isError':False},
                  {'type':'message_end','message':{'role':'assistant','usage':{'input':120,'output':12,'cacheRead':200},'stopReason':'stop','content':[{'type':'text','text':'Отчёт готов.'}]}}]
            path.write_text('\n'.join(json.dumps(x) for x in msgs)+'\n')
            r=bench.pi_events(path)
            self.assertEqual(r['status'],'completed')
            self.assertEqual(r['answer'],'Отчёт готов.')
            self.assertEqual(r['tool_calls']['read'],1)
            self.assertEqual(r['peak_context_estimate'],320)

    def test_no_write_tools(self):
        src=Path(bench.__file__).read_text()
        self.assertIn('read,grep,find,ls',src)
        self.assertNotIn('write,edit,bash',src)
        self.assertTrue((core.ROOT/'benchmarks/extensions/tool-guard.js').is_file())
        # Public checkouts may intentionally omit the private-project prompts.
        prompts = list((core.ROOT/'benchmarks/prompts').glob('*.md'))
        self.assertIn(len(prompts), (0,2))

    def test_verified_rejects_unowned_process(self):
        with mock.patch.object(core,'load_json',return_value={'service':'llama','pid':1234,'ticks':22,'exe':'/bin/llama-server','alias':'fake'}),\
             mock.patch.object(core,'start_ticks',return_value=99):
            self.assertIsNone(core.verified('llama'))

    def test_qa_expected(self):
        self.assertEqual(73*19-48,1339)
        self.assertEqual(17*(24-9)+36/3,267)
        self.assertEqual(12**2+13**2,313)

if __name__=='__main__':unittest.main()
