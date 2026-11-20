# Contributing (draft)

- Discuss larger API or UX changes in an issue first.
- Submit small pull requests with tests and clear reproduction steps.
- Keep generated logs, user profiles, model weights and private project paths out of commits.
- Run `python3 release_preflight.py` and `python3 -m unittest discover -s tests -v`.
- Test GUI changes on a supported Qt6 desktop when possible; unit tests alone
  do not prove that a GUI flow is correct.
