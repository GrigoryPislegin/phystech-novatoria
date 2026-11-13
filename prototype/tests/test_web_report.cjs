const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const test = require('node:test');

const { parseReport, filterRows, statusCounts } = require('../static/report.js');

function example(name = 'disputed') {
  return JSON.parse(readFileSync(join(__dirname, 'fixtures', 'web', name + '.json'), 'utf8'));
}

test('the current success and disputed reports expose the four assessment statuses', () => {
  const success = parseReport(JSON.stringify(example('success')));
  const disputed = parseReport(JSON.stringify(example()));
  assert.deepEqual([success.processed, success.total], [3, 3]);
  assert.equal(success.jobs[0].score.lower, 100);
  assert.equal(disputed.jobs[0].score.lower, 50);
  assert.deepEqual(new Set([success, disputed].flatMap(report =>
    report.jobs.flatMap(job => job.rows.map(row => row.status))
  )), new Set(['full', 'partial', 'unknown', 'fail']));
  assert.equal(success.requirementsConfirmed, false);
  assert.equal(success.finalAllowed, false);
});

test('an incomplete run retains successful jobs and identifies every skipped job', () => {
  const report = parseReport(JSON.stringify(example('incomplete')));
  assert.deepEqual([report.processed, report.total, report.complete], [1, 3, false]);
  assert.deepEqual(report.jobs.map(job => job.id), ['job-001']);
  assert.deepEqual(report.unprocessed.map(job => job.id), ['job-002', 'job-003']);
  assert.equal(report.unprocessed[0].reason, 'evaluation_failed');
});

test('legacy reports use source quotes and keep model prose marked as unverified', () => {
  const raw = example('success');
  delete raw.presentation;
  delete raw.verification;
  const first = raw.ranking.jobs[0];
  first.requirements.items[0].text = 'Придуманный опыт';
  first.evaluation.rows[0].comment = 'Заявление модели';
  const report = parseReport(JSON.stringify(raw));
  const row = report.jobs[0].rows[0];
  assert.equal(row.label, row.requirementQuote);
  assert.equal(row.comment, 'Заявление модели');
  assert.equal(row.commentFromModel, true);
  assert.equal(row.verified, false);
  assert.equal(row.evidence, null);
  assert.equal(report.requirementsConfirmed, false);
});

test('prepared presentation wins over free model prose and unsafe local file metadata', () => {
  const raw = example();
  raw.ranking.jobs[0].evaluation.rows[0].comment = 'Неподтверждённый свободный текст';
  raw.manifest = { scope: 'local_only_not_model_payload', jobs: [
    { job_id: 'job-001', filename: '/private/resume.docx', label: 'Внутренний файл' }
  ] };
  const report = parseReport(JSON.stringify(raw));
  assert.equal(report.jobs[0].title, 'job-001');
  assert.notEqual(report.jobs[0].rows[0].comment, raw.ranking.jobs[0].evaluation.rows[0].comment);
  assert.equal(report.jobs[0].rows[0].commentFromModel, false);
  assert.equal(report.jobs[0].rows[0].verified, false);
  assert.equal(report.jobs[0].rows[0].evidence.state, 'structure_ok');
  assert.deepEqual(report.jobs[0].rows[0].resumeQuotes, ['Разрабатывал на Python 3 года.']);
});

test('exported review markers stay separate from confirmation and the stored score', () => {
  const raw = example();
  const job = raw.ranking.jobs[0];
  job.score_review.excluded_mandatory_ids = ['r1'];
  raw.presentation.jobs[0].rows[0].mandatory_check.state = 'needs_review';
  raw.presentation.jobs[0].rows[0].mandatory_check.reasons = [
    { message: 'Проверьте обязательность', context: 'Фрагмент отчёта' }
  ];
  raw.privacy = { professional_information_may_be_hidden: true };
  const report = parseReport(JSON.stringify(raw));
  assert.deepEqual(report.jobs[0].excluded, ['r1']);
  assert.equal(report.jobs[0].score.lower, job.score.lower);
  assert.equal(report.jobs[0].rows[0].mandatoryExcluded, true);
  assert.equal(report.jobs[0].rows[0].mandatoryCheck.reasons[0].context, 'Фрагмент отчёта');
  assert.equal(report.jobs[0].rows[0].verified, false);
  assert.equal(report.finalAllowed, false);
  assert.equal(report.privacyWarning, true);
});

test('ranking order and ties stay as stored, while row filters and search are independent', () => {
  const raw = example('success');
  raw.ranking.jobs[1].rank = 1;
  raw.presentation.jobs[1].rank = 1;
  const { jobs } = parseReport(JSON.stringify(raw));
  assert.deepEqual(jobs.map(job => job.rank), [1, 1, 3]);
  assert.equal(filterRows(jobs[0].rows, 'all', '  pYtHon  ').length, 1);
  assert.equal(filterRows(jobs[0].rows, 'unknown', '').length, 0);
  assert.equal(filterRows(jobs[1].rows, 'unknown', 'java').length, 1);
  assert.equal(filterRows(jobs[2].rows, 'fail', '').length, 1);
  assert.deepEqual(statusCounts(jobs[0].rows), { full: 2, partial: 0, unknown: 0, fail: 0 });
  assert.equal(jobs[0].rows.length, 2);
});

test('quotes stay literal and a missing résumé quote stays empty', () => {
  const raw = example();
  const markup = '<strong>Навык</strong>';
  raw.presentation.jobs[0].rows[0].requirement_quote = markup;
  raw.ranking.jobs[0].requirements.items[0].quote = markup;
  const { jobs } = parseReport(JSON.stringify(raw));
  assert.equal(jobs[0].rows[0].requirementQuote, markup);
  assert.deepEqual(jobs[1].rows[0].resumeQuotes, []);
});

test('prepared rows must cover and agree with the underlying assessment', () => {
  const variants = [
    job => job.rows.pop(),
    job => { job.rows[0].status = 'partial'; },
    job => { job.rows[0].resume_quotes = []; },
    job => { job.rows[0].resume_quotes = ['Цитата из другого факта']; },
    job => { job.rows[0].requirement_quote = 'Подменённое требование'; }
  ];
  for (const mutate of variants) {
    const raw = example('success');
    mutate(raw.presentation.jobs[0]);
    assert.throws(() => parseReport(JSON.stringify(raw)), /структур/);
  }
});

test('invalid JSON, unknown schemas and inconsistent reports fail explicitly', () => {
  for (const input of ['', 'null', '[', '{}', '{"schema_version":"9"}']) {
    assert.throws(() => parseReport(input));
  }
  const raw = example('incomplete');
  raw.ranking.complete = true;
  assert.throws(() => parseReport(JSON.stringify(raw)), /структур/);
  const complete = example('success');
  complete.presentation.jobs[0].rows[0].status = 'made_up';
  assert.throws(() => parseReport(JSON.stringify(complete)), /структур/);
});

test('malformed recommendations and oversized job sets cannot replace an open report', () => {
  const report = example('success');
  report.ranking.recommendation = { toString: null };
  assert.throws(() => parseReport(JSON.stringify(report)), /структур/);

  const incomplete = example('incomplete');
  incomplete.unprocessed_job_ids = Array.from({ length: 20 }, (_, index) => 'skipped-' + index);
  delete incomplete.unprocessed;
  assert.throws(() => parseReport(JSON.stringify(incomplete)), /структур/);
});

test('dashboard preserves stored rank, bounds and weighted coverage for an incomplete run', () => {
  const { describeDashboard } = require('../static/report.js');
  const raw = example('incomplete');
  Object.assign(raw.ranking.jobs[0].score, { lower: 17.25, upper: 79, coverage: 31.5 });
  const report = parseReport(JSON.stringify(raw));
  const dashboard = describeDashboard(report);
  assert.deepEqual(dashboard.map(job => [job.rank, job.lower, job.upper, job.coverage]), [[1, 17.25, 79, 31.5]]);
  assert.deepEqual(dashboard[0].counts, statusCounts(report.jobs[0].rows));
  assert.equal(dashboard[0].total, report.jobs[0].rows.length);
  assert.deepEqual(describeDashboard({ jobs: [] }), []);
});

test('the dashboard omits raw vacancy identifiers from imported text', () => {
  const { describeDashboard } = require('../static/report.js');
  const raw = example('success');
  const id = '<img src=x onerror=alert(1)>/private/vacancy';
  raw.ranking.jobs[0].job_id = id;
  raw.presentation.jobs[0].job_id = id;
  const [job] = describeDashboard(parseReport(JSON.stringify(raw)));
  assert.equal(job.title, '№1');
  assert.equal(JSON.stringify(job).includes(id), false);
});

test('bundled demo uses the same validated synthetic input as the manager report tests', () => {
  const demo = require('../static/demo-report.js');
  assert.deepEqual(JSON.parse(demo), example('manager-profile'));
  const report = parseReport(demo);
  assert.equal(report.mode, 'synthetic_replay_NOT_model_output');
  assert.equal(report.profile.state, 'structure_ok');
  assert.ok(report.jobs[0].conditions.items.some(item => item.state === 'conflict'));
});

test('comparison uses stored outcomes and references an existing quoted row', () => {
  const raw = example('success');
  const [leader, next] = raw.ranking.jobs;
  const row = raw.presentation.jobs[0].rows[0];
  const deciding = {
    job_id: leader.job_id, requirement_id: row.requirement_id, status: row.status,
    requirement_quote: row.requirement_quote, cv_quotes: row.resume_quotes, effect: 75.5
  };
  raw.comparisons = [{
    job_a: leader.job_id, job_b: next.job_id, outcome: 'a_higher', reason: 'lower_bound',
    summary: 'Не доверять произвольной сводке <script>attacker</script>',
    deciding: [deciding, { ...deciding, requirement_quote: 'Подменённая цитата' }],
    swings: [{ row: deciding, assumed_status: 'full', result: 'tie' }],
    caveats: ['different_requirement_lists']
  }];
  const report = parseReport(JSON.stringify(raw));
  const [comparison] = report.comparisons;
  assert.deepEqual([comparison.outcome, comparison.reason, comparison.caveats],
    ['a_higher', 'lower_bound', ['different_requirement_lists']]);
  assert.deepEqual(comparison.deciding.map(factor => factor.row), [report.jobs[0].rows[0]]);
  assert.equal(comparison.swings[0].result, 'tie');
  assert.doesNotMatch(JSON.stringify(comparison), /<script>|Подменённая/);

  leader.rank = next.rank;
  raw.presentation.jobs[0].rank = leader.rank;
  assert.deepEqual(parseReport(JSON.stringify(raw)).comparisons, []);
  raw.comparisons[0].outcome = 'tie';
  raw.comparisons[0].reason = 'tie';
  raw.comparisons[0].deciding = [];
  assert.equal(parseReport(JSON.stringify(raw)).comparisons[0].outcome, 'tie');
});
