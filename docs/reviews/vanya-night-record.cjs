/* Record the V11 handoff using the browser and the isolated synthetic service. */
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const fs = require('node:fs/promises');
const { join } = require('node:path');
const { pathToFileURL } = require('node:url');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const [state, output] = process.argv.slice(2);
const viewport = { width: 1280, height: 720 };
const wait = seconds => new Promise(resolve => setTimeout(resolve, seconds * 1000));
const sha = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
const base = join(output, 'nanimai-v11-' + sha.slice(0, 7));

async function caption(page, title, copy) {
  await page.evaluate(({ title, copy, sha }) => {
    document.getElementById('acceptance-caption')?.remove();
    const card = document.createElement('aside');
    card.id = 'acceptance-caption';
    Object.assign(card.style, {
      position: 'fixed', left: '20px', bottom: '18px', zIndex: 100,
      width: 'min(755px, calc(100% - 40px))', padding: '13px 17px',
      background: '#2b2737', color: '#fff', borderRadius: '14px',
      boxShadow: '0 8px 25px #0003', pointerEvents: 'none', font: '15px/1.4 system-ui'
    });
    const head = document.createElement('strong');
    head.textContent = title;
    const text = document.createElement('div');
    text.textContent = copy;
    const meta = document.createElement('small');
    meta.style.color = '#d7dbff';
    meta.textContent = 'Синтетический replay · Подготовленные ответы · 0 внешних запросов · ' + sha.slice(0, 12);
    card.append(head, text, meta);
    document.body.append(card);
  }, { title, copy, sha });
}

async function position(target, top = 70) {
  await target.evaluate((element, offset) => window.scrollTo({
    top: window.scrollY + element.getBoundingClientRect().top - offset,
    behavior: 'instant'
  }), top);
}

async function decision(page, action) {
  await page.locator(`[data-review-action="${action}"]:visible`).press('Enter');
  await page.locator('#save-review').press('Enter');
  await page.locator('#review-message').filter({ hasText: 'Решение сохранено' }).waitFor();
}

(async () => {
  const { origin, ids } = JSON.parse(await fs.readFile(join(state, 'browser.json'), 'utf8'));
  const browser = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined, headless: true });
  const context = await browser.newContext({
    viewport, acceptDownloads: true, recordVideo: { dir: state, size: viewport }
  });
  const unexpected = [];
  await context.route('**/*', route => {
    const url = route.request().url();
    if (url.startsWith(origin + '/') && !(route.request().method() === 'POST' && url === origin + '/api/runs')) {
      return route.continue();
    }
    if (url.startsWith('file:')) return route.continue();
    unexpected.push('Неожиданный вызов из демонстрации');
    return route.abort();
  });
  const page = await context.newPage();
  const video = page.video();
  page.on('pageerror', error => unexpected.push(error.message));
  try {
    await page.goto(origin);
    await page.locator('#show-runs').press('Enter');
    const entry = page.locator(`[data-run-id="${ids.disputed}"]`);
    await position(entry, 260);
    await caption(page, 'Открываем сохранённый спорный запуск',
      'В истории видны режим, дата и состояние. В списке есть прерванный запуск без отчёта.');
    await wait(9);
    await entry.getByRole('button', { name: 'Открыть отчёт' }).press('Enter');
    await page.locator('#run-review').filter({ hasText: 'Ревизия 1' }).waitFor();
    await position(page.locator('.run-summary'), 20);
    await caption(page, 'Рейтинг и версия отчёта',
      'Обработаны две вакансии. Политика и ревизия видны рядом с режимом. Порядок рассчитывает сервер.');
    await wait(11);
    await page.locator('#job-list .job-option').first().press('Enter');
    const ambiguous = page.locator('#review-list details').filter({ hasText: 'Цитата стоит в разных контекстах' });
    await ambiguous.locator('summary').press('Enter');
    await position(ambiguous, 28);
    await caption(page, 'Приоритет 1 · неоднозначная цитата',
      'Слева требование вакансии, справа фрагмент резюме. Одинаковый «Python» встречается под двумя разными заголовками.');
    await wait(13);

    await page.locator('#requirements-draft-title').press('Enter');
    await position(page.locator('#requirements-draft'), 20);
    await caption(page, 'Состав требований · ревизия 1',
      'Сверяем формулировки, обязательность и фрагменты вакансии, которые не попали в список.');
    await wait(11);
    await decision(page, 'confirm_requirements');
    await page.locator('#run-review').filter({ hasText: 'Ревизия 2' }).waitFor();
    const conflict = page.locator('#review-list details').filter({ hasText: 'Согласуйте условия' });
    await conflict.locator('summary').press('Enter');
    await position(conflict, 45);
    await caption(page, 'Спорное условие · офис или удалённо',
      'Слева условие вакансии, справа предпочтение кандидата. Рекрутер может принять исключение, конфликт сохраняется.');
    await wait(14);
    await decision(page, 'accept_condition');
    await page.reload();
    await page.locator('#run-review').filter({ hasText: 'Ревизия 3' }).waitFor();
    await position(page.locator('.run-summary'), 25);
    await caption(page, 'Перезагрузка открывает ту же запись',
      'Запуск восстанавливается по ссылке. Исключение сохранено, неоднозначная цитата по-прежнему блокирует передачу.');
    await wait(10);
    const [download] = await Promise.all([
      page.waitForEvent('download'), page.locator('#manager-report').press('Enter')
    ]);
    const file = base + '-manager.html';
    await download.saveAs(file);
    await page.goto(pathToFileURL(file).href);
    assert.match(await page.locator('header .eyebrow').textContent(), /Ревизия 3/);
    await page.pdf({ path: base + '-manager.pdf', format: 'A4', printBackground: true });
    await caption(page, 'Печатный пакет менеджеру',
      'Вакансия, ревизия и состояние проверки совпадают с экраном. Пакет показывает, что передача заблокирована.');
    await wait(13);
    await position(page.locator('#conditions'), 55);
    await caption(page, 'Основания остаются в печати',
      'Две цитаты, принятый HR конфликт и предупреждение о потере профессиональных сведений остаются в пакете.');
    await wait(13);
    assert.deepEqual(unexpected, []);
  } finally {
    await context.close();
    await browser.close();
  }
  await video.saveAs(base + '.webm');
  console.log(sha, base + '.webm');
})().catch(error => { console.error(error); process.exitCode = 1; });
