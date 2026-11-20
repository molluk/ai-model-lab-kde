# AI Model Lab localization / Локализация

## Built-in / Встроенные языки

- `ru` — Русский (source language; no separate catalog required)
- `en` — English (`en.json`)

The language menu appears next to **Refresh**. A change is saved to `settings.json`
under `"language"` and takes effect immediately by recreating the application
window. Running model servers are not restarted. Switching is deferred while a
benchmark or model-management operation is in progress.

Меню языков находится рядом с кнопкой **«Обновить»**. Выбранный язык
сохраняется в `settings.json` (`"language"`) и применяется без остановки ИИ.
При активном тесте или операции запуска/остановки сначала завершите операцию.

## Add a translation / Добавить перевод

Create `locales/<ISO-language-code>.json` in UTF-8, using `en.json` as an example:

```json
{
  "name": "Español",
  "translations": {
    "🧠 Модели": "🧠 Modelos",
    "↻ Обновить": "↻ Actualizar"
  }
}
```

The new language appears in the menu after restarting the application. Russian
is the fallback language for missing translations. Translate all entries from
`en.json` for a complete localization. Strings in model profiles (names,
paths, user descriptions), server logs and benchmark outputs are user/engine
data and are not automatically translated.

Новые языки появляются после перезапуска приложения. Непереведённые строки
остаются русскими. Для полноценного перевода добавьте все ключи из `en.json`.
Названия, пути и пользовательские описания моделей, логи серверов и вывод тестов
не переводятся автоматически.
