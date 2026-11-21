# Installation and use (English)

[Русский](INSTALL_RU.md) · [Home](../README.md)

## 1. Prepare the host

Tested target: **CachyOS / Arch Linux, KDE Plasma**. Linux Python 3.11+ and a built `llama-server` are required. NVIDIA GPU management needs compatible drivers and `nvidia-smi`.

```bash
sudo pacman -Syu pyside6
python3 -c 'from PySide6.QtWidgets import QApplication; print("PySide6 OK")'
```

Build/install [llama.cpp](https://github.com/ggml-org/llama.cpp) according to its upstream instructions, preferably with CUDA support if you have NVIDIA GPUs. The project does not include or build llama.cpp, nor does it download GGUF weights.

## 2. Install AI Model Lab

In the directory cloned from GitHub (or extracted source):

```bash
python3 release_preflight.py
python3 -m unittest discover -s tests -v
bash ./install.sh
~/.local/bin/ai-model-lab
```

Default destination: `~/AI/AI-Model-Lab`. Use `AI_MODEL_LAB_HOME=/your/directory bash ./install.sh` to change it. The installer creates local configs from `*.example.json` only if they do not already exist, and preserves installed profiles, reports and logs during upgrades.

## 3. Set real paths

Open the installed application's **Models / Settings** tabs and set the actual location of your `.gguf` file, model context and API port. The example catalog is intentionally generic: paths such as `~/AI/models` may not exist. Point the application's `server_bin` setting in **`~/AI/AI-Model-Lab/models.json`** to your executable `llama-server` (or the corresponding path under your custom installation directory).

You may edit `models.json` as text while the GUI is fully closed. Before editing, make a backup; do not modify running profile settings without understanding the effect on the next launch.

## 4. Multiple GPUs or models

Find NVIDIA GPUs and their stable UUIDs:

```bash
nvidia-smi --query-gpu=index,name,uuid,memory.total --format=csv
```

In the model editor, choose a GPU UUID (preferred for identical cards) or CUDA index, and a free API port. Example: Blend Q4 → UUID of first GPU on `8080`; cloned Blend Q4 → UUID of second GPU on `8081`. The clone may reuse the same GGUF file. Each model instance is an independent process and uses its own memory. Multiple models on one GPU are possible only if memory resources permit.

## 5. Pi, OpenCode, Open WebUI and Agent Office

Install optional agents and UIs **separately using their upstream instructions**. In AI Model Lab, select Pi or OpenCode beside **Open in** to save the model preference. This does not start any client or model. Start the model first, wait until it is ready, then click **Open in**.

The client launcher targets the selected local API address and normally leaves your global client configuration untouched. When needed, an isolated Pi profile is created under `data/clients/`. The tools/permissions available to an agent are still governed by the agent itself.

**Open WebUI** is expected at `http://127.0.0.1:3000`. The integrated service start/stop operations depend on a suitable systemd-user service; a manually installed Open WebUI may require external setup. Agent Office and ComfyUI locations are configurable separately.

## 6. Benchmarks and reports

Use the **Tests** tab for API speed, numerical QA, synthetic long context, and sample Android tasks. Output is written under `data/reports`; logs under `data/logs`. See [benchmarks documentation](BENCHMARKS.md). Some Android agent runs require a configured Pi installation and a matching model endpoint/context. Read-only tool restrictions do not constitute an OS sandbox.

The old project-specific benchmark prompts are deliberately **not** included in the public release. Comparisons to old private benchmark runs are not equivalent.

## 7. Troubleshooting

- **No `PySide6`**: run `sudo pacman -Syu pyside6` and verify with the import command above.
- **`llama-server` not found**: set `server_bin` to the real compiled executable and confirm execute permissions.
- **GGUF not found**: choose the exact model file path; a wildcard matching multiple files is ambiguous.
- **Port busy**: give each active server a different TCP port. Do not kill unrelated processes merely to free a port.
- **No GPU / wrong GPU**: check `nvidia-smi` and the selected GPU UUID. An empty GPU selection means automatic behavior, not guaranteed single-device isolation.
- **Model cannot fit in VRAM**: lower context/GPU layers or use a smaller model; reduced memory usage can reduce speed.
- **Pi/OpenCode will not start**: install the chosen client, then verify its command is available in the GUI user's PATH. The model must be running first.
- **Something fails to launch**: run `~/.local/bin/ai-model-lab` from a terminal and inspect the app log directory. Share error text without credentials or local private files.

## 8. Upgrading / uninstalling

Re-run `bash ./install.sh` from a newer release. App sources are updated; local `models.json`, `settings.json` and `data/` remain. The installer backs up selected program files during upgrades. To uninstall, stop managed services first, then remove the installed app folder and its desktop launcher manually **after backing up any profiles/reports you want to keep**.

## Opening WebUI and Agent Office with one click

On the **Models** page, choose **In a browser tab**, **In a separate
browser window**, or **In a separate window without browser controls**
next to **Open WebUI** / **Open Agent Office**. Each service remembers its
own preference. The same controls appear under **Management** (including ComfyUI).
Existing `window` settings retain normal browser-window behavior.

Click **Open** once. If the service is stopped, AI Model Lab starts it, waits
for the local HTTP interface to respond, then opens the selected browser view.
If it already runs (including an external process), the application only opens
it; it does not take ownership of the external process.

**Open WebUI:** configure a `systemd --user` unit or install the
`open-webui` CLI. If the configured unit is missing, AI Model Lab can start an
existing CLI on loopback port 3000; it never downloads software automatically.
**Agent Office:** point `office_dir` at the folder containing `run.py`.
If its URL cannot be discovered from the managed process log, set `office_url`
to the actual local HTTP URL.

A new *tab* is requested through desktop browser integration; the browser's
own settings may change whether this reuses a window. A *regular browser window*
requires a supported installed browser (e.g. Firefox, Chromium or Brave) and
uses `--new-window`.

An *app window* omits tabs, the address bar, and browser navigation controls.
It launches a locally installed Chromium-family browser (Chromium, Google Chrome,
Brave, Vivaldi or Microsoft Edge) with `--app=http://127.0.0.1:<port>`.
This is a separate browser-powered web-app window, **not** a native KDE widget
or a browser plugin. Firefox-only installations need a supported Chromium-family
browser for this mode. If the requested mode cannot be launched, AI Model Lab
reports an error and never silently switches to another mode. The service
remains running.
