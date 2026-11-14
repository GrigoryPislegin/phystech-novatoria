const assert = require('node:assert/strict');
const test = require('node:test');
const { createRunApi } = require('../static/run-api.js');

const runId = 'f'.repeat(32);
const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { 'Content-Type': 'application/json' }
});

test('the offline viewer treats a missing session route as unavailable', async () => {
  const paths = [];
  const api = createRunApi(async path => {
    paths.push(path);
    return new Response('Not found', { status: 404 });
  });
  assert.equal(await api.session(), null);
  assert.deepEqual(paths, ['/api/session']);
});

test('synthetic start, read, cancel and delete follow the local contract', async () => {
  const calls = [];
  const api = createRunApi(async (path, options) => {
    calls.push([path, options]);
    if (path === '/api/session') return json({ csrf_token: 'local-token', capabilities: {} });
    if (options.method === 'DELETE') return new Response(null, { status: 204 });
    return json({ run_id: runId, state: 'queued' }, path === '/api/runs' ? 202 : 200);
  });
  await api.session();
  await api.start({ mode: 'synthetic-replay', scenario: 'incomplete', idempotency_key: 'same-key' });
  await api.get(runId);
  await api.report(runId);
  await api.cancel(runId);
  await api.review(runId, { expected_revision: 1, job_id: 'job-001', action: 'read_context', item_id: 'review-item' });
  await api.remove(runId);
  assert.deepEqual(calls.map(([path, options]) => [path, options.method]), [
    ['/api/session', 'GET'], ['/api/runs', 'POST'], ['/api/runs/' + runId, 'GET'],
    ['/api/runs/' + runId + '/report', 'GET'], ['/api/runs/' + runId + '/cancel', 'POST'],
    ['/api/runs/' + runId + '/review', 'POST'],
    ['/api/runs/' + runId, 'DELETE']
  ]);
  for (const [, options] of calls) {
    assert.equal(options.credentials, 'same-origin');
    assert.equal(options.headers['X-CSRF-Token'], options.method === 'GET' ? undefined : 'local-token');
  }
  assert.equal(JSON.parse(calls[1][1].body).idempotency_key, 'same-key');
  await assert.rejects(() => api.get('..'), /запуск/);
});

test('failed requests have fixed local feedback and cannot leak backend messages', async () => {
  const api = createRunApi(async path => path === '/api/session'
    ? json({ csrf_token: 'local-token', capabilities: {} })
    : json({ error: '/private/source.pdf <script>alert(1)</script>' }, 409));
  await api.session();
  await assert.rejects(() => api.get(runId), error => {
    assert.equal(error.status, 409);
    assert.doesNotMatch(error.message, /private|<script>/);
    return true;
  });
});

test('local inspection keeps the upload body scoped to its dedicated endpoint', async () => {
  const calls = [];
  const input = {
    resume: { name: 'resume.txt', content_base64: '0KLQtdC60YHRgg==' },
    jobs: [{ name: 'vacancy.txt', content_base64: 'Sm9i' }]
  };
  const api = createRunApi(async (path, options) => {
    calls.push([path, options]);
    if (path === '/api/session') return json({ csrf_token: 'fixture', capabilities: {} });
    return json({ input_id: runId, ready: true, files: [] });
  });
  await api.session();
  assert.equal((await api.inspect(input)).input_id, runId);
  assert.equal(calls[1][0], '/api/inputs/inspect');
  assert.deepEqual(JSON.parse(calls[1][1].body), input);
  assert.equal(calls[1][1].headers['X-CSRF-Token'], 'fixture');
});

test('timeout on start leaves the same request available for a user retry', async () => {
  const calls = [];
  const api = createRunApi(async (path, options) => {
    if (path === '/api/session') return json({ csrf_token: 'fixture', capabilities: {} });
    calls.push(JSON.parse(options.body));
    if (calls.length > 1) return json({ run_id: runId }, 202);
    return new Promise((resolve, reject) => {
      const keepAlive = setTimeout(() => reject(new Error('Timeout not enforced')), 250);
      options.signal.addEventListener('abort', () => {
        clearTimeout(keepAlive);
        reject(options.signal.reason);
      }, { once: true });
    });
  }, 10);
  await api.session();
  const body = { mode: 'protected-live', input_id: runId, budget: 1, idempotency_key: 'one-paid-run' };
  await assert.rejects(() => api.start(body), /не ответил вовремя/);
  assert.deepEqual(calls, [body]);
  assert.equal((await api.start(body)).run_id, runId);
  assert.deepEqual(calls, [body, body]);
});

test('selected pair uses a same-origin read and encodes vacancy IDs as values', async () => {
  const calls = [];
  const api = createRunApi(async (path, options) => {
    calls.push([path, options]);
    return json({ revision: 1, comparison: {} });
  });
  assert.equal((await api.comparison(runId, 'a&b=x', 'other')).revision, 1);
  assert.equal(calls[0][0], '/api/runs/' + runId + '/report?a=a%26b%3Dx&b=other');
  assert.equal(calls[0][1].method, 'GET');
});
