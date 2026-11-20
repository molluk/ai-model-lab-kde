#!/usr/bin/env bash
# AI Lab: local, foreground launchers for llama.cpp and Open WebUI.
# Works from Fish, Bash, and XDG .desktop entries. Does not edit Android projects.
set -Eeuo pipefail

SERVER_BIN="${AI_LAB_LLAMA_SERVER:-$HOME/llama.cpp/build/bin/llama-server}"
MODEL_ROOT="${AI_LAB_MODEL_ROOT:-/home/USER/AI/models}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/ai-lab-shortcuts"
SERVER_STATE="$STATE_DIR/llama-server.state"
HOST="127.0.0.1"
PORT=8080

say_error() { printf 'ОШИБКА: %s\n' "$*" >&2; }
fail() { say_error "$*"; exit 1; }

help_text() {
  cat <<'EOF'
AI Lab — запуск локальных серверов

Команды:
  ai-lab.sh model blend-q4 [--dry-run]
  ai-lab.sh model blend-q5 [--dry-run]
  ai-lab.sh model qwen38-27b [--dry-run]
  ai-lab.sh model coder-30b [--dry-run]
  ai-lab.sh model devstral-24b [--dry-run]
  ai-lab.sh stop          — остановить только сервер, запущенный этим лаунчером
  ai-lab.sh status        — состояние порта 8080 и запущенного процесса
  ai-lab.sh webui         — запустить локальный Open WebUI на порту 3000
  ai-lab.sh open-webui    — открыть интерфейс в браузере
  ai-lab.sh doctor        — проверить пути к файлам моделей и Pi contextWindow

Переменные для исправления нестандартных путей:
  AI_LAB_LLAMA_SERVER, AI_LAB_MODEL_ROOT,
  AI_LAB_BLEND_Q4_GGUF, AI_LAB_BLEND_Q5_GGUF,
  AI_LAB_QWEN38_27B_GGUF, AI_LAB_CODER_30B_GGUF,
  AI_LAB_DEVSTRAL_24B_GGUF.
EOF
}

check_port() {
  local port="$1"
  python3 - "$port" <<'PY'
import socket, sys
try:
    with socket.create_connection(('127.0.0.1', int(sys.argv[1])), timeout=0.6):
        sys.exit(0)
except OSError:
    sys.exit(1)
PY
}

server_props() {
  python3 - <<'PY'
import json, urllib.request
try:
    with urllib.request.urlopen('http://127.0.0.1:8080/props', timeout=1.5) as r:
        p=json.load(r)
    ctx=p.get('default_generation_settings',{}).get('n_ctx',p.get('n_ctx'))
    print('Модель:',p.get('model_alias','неизвестно'),'| Контекст:',ctx)
except Exception as e:
    print('Сервис отвечает на TCP, но /props недоступен:',type(e).__name__)
PY
}

start_ticks() { awk '{print $22}' "/proc/$1/stat" 2>/dev/null || true; }
load_state() {
  [[ -f "$SERVER_STATE" ]] || return 1
  mapfile -t state_lines < "$SERVER_STATE"
  [[ ${#state_lines[@]} -ge 4 ]] || return 1
  STATE_PID="${state_lines[0]}"
  STATE_TICKS="${state_lines[1]}"
  STATE_EXE="${state_lines[2]}"
  STATE_ALIAS="${state_lines[3]}"
  [[ "$STATE_PID" =~ ^[0-9]+$ ]] || return 1
  [[ "$STATE_TICKS" =~ ^[0-9]+$ ]] || return 1
}
owned_server_alive() {
  load_state || return 1
  [[ -r "/proc/$STATE_PID/stat" ]] || return 1
  [[ "$(start_ticks "$STATE_PID")" == "$STATE_TICKS" ]] || return 1
  local actual
  actual="$(readlink -f "/proc/$STATE_PID/exe" 2>/dev/null || true)"
  [[ -n "$actual" && "$actual" == "$STATE_EXE" ]] || return 1
}

stop_server() {
  if owned_server_alive; then
    printf 'Останавливаю только наш llama-server: PID=%s, alias=%s\n' "$STATE_PID" "$STATE_ALIAS"
    kill -TERM "$STATE_PID"
    rm -f "$SERVER_STATE"
  else
    printf 'Нет подтверждённого процесса llama-server, запущенного этим лаунчером.\n'
    printf 'Чужие процессы и серверы не останавливаются.\n'
    return 1
  fi
}

status_server() {
  if owned_server_alive; then
    printf 'Наш llama-server работает: PID=%s, alias=%s\n' "$STATE_PID" "$STATE_ALIAS"
  else
    printf 'Наш управляемый llama-server не обнаружен.\n'
  fi
  if check_port "$PORT"; then
    printf 'TCP %s:%s занят.\n' "$HOST" "$PORT"
    server_props
  else
    printf 'TCP %s:%s свободен.\n' "$HOST" "$PORT"
  fi
  if check_port 3000; then printf 'Open WebUI: порт 3000 занят.\n'; else printf 'Open WebUI: порт 3000 свободен.\n'; fi
}

# Choose only an exact known file or a *unique* filename match. Never silently select an arbitrary quant.
select_model() {
  local alias="$1" override_var='' override='' exact='' glob='' context=131072
  THINKING_KWARGS=0
  case "$alias" in
    blend-q4)
      override_var=AI_LAB_BLEND_Q4_GGUF
      exact="$MODEL_ROOT/Qwen3.8-3.6-27B-blend GGUF/Qwen3.8-3.6-27B-blend-Q4_K_M.gguf"
      glob='*blend*Q4_K_M.gguf'
      THINKING_KWARGS=1 ;;
    blend-q5)
      override_var=AI_LAB_BLEND_Q5_GGUF
      glob='*blend*Q5_K_M.gguf'
      context=32768
      THINKING_KWARGS=1 ;;
    qwen38-27b)
      override_var=AI_LAB_QWEN38_27B_GGUF
      exact="$MODEL_ROOT/Qwen3.8-27B/Qwen3.8-27B-Q4_K_M.gguf"
      glob='*Qwen3.8-27B*Q4_K_M.gguf'
      THINKING_KWARGS=1 ;;
    coder-30b)
      override_var=AI_LAB_CODER_30B_GGUF
      exact="$MODEL_ROOT/Qwen_Qwen3-Coder-30B-A3B-Instruct-GGUF/Qwen3-Coder-30B-A3B-Instruct.Q4_K_M.gguf"
      glob='*Coder*30B*Q4_K_M.gguf' ;;
    devstral-24b)
      override_var=AI_LAB_DEVSTRAL_24B_GGUF
      glob='*Devstral*Q4_K_M.gguf'
      context=32768 ;;
    *) fail "Неизвестная модель '$alias'; список: ./ai-lab.sh help" ;;
  esac
  MODEL_CTX="$context"
  MODEL_ALIAS="$alias"
  override="${!override_var:-}"
  if [[ -n "$override" ]]; then
    [[ -f "$override" ]] || fail "Заданный $override_var файл не найден: $override"
    MODEL_FILE="$override"
    return
  fi
  if [[ -n "$exact" && -f "$exact" ]]; then
    MODEL_FILE="$exact"
    return
  fi
  [[ -d "$MODEL_ROOT" ]] || fail "Каталог моделей отсутствует: $MODEL_ROOT"
  local -a matches=()
  mapfile -d '' -t matches < <(find "$MODEL_ROOT" -type f -iname "$glob" -print0 2>/dev/null)
  if [[ ${#matches[@]} -eq 0 ]]; then
    fail "GGUF для '$alias' не найден (шаблон $glob). Укажи $override_var в окружении или исправь путь."
  elif [[ ${#matches[@]} -gt 1 ]]; then
    printf 'Найдено несколько вариантов, выбор запрещён во избежание ошибки:\n' >&2
    printf '  %s\n' "${matches[@]}" >&2
    fail "Укажи конкретный файл через $override_var"
  fi
  MODEL_FILE="${matches[0]}"
}

model_args() {
  local alias="$1"
  ARGS=(
    -m "$MODEL_FILE"
    -ngl 99
    -c "$MODEL_CTX"
    -np 1
    -b 1024
    -ub 256
    -fa on
    --no-kv-offload
    --cache-type-k q8_0
    --cache-type-v q8_0
    --jinja
    --reasoning off
  )
  if [[ "$THINKING_KWARGS" == 1 ]]; then
    ARGS+=( --chat-template-kwargs '{"enable_thinking":false}' )
  fi
  ARGS+=(
    --temp 0.7
    --top-p 0.8
    --top-k 20
    --min-p 0
    --repeat-penalty 1
    --metrics
    --host "$HOST"
    --port "$PORT"
    --alias "$alias"
  )
}

print_cmd() {
  printf 'Команда запуска:\n'
  printf '%q ' "$SERVER_BIN" "${ARGS[@]}"
  printf '\n'
}

start_model() {
  local alias="${1:-}"
  local dry="${2:-}"
  [[ -n "$alias" ]] || fail 'Укажи alias модели'
  select_model "$alias"
  model_args "$alias"
  [[ -x "$SERVER_BIN" ]] || fail "llama-server не найден или неисполняем: $SERVER_BIN"
  if [[ "$dry" == '--dry-run' ]]; then
    printf 'Проверка: файл GGUF найден. Запуск не выполняется.\n'
    print_cmd
    return 0
  elif [[ -n "$dry" ]]; then fail "Неизвестный аргумент: $dry"; fi
  if check_port "$PORT"; then
    say_error "Порт $PORT занят, останавливать чужой сервер не буду."
    server_props
    return 2
  fi
  if owned_server_alive; then
    fail "Наш llama-server уже работает (PID=$STATE_PID), не запускаю второй экземпляр."
  fi
  mkdir -p "$STATE_DIR/logs"
  chmod 700 "$STATE_DIR" "$STATE_DIR/logs"
  umask 077
  local pid="$BASHPID" ticks log tmp exepath
  ticks="$(start_ticks "$pid")"
  [[ "$ticks" =~ ^[0-9]+$ ]] || fail "Не удалось прочитать /proc/$pid/stat"
  exepath="$(readlink -f "$SERVER_BIN")"
  log="$STATE_DIR/logs/${alias}_$(date +'%d-%m-%Y_%H-%M-%S').log"
  tmp="$SERVER_STATE.tmp.$pid"
  printf '%s\n%s\n%s\n%s\n' "$pid" "$ticks" "$exepath" "$alias" > "$tmp"
  mv -f "$tmp" "$SERVER_STATE"
  printf 'Модель: %s\nGGUF: %s\nКонтекст: %s токенов\nKV cache: RAM (q8_0), GPU layers: 99\nАдрес: http://%s:%s/v1\n' \
    "$alias" "$MODEL_FILE" "$MODEL_CTX" "$HOST" "$PORT"
  printf 'Журнал: %s\nДля завершения — Ctrl+C в этом окне или ярлык «AI Lab — Стоп llama.cpp».\n' "$log"
  exec > >(tee -a "$log") 2>&1
  exec "$SERVER_BIN" "${ARGS[@]}"
}

find_webui() {
  local candidate
  if command -v open-webui >/dev/null 2>&1; then
    WEBUI_BIN="$(command -v open-webui)"
    return 0
  fi
  for candidate in "$HOME/.local/bin/open-webui" \
      "$HOME/.local/share/uv/tools/open-webui/bin/open-webui"; do
    if [[ -x "$candidate" ]]; then WEBUI_BIN="$candidate"; return 0; fi
  done
  return 1
}

start_webui() {
  if check_port 3000; then
    printf 'Порт 3000 уже занят. Возможно, Open WebUI работает.\n'
    return 2
  fi
  find_webui || fail 'Не найден open-webui. Этот ярлык ничего не устанавливает и не скачивает.'
  mkdir -p "$STATE_DIR/logs"
  chmod 700 "$STATE_DIR" "$STATE_DIR/logs"
  umask 077
  local log="$STATE_DIR/logs/open-webui_$(date +'%d-%m-%Y_%H-%M-%S').log"
  printf 'Запускаю Open WebUI на http://127.0.0.1:3000\nЛог: %s\nДля остановки используй Ctrl+C.\n' "$log"
  exec > >(tee -a "$log") 2>&1
  exec "$WEBUI_BIN" serve --host 127.0.0.1 --port 3000
}

open_webui() {
  command -v xdg-open >/dev/null 2>&1 || fail 'Утилита xdg-open отсутствует'
  xdg-open 'http://127.0.0.1:3000' >/dev/null 2>&1 &
}

doctor() {
  printf 'llama-server: %s\n' "$SERVER_BIN"
  if [[ -x "$SERVER_BIN" ]]; then echo '  OK'; else echo '  НЕ НАЙДЕН'; fi
  for alias in blend-q4 blend-q5 qwen38-27b coder-30b devstral-24b; do
    # Run resolution in a subshell to retain nonzero statuses without breaking the full doctor command.
    ( select_model "$alias" && printf '%-14s контекст=%-6s %s\n' "$alias" "$MODEL_CTX" "$MODEL_FILE" ) || true
  done
  printf '\nНастройки Pi (только чтение):\n'
  python3 - <<'PY'
import json, pathlib
p=pathlib.Path.home()/'.pi/agent/models.json'
try:
    data=json.loads(p.read_text(encoding='utf-8'))
    for m in data.get('providers',{}).get('local-lab',{}).get('models',[]):
        print(f"  {m.get('id')}: contextWindow={m.get('contextWindow')}, maxTokens={m.get('maxTokens')}")
except (OSError,ValueError,TypeError) as e:
    print('  Не удалось прочитать models.json:',str(e))
PY
  printf '\n'; status_server
}

cmd="${1:-help}"
case "$cmd" in
  model) shift; start_model "${1:-}" "${2:-}" ;;
  stop) stop_server ;;
  status) status_server ;;
  webui) start_webui ;;
  open-webui) open_webui ;;
  doctor) doctor ;;
  help|--help|-h) help_text ;;
  *) fail "Неизвестная команда '$cmd' (помощь: ./ai-lab.sh help)" ;;
esac
