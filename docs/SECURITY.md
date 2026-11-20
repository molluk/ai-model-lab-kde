# Security policy (draft)

This project manages long-running local processes and has tools that can reach
projects and files selected by the user. **Read-only tools in a Pi benchmark are
not an operating-system sandbox.** Use isolated projects when testing unknown agents.

Before reporting a vulnerability, collect only the minimal reproduction details.
Never share credentials, user-specific `models.json` / `settings.json`, process
logs, private source code, or token-bearing HTTP headers in public issues.

Before publishing a repository, audit tracked files with `git ls-files` and
scan for credentials and personal paths. If a secret was ever pushed, revoke /
rotate it; deleting the latest commit alone does not remove repository history.

This is a pre-release project; security contact details are to be supplied by
the maintainer before public launch.
