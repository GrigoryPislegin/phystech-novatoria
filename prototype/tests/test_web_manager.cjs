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
  assert.match(html, /Состав подтверждён в отчёте/);
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
  assert.match(html, /Риски и пробелы.*Доказательство требует проверки/);
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
