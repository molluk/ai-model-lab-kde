# Publishing the reconstructed history to GitHub

This repository has Git history reconstructed from eleven supplied release ZIPs,
- Public history: PolyForm Noncommercial 1.0.0 is present in every commit and tag; earlier distributed copies may have different terms.
check `git log` before publication.

## Before anything: confirm the license

- Public history: PolyForm Noncommercial 1.0.0 is present in every commit and tag; earlier distributed copies may have different terms.

## Create an empty GitHub repository

1. Sign in as **molluk** at https://github.com/new.
2. Name: **ai-model-lab-kde**; visibility: **Public**.
3. Set the description to:
   `AI Model Lab — a KDE/Qt6 desktop app for managing local LLMs, multiple GPUs, llama.cpp servers, AI agents, and benchmarks on Linux.`
4. Leave **README**, **.gitignore**, and **License** disabled: they are already in Git.
5. Click **Create repository**. Do not upload files in the web UI afterwards.

- Public history: PolyForm Noncommercial 1.0.0 is present in every commit and tag; earlier distributed copies may have different terms.

From the directory containing this `.git` folder:

```bash
git status --short
python3 release_preflight.py
python3 -m unittest discover -s tests -v
git remote add origin https://github.com/molluk/ai-model-lab-kde.git
git push --set-upstream origin main
git push origin --tags
```

If `origin` already exists, inspect with `git remote -v` rather than blindly
replacing it. The GitHub account must be authenticated for `git push`
(usually GitHub CLI `gh auth login`, a credential helper, or SSH; GitHub
account password authentication over Git HTTPS is not supported).

Do not run `git push --force`. Preserve history and release tags.

For step-by-step Russian instructions, see [`PUBLISH_TO_GITHUB_RU.md`](PUBLISH_TO_GITHUB_RU.md).

## Review before making public

The project is an experimental alpha, **not tested as a general-purpose
production application**. Re-check `git ls-files`, `.gitignore`, LICENSE,
- Public history: PolyForm Noncommercial 1.0.0 is present in every commit and tag; earlier distributed copies may have different terms.
`models.json`, `settings.json`, `data/`, private code, model weights,
or access tokens. The public Android prompts are generic examples and
not directly comparable with historical local benchmarks.
