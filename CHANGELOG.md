# Changelog (verified against attached release archives)

**Provenance:** the commit history is reconstructed; entries describe observed
features/changes in the corresponding ZIP, not claims about original commit dates.

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
