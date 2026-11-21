# AI Model Lab — local AI workstation manager for KDE

**English** · [Русский](docs/README_RU.md) · [Documentation](docs/INDEX.md) · [Windows port plan](docs/WINDOWS_PORT.md) · [Changelog](docs/CHANGELOG.md)

AI Model Lab is an experimental desktop application built with **Python and Qt6** for launching, monitoring and testing local language models on Linux. It manages independent [llama.cpp](https://github.com/ggml-org/llama.cpp) servers and integrates optional AI clients and services.

> **Status: Alpha / experimental.** Primarily developed for CachyOS / Arch Linux with KDE Plasma. Other Linux desktops and GPU configurations need validation. This project does **not** bundle model weights, llama.cpp or external AI clients.

## Features

- **LLM profiles:** add, edit, clone and remove GGUF configurations; adjust context, sampling, CPU/GPU offload, KV cache and multimodal settings.
- **Multiple independent servers:** assign a port and NVIDIA GPU index/UUID per profile; run more than one model simultaneously when hardware resources permit.
- **Local monitoring:** GPU load, VRAM, RAM, process status, live logs and benchmark history.
- **AI clients:** open a running model with **Pi** or **OpenCode**, keeping per-model client preferences. Optional [Pi Office Bridge](docs/PI_OFFICE_BRIDGE.md) displays actual Pi sessions in Agent Office.
- **Services:** manage compatible Open WebUI, Agent Office and ComfyUI setups, or add custom local services. Open each built-in web UI in a browser tab, regular window, or standalone Chromium-style app window without browser controls.
- **Benchmarks:** API throughput, simple QA checks, synthetic context-recall tasks and sample Android code-navigation scenarios; results stay on your machine.
- **Localization:** Russian and English UI; translation catalogs are extendable.
- **KDE system tray:** close the GUI while keeping managed servers running, or explicitly stop all owned services when exiting.

Separate models can share a GPU **only if sufficient VRAM/RAM is available**. GPU memory is not automatically pooled, and simultaneous execution is not a guarantee that both models will fit.

## Requirements and quick start

- Linux with **Python 3.11+** and Qt6 Python bindings (Arch/CachyOS package: `pyside6`).
- A separately installed [llama.cpp](https://github.com/ggml-org/llama.cpp) `llama-server` and GGUF model(s).
- For NVIDIA-specific features: working drivers, CUDA-compatible setup and `nvidia-smi`.
- Optional tools such as Pi, OpenCode, Open WebUI, Agent Office and ComfyUI must be installed separately.

On CachyOS / Arch Linux, from the **repository root**:

```bash
sudo pacman -Syu pyside6
python3 release_preflight.py
bash ./install.sh
~/.local/bin/ai-model-lab
```

The installer uses `~/AI/AI-Model-Lab` by default and preserves existing profiles and reports during upgrades. Set GGUF and `llama-server` paths in the application before first use.

**Installation guides:** [English](docs/INSTALL.md) · [Русский](docs/INSTALL_RU.md)

## Documentation

All guides and release history are under **[`docs/`](docs/INDEX.md)**:

- [Documentation index (EN / RU)](docs/INDEX.md)
- [Installation and troubleshooting](docs/INSTALL.md) · [Установка и диагностика](docs/INSTALL_RU.md)
- [Benchmarks and safety](docs/BENCHMARKS.md) · [Localization / Локализация](docs/LOCALIZATION.md)
- [Contributing](docs/CONTRIBUTING.md) · [Security](docs/SECURITY.md)
- [Changelog](docs/CHANGELOG.md) · [Git history provenance](docs/HISTORY_PROVENANCE.md)
- [License history](docs/LICENSING_HISTORY.md) · [Licensing guide](docs/LICENSING_GUIDE.md)

## Development

```bash
python3 release_preflight.py
python3 -m unittest discover -s tests -v
```

Automated tests do not replace validation of the real KDE UI, GPU drivers or CUDA inference.

## Security and privacy

The local Git checkout and installed application must not include private `models.json`, `settings.json`, `services.json`, API tokens, `data/` logs/reports, chat histories, private Android projects or GGUF weights. Pi/OpenCode tool restrictions do **not** provide OS-level filesystem isolation. Do not expose local HTTP APIs to untrusted networks without independent authentication and isolation. See [Security](docs/SECURITY.md).

## License and attribution

Copyright © 2026 **molluk and AI Model Lab contributors**.

Distributed under **[PolyForm Noncommercial License 1.0.0](LICENSE)**; see [NOTICE](NOTICE) and [licensing history](docs/LICENSING_HISTORY.md). **Commercial use requires separate permission from the rightsholder(s).** This is **source-available, not OSI-defined Open Source**.

The public Git history is reconstructed from release archives and disclosed as such in [HISTORY_PROVENANCE.md](docs/HISTORY_PROVENANCE.md). Separately supplied older copies may retain the rights originally granted to their recipients.
