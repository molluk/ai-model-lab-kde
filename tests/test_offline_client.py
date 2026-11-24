"""Offline-client network isolation tests; bubblewrap is never required by CI."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import socketserver
import sys
import tempfile
import threading
import unittest
from unittest import mock
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import offline_client
import client_launcher


class Echo(socketserver.BaseRequestHandler):
    def handle(self):
        message = self.request.recv(1024)
        self.request.sendall(message.upper())


class EchoServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class OfflineTests(unittest.TestCase):
    def test_per_model_default_and_modes(self):
        self.assertEqual(offline_client.mode({}), "online")
        self.assertEqual(offline_client.mode({"client_network": "offline"}), "offline")
        self.assertEqual(offline_client.mode({"client_network": "bogus"}), "online")

    def test_missing_bubblewrap_refuses_launch(self):
        with mock.patch.object(offline_client.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "НЕ запущен"):
                offline_client.require_bubblewrap()

    def test_sandbox_argv_uses_unshare_net_and_single_loopback_forwarder(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            argv = offline_client.sandbox_argv(
                "/usr/bin/bwrap", ROOT / "offline_client.py",
                p / "proxy.sock", 8080, p, ["/usr/bin/agent", "--model", "qwen"])
            self.assertIn("--unshare-net", argv)
            self.assertIn("--die-with-parent", argv)
            self.assertEqual(argv[0], "/usr/bin/bwrap")
            self.assertEqual(argv[argv.index("sandbox") + 2], "8080")
            self.assertEqual(argv[-3:], ["/usr/bin/agent", "--model", "qwen"])

    def test_host_unix_bridge_only_forwards_to_configured_local_port(self):
        with EchoServer(("127.0.0.1", 0), Echo) as tcp:
            th = threading.Thread(target=tcp.serve_forever, daemon=True)
            th.start()
            try:
                with tempfile.TemporaryDirectory() as td:
                    sock_path = Path(td) / "bridge.sock"
                    with offline_client.host_bridge(sock_path, tcp.server_address[1]) as bridge:
                        bridge_thread = threading.Thread(target=bridge.serve_forever,
                                                         daemon=True)
                        bridge_thread.start()
                        try:
                            with socket.socket(socket.AF_UNIX) as unix:
                                unix.settimeout(3)
                                unix.connect(str(sock_path))
                                unix.sendall(b"hello")
                                self.assertEqual(unix.recv(1024), b"HELLO")
                            self.assertEqual(sock_path.stat().st_mode & 0o777, 0o600)
                        finally:
                            bridge.shutdown()
                            bridge_thread.join(timeout=3)
            finally:
                tcp.shutdown()
                th.join(timeout=3)

    def test_both_proxy_sides_reach_only_the_selected_local_server(self):
        with EchoServer(("127.0.0.1", 0), Echo) as model_server:
            t1 = threading.Thread(target=model_server.serve_forever, daemon=True)
            t1.start()
            try:
                with tempfile.TemporaryDirectory() as td:
                    path = Path(td) / "socket"
                    with offline_client.host_bridge(path, model_server.server_address[1]) as host:
                        t2 = threading.Thread(target=host.serve_forever, daemon=True)
                        t2.start()
                        try:
                            # The same bridge can run in normal loopback for
                            # testing; bubblewrap creates the separate namespace.
                            with offline_client.sandbox_bridge(path, 0) as guest:
                                t3 = threading.Thread(target=guest.serve_forever, daemon=True)
                                t3.start()
                                try:
                                    with socket.create_connection(
                                            guest.server_address, timeout=3) as connection:
                                        connection.sendall(b"loopback")
                                        self.assertEqual(connection.recv(1024), b"LOOPBACK")
                                finally:
                                    guest.shutdown()
                                    t3.join(timeout=3)
                        finally:
                            host.shutdown()
                            t2.join(timeout=3)
            finally:
                model_server.shutdown()
                t1.join(timeout=3)

    def test_run_isolated_does_not_exec_unrestricted_client(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            observed = {}
            def simulated_runner(cmd, *, cwd, env):
                observed["cmd"] = cmd
                observed["env"] = env
                observed["cwd"] = cwd
                path = Path(cmd[cmd.index("sandbox") + 1])
                self.assertTrue(path.is_socket())
                return SimpleNamespace(returncode=0)
            env = {"HTTP_PROXY": "http://unsafe", "PATH": "/usr/bin"}
            result = offline_client.run_isolated(
                args=["/usr/bin/echo", "ok"], env=env, port=8090,
                workspace=root, app_data=root / "data",
                runner=simulated_runner, bwrap="/usr/bin/bwrap")
            self.assertEqual(result, 0)
            self.assertIn("--unshare-net", observed["cmd"])
            self.assertNotIn("HTTP_PROXY", observed["env"])
            self.assertEqual(observed["env"]["NO_PROXY"], "localhost,127.0.0.1,::1")
            self.assertEqual(observed["cwd"], str(root))
            self.assertEqual(list((root / "data/offline-sockets").glob("client-*")), [])

    def test_client_launcher_policy_reaches_sandbox_not_execvpe(self):
        info = {"alias": "qwen", "port": 8090, "context": 32768,
                "name": "Qwen", "url": "http://127.0.0.1:8090/v1"}
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(client_launcher, "effective_instance", return_value=info), \
                 mock.patch.object(client_launcher, "find_executable", return_value="/bin/pi"), \
                 mock.patch.object(client_launcher, "workspace_dir", return_value=Path(td)), \
                 mock.patch.object(client_launcher, "build_command", return_value=(["/bin/pi"], {}, "Pi")), \
                 mock.patch.object(client_launcher.multi, "profile_by_id", return_value={
                     "id": "qwen", "client_network": "offline"}), \
                 mock.patch.object(client_launcher.offline_client, "run_isolated", return_value=0) as isolated, \
                 mock.patch.object(client_launcher.os, "execvpe") as executable:
                result = client_launcher.execute("pi", "qwen")
                self.assertEqual(result, 0)
                self.assertEqual(isolated.call_args.kwargs["port"], 8090)
                executable.assert_not_called()


if __name__ == "__main__":
    unittest.main()
