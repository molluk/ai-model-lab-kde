# AI Model Lab KDE

[Русский](README_RU.md) | **English** | [Installation](INSTALL.md) | [Changelog](CHANGELOG.md) | [Contributing](CONTRIBUTING.md)

**AI Model Lab** is an experimental, open-source Python/Qt6 desktop app for starting and monitoring local AI models on Linux. It manages independent `llama.cpp` servers, connects developer agents to a selected server, and runs reproducible local benchmarks.

> **Development preview — v3.7.** Built primarily for CachyOS / Arch Linux with KDE Plasma. Other distributions, GPUs, and clients need testing. It does not download LLM weights.

## Features

- **Model profiles:** add, edit, clone, delete and save GGUF model profiles; configure context, sampling, CPU/GPU layers, KV cache, and optional multimodal settings.
- **Independent servers:** run different models simultaneously on different localhost ports, and optionally bind each to a NVIDIA GPU by index or UUID. Multiple processes may share a GPU if memory permits; VRAM is not pooled automatically.
- **Live monitoring:** NVIDIA GPU/VRAM utilization, host RAM, process status, logs, and historical benchmark statistics.
- **Service controls:** manage individually launched `llama-server`, Open WebUI, Agent Office, and ComfyUI (depending on local installation).
- **Agent clients:** select Pi or OpenCode per model and open the client against the *running* server's API, without rewriting the global client configuration.
- **Built-in benchmarks:** speed, numerical QA, synthetic context recall and example Android source-navigation tasks; per-run reports stay in the application's data folder.
- **KDE tray:** hide the window while the managed servers continue running. Profile preferences survive GUI restarts.

## Requirements

- Linux, Python 3.11+, Qt6 Python bindings (`pyside6` on CachyOS / Arch Linux).
- [llama.cpp](https://github.com/ggml-org/llama.cpp) built with `llama-server` on your machine and at least one compatible `.gguf` model file.
- For NVIDIA-specific monitoring and GPU affinity: compatible drivers/CUDA and working `nvidia-smi`.
- Optional: [Pi](https://github.com/badlogic/pi-mono), [OpenCode](https://opencode.ai/), [Open WebUI](https://github.com/open-webui/open-webui), Agent Office and ComfyUI. Install these separately as needed.

## Quick start (CachyOS / Arch)

```bash
sudo pacman -Syu pyside6
python3 release_preflight.py
bash ./install.sh
~/.local/bin/ai-model-lab
```

The installer copies the app to `~/AI/AI-Model-Lab` by default (override via `AI_MODEL_LAB_HOME`). A KDE application shortcut is created. Your models stay where they are; edit the example model profiles after installation.

See **[INSTALL.md](INSTALL.md)** for a complete setup walkthrough, model paths, GPU assignment, Pi/OpenCode, troubleshooting and upgrades. The Russian instructions are at **[INSTALL_RU.md](INSTALL_RU.md)**.

## Using the app

1. Go to **Models → Edit** and set the GGUF path, `llama-server` path, model context, GPU affinity and a unique API port. Save the profile.
2. Click **Start model**, then wait for the ready/running state. Opening Pi/OpenCode before the model is ready is intentionally blocked.
3. Choose **Pi** or **OpenCode** next to **Open in**. Merely changing that preference saves it and **does not** start the server.
4. Run API tests on the **Tests** tab; read outputs and compare histories in **Reports**.
5. Stop an individual process under **Management**, or close just the GUI and leave servers running.

## What stays on disk

| Data | Location |
|---|---|
| Model profiles | `models.json` inside the installed app |
| App options | `settings.json` |
| Managed process metadata | `data/instances/` |
| Logs | `data/logs/` |
| Benchmark reports | `data/reports/` |
| Isolated agent configurations | `data/clients/` |

These local data files must **not** be committed. The repository contains only `models.example.json` and `settings.example.json`. The examples are not guaranteed ready to start until actual paths are supplied.

## Developer checks

```bash
python3 release_preflight.py
python3 -m unittest discover -s tests -v
```

The tests include headless checks; they do **not** certify UI behavior on every compositor, model load, CUDA reliability, or performance.

## Security and privacy

- Interactive AI agents may be allowed by their own configuration to access or modify files. Restrict access and permissions before using them on sensitive code. A read-only list of Pi tools is **not** an OS sandbox.
- Do not push actual `models.json`, `settings.json`, `data/`, API credentials, chat history, private Android repositories, or downloaded GGUF weights.
- Local HTTP APIs bind to loopback by default. Review any changes before exposing an API outside the host.

See [SECURITY.md](SECURITY.md) and [HISTORY_PROVENANCE.md](HISTORY_PROVENANCE.md).

## Project history and license

The tagged Git history v1.0–v3.7 was **reconstructed from release ZIPs**, not recovered from the original development commits. It records verifiable release changes, with sanitized example configurations. See [CHANGELOG.md](CHANGELOG.md).

Maintainer: [@molluk](https://github.com/molluk). **All commits and tags in this reconstructed public history use PolyForm Noncommercial 1.0.0.** Earlier separately circulated ZIP archives may have different licensing; that is not retroactively changed. Preserve the applicable copyright and license notices when redistributing. See [LICENSE](LICENSE) and [LICENSING_GUIDE.md](LICENSING_GUIDE.md).

## Localization (v3.8)
The toolbar now includes a Russian/English selector. UI catalogs are stored
in `locales/`. The selected language is saved in user `settings.json`.
