# Changelog (verified against attached release archives)

**Provenance:** the commit history is reconstructed; entries describe observed
features/changes in the corresponding ZIP, not claims about original commit dates.

## Unreleased — installed build identification
- Show version and short installed Git commit hash at the lower-right edge of the main window; show full SHA and local-change marker on hover.
- Generate the build manifest during installation from the actual source checkout, without changing user profiles or depending on Git at GUI runtime.
- Explicitly show an unknown SHA when provenance is unavailable.
- Add headless regression tests and RU/EN documentation.

## Unreleased — experimental Windows bootstrap (feature branch)
- Add a Windows onedir PyInstaller build script and Windows CI smoke/packaging workflow.
- Keep Linux installed configuration layout unchanged; Windows user configuration and data are placed in LocalAppData.
- Replace a POSIX-only import/lock with a platform-specific advisory lock module; include new modules in the Linux installer and preflight.
- Document that safe Windows process identity/termination, model management and service integration are not yet implemented.

## Unreleased — standalone browser app windows
- Add a third per-service opening mode: standalone Chromium-family `--app=URL` window without browser controls, alongside tabs and regular browser windows.
- Keep the existing `window` preference semantics; select the default supported app browser without launching shell commands, and fail clearly if none is installed.
- Extend both service selectors, EN translations, RU/EN guides, and headless dispatch/preference regression tests.

## Unreleased — Pi Office Bridge
- Add optional observer extension for real Pi lifecycle, tool, and UI-wait events, using Agent Office's existing atomic inbox protocol.
- Auto-load in Pi launched through AI Model Lab, including isolated provider profiles; skip explicit load when the bridge is already present in the Pi extension directory.
- Add opt-in global Pi symlink install/status/uninstall without modifying Pi configuration or tool permissions.
- Ship offline bridge event-contract tests, optional Node.js verification, RU/EN setup guides, and packaging checks.

## Unreleased — one-click service opening
- Open WebUI and Agent Office with a single click: start stopped services, wait for HTTP readiness, then open the browser.
- Choose browser tab or separate window for each service; preferences persist in settings.json.
- Use the configured user-systemd WebUI unit, or a verified locally installed open-webui CLI when the unit is unavailable.
- Track and stop Lab-owned CLI WebUI processes on explicit stop/full exit, without touching external processes.
- Add headless service/browser tests, English translations and packaging checks.

## v3.10 — Verified full shutdown
- Add a fourth close-dialog option: Exit and stop all AI Model Lab-managed services.
- Include managed llama.cpp servers, Agent Office, ComfyUI, systemd-user WebUI, and custom services.
- Check termination outcomes; keep GUI open on failure; never kill external processes or independent Pi/OpenCode sessions.
- Apply PolyForm Noncommercial 1.0.0 to every reconstructed public-history commit and release tag.

## v3.9 — Custom services and licensing
- Unified the Start/Stop buttons for built-in WebUI, Agent Office, and ComfyUI services with state indicators.
- Added editable custom local service profiles, independent background processes, status checks and verified PID-based stopping.
- Added custom-service controls and initial noncommercial licensing documents (public history later normalized to PolyForm in every snapshot).

## v3.8 — Localization
- Added Russian/English language selector in the title area and JSON translation catalogs.
- Persisted language preference without restarting managed model servers.


## v3.7
- Highlight the selected model row with a persistent, contrasting background.
- Separate the client launch button from the Pi/OpenCode selector.
- Save per-model client preferences without starting the server.
- Add actionable missing-client/WebUI/Agent Office installation guidance.
- Add headless regression tests for the new UI flow and preference persistence.
- Replace private Android benchmark prompts with generic public examples in the public source package.

## v3.6
- Fix Qt CSS f-string escaping and add a pre-install regression check.
- Add preferred client per model and public-source templates/safeguards.

## v3.5
- Add client launcher for OpenCode/Pi routed to the selected model and port.
- Add local/isolated agent configuration and client workspace setting.

## v3.4
- Place compact add/clone/delete/edit controls under model lists.
- Add retention periods and manual deletion of old logs and reports.

## v3.3
- Add model GPU/port/PID columns, column dividers and persisted widths.
- Show only running instances under Management and allow GPU selection by UUID.
- Improve layout scrolling for narrower windows.

## v3.2
- Support independent llama.cpp processes by alias, port and GPU.
- Add system tray, status colors, clone action and tabbed profile editor.

## v3.1
- Introduce state-aware model action, scrollable model information and live logs.
- Add model editing and add/delete actions in GUI.

## v3.0
- Introduce Qt6/KDE GUI, hardware metrics, model/service management.
- Bundle benchmark runner, telemetry, Pi guard and report viewer.

## v2.1
- Split terminal menus into Tests and Management sections.
- Add individual service controls and Android benchmark/report actions.

## v2.0
- Consolidate model launches under a local AI management CLI.
- Add model profiles, menu, stop/status actions and quick performance checks.

## v1.0
- Create KDE shortcuts and Bash launcher for local llama.cpp model servers.
- Include simple state/stop actions, startup scripts and an installation README.
