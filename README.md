# AI Model Lab (KDE) — pre-release source

A local Python/Qt6 application for managing independent llama.cpp servers, GPU affinity,
Open WebUI / Agent Office / ComfyUI, launching Pi or OpenCode, and offline benchmarks.

**Status:** experimental developer preview, not yet production-hardened.

## Environment

- Linux / KDE Plasma, Python 3.11+, Qt6 Python bindings (`pyside6` on Arch/CachyOS).
- An installed `llama-server` from [llama.cpp](https://github.com/ggml-org/llama.cpp).
- NVIDIA GPUs require working CUDA drivers and `nvidia-smi` for GPU-specific features.
- Pi and OpenCode are optional external tools, installed independently.

## Install

```bash
sudo pacman -S pyside6
bash ./install.sh
~/.local/bin/ai-model-lab
```

`install.sh` copies the app into `${AI_MODEL_LAB_HOME:-$HOME/AI/AI-Model-Lab}`.
Model files are never copied. When `models.json` / `settings.json` do not exist,
the installer creates them from the bundled example files. Existing configs
and reports are preserved across upgrades.

## Development and tests

```bash
python3 release_preflight.py
python3 -m unittest discover -s tests -v
```

The release preflight checks all Python sources and evaluates the Qt stylesheet
without requiring a graphical environment. UI and CUDA integration still
need real-device testing.

## Privacy & security

Do not commit `data/`, actual `models.json` or `settings.json`, API keys, private
Android sources, model weights, or chat history. See [SECURITY.md](SECURITY.md).

The public-source P1/P2 Android prompts are generic examples and live under
`benchmarks/prompts/`. They are **not the same benchmarks** used in private
Android-project experiments; do not compare scores across these suites as if
identical. Pi agent tests require separately installed and configured Pi.

## License

**PolyForm Noncommercial License 1.0.0** (see `LICENSE`, `NOTICE`, `LICENSING_HISTORY.md`). Commercial use requires separate authorization from the rightsholder(s). This is source-available, **not** OSI open-source. Trademarks and model weights are not included.

## Languages (v3.8)

The top bar now includes a language selector next to **Refresh**:
**Русский / English**. The selection is saved in `settings.json` under
`"language"`, and the window is rebuilt without stopping detached model
servers. Finish a benchmark or model start/stop operation before changing
language. Model responses, logs, benchmark outputs, and user-defined profile
names are not translated.

Translation catalogs live in `locales/`. See `locales/README.md` to add other
languages; missing translations fall back to Russian.

**Licensing history note:** previous archived versions may have been provided under MIT. Changing the current license does not retroactively revoke prior MIT rights. See `LICENSING_HISTORY.md`.


## User-defined AI services (v3.9)

The **Management** tab supports custom local services. Click **Add service** to
configure a unique ID, display name, an argv-style launch command (no shell),
working directory, optional loopback health-check URL, and optional browser URL.
Each custom service has one Start/Stop button that changes with its state.
Only the exact process launched by AI Model Lab can be stopped from the GUI;
unrelated system processes are never killed by name. Profiles are stored in
`services.json`, and runtime metadata/logs in `data/`.

**Security:** entering a command grants it your Linux user privileges. Use only
commands you trust. Do not put secrets in command-line arguments; they can be
visible to other local users through process listings.

### Exit modes (v3.10)

Closing the KDE window offers **Minimize to tray**, **Exit (keep servers running)**, **Exit and stop all managed services**, and **Cancel**. Full exit gracefully stops only owned llama.cpp instances, user-created AI services, managed Agent Office/ComfyUI processes, and the configured user-systemd WebUI unit. External processes and independently launched Pi/OpenCode sessions are not terminated. If an owned service fails to stop, the window remains open and reports the error.
