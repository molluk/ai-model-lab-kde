# Pi Office Bridge — live Pi sessions in Agent Office

AI Model Lab ships a local Pi observer extension that writes genuine runtime
events into `~/.hermes/pixel-office/inbox/`, where Agent Office ingests them.
It requires no additional network service, paid provider or daemon.

## Observation scope

- `session_start`: actual Pi session established;
- `agent_start` → `session_busy`, `agent_settled` → `session_idle`;
- `tool_execution_start/end`: tool name, call ID and outcome;
- `ui_prompt_start/end`: user input wait and response;
- `session_shutdown`: session exit.

It **does not send prompts, generated text, tool parameters, file paths,
file contents or credentials**. No fake agent roles or token usage are
reported. Events use immutable JSON envelopes, atomic rename and fsync.

## Pi launched from AI Model Lab

Install via `bash ./install.sh` from the repository root. Open a running
model with **Open in Pi**. `client_launcher.py` uses the selected model's actual
API port and adds `--extension <app>/extensions/pi-office-bridge.js` if the
bridge is not already present in that Pi profile's extension directory.
This includes isolated Pi configurations and preserves global Pi settings.
AI benchmark jobs using `--no-extensions` remain unaffected.

## Optional integration for standalone terminal Pi

```bash
python3 ~/AI/AI-Model-Lab/pi_bridge_manager.py --status
python3 ~/AI/AI-Model-Lab/pi_bridge_manager.py --install
```

Restart Pi. To remove only this bridge-owned symlink:

```bash
python3 ~/AI/AI-Model-Lab/pi_bridge_manager.py --uninstall
```

No existing Pi extension is overwritten and `models.json` is not edited.
For a custom `PI_CODING_AGENT_DIR`, use an explicit `--extension` flag or
install an extension in that directory.

## Verification and troubleshooting

Open Agent Office (typically `http://127.0.0.1:8113`), start Pi with the
extension and execute a harmless prompt. A new Pi sprite should become busy
and return idle when work settles. Merely running llama-server does not
create an agent session. The inbox is consumed promptly when Office runs,
so an empty inbox is normal.

Check that Pi loads the extension, `HERMES_HOME` matches Agent Office and
the inbox is writable. When Agent Office is offline, published events queue
on disk. Observer failures never block Pi. Abruptly killed Pi processes may
not emit their shutdown event; Agent Office handles stale sessions separately.

**Trust boundary:** Pi extensions run with the host Pi process's OS user
permissions. Review the source before enabling. The bridge neither changes
tool approvals nor creates agent processes.
