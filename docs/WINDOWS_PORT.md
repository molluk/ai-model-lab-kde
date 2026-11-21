# Windows 10/11 port — experimental branch

**Status:** Windows GUI packaging/bootstrap milestone, **not a release**.
PySide6 provides a cross-platform UI, but the current app still relies on Linux
`/proc`, POSIX process signals, `systemd`, and Linux-specific AI-service paths.
Building an `.exe` does not yet make model management safe or functional.

## Build (Windows, Python 3.11 x64)

```powershell
python -m pip install -r windows/requirements-build.txt
powershell -ExecutionPolicy Bypass -File windows/build.ps1 -SkipInstall
```

The result is `dist/AI-Model-Lab/AI-Model-Lab.exe` (PyInstaller onedir).
Windows keeps user data under `%LOCALAPPDATA%\AI-Model-Lab\`. Linux retains
its existing installed-directory layout and `install.sh` workflow.
Private configs, tokens, models and Android projects must not be committed.

## Remaining work

1. [x] Platform-safe import/locking, data directory and Windows CI packaging.
2. [ ] Cross-platform owned-process identity (creation timestamp, executable, argv)
   and safe termination, preventing PID reuse and accidental external termination.
3. [ ] Multiple Windows `llama-server.exe` instances, GPU UUID isolation, VRAM tests.
4. [ ] Windows Pi/OpenCode, WebUI, Agent Office, ComfyUI and benchmarks.
5. [ ] Native RAM/CPU measurements, exit handling, localized errors.
6. [ ] Run real Windows 10 and Windows 11 tests; installer/signing.

Until process ownership is implemented, Windows users must not treat model
and service start/stop controls as functional or safe. Use the Linux release
from `main` for production.
