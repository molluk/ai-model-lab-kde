#!/usr/bin/env bash
set -Eeuo pipefail
SRC="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/ai-model-lab-v2"
BIN="$HOME/.local/bin/ai-model-lab-v2"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
install -d -m 0755 "$DEST" "$(dirname "$BIN")" "$APPS"
# Keep any old personal config on reinstall. Never overwrite it silently.
install -m 0755 "$SRC/ai_lab.py" "$DEST/ai_lab.py"
if [[ ! -e "$DEST/models.json" ]]; then
    install -m 0644 "$SRC/models.json" "$DEST/models.json"
fi
cat > "$BIN" <<EOF
#!/usr/bin/env bash
exec /usr/bin/env python3 "$DEST/ai_lab.py" "\$@"
EOF
chmod 0755 "$BIN"
DSTART=""
if command -v xdg-user-dir >/dev/null 2>&1; then
    DSTART="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
fi
if [[ -z "$DSTART" || "$DSTART" == "$HOME" ]]; then
    for d in "$HOME/Рабочий стол" "$HOME/Desktop"; do
        if [[ -d "$d" ]]; then DSTART="$d"; break; fi
    done
fi
# No surprise creation of an unused Desktop dir.
write_desktop() {
    local id="$1" name="$2" comment="$3" args="$4" icon="$5"
    local file="$APPS/ai-v2-$id.desktop"
    cat > "$file" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$name
Comment=$comment
Exec=$BIN $args
Icon=$icon
Terminal=true
Categories=Development;Science;
StartupNotify=false
EOF
    chmod 0644 "$file"
    if [[ -n "$DSTART" && -d "$DSTART" ]]; then
        cp "$file" "$DSTART/ai-v2-$id.desktop"
        chmod +x "$DSTART/ai-v2-$id.desktop"
    fi
}
write_desktop manager 'AI Lab — Менеджер моделей' 'Выбор модели, тесты и управление сервисами' 'menu' 'applications-development'
write_desktop tests 'AI Lab — Тесты' 'Скорость API, Android бенчмарки, отчёты и сравнения' 'tests' 'utilities-system-monitor'
write_desktop manage 'AI Lab — Управление' 'Отдельный запуск и остановка llama.cpp, WebUI, Agent Office, ComfyUI' 'manage' 'preferences-system'
write_desktop blend-q4 'AI Lab — Blend Q4 (128K) — Android-анализ' 'Android-архитектура, глубокий анализ кода' 'start blend-q4 --menu' 'utilities-terminal'
write_desktop blend-q5 'AI Lab — Blend Q5 (32K) — квантизация' 'Сравнение качества Q4 и Q5' 'start blend-q5 --menu' 'utilities-terminal'
write_desktop qwen38-27b 'AI Lab — Qwen3.8 (128K) — ревью' 'Независимый Android-анализ и ревью' 'start qwen38-27b --menu' 'utilities-terminal'
write_desktop coder-30b 'AI Lab — Coder 30B (128K) — кодинг' 'Быстрая генерация и правки кода' 'start coder-30b --menu' 'utilities-terminal'
write_desktop coder-30b-ud 'AI Lab — Coder 30B UD (96K) — эксперимент' 'Экспериментальный Coder' 'start coder-30b-ud --menu' 'utilities-terminal'
write_desktop qwen3-vl-30b 'AI Lab — Qwen3-VL (32K) — изображения' 'Обработка изображений и UI-дизайн' 'start qwen3-vl-30b --menu' 'applications-graphics'
write_desktop devstral-24b 'AI Lab — Devstral 24B (32K) — кодинг' 'Быстрые задачи программирования' 'start devstral-24b --menu' 'utilities-terminal'
write_desktop status 'AI Lab — Статус серверов' 'Модель, GPU, VRAM, контекст и сервисы' 'status' 'dialog-information'
write_desktop stop-all 'AI Lab — Остановить все сервисы' 'Запрашивает подтверждение остановки' 'stop-all --ask' 'media-playback-stop'
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$APPS" >/dev/null 2>&1 || true
fi
printf '\nУстановлено: %s\nМеню: %s/ai-v2-*.desktop\n' "$BIN" "$APPS"
if [[ -n "$DSTART" ]]; then printf 'Рабочий стол: %s/ai-v2-*.desktop\n' "$DSTART"; fi
printf '\nПроверка: %q doctor\n' "$BIN"
printf 'Старые ярлыки, ai-menu.sh, ai-stop.sh, скрипты моделей и программы Hugging Face НЕ изменены.\n'
