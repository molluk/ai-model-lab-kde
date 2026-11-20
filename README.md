# AI Model Lab (KDE) — v3.7 source with reconstructed release history

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

**Public benchmarks:** two generic Android source-navigation prompts are supplied
under `benchmarks/prompts/` for demonstration. They are **not** the original
project-specific private benchmark prompts; scores must not be compared to
pre-release benchmark archives. See `HISTORY_PROVENANCE.md`.

The model catalog bundled with this public source is an example only. Set your own
GGUF paths and endpoints before launching a model.

## License

PolyForm Noncommercial 1.0.0 (see `LICENSE` and `NOTICE`). Trademarks and model weights are not included.
