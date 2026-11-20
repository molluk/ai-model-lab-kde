#!/usr/bin/env bash
# Offline, no root; installs all source and benchmarks into a single folder.
set -Eeuo pipefail
SOURCE="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
DEST="${AI_MODEL_LAB_HOME:-$HOME/AI/AI-Model-Lab}"
mkdir -p "$DEST" "$HOME/.local/bin" "$HOME/.local/share/applications"

# Preserve existing profiles and reports when upgrading.
for name in core.py multi.py gui.py bench.py run.sh README_RU.md; do
  install -m 0644 "$SOURCE/$name" "$DEST/$name"
done
install -m 0755 "$SOURCE/install.sh" "$DEST/install.sh"
for name in models.json settings.json; do
  if [[ ! -f "$DEST/$name" ]]; then install -m 0600 "$SOURCE/$name" "$DEST/$name"; fi
done
mkdir -p "$DEST/benchmarks/prompts" "$DEST/benchmarks/extensions" "$DEST/tests" "$DEST/assets"
install -m 0644 "$SOURCE/benchmarks/README.md" "$DEST/benchmarks/README.md"
install -m 0644 "$SOURCE/benchmarks/prompts/"*.md "$DEST/benchmarks/prompts/"
install -m 0644 "$SOURCE/benchmarks/extensions/"*.js "$DEST/benchmarks/extensions/"
install -m 0644 "$SOURCE/tests/"test_*.py "$DEST/tests/"
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
