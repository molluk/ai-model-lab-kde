#!/usr/bin/env bash
# Install only independent AI Lab shortcuts. Existing model-lab scripts are untouched.
set -Eeuo pipefail
SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
DEST="$HOME/ai-model-lab/shortcuts"
APP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"

install -d -m 0755 "$DEST" "$APP_DIR"
install -m 0755 "$SOURCE_DIR/ai-lab.sh" "$DEST/ai-lab.sh"

DESKTOP_DIR=''
if command -v xdg-user-dir >/dev/null 2>&1; then
  DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || true)"
fi
if [[ -z "$DESKTOP_DIR" || "$DESKTOP_DIR" == "$HOME" ]]; then
  for d in "$HOME/Рабочий стол" "$HOME/Desktop"; do
    if [[ -d "$d" ]]; then DESKTOP_DIR="$d"; break; fi
  done
fi
if [[ -z "$DESKTOP_DIR" || "$DESKTOP_DIR" == "$HOME" ]]; then
  DESKTOP_DIR="$HOME/Desktop"
  printf 'Не найден XDG Desktop, использую %s\n' "$DESKTOP_DIR"
fi
install -d -m 0755 "$DESKTOP_DIR"

add_shortcut() {
  local slug="$1" name="$2" comment="$3" action="$4" terminal="$5" icon="$6"
  local target="$APP_DIR/ai-lab-$slug.desktop"
  cat > "$target" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$name
Comment=$comment
Exec="$DEST/ai-lab.sh" $action
Icon=$icon
Terminal=$terminal
Categories=Development;Science;
StartupNotify=false
EOF
  chmod 755 "$target"
  install -m 0755 "$target" "$DESKTOP_DIR/ai-lab-$slug.desktop"
}

add_shortcut blend-q4      'AI Lab — Blend Q4 (128K)'       'Запустить llama-server Blend Q4; 128K, thinking off'             'model blend-q4'    true  utilities-terminal
add_shortcut blend-q5      'AI Lab — Blend Q5 (32K)'       'Экспериментальный профиль Blend Q5; 32K'                        'model blend-q5'    true  utilities-terminal
add_shortcut qwen38-27b    'AI Lab — Qwen3.8 27B (128K)'   'Запустить llama-server Qwen3.8 27B; 128K, thinking off'         'model qwen38-27b'  true  utilities-terminal
add_shortcut coder-30b     'AI Lab — Qwen3-Coder (128K)'   'Запустить llama-server Qwen3-Coder 30B; 128K'                   'model coder-30b'   true  utilities-terminal
add_shortcut devstral-24b  'AI Lab — Devstral 24B (32K)'   'Экспериментальный профиль Devstral; 32K'                       'model devstral-24b' true utilities-terminal
add_shortcut llama-stop    'AI Lab — Стоп llama.cpp'      'Остановить только сервер, запущенный этим комплектом ярлыков'  'stop'              true  media-playback-stop
add_shortcut status        'AI Lab — Статус серверов'    'Проверка llama.cpp и Open WebUI'                                'doctor'            true  dialog-information
add_shortcut webui-start   'AI Lab — Запуск Open WebUI'  'Запустить локальный веб-интерфейс на порту 3000'                'webui'            true  applications-internet
add_shortcut webui-open    'AI Lab — Открыть Open WebUI' 'Открыть http://127.0.0.1:3000'                                 'open-webui'       false applications-internet

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$APP_DIR" >/dev/null 2>&1 || true
fi
printf '\nУстановлено!\nСкрипт: %s/ai-lab.sh\nМеню KDE/XDG: %s/ai-lab-*.desktop\nРабочий стол: %s/ai-lab-*.desktop\n' \
  "$DEST" "$APP_DIR" "$DESKTOP_DIR"
printf '\nПроверка без запуска модели:\n  bash "%s/ai-lab.sh" doctor\n\n' "$DEST"
printf 'Окно терминала с работающей моделью должно оставаться открытым.\n'
