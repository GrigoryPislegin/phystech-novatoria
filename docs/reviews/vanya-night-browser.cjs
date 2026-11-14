/* Run with Node and Playwright against the isolated service in vanya-night-fixtures.py. */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const { join } = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const state = process.argv[2];
const viewport = { width: 1280, height: 720 };
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const node = (page, id) => page.locator('#' + id);
const shows = (target, text) => target.filter({ hasText: text }).waitFor({ timeout: 8_000 });
const key = target => target.press('Enter');
const reportAt = id => '/api/runs/' + id + '/report';
const decisionAt = id => '/api/runs/' + id + '/review';
const found = (page, detail) => node(page, 'review-list').locator('details').filter({ hasText: detail });
const readReport = async (context, origin, id) => (await context.request.get(origin + reportAt(id))).json();

async function openFromList(page, id) {
  if (!(await node(page, 'run-center').isVisible())) await key(node(page, 'show-runs'));
  await key(page.locator(`[data-run-id="${id}"]`).getByRole('button', { name: 'Открыть отчёт', exact: true }));
  await page.waitForURL(url => url.searchParams.get('run') === id);
  await shows(node(page, 'file-status'), 'Открыт отчёт локального запуска');
}

async function save(page, action) {
  await key(page.locator(`[data-review-action="${action}"]:visible`).first());
  if (action !== 'read_context') {
    await node(page, 'confirm-review').waitFor();
    await key(node(page, 'save-review'));
  }
  await shows(node(page, 'review-message'), 'Решение сохранено');
}

async function exported(page, name) {
  const [download] = await Promise.all([page.waitForEvent('download'), key(node(page, 'manager-report'))]);
  const file = join(state, name + '.html');
  await download.saveAs(file);
  return { file, html: await fs.readFile(file, 'utf8') };
}

async function real(browser, origin, ids) {
  const context = await browser.newContext({ viewport, acceptDownloads: true });
  const page = await context.newPage();
  const unexpected = [];
  let starts = 0;
  page.on('pageerror', error => unexpected.push(error.message));
  context.on('request', request => {
    if (request.method() === 'POST' && request.url() === origin + '/api/runs') starts++;
  });
  await context.route('**/*', route => {
    const url = route.request().url();
    if (url.startsWith(origin + '/') || url.startsWith('file:')) return route.continue();
    unexpected.push('Внешний запрос');
    return route.abort();
  });
  try {
    await page.goto(origin);
    await key(node(page, 'show-runs'));
    const interrupted = page.locator(`[data-run-id="${ids.interrupted}"]`);
    await shows(interrupted, 'Сервер перезапустился');
    assert.equal(await interrupted.getByRole('button', { name: 'Открыть отчёт' }).count(), 0);
    await openFromList(page, ids.success);
    await shows(node(page, 'run-mode'), 'Синтетический replay');
    await shows(node(page, 'run-review-detail'), 'draft-2026-11-14-v3');
    assert.equal(await node(page, 'run-count').textContent(), '3 из 3');
    await key(page.locator('#job-list .job-option').nth(1));
    const pair = page.waitForResponse(response => new URL(response.url()).searchParams.has('a'));
    await node(page, 'comparison-job').selectOption('1');
    assert.equal((await pair).status(), 200);
    await shows(node(page, 'comparison-summary'), 'выше');
    await key(page.locator('#job-list .job-option').first());

    await key(found(page, 'Проверьте список требований').locator('summary'));
    await key(found(page, 'Проверьте список требований').getByRole('button', { name: 'К составу требований' }));
    assert.equal(await page.evaluate(() => document.activeElement.id), 'requirements-draft-title');
    await shows(node(page, 'requirements-draft-content'), 'Обязательное по отчёту');
    await shows(node(page, 'requirements-draft-content'), 'Фрагменты вакансии вне списка');
    await key(page.getByRole('button', { name: 'Подтвердить состав · ревизия 1' }));
    await shows(node(page, 'review-dialog-copy'), 'Ревизия 1');
    await page.keyboard.press('Escape');
    await node(page, 'confirm-review').waitFor({ state: 'hidden' });
    assert.equal((await readReport(context, origin, ids.success)).revision, 1);
    await save(page, 'confirm_requirements');
    await shows(node(page, 'run-review'), 'Ревизия 2');
    await save(page, 'mark_for_handoff');
    await shows(node(page, 'review-state'), 'Проверено рекрутером для передачи');
    const reviewed = await readReport(context, origin, ids.success);
    assert.equal(reviewed.revision, 3);
    assert.equal(reviewed.review_history.length, 2);
    assert.match((await exported(page, 'reviewed')).html, /Ревизия 3[\s\S]*Проверено рекрутером для передачи/);

    await openFromList(page, ids.disputed);
    await shows(node(page, 'run-review'), 'Ревизия 1');
    const ambiguous = found(page, 'Цитата стоит в разных контекстах');
    await key(ambiguous.locator('summary'));
    await shows(ambiguous, 'Приоритет 1');
    await shows(ambiguous, 'Работал с: → Python');
    await shows(ambiguous, 'Не работал с: → Python');
    await node(page, 'requirement-search').fill('Неизвестное требование');
    await key(ambiguous.getByRole('button', { name: 'К оценке требования' }));
    assert.match(await page.evaluate(() => document.activeElement.textContent), /Python/);
    assert.equal(await page.evaluate(() => document.activeElement.getAttribute('aria-expanded')), 'true');
    await key(node(page, 'requirements-draft-title'));
    await shows(node(page, 'requirements-draft-content'), 'Работа в офисе');
    await save(page, 'confirm_requirements');
    const conflict = found(page, 'Согласуйте условия');
    await key(conflict.locator('summary'));
    await shows(conflict, 'Рассматриваю только удалённую работу');
    await shows(conflict, 'Работа в офисе');
    await key(conflict.getByRole('button', { name: 'К условию' }));
    assert.match(await page.evaluate(() => document.activeElement.textContent), /Формат работы/);
    await save(page, 'accept_condition');
    await shows(node(page, 'condition-list'), 'Исключение принято');
    assert.equal(await page.locator('[data-review-action="mark_for_handoff"]').count(), 0);
    const print = await exported(page, 'disputed');
    assert.match(print.html, /Ревизия 3[\s\S]*Передача заблокирована/);
    assert.match(print.html, /Возможный конфликт[\s\S]*Решение HR · Исключение принято/);
    assert.match(print.html, /Защита могла скрыть/);
    const printed = await context.newPage();
    await printed.goto(pathToFileURL(print.file).href);
    await printed.pdf({ path: join(state, 'disputed.pdf'), format: 'A4' });
    await printed.close();

    await openFromList(page, ids.incomplete);
    await shows(node(page, 'run-note-title'), 'Неполный рейтинг');
    const skipped = found(page, 'Вакансия не обработана');
    await key(skipped.locator('summary'));
    await shows(skipped.locator('.source-note'), 'Вакансия не обработана');
    assert.match((await exported(page, 'incomplete')).html, /Неполный результат[\s\S]*Ревизия 1/);
    await openFromList(page, ids.success);
    await page.reload();
    await shows(node(page, 'review-state'), 'Проверено рекрутером для передачи');
    await shows(node(page, 'run-review'), 'Ревизия 3');
    assert.doesNotMatch(await node(page, 'job-detail').innerText(), /Работа в офисе|удалённую работу/);

    await key(node(page, 'show-runs'));
    const saved = page.locator(`[data-run-id="${ids.success}"]`);
    await key(saved.getByRole('button', { name: 'Удалить' }));
    await shows(node(page, 'delete-run-label'), 'Подходящая вакансия');
    await shows(node(page, 'delete-run-copy'), 'Обработанные копии документов, отчёт и решения');
    await page.keyboard.press('Escape');
    await node(page, 'confirm-run-removal').waitFor({ state: 'hidden' });
    assert.equal((await context.request.get(origin + reportAt(ids.success))).status(), 200);
    await key(saved.getByRole('button', { name: 'Удалить' }));
    await key(node(page, 'remove-run'));
    await shows(node(page, 'file-status'), 'Запуск удалён');
    await saved.waitFor({ state: 'detached' });
    assert.equal(await node(page, 'manager-report').isVisible(), false);
    assert.equal((await context.request.get(origin + reportAt(ids.success))).status(), 404);
    assert.equal((await readReport(context, origin, ids.disputed)).revision, 3);
    await page.goto(origin + '/?run=' + '0'.repeat(32));
    await shows(node(page, 'file-status'), 'Запуск недоступен');
    assert.equal(await node(page, 'report-workspace').isVisible(), false);
    assert.equal(starts, 0);
    assert.deepEqual(unexpected, []);
  } finally {
    await context.close();
  }
}

async function fake(browser, origin, id, input) {
  const context = await browser.newContext({ viewport, acceptDownloads: true });
  const page = await context.newPage();
  const unexpected = [];
  const unsafe = '<span data-qa-inert>контрольная метка</span>';
  const long = ('Фрагмент длинной русской фразы для проверки переноса. '.repeat(101) + unsafe).trim();
  const raw = structuredClone(input);
  const [, rival] = raw.ranking.jobs;
  const row = rival.evaluation.rows[0];
  assert.equal(row.status, 'unknown');
  const prepared = raw.presentation.jobs.find(item => item.job_id === rival.job_id);
  prepared.rows[0].explanation = long;
  const item = raw.review_queue.items.find(entry => entry.job_id === rival.job_id && entry.action === 'ask_candidate');
  item.refs.push({ source: 'cv', quote: long, sentence: null, heading: 'Приложение' });
  const handoff = raw.handoff.find(entry => entry.job_id === rival.job_id);
  const decisions = [];
  let reportReads = 0, starts = 0, version = 1;
  let failRefresh = true;
  await context.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    const method = route.request().method();
    if (url.pathname === '/api/session') {
      return route.fulfill({ json: { csrf_token: 'fake-test-token', capabilities: { operations: ['read', 'review'] } } });
    }
    if (url.pathname === reportAt(id) && method === 'GET') {
      reportReads++;
      if (failRefresh && reportReads === 2) {
        return route.fulfill({ status: 503, json: { error: unsafe } });
      }
      return route.fulfill({ json: { ...raw, revision: version } });
    }
    if (url.pathname === decisionAt(id) && method === 'POST') {
      const action = route.request().postDataJSON();
      decisions.push(action);
      if (decisions.length === 1) {
        version++;
        return route.fulfill({ status: 409, json: { error: 'stale_revision' } });
      }
      if (decisions.length === 2) {
        return route.fulfill({ status: 409, json: { error: 'action_not_allowed' } });
      }
      assert.equal(action.expected_revision, version);
      assert.equal(action.action, 'read_context');
      assert.equal(action.item_id, item.id);
      assert.equal(action.job_id, rival.job_id);
      await pause(300);
      version++;
      handoff.acknowledged.push(item.id);
      delete handoff.allowed_actions[item.id];
      return route.fulfill({ json: { report: { ...raw, revision: version } } });
    }
    if (url.pathname === '/api/runs' && method === 'POST') starts++;
    unexpected.push(url.pathname);
    return route.fulfill({ status: 500, json: { error: unsafe } });
  });
  page.on('pageerror', error => unexpected.push(error.message));
  try {
    const address = origin + '/?run=' + id;
    await page.goto(address);
    await shows(node(page, 'run-review'), 'Ревизия 1');
    await key(page.locator('#job-list .job-option').nth(1));
    const unknown = found(page, 'Уточните у кандидата');
    await key(unknown.locator('summary'));
    await shows(unknown, long);
    assert.equal(await unknown.locator('[data-qa-inert]').count(), 0);
    await key(unknown.getByRole('button', { name: 'К оценке требования' }));
    await shows(page.locator('#requirement-rows'), 'Сведения не указаны');
    await shows(page.locator('#requirement-rows .evidence-row:visible'), long);
    assert.equal(await page.locator('[data-qa-inert]').count(), 0);
    await key(unknown.getByRole('button', { name: 'Отметить ознакомление' }));
    await shows(node(page, 'review-message'), 'Обновить отчёт не удалось');
    assert.equal(await node(page, 'manager-report').isEnabled(), false);
    await key(page.locator('#job-list .job-option').first());
    await shows(node(page, 'review-message'), 'Откройте этот запуск снова');
    assert.equal(decisions.length, 1);

    failRefresh = false;
    await page.reload();
    await shows(node(page, 'run-review'), 'Ревизия 2');
    await key(page.locator('#job-list .job-option').nth(1));
    await key(unknown.locator('summary'));
    const mark = unknown.getByRole('button', { name: 'Отметить ознакомление' });
    await key(mark);
    await shows(node(page, 'review-message'), 'действие недоступно');
    assert.equal(decisions.length, 2);
    await mark.focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('Enter');
    await shows(node(page, 'review-message'), 'Сохраняем решение');
    assert.equal(await node(page, 'report-file').isEnabled(), false);
    assert.equal(await node(page, 'manager-report').isEnabled(), false);
    await shows(node(page, 'review-message'), 'Решение сохранено');
    await shows(node(page, 'run-review'), 'Ревизия 3');
    await shows(unknown, 'Ознакомились');
    await shows(page.locator('#requirement-rows'), 'Сведения не указаны');
    assert.deepEqual(decisions.map(action => action.expected_revision), [1, 2, 2]);
    assert.equal(decisions[1].idempotency_key, decisions[2].idempotency_key);
    const marked = await exported(page, 'acknowledged');
    assert.match(marked.html, /Рекрутер ознакомился с замечаниями · 1/);
    assert.match(marked.html, /Сведения не указаны/);
    assert.equal(marked.html.includes(unsafe), false);
    await page.setViewportSize({ width: 640, height: 480 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);

    await node(page, 'report-file').setInputFiles({
      name: 'broken.json', mimeType: 'application/json', buffer: Buffer.from('{')
    });
    await shows(node(page, 'file-status'), 'предыдущий отчёт');
    assert.equal(new URL(page.url()).searchParams.get('run'), id);
    const foreign = structuredClone(raw);
    foreign.ranking.jobs[0].requirements_review.state = 'confirmed';
    foreign.handoff[0].state = 'reviewed_for_handoff';
    foreign.handoff[0].requirements_confirmed = true;
    foreign.handoff[0].can_mark_for_handoff = true;
    foreign.revision = 99;
    const name = unsafe + '.json';
    await node(page, 'report-file').setInputFiles({
      name, mimeType: 'application/json', buffer: Buffer.from(JSON.stringify(foreign))
    });
    await shows(node(page, 'run-review'), 'Внешний непроверенный файл');
    await shows(node(page, 'file-status'), name);
    assert.equal(await page.locator('[data-qa-inert], [data-review-action]').count(), 0);
    assert.equal(new URL(page.url()).searchParams.has('run'), false);
    const external = await exported(page, 'external');
    assert.match(external.html, /Внешний непроверенный файл[\s\S]*Подтверждение состава не проверено/);
    assert.doesNotMatch(external.html, /Проверено рекрутером для передачи|Ревизия 99/);
    assert.equal(starts, 0);
    assert.deepEqual(unexpected, []);
  } finally {
    await context.close();
  }
}

async function startTwice(browser, origin) {
  const context = await browser.newContext({ viewport });
  try {
    const page = await context.newPage();
    const attempts = [];
    await context.route(origin + '/api/runs', async route => {
      if (route.request().method() !== 'POST') return route.continue();
      attempts.push(route.request().postDataJSON());
      const response = await route.fetch();
      if (attempts.length === 1) return route.abort('failed');
      await route.fulfill({ response });
    });
    await page.goto(origin);
    await key(node(page, 'show-runs'));
    await node(page, 'start-run').focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('Enter');
    await shows(node(page, 'runs-message'), 'Локальный сервер не отвечает');
    assert.equal(attempts.length, 1);
    await key(node(page, 'start-run'));
    await shows(node(page, 'runs-message'), 'Запуск создан');
    assert.equal(attempts.length, 2);
    assert.deepEqual(attempts[0], attempts[1]);
    const { runs } = await (await context.request.get(origin + '/api/runs')).json();
    assert.equal(runs.filter(run => run.scenario === 'success').length, 1);
    const id = runs.find(run => run.scenario === 'success').run_id;
    await openFromList(page, id);
    await shows(page.locator('#requirement-rows'), 'Полное соответствие');
    await key(page.locator('#job-list .job-option').nth(1));
    await shows(page.locator('#requirement-rows'), 'Сведения не указаны');
    await key(page.locator('#job-list .job-option').nth(2));
    await shows(page.locator('#requirement-rows'), 'Несоответствие');

    await key(node(page, 'show-runs'));
    await node(page, 'run-scenario').selectOption('disputed');
    await key(node(page, 'start-run'));
    await shows(node(page, 'runs-message'), 'Запуск создан');
    const { runs: updated } = await (await context.request.get(origin + '/api/runs')).json();
    await openFromList(page, updated[0].run_id);
    await shows(page.locator('#requirement-rows'), 'Частичное соответствие');
  } finally {
    await context.close();
  }
}

(async () => {
  const { origin, ids } = JSON.parse(await fs.readFile(join(state, 'browser.json'), 'utf8'));
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, headless: true });
  try {
    const setup = await browser.newContext();
    const raw = await readReport(setup, origin, ids.success);
    await setup.close();
    await fake(browser, origin, ids.success, raw);
    console.log('Fake service: stale, refusal, double action, XSS, unknown and external import passed.');
    await real(browser, origin, ids);
    console.log('Local service: success, disputed, incomplete, interrupted, reload, print and deletion passed.');
    await startTwice(browser, origin);
    console.log('Local service: double start and retry after a lost response reused one run.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
