# Как опубликовать AI Model Lab в GitHub

[English](PUBLISH_TO_GITHUB.md) · [Проверка перед публикацией](GITHUB_PUBLISHING_CHECKLIST.md)

- Публичная история: лицензия PolyForm Noncommercial 1.0.0 во всех коммитах и тегах; ранее отдельно переданные копии могут иметь другие условия.

## 1. Создай пустой репозиторий

Перейди на https://github.com/new под нужным аккаунтом. Введи:

- Owner: `molluk`
- Repository name: `ai-model-lab-kde`
- Description: `AI Model Lab — KDE/Qt6 desktop app for managing local LLMs, llama.cpp servers, GPUs, agent clients, and benchmarks on Linux.`
- Visibility: **Public**
- **Add README: Off**, **Add .gitignore: No .gitignore**, **Add license: No license** — всё это уже включено в локальный Git.

Нажми **Create repository**, но не загружай файлы в веб-интерфейсе.

## 2. Подготовь локальный Git

Скачай архив с **полным `.git`**, распакуй его и перейди в каталог, где находятся `README.md` и `.git`. Не делай `git init` заново.

```fish
cd /путь/к/ai-model-lab-kde
git status --short
git log --oneline -15
git tag --list
python3 release_preflight.py
python3 -m unittest discover -s tests -v
```

Проверь содержимое `git ls-files`, текущую лицензию, список тегов и отсутствие конфиденциальных файлов не только в `main`, но и в истории. Не добавляй `models.json`, `settings.json`, `data/`, API-ключи или частные исходники.

## 3. Авторизация GitHub

Используй настроенный SSH или GitHub CLI. Для CLI:

```fish
sudo pacman -S github-cli
gh auth login
gh auth status
```

Пароль от аккаунта GitHub не используется для обычного HTTPS `git push`. Авторизация должна пройти под аккаунтом, имеющим право записи в репозиторий.

## 4. Отправь все коммиты и теги

```fish
git remote -v
```

Если `origin` отсутствует:

```fish
git remote add origin https://github.com/molluk/ai-model-lab-kde.git
```

Если уже есть, проверь его URL и при необходимости исправь осознанно (не создавай второй `origin`). Затем:

```fish
git push -u origin main
git push origin --tags
```

**Не используй `--force` или `git push --mirror`.** Не загружай ZIP с кодом вместо Git-истории: так потеряются коммиты и теги.

## 5. Проверка на GitHub

Открой https://github.com/molluk/ai-model-lab-kde . Проверь README с переключением RU/EN, `LICENSE`, `docs/INSTALL_RU.md`, `docs/INSTALL.md`, коммиты, теги, GitHub Actions (Tests). Если всё верно, можно создавать первый Release (Alpha/Experimental) на актуальном теге; сначала проверь, что тег относится к нужной версии и текст релиза корректен.

**Примечание:** история была восстановлена по ZIP и помечена как таковая в `HISTORY_PROVENANCE.md`. Это не первоначальные коммиты разработчиков.

### Внимание: пересобранная история

Во **всех коммитах и тегах** новой публичной истории лицензия PolyForm Noncommercial 1.0.0. Используй только финальный репозиторий v3.10, а не старые архивы. GitHub-репозиторий должен быть пустым; не используй `--force` и не объединяй эту историю с прежними Git-снимками.
