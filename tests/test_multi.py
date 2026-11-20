"""Multi-instance safety tests with two real local mock HTTP servers, no GPUs required."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import multi
import core

FAKE_SERVER = r'''import argparse,json
from http.server import HTTPServer,BaseHTTPRequestHandler
p=argparse.ArgumentParser()
p.add_argument('--port',type=int,required=True)
p.add_argument('--alias',required=True)
a=p.parse_args()
class H(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        body=json.dumps({'status':'ok'} if self.path=='/health' else {'model_alias':a.alias})
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.end_headers()
        self.wfile.write(body.encode())
HTTPServer(('127.0.0.1',a.port),H).serve_forever()
'''

class TestMulti(unittest.TestCase):
    def test_profile_defaults_and_unique_alias(self):
        self.assertEqual(multi.port_of({'port':8081}),8081)
        self.assertEqual(multi.gpu_of({'gpu':'1'}),'1')
        self.assertEqual(multi.gpu_of({'gpu':'GPU-aaaa-bbbb-cccc'}),'GPU-aaaa-bbbb-cccc')
        with self.assertRaises(ValueError):multi.validate_alias('../bad')
        with self.assertRaises(ValueError):multi.port_of({'port':80})
        with self.assertRaises(ValueError):multi.gpu_of({'gpu':'1; rm -rf /'})

    def test_two_servers_are_independent_and_identity_protected(self):
        import socket
        def free_port():
            with socket.socket() as s:
                s.bind(('127.0.0.1',0))
                return s.getsockname()[1]
        a,b=free_port(),free_port()
        while a==b:b=free_port()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'llama-server').write_text(FAKE_SERVER)
            (root/'llama-server').chmod(0o700)
            profiles=[{'id':'one','port':a,'gpu':'0','context':8192,'name':'One'},
                      {'id':'two','port':b,'gpu':'1','context':8192,'name':'Two'},
                      {'id':'three','port':a,'gpu':'1','context':8192,'name':'Same-port'}]
            def server_command(profile):
                return [sys.executable,str(root/'llama-server'),'--port',str(profile['port']),'--alias',profile['id']]
            with mock.patch.object(multi,'INSTANCES',root/'data'/'instances'),\
                 mock.patch.object(core,'DATA',root/'data'),\
                 mock.patch.object(core,'LOGS',root/'data'/'logs'),\
                 mock.patch.object(core,'REPORTS',root/'data'/'reports'),\
                 mock.patch.object(multi,'profile_by_id',side_effect=lambda alias:next((x for x in profiles if x['id']==alias),None)),\
                 mock.patch.object(core,'server_command',side_effect=server_command),\
                 mock.patch.object(core,'verified',return_value=None):
                try:
                    x=multi.launch('one')
                    y=multi.launch('two')
                    self.assertIn('работает',x)
                    self.assertIn('работает',y)
                    self.assertTrue(multi.inspect('one')['managed'])
                    self.assertTrue(multi.inspect('two')['managed'])
                    self.assertEqual(multi.inspect('three')['state'],'port_conflict')
                    with self.assertRaises(RuntimeError):multi.launch('three')
                    # Cannot launch an alias twice.
                    with self.assertRaises(RuntimeError):multi.launch('one')
                    one=multi.metadata('one').copy()
                    self.assertEqual(one['gpu'],'0')
                    self.assertEqual(multi.metadata('two')['gpu'],'1')
                    # A forged PID start tick must never allow stopping another service.
                    wrong=dict(one,ticks=0)
                    self.assertFalse(multi.owned(wrong))
                    multi.stop('one')
                    self.assertFalse(multi.inspect('one')['alive'])
                    self.assertTrue(multi.inspect('two')['alive'])
                finally:
                    multi.stop('one')
                    multi.stop('two')
