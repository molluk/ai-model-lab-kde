#!/usr/bin/env python3
"""Best-effort network-namespace sandbox for Pi/OpenCode launched by AI Model Lab.

Uses bubblewrap --unshare-net for actual TCP/IP isolation and a single fixed
AF_UNIX -> 127.0.0.1:model-port bridge.  Does NOT sandbox the llama-server,
existing sessions, files, D-Bus, or third-party clients. Never silently falls
back to an unsandboxed launch when offline is selected.

The chosen network namespace has only its own loopback network. The UNIX bridge
provides access exclusively to the selected local llama-server port. The client
still sees the normal OpenAI-compatible URL http://127.0.0.1:PORT/v1.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import select
import shutil
import socket
import socketserver
import subprocess
import sys
import tempfile
import threading

POLICIES = ("online", "offline")


def mode(profile: dict | None) -> str:
    value = (profile or {}).get("client_network", "online")
    return value if value in POLICIES else "online"


def require_bubblewrap() -> str:
    binary = shutil.which("bwrap")
    if not binary:
        raise RuntimeError(
            "Режим офлайн требует bubblewrap (CachyOS/Arch: пакет bubblewrap). "
            "Клиент НЕ запущен; разрешение сети не подменялось.")
    return binary


def _relay(a: socket.socket, b: socket.socket) -> None:
    sockets = [a, b]
    try:
        while sockets:
            readable, _, _ = select.select(sockets, [], [], 1)
            for source in readable:
                target = b if source is a else a
                data = source.recv(65536)
                if not data:
                    return
                target.sendall(data)
    except (OSError, ValueError):
        pass
    finally:
        for sock in (a, b):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass


class ThreadedUnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True


def host_bridge(socket_path: Path, port: int):
    """Host can dial exactly one configured local TCP destination."""
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            try:
                dest = socket.create_connection(("127.0.0.1", port), timeout=5)
            except OSError:
                self.request.close()
                return
            _relay(self.request, dest)
    server = ThreadedUnixServer(str(socket_path), Handler)
    os.chmod(socket_path, 0o600)
    return server


def sandbox_bridge(socket_path: Path, port: int):
    """Inside --unshare-net, expose localhost PORT with a UNIX-only upstream."""
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            dest = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                dest.connect(str(socket_path))
            except OSError:
                dest.close()
                self.request.close()
                return
            _relay(self.request, dest)
    return ThreadedTCPServer(("127.0.0.1", port), Handler)


def sandbox_argv(bwrap: str, script: Path, socket_path: Path, port: int,
                 workspace: Path, client_args: list[str]) -> list[str]:
    """Use no shell, no sudo; preserve the existing filesystem for dev tools."""
    if not 1024 <= int(port) <= 65535:
        raise ValueError("Недопустимый порт локальной модели")
    if not workspace.is_dir():
        raise FileNotFoundError("Рабочий каталог клиента отсутствует: " + str(workspace))
    if not client_args:
        raise ValueError("Не задана команда ИИ-клиента")
    return [
        bwrap, "--unshare-net", "--die-with-parent",
        "--bind", "/", "/",
        "--proc", "/proc", "--dev-bind", "/dev", "/dev",
        "--chdir", str(workspace),
        "--", sys.executable, str(script), "sandbox", str(socket_path),
        str(port), "--", *client_args,
    ]


def run_isolated(*, args: list[str], env: dict[str, str], port: int,
                 workspace: Path, app_data: Path,
                 runner=subprocess.run, bwrap: str | None = None) -> int:
    """On any missing dependency/setup error, do not run the agent normally."""
    binary = bwrap or require_bubblewrap()
    port = int(port)
    directory = app_data / "offline-sockets"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    if directory.is_symlink():
        raise RuntimeError("Недопустимая символьная ссылка в каталоге офлайн-сокетов")
    directory.chmod(0o700)
    script = Path(__file__).resolve()
    with tempfile.TemporaryDirectory(prefix="client-", dir=directory) as td:
        sock = Path(td) / "model.sock"
        bridge = host_bridge(sock, port)
        serving = threading.Thread(target=bridge.serve_forever,
                                   kwargs={"poll_interval": 0.1}, daemon=True)
        serving.start()
        try:
            cmd = sandbox_argv(binary, script, sock, port, workspace, args)
            isolated_env = dict(env)
            # Proxies cannot bring internet back into an isolated netns, but
            # removing them avoids routing even local API traffic away.
            for key in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
                        "http_proxy", "https_proxy", "all_proxy"):
                isolated_env.pop(key, None)
            isolated_env["NO_PROXY"] = "localhost,127.0.0.1,::1"
            isolated_env["no_proxy"] = isolated_env["NO_PROXY"]
            completed = runner(cmd, env=isolated_env, cwd=str(workspace))
            return int(completed.returncode)
        finally:
            bridge.shutdown()
            bridge.server_close()
            serving.join(timeout=2)


def sandbox_process(socket_path: Path, port: int, argv: list[str]) -> int:
    """A small proxy stays alive while the interactive terminal client runs."""
    with sandbox_bridge(socket_path, port) as bridge:
        thread = threading.Thread(target=bridge.serve_forever,
                                  kwargs={"poll_interval": 0.1}, daemon=True)
        thread.start()
        try:
            child = subprocess.run(argv, check=False)
            return child.returncode
        finally:
            bridge.shutdown()
            thread.join(timeout=2)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("role", choices=["sandbox"])
    parser.add_argument("socket_path", type=Path)
    parser.add_argument("port", type=int)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        parser.error("Отсутствует команда клиента")
    return sandbox_process(args.socket_path, args.port, command)


if __name__ == "__main__":
    raise SystemExit(main())
