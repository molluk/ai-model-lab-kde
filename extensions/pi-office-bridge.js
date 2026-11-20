/**
 * Pi -> Agent Office observer bridge (no external dependencies).
 *
 * Emits only real Pi lifecycle and tool events. Does not send prompts,
 * responses, tool arguments, file names or environment contents.
 * Agent Office reads immutable events from ~/.hermes/pixel-office/inbox.
 * This module never changes Pi tool permissions or starts an agent.
 */
import { randomUUID } from 'node:crypto';
import {
  closeSync, existsSync, fsyncSync, mkdirSync, openSync,
  readFileSync, renameSync, unlinkSync, writeFileSync,
} from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';

const OFFICE_ROOT = join(process.env.HERMES_HOME || join(homedir(), '.hermes'), 'pixel-office');
const WRITER_ID = randomUUID().replaceAll('-', '');
let sequence = 0;
let latestCreatedNs = 0n;

function currentEpoch(root) {
  const file = join(root, 'event-epoch');
  if (!existsSync(file)) return 'initial';
  const raw = readFileSync(file, 'utf8').trim();
  if (!raw.startsWith('{')) return raw || 'initial';
  const intent = JSON.parse(raw);
  if (intent.version !== 1 || intent.reset !== true ||
      typeof intent.epoch !== 'string' || !intent.epoch) {
    throw new Error('Invalid Agent Office event epoch');
  }
  return intent.epoch;
}

/** Atomic, fsync'd publication compatible with Agent Office event_inbox.py. */
export function publishOfficeEvent(event, root = OFFICE_ROOT) {
  if (!event || typeof event.event !== 'string' || !event.event ||
      typeof event.session_id !== 'string' || !event.session_id) {
    throw new TypeError('Invalid observer event');
  }
  const inbox = join(root, 'inbox');
  mkdirSync(inbox, { recursive: true, mode: 0o700 });
  const epoch = currentEpoch(root);
  const nowNs = BigInt(Date.now()) * 1000000n;
  const createdNs = nowNs > latestCreatedNs ? nowNs : latestCreatedNs + 1n;
  latestCreatedNs = createdNs;
  const name = `${createdNs.toString().padStart(20, '0')}-${WRITER_ID}-${String(++sequence).padStart(12, '0')}.json`;
  const target = join(inbox, name);
  const tmp = join(inbox, `.${name}.tmp`);
  const envelope = {
    version: 1,
    epoch,
    created_ns: createdNs.toString(),
    writer_id: WRITER_ID,
    sequence,
    event: {
      ts: Date.now() / 1000,
      platform: 'pi',
      pid: process.pid,
      ...event,
    },
  };
  let fd;
  try {
    fd = openSync(tmp, 'wx', 0o600);
    writeFileSync(fd, JSON.stringify(envelope) + '\n', 'utf8');
    fsyncSync(fd);
    closeSync(fd);
    fd = undefined;
    renameSync(tmp, target);
    return target;
  } finally {
    if (fd !== undefined) {
      try { closeSync(fd); } catch { /* best effort */ }
    }
    try { unlinkSync(tmp); } catch { /* already renamed or unavailable */ }
  }
}

/** The observer must never block or disrupt Pi's normal operation. */
export default function piOfficeBridge(pi) {
  let currentSession = '';
  let openPrompt = '';
  // Truly distinct processes cannot claim the same active office sprite.
  // Session UUID is included to make the identity traceable without content.
  const fallbackSession = randomUUID();

  const send = (kind, fields = {}) => {
    if (!currentSession) return;
    try {
      publishOfficeEvent({ event: kind, session_id: currentSession, ...fields });
    } catch {
      // Observer is fail-open. Agent Office may be absent or unwritable.
    }
  };

  pi.on('session_start', (_event, ctx) => {
    try {
      const realId = ctx.sessionManager.getSessionId();
      currentSession = `pi:${realId || fallbackSession}`;
    } catch {
      currentSession = `pi:${fallbackSession}`;
    }
    openPrompt = '';
    send('session_start');
  });

  pi.on('agent_start', () => send('session_busy'));
  // agent_end is NOT a final idle signal: Pi may retry, compact or continue.
  pi.on('agent_settled', () => send('session_idle'));

  pi.on('tool_execution_start', (event) => {
    send('tool_start', {
      tool_name: String(event.toolName || 'unknown').slice(0, 80),
      call_id: String(event.toolCallId || '').slice(0, 160),
    });
  });
  pi.on('tool_execution_end', (event) => {
    const details = {
      tool_name: String(event.toolName || 'unknown').slice(0, 80),
      call_id: String(event.toolCallId || '').slice(0, 160),
      status: event.isError ? 'error' : 'completed',
    };
    if (Number.isFinite(event.durationMs) && event.durationMs >= 0) {
      details.duration_ms = event.durationMs;
    }
    send('tool_end', details);
  });

  // Pi emits these only for real user-facing prompts; no prompt text is stored.
  pi.on('ui_prompt_start', () => {
    if (openPrompt) return;
    openPrompt = randomUUID();
    send('input_request', { request_id: openPrompt });
  });
  pi.on('ui_prompt_end', () => {
    if (!openPrompt) return;
    send('input_response', { request_id: openPrompt, choice: 'provided' });
    openPrompt = '';
  });

  pi.on('session_shutdown', () => {
    if (openPrompt) {
      send('input_response', { request_id: openPrompt, choice: 'cancelled' });
      openPrompt = '';
    }
    send('session_end');
    currentSession = '';
  });
}
