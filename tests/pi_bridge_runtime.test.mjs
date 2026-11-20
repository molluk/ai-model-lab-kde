import assert from 'node:assert/strict';
import { existsSync, mkdtempSync, readdirSync, readFileSync, writeFileSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = mkdtempSync(join(tmpdir(), 'ai-lab-pi-office-'));
process.env.HERMES_HOME = root;
const { default: extension, publishOfficeEvent } = await import(pathToFileURL(resolve('extensions/pi-office-bridge.js')).href);
const events = new Map();
extension({ on(type, fn) { events.set(type, fn); } });
const session = { sessionManager: { getSessionId: () => 'session-123' } };
const send = (type, payload = {}, ctx = session) => events.get(type)(payload, ctx);
const list = () => readdirSync(join(root, 'pixel-office', 'inbox')).filter(f => f.endsWith('.json'));
const read = () => list().sort().map(f => {
  const text = readFileSync(join(root, 'pixel-office', 'inbox', f), 'utf8');
  const record = JSON.parse(text);
  assert.equal(record.version, 1);
  assert.equal(record.event.platform, 'pi');
  assert.equal(record.epoch, 'initial');
  assert.equal(record.event.session_id, 'pi:session-123');
  assert.match(record.writer_id, /^[a-f0-9]{32}$/);
  assert.match(record.created_ns, /^\d{19,20}$/);
  assert.equal(statSync(join(root, 'pixel-office', 'inbox', f)).mode & 0o777, 0o600);
  return record.event;
});

assert.equal(existsSync(join(root, 'pixel-office', 'inbox')), false); // factory does not publish
assert.ok(events.has('agent_settled'));
await send('session_start');
await send('agent_start');
await send('tool_execution_start', { toolName: 'read', toolCallId: 'tool-1', args: { path: '/secrets/.env' } });
await send('tool_execution_end', { toolName: 'read', toolCallId: 'tool-1', isError: false, durationMs: 82, result: { content: 'PRIVATE' } });
await send('ui_prompt_start', { title: 'Sensitive approval title' });
await send('ui_prompt_end');
await send('agent_settled', { aborted: false });
await send('session_shutdown', { reason: 'quit' });
const out = read();
assert.deepEqual(out.map(e => e.event), ['session_start','session_busy','tool_start','tool_end','input_request','input_response','session_idle','session_end']);
assert.equal(out[3].duration_ms, 82);
assert.equal(out[3].status, 'completed');
assert.equal(out[4].request_id, out[5].request_id);
const encoded = JSON.stringify(out);
assert.ok(!encoded.includes('PRIVATE') && !encoded.includes('/secrets') && !encoded.includes('Sensitive'));

// Pi emits multiple settle/agent runs; bridge does not mark idle on agent_end.
assert.equal(events.has('agent_end'), false);
assert.equal(read().length, 8);
// On switch, a new session is observed with its own identity.
await send('session_start', {}, { sessionManager: { getSessionId: () => 'session-new' } });
const newer = list().sort().map(f => JSON.parse(readFileSync(join(root, 'pixel-office', 'inbox', f),'utf8')).event);
assert.equal(newer.at(-1).session_id, 'pi:session-new');

// Reset epoch observed atomically before next event.
writeFileSync(join(root, 'pixel-office', 'event-epoch'), JSON.stringify({ version: 1, reset: true, epoch: 'reset-123' }));
const at = publishOfficeEvent({ event: 'session_start', session_id: 'pi:test' });
assert.equal(JSON.parse(readFileSync(at, 'utf8')).epoch, 'reset-123');
rmSync(root, { recursive: true, force: true });
console.log('Pi Office Bridge event contract: OK');
