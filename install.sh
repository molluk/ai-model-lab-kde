#!/usr/bin/env bash
# Offline, no root; installs all source and benchmarks into a single folder.
set -Eeuo pipefail
SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
# Validate before touching an existing installation.
/usr/bin/env python3 "$SOURCE/release_preflight.py"
DEST="${AI_MODEL_LAB_HOME:-$HOME/AI/AI-Model-Lab}"
mkdir -p "$DEST" "$HOME/.local/bin" "$HOME/.local/share/applications"

# Copy previously installed program code into a dated rollback directory.
# User profiles, reports and runtime records remain in their original paths.
if [[ -f "$DEST/gui.py" ]]; then
  BACKUP="$DEST/data/backups/release-$(date +%Y%m%d_%H%M%S)"
  mkdir -p "$BACKUP"
  for f in core.py multi.py model_catalog.py model_maintenance.py model_folders.py model_inventory.py offline_client.py artifact_cleanup.py version_info.py gui.py bench.py client_launcher.py pi_bridge_manager.py i18n.py custom_services.py shutdown_manager.py service_browser.py run.sh install.sh; do
    if [[ -f "$DEST/$f" ]]; then cp -p "$DEST/$f" "$BACKUP/$f"; fi
  done
  printf 'Резервная копия прежнего кода: %s\n' "$BACKUP"
fi

# Preserve existing profiles and reports when upgrading.
for name in core.py multi.py model_catalog.py model_maintenance.py model_folders.py version_info.py gui.py bench.py client_launcher.py pi_bridge_manager.py i18n.py custom_services.py shutdown_manager.py service_browser.py release_preflight.py run.sh README.md LICENSE NOTICE; do
  install -m 0644 "$SOURCE/$name" "$DEST/$name"
done
install -m 0755 "$SOURCE/install.sh" "$DEST/install.sh"
# Record the exact source checkout being installed. The installed folder has no .git.
# Never guess a SHA for ZIP/source installations with no Git metadata.
python3 "$SOURCE/version_info.py" --write "$DEST/build_info.json" --source "$SOURCE"
# Ship public examples for tests and as migration references; never overwrite profiles.
for sample in models.example.json settings.example.json services.example.json; do
  install -m 0644 "$SOURCE/$sample" "$DEST/$sample"
done
for name in models.json settings.json; do
  if [[ ! -f "$DEST/$name" ]]; then
    if [[ -f "$SOURCE/$name" ]]; then
      install -m 0600 "$SOURCE/$name" "$DEST/$name"
    else
      install -m 0600 "$SOURCE/${name%.json}.example.json" "$DEST/$name"
    fi
  fi
done
# Custom services are local user configuration: never overwrite an existing file.
if [[ ! -f "$DEST/services.json" ]]; then
  install -m 0600 "$SOURCE/services.example.json" "$DEST/services.json"
fi
mkdir -p "$DEST/benchmarks/prompts" "$DEST/benchmarks/extensions" "$DEST/tests" "$DEST/assets" "$DEST/locales" "$DEST/docs" "$DEST/extensions"
# Install consolidated documentation without changing user profiles or reports.
for doc in "$SOURCE"/docs/*.md; do
  [[ -f "$doc" ]] || continue
  install -m 0644 "$doc" "$DEST/docs/$(basename "$doc")"
done
if compgen -G "$SOURCE/locales/*.json" >/dev/null; then install -m 0644 "$SOURCE/locales/"*.json "$DEST/locales/"; fi
if compgen -G "$SOURCE/benchmarks/prompts/*.md" >/dev/null; then
  install -m 0644 "$SOURCE/benchmarks/prompts/"*.md "$DEST/benchmarks/prompts/"
fi
install -m 0644 "$SOURCE/benchmarks/extensions/"*.js "$DEST/benchmarks/extensions/"
install -m 0644 "$SOURCE/tests/"test_*.py "$DEST/tests/"
install -m 0644 "$SOURCE/extensions/pi-office-bridge.js" "$DEST/extensions/pi-office-bridge.js"
if compgen -G "$SOURCE/tests/*.mjs" >/dev/null; then
  install -m 0644 "$SOURCE/tests/"*.mjs "$DEST/tests/"
fi
if compgen -G "$SOURCE/assets/*.svg" >/dev/null; then install -m 0644 "$SOURCE/assets/"*.svg "$DEST/assets/"; fi
mkdir -p "$DEST/data/reports" "$DEST/data/logs"
chmod 700 "$DEST/data" "$DEST/data/reports" "$DEST/data/logs"
BIN="$HOME/.local/bin/ai-model-lab"
cat > "$BIN" <<EOF
#!/usr/bin/env bash
exec /usr/bin/env python3 "$DEST/gui.py" "\$@"
EOF
chmod +x "$BIN"
DESKTOP="$HOME/.local/share/applications/ai-model-lab-kde.desktop"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=AI Model Lab — KDE
Comment=Локальные ИИ-модели, управление сервисами, графики и тесты
Exec=$BIN
Icon=$DEST/assets/ai-model-lab.svg
Terminal=false
Categories=Development;Science;System;
StartupNotify=true
EOF
chmod 0644 "$DESKTOP"
DESK=""
if command -v xdg-user-dir >/dev/null 2>&1; then DESK="$(xdg-user-dir DESKTOP 2>/dev/null || true)"; fi
if [[ ! -d "$DESK" || "$DESK" == "$HOME" ]]; then
  for d in "$HOME/Рабочий стол" "$HOME/Desktop"; do
    if [[ -d "$d" ]]; then DESK="$d"; break; fi
  done
fi
if [[ -n "$DESK" && -d "$DESK" && "$DESK" != "$HOME" ]]; then
  cp "$DESKTOP" "$DESK/ai-model-lab-kde.desktop"
  chmod +x "$DESK/ai-model-lab-kde.desktop"
fi
if command -v update-desktop-database >/dev/null; then
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi
printf '\nГотово!\nПриложение: %s\nОтчёты: %s\nЯрлык: %s\n' "$DEST" "$DEST/data/reports" "$DESKTOP"
printf 'Запуск: %s\n' "$BIN"
if ! /usr/bin/env python3 -c 'import PySide6' 2>/dev/null && ! /usr/bin/env python3 -c 'import PyQt6' 2>/dev/null; then
  printf '\nНе найден Qt6 для Python. Для CachyOS/Arch: sudo pacman -S pyside6\n'
fi
printf 'Предыдущие AI Lab, настройки Pi, GGUF, Android-проекты НЕ изменялись.\n'
