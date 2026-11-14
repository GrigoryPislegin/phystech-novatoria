const assert = require('node:assert/strict');
const { createHash } = require('node:crypto');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const test = require('node:test');

const { parseReport } = require('../static/report.js');
const { renderManagerReport } = require('../static/manager-report.js');

function example(name = 'success') {
  return JSON.parse(readFileSync(join(__dirname, 'fixtures', 'web', name + '.json'), 'utf8'));
}

function render(raw, index = 0) {
  const report = parseReport(JSON.stringify(raw));
  return renderManagerReport(report, report.jobs[index].id);
}

test('the brief keeps the selected vacancy, recommendation and references to the same evidence', () => {
  const raw = example();
  const top = render(raw);
  assert.match(top, /job-001/);
  assert.match(top, /Проверьте цитаты по вакансиям на первом месте/);
  assert.match(top, /Python обязателен/);
  assert.match(top, /Разрабатывал на Python 3 года/);
  assert.match(top, /href="#evidence-1"/);
  assert.match(top, /id="evidence-1"/);
  assert.doesNotMatch(top, /Вопросы кандидату/);

  const other = render(raw, 1);
  assert.match(other, /job-002/);
  assert.match(other, /Java обязателен/);
  assert.match(other, /Сведения не указаны/);
  assert.match(other, /Вопросы кандидату/);
  assert.doesNotMatch(other, /Python обязателен|job-001/);
});

test('incomplete, unknown and review states stay visible in print', () => {
  const raw = example('incomplete');
  raw.privacy = { professional_information_may_be_hidden: true };
  const review = { vacancy_id: 'job-001', state: 'confirmed', reasons: [] };
  raw.ranking.jobs[0].requirements_review = review;
  raw.presentation.jobs[0].requirements_review = review;
  raw.ranking.jobs[0].score_review.excluded_mandatory_ids = ['r1'];
  raw.presentation.jobs[0].rows[0].mandatory_applied_to_score = false;
  raw.presentation.jobs[0].rows[0].mandatory_check.state = 'needs_review';
  const html = render(raw);
  assert.match(html, /Неполный результат[\s\S]+1 из 3/);
  assert.match(html, /Места предварительные/);
  assert.match(html, /Синтетический replay/);
  assert.match(html, /Подтверждение состава не проверено/);
  assert.match(html, /Внешний непроверенный файл/);
  assert.match(html, /Черновик для проверки/);
  assert.match(html, /Обязательность требует проверки/);
  assert.match(html, /защита могла скрыть/i);
  assert.ok(html.indexOf('Неполный результат') < html.indexOf('Предварительная рекомендация'));
});

test('report provenance preserves full digests and ignores private paths', () => {
  const raw = example();
  const resume = 'a'.repeat(64);
  const vacancy = 'b'.repeat(64);
  const policy = 'c'.repeat(64);
  const model = 'd'.repeat(64);
  raw.safe_resume_sha256 = resume;
  raw.ranking.jobs[0].safe_source_sha256 = vacancy;
  raw.ranking.jobs[0].score.policy_sha256 = policy;
  raw.model = 'synthetic-model-id';
  raw.model_sha256 = model;
  raw.manifest = { jobs: [{ job_id: 'job-001', filename: '/private/secret-candidate.docx' }] };
  raw.run_metadata = { run_id: 'https://invalid.local/secret-candidate.docx' };
  const html = render(raw);
  for (const value of [resume, vacancy, policy, model, raw.model, raw.ranking.jobs[0].score.policy_version]) {
    assert.ok(html.includes(value));
  }
  assert.doesNotMatch(html, /private|secret-candidate/);
});

test('private and source-derived vacancy identifiers are replaced with their position', () => {
  for (const id of ['/private/synthetic-vacancy.docx', 'job-' + 'a'.repeat(24) + '-1']) {
    const raw = example();
    raw.ranking.jobs[0].job_id = id;
    raw.presentation.jobs[0].job_id = id;
    const report = parseReport(JSON.stringify(raw));
    assert.equal(report.jobs[0].title, '№1');
    const html = renderManagerReport(report, id);
    assert.match(html, /Вакансия №1/);
    assert.ok(!html.includes(id));
  }
});

test('legacy rows without evidence checks remain review items, even with full assessments', () => {
  const raw = example();
  delete raw.presentation;
  const html = render(raw);
  assert.match(html, /Нет оценок полного соответствия со структурно сверенными цитатами/);
  assert.match(section(html, 'vacancy-fit'), /Риски и пробелы[\s\S]*Доказательство требует проверки/);
  assert.match(html, /Разрабатывал на Python 3 года/);
  assert.doesNotMatch(html, /пробелы не отмечены|Вопросы кандидату/);
});

test('legacy free prose stays out of print and long source quotes remain literal', () => {
  const raw = example('disputed');
  delete raw.presentation;
  const requirement = raw.ranking.jobs[0].requirements.items[0];
  requirement.quote = 'Длинная русская цитата. '.repeat(100) +
    '\n="Синтетика" <strong>буквальный текст</strong> & продолжение. </script><script>synthetic()</script>';
  requirement.mandatory_quote = requirement.quote;
  raw.ranking.jobs[0].evaluation.rows[0].comment = 'Вымышленные 99 лет опыта';
  raw.ranking.jobs[0].evaluation.rows[0].question = 'Непроверенный личный вопрос';
  const html = render(raw);
  assert.match(html, /&lt;strong&gt;буквальный текст&lt;\/strong&gt; &amp; продолжение/);
  assert.match(html, /="Синтетика"|=&quot;Синтетика&quot;/);
  assert.ok(html.includes('Длинная русская цитата. '.repeat(100)));
  assert.doesNotMatch(html, /<strong>буквальный текст|99 лет|Непроверенный личный вопрос/);
  assert.match(html, /&lt;\/script&gt;&lt;script&gt;synthetic\(\)&lt;\/script&gt;/);
  const scripts = Array.from(html.matchAll(/<script>(.*?)<\/script>/gs), match => match[1]);
  assert.equal(scripts.length, 1);
  assert.match(scripts[0], /window\.print\(\)/);
  assert.ok(html.includes("script-src 'sha256-" + createHash('sha256').update(scripts[0]).digest('base64') + "'"));
  assert.doesNotMatch(html, /<iframe|src=|https?:\/\//);
});

test('brief uses validated rows and caps questions to actual gaps', () => {
  const raw = example('disputed');
  const job = raw.ranking.jobs[0];
  const prepared = raw.presentation.jobs[0];
  prepared.manager_brief = {
    grounds: [{ label: 'Непроверенное основание' }],
    questions: ['Непроверенный вопрос'],
    final_allowed: true
  };
  for (let n = 2; n <= 7; n++) {
    const quote = 'Уточнить синтетический навык ' + n;
    const id = 'gap-' + n;
    job.requirements.items.push({ id, text: quote, quote, mandatory_quote: null });
    job.evaluation.rows.push({ requirement_id: id, status: 'unknown', fact_ids: [] });
    prepared.rows.push({ requirement_id: id, requirement_quote: quote, label: quote,
      status: 'unknown', resume_quotes: [] });
  }
  const html = render(raw);
  assert.doesNotMatch(html, /Непроверенное основание|Непроверенный вопрос/);
  assert.match(html, /Черновик для проверки/);
  assert.equal((html.match(/class="manager-question"/g) || []).length, 5);
  assert.equal((html.match(/<article /g) || []).length, 7);
  assert.match(html, /Сведения не указаны/);
});

function section(html, id) {
  return html.match(new RegExp('<section id="' + id + '"[^>]*>[\\s\\S]*?</section>'))?.[0] ?? '';
}

test('the jury example shows a sourced profile, fit reasons and a conflict only for the selected vacancy', () => {
  const raw = example('manager-profile');
  const first = render(raw);
  const profile = section(first, 'candidate-profile');
  for (const label of [
    'Backend-разработчик, 5 лет коммерческой разработки', 'Python', 'Django', 'PostgreSQL',
    'ведущий разработчик', 'сервис онлайн-обучения', '2021 — по настоящее время',
    'Сократил время ответа API', 'с 800 до 200 мс'
  ]) {
    assert.ok(profile.includes(label), label);
  }
  assert.match(profile, /href="#profile-source-\d+"/);
  assert.match(first, /id="profile-source-1"/);
  assert.match(section(first, 'vacancy-fit'), /Соответствие частичное[\s\S]*Опыт Python от 3 лет/i);
  assert.match(section(first, 'vacancy-fit'), /Django/);
  assert.match(section(first, 'vacancy-fit'), /class="fit-citation">Резюме «Backend-разработчик/);
  assert.match(section(first, 'conditions'), /Возможный конфликт[\s\S]*Формат работы: только удалённо[\s\S]*Формат работы: только офис/);
  assert.match(section(first, 'conditions'), /Зарплата[\s\S]*Нужно уточнить/);
  assert.match(section(first, 'conditions'), /Решение по условиям принимает HR/);

  const second = render(raw, 1);
  assert.equal(section(second, 'candidate-profile'), profile);
  assert.match(section(second, 'vacancy-fit'), /Недостаточно сведений[\s\S]*Java/);
  assert.match(section(second, 'conditions'), /Условия совпадают по отчёту/);
  assert.doesNotMatch(second, /только офис|Возможный конфликт/);
});

test('a condition conflict remains separate from the stored score and vacancy verdict', () => {
  const raw = example('manager-profile');
  const report = parseReport(JSON.stringify(raw));
  const withConflict = section(renderManagerReport(report, 'job-001'), 'vacancy-fit');
  delete raw.ranking.jobs[0].conditions;
  const withoutConditions = section(render(raw), 'vacancy-fit');
  assert.equal(withConflict, withoutConditions);
  assert.equal(report.jobs[0].score.lower, raw.ranking.jobs[0].score.lower);
});

test('a selected vacancy gets its own provisional verdict independent of ranking position and score', () => {
  const raw = example('success');
  assert.match(section(render(raw), 'vacancy-fit'), /Нужна проверка[\s\S]*Состав не подтверждён/);
  raw.ranking.jobs[0].requirements_review = { vacancy_id: 'job-001', state: 'confirmed', reasons: [] };
  assert.match(section(render(raw), 'vacancy-fit'), /Нужна проверка[\s\S]*Подтверждение состава не проверено/);
  raw.run_id = 'a'.repeat(32);
  raw.revision = 2;
  const context = { runId: raw.run_id, revision: raw.revision };
  const serverReport = () => renderManagerReport(parseReport(JSON.stringify(raw)), 'job-001', context);
  assert.match(section(serverReport(), 'vacancy-fit'), /Нужна проверка/);
  raw.handoff = [{ job_id: 'job-001', requirements_confirmed: true, state: 'draft' }];
  assert.match(section(serverReport(), 'vacancy-fit'), /По оценённым требованиям соответствует/);
  assert.match(section(render(raw, 2), 'vacancy-fit'), /Есть несоответствие[\s\S]*SQL/);
  const changed = example('success');
  changed.ranking.jobs[0].score_review.excluded_mandatory_ids = ['r1'];
  assert.match(section(render(changed), 'vacancy-fit'), /Нужна проверка[\s\S]*Обязательность требует проверки/);
  assert.match(section(render(example('incomplete')), 'vacancy-fit'), /Нужна проверка[\s\S]*Обработана часть вакансий/);
  assert.doesNotMatch(section(render(raw), 'vacancy-fit'), /полностью подходит/i);
});

test('older reports and a profile with missing or invalid data keep explicit empty states', () => {
  const old = render(example());
  assert.match(section(old, 'candidate-profile'), /не извлечён/i);
  assert.match(section(old, 'conditions'), /не сравнивались/i);

  const raw = example('manager-profile');
  for (const key of Object.keys(raw.profile.display).filter(key => key.startsWith('last_position.'))) {
    delete raw.profile.display[key];
    delete raw.profile.spans[key];
  }
  delete raw.profile.display['achievements[0].result'];
  delete raw.profile.spans['achievements[0].result'];
  assert.match(section(render(raw), 'candidate-profile'), /Последняя роль[\s\S]*Не извлечена/);
  assert.match(section(render(raw), 'candidate-profile'), /Результат не указан/);
  raw.profile.state = 'invalid';
  assert.match(section(render(raw), 'candidate-profile'), /Не удалось проверить/);
  assert.doesNotMatch(section(render(raw), 'candidate-profile'), /Backend-разработчик/);
});

test('profile displays only sourced claims and keeps negation in the shown context', () => {
  const raw = example('manager-profile');
  raw.profile.display['summary[0]'] = 'Придуманные 99 лет опыта';
  raw.profile.display['summary[1]'] = 'Выдуманное достижение';
  raw.profile.display['stack[0]'] = 'Python';
  const span = raw.profile.spans['stack[0]'][0];
  raw.facts.items.find(fact => fact.id === 'f2').quote += '\nНе работал с Python.';
  for (const job of raw.presentation.jobs) {
    for (const row of job.rows) {
      row.resume_quotes = row.resume_quotes.map(quote => quote.startsWith('Навыки:')
        ? quote + '\nНе работал с Python.' : quote);
    }
  }
  span.sentence = 'Не работал с Python';
  const html = render(raw);
  const profile = section(html, 'candidate-profile');
  assert.doesNotMatch(profile, /Придуманные|Выдуманное/);
  assert.match(profile, /Не работал с Python/);
  assert.doesNotMatch(profile, />Python<\/a>/);
});

test('conditions require both matching sources, preserve HR review and ignore model prose', () => {
  const raw = example('manager-profile');
  const items = raw.ranking.jobs[0].conditions.items;
  items[0].vacancy_span.source_id = 'job-002';
  items[0].note = 'Постороннее объяснение модели';
  assert.doesNotMatch(section(render(raw), 'conditions'), /Возможный конфликт|Постороннее объяснение/);
  assert.match(section(render(raw), 'conditions'), /Не удалось проверить/);

  const second = raw.ranking.jobs[1].conditions.items[0];
  second.kind = 'salary';
  const html = section(render(raw, 1), 'conditions');
  assert.match(html, /Зарплата[\s\S]*Нужно уточнить/);
  assert.doesNotMatch(html, /Возможный конфликт|Условия совпадают/);
});

test('a possible salary conflict is shown to HR for manual comparison', () => {
  const raw = example('manager-profile');
  const items = raw.ranking.jobs[0].conditions.items;
  const salary = items[1];
  const quote = 'До 200 000 рублей в месяц';
  salary.state = 'conflict';
  salary.check = 'needs_review';
  salary.vacancy_span = { ...items[0].vacancy_span, quote, sentence: quote,
    end: items[0].vacancy_span.start + quote.length };
  salary.findings = [
    { where: 'conditions[1]', severity: 'review', code: 'salary_terms_unverified' },
    { where: 'conditions[1]', severity: 'review', code: 'condition_conflict' }
  ];
  const html = section(render(raw), 'conditions');
  assert.match(html, /Зарплата <span>· Возможный конфликт · Нужна ручная сверка/);
  assert.match(html, /250 000 рублей/);
  assert.match(html, /200 000 рублей/);
});

test('a condition with ambiguous evidence is different from an unstated condition', () => {
  const raw = example('manager-profile');
  const salary = raw.ranking.jobs[0].conditions.items[1];
  salary.cv_span = null;
  salary.check = 'needs_review';
  salary.findings = [
    { where: 'conditions[1].cv', severity: 'review', code: 'ambiguous_location' }
  ];
  const html = section(render(raw), 'conditions');
  assert.match(html, /Резюме<\/span> Не удалось привязать цитату/);
  assert.match(html, /Вакансия<\/span> Сведения не указаны/);
});

test('long profile evidence goes in the cited appendix without an incomplete skill claim', () => {
  const raw = example('manager-profile');
  const sentence = 'Python, Django, PostgreSQL, интеграции, автоматизация сборки, тестирование и мониторинг production — с этим стеком ещё не работал';
  for (const [path, spans] of Object.entries(raw.profile.spans)) {
    if (path.startsWith('stack[')) spans[0].sentence = sentence;
  }
  const html = render(raw);
  assert.match(section(html, 'candidate-profile'), /См\. полный фрагмент/);
  assert.doesNotMatch(section(html, 'candidate-profile'), /PostgreSQL/);
  assert.ok(html.includes(sentence));
});

test('a missing or duplicated condition cannot be printed as a conflict', () => {
  const absent = example('manager-profile');
  absent.ranking.jobs[0].conditions.items[0].vacancy_span = null;
  assert.match(section(render(absent), 'conditions'), /Не удалось проверить/);
  assert.doesNotMatch(section(render(absent), 'conditions'), /Возможный конфликт/);

  const duplicate = example('manager-profile');
  const items = duplicate.ranking.jobs[0].conditions.items;
  items.push({ ...items[0] });
  assert.match(section(render(duplicate), 'conditions'), /Не удалось проверить/);
  assert.doesNotMatch(section(render(duplicate), 'conditions'), /Возможный конфликт/);
});

test('handoff review state in print requires current trusted server context', () => {
  const raw = example('manager-profile');
  const jobId = raw.ranking.jobs[0].job_id;
  raw.run_id = 'b'.repeat(32);
  raw.revision = 12;
  raw.handoff = [{
    job_id: jobId, state: 'reviewed_for_handoff',
    accepted_exceptions: ['abc'], requirements_confirmed: true
  }];
  const report = parseReport(JSON.stringify(raw));
  const imported = renderManagerReport(report, jobId);
  assert.match(imported, /Внешний непроверенный файл[\s\S]*Черновик для проверки/);
  assert.doesNotMatch(imported, /Ревизия 12|Принятые исключения|Состав подтверждён/);
  const context = { runId: raw.run_id, revision: 12 };
  const reviewed = renderManagerReport(report, jobId, context);
  assert.match(reviewed, /Проверено рекрутером для передачи/);
  assert.match(reviewed, /Ревизия 12/);
  assert.match(reviewed, /Принятые исключения по условиям · 1/);
  assert.match(reviewed, /Возможный конфликт/);
  assert.match(renderManagerReport(report, jobId, { ...context, revision: 11 }), /Черновик для проверки/);
  assert.match(renderManagerReport(report, raw.ranking.jobs[1].job_id, context), /Черновик для проверки/);
});
