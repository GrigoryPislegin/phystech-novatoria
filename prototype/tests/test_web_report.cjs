const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const test = require('node:test');

const { parseReport, filterRows, statusCounts } = require('../static/report.js');
const { describeFailure, describeRun } = require('../static/report.js');

test('zero results and privacy failures have static actionable feedback', () => {
  assert.equal(describeRun({ mode:'live_local_privacy', processed:0, complete:false }).recommendation[0],
    'Анализ не выполнен');
  assert.match(describeFailure({code:'privacy_residual_findings', stage:'facts',
    privacy:{direction:'response'}}), /Извлечение фактов.*Ответ модели.*защит/);
  assert.doesNotMatch(describeFailure({code:'private@example.org', stage:'/private/source',
    privacy:{direction:'model-secret'}}), /private|model-secret/);
});

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
  incomplete.unprocessed_job_ids = Array.from({ length: 30 }, (_, index) => 'skipped-' + index);
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

function leaderExample(name = 'success') {
  const raw = example(name);
  raw.policy_version = 'draft-2026-11-14-v3';
  for (const job of raw.ranking.jobs) Object.assign(job.score, {policy_version:raw.policy_version, resolution:25,
    conflict_ids:[], units:job.evaluation.rows.map(row => ({ids:[row.requirement_id], state:row.status,
      group:job.requirements.items.find(item => item.id === row.requirement_id).mandatory_quote ? 'core' : 'extra'}))});
  const job = raw.ranking.jobs[0];
  const row = raw.presentation.jobs[0].rows[0];
  const ref = { job_id: job.job_id, requirement_id: row.requirement_id,
    status: row.status, requirement_quote: row.requirement_quote,
    cv_quotes: row.resume_quotes, effect: 75 };
  raw.leader = { policy_version: raw.policy_version, job_ids: [job.job_id], state: name === 'success' ? 'stable' : 'open',
    summary: '<script>Подтверждено HR</script>', factors: [ref], limits: [], can_change: [],
    close_to: [], challengers: [], unassessed: [raw.ranking.jobs[1].job_id] };
  return raw;
}

test('leader analysis resolves source rows without trusting prose or granting HR approval', () => {
  const report = parseReport(JSON.stringify(leaderExample()));
  assert.equal(report.leader.state, 'stable');
  assert.equal(report.leader.factors[0].row, report.jobs[0].rows[0]);
  assert.equal(report.leader.unassessed[0], report.jobs[1]);
  assert.doesNotMatch(JSON.stringify(report.leader), /script|Подтверждено HR/);
  assert.equal(report.finalAllowed, false);
  assert.equal(parseReport(JSON.stringify(example('success'))).leader, null);
});

test('invalid leader references and policy versions cannot explain the ranking', () => {
  const mutations = [
    raw => { raw.leader.factors[0].requirement_quote = 'Подменённая цитата'; },
    raw => { raw.leader.factors[0].job_id = raw.ranking.jobs[1].job_id; },
    raw => { raw.leader.factors[0].effect = 101; },
    raw => { raw.ranking.jobs[2].score.policy_version = 'draft-2026-11-13-v2'; },
    raw => { raw.policy_version = 'unknown'; },
    raw => { raw.leader.job_ids = [raw.ranking.jobs[1].job_id]; },
    raw => { raw.leader.can_change = [{row: raw.leader.factors[0], kind: 'made_up', role: 'leader'}]; },
    raw => { raw.leader.state = 'none_fit'; },
    raw => { raw.leader.state = 'tie'; },
    raw => { raw.leader.unassessed = raw.leader.job_ids; },
    raw => { raw.leader.close_to = raw.leader.job_ids; },
    raw => { raw.leader.challengers = raw.leader.job_ids; },
    raw => { raw.leader.state = 'open'; raw.leader.can_change = [
      {row:raw.leader.factors[0], kind:'unknown', role:'leader'}]; }
  ];
  for (const mutate of mutations) {
    const raw = leaderExample();
    mutate(raw);
    const report = parseReport(JSON.stringify(raw));
    assert.equal(report.leader, null);
    assert.equal(report.jobs.length, 3);
  }
  const disputed = leaderExample('disputed');
  disputed.leader.state = 'stable';
  assert.equal(parseReport(JSON.stringify(disputed)).leader, null);
  disputed.ranking.recommendation = 'review_top';
  assert.equal(parseReport(JSON.stringify(disputed)).leader, null);
});

test('decisive flags are strict booleans and close margins must agree with stored scores', () => {
  const raw = leaderExample('disputed');
  const [a, b] = raw.ranking.jobs;
  raw.leader.can_change = [{row:raw.leader.factors[0], kind:'partial', role:'leader'}];
  raw.review_queue = {schema_version:'review-queue-0.1', policy_version:raw.policy_version, items:[
    {id:'a', job_id:a.job_id, requirement_id:raw.leader.factors[0].requirement_id, explanation:'Уточнить', decisive:true},
    {id:'b', job_id:b.job_id, explanation:'Проверить', decisive:'true'}
  ]};
  let report = parseReport(JSON.stringify(raw));
  assert.deepEqual(report.reviewItems.map(item => item.decisive), [true, false]);
  b.score.lower = 45;
  raw.comparisons = [{job_a:a.job_id, job_b:b.job_id, outcome:'a_higher', reason:'lower_bound',
    deciding:[], swings:[], close:true, margin:a.score.lower-b.score.lower, caveats:['close_margin']}];
  report = parseReport(JSON.stringify(raw));
  assert.deepEqual(report.comparisons[0].caveats, ['close_margin']);
  raw.comparisons[0].margin = -1;
  report = parseReport(JSON.stringify(raw));
  assert.deepEqual(report.comparisons[0].caveats, []);
  raw.comparisons[0].margin = a.score.lower-b.score.lower;
  for (const job of raw.ranking.jobs) job.score.policy_version = 'draft-2026-11-13-v2';
  report = parseReport(JSON.stringify(raw));
  assert.deepEqual(report.comparisons[0].caveats, []);
  assert.ok(report.reviewItems.every(item => item.decisive === false));
});


test('v3 optional metadata cannot reinterpret legacy reports or break readable base data', () => {
  for (const ids of [['r1'], 'malformed']) {
    const raw = example('success');
    raw.ranking.jobs[0].score.conflict_ids = ids;
    raw.ranking.jobs[0].score.units = [{ids:['r1','r2'], state:'conflict'}];
    const report = parseReport(JSON.stringify(raw));
    assert.deepEqual(report.jobs[0].conflicts, []);
    assert.deepEqual(report.jobs[0].units, []);
  }
  const raw = leaderExample();
  raw.ranking.jobs[0].score.units = [{ids:['r1','r2'], state:'conflict'}];
  raw.ranking.jobs[0].score.conflict_ids = ['r1','r2'];
  const report = parseReport(JSON.stringify(raw));
  assert.equal(report.jobs.length, 3);
  assert.equal(report.leader, null);
  assert.deepEqual(report.jobs[0].conflicts, []);
});

test('30 vacancies remain complete and the 31st is rejected', () => {
  const raw = example('success');
  const first = raw.ranking.jobs[0];
  delete raw.presentation;
  raw.ranking.jobs = Array.from({length:30}, (_,index) => ({...structuredClone(first),job_id:'batch-'+index,rank:index+1}));
  assert.equal(parseReport(JSON.stringify(raw)).jobs.length,30);
  raw.ranking.jobs.push({...structuredClone(first),job_id:'batch-30',rank:31});
  assert.throws(() => parseReport(JSON.stringify(raw)), /структур/);
});

test('display aliases are run-bound, literal, stable and separate from score input', () => {
  const { bindDisplayData, createDisplayText, displayCopy } = require('../static/report.js');
  const ref = '[[PRIV:0123456789abcdef:1:ORG]]';
  const other = '[[PRIV:0123456789abcdef:2:PERSON]]';
  const report = parseReport(JSON.stringify(example('success')));
  report.runId = 'a'.repeat(32); report.revision = 2;
  report.jobs[0].rows[0].label = ref;
  const original = JSON.stringify(report.jobs[0].score);
  const data = {run_id:report.runId,revision:2,aliases:{[ref]:'<img src=x> Vue.js'},job_titles:{[report.jobs[0].id]:ref}};
  assert.throws(() => bindDisplayData(report,{...data,revision:1}), /Версия/);
  assert.throws(() => bindDisplayData(report,{...data,run_id:'b'.repeat(32)}), /Версия/);
  const display = bindDisplayData(report,data);
  assert.equal(display(ref),'<img src=x> Vue.js');
  assert.equal(display(other),'Фрагмент 1');
  assert.equal(display(other),'Фрагмент 1');
  assert.equal(filterRows(report.jobs[0].rows,'all','vue',display).length,1);
  assert.equal(report.jobs[0].rows[0].label,ref);
  assert.equal(JSON.stringify(report.jobs[0].score),original);
  const copy = displayCopy(report,display);
  assert.equal(copy.jobs[0].rows[0].label,'<img src=x> Vue.js');
  assert.equal(createDisplayText()(ref),'Фрагмент 1');
  assert.equal(bindDisplayData(report,null)(ref),'Фрагмент 1');
});

test('brief uses bounded server groups and never turns missing evidence into zero', () => {
  const raw = example('success');
  raw.policy_version = 'draft-2026-11-14-v3';
  const job = raw.ranking.jobs[0];
  for (const entry of raw.ranking.jobs) entry.score.policy_version = raw.policy_version;
  const ids = job.requirements.items.map(item=>item.id);
  job.score.coverage = 50;
  job.score.lower = 50;
  job.score.upper = 100;
  job.evaluation.rows[1] = {...job.evaluation.rows[1],status:'unknown',fact_ids:[],question:'Уточните опыт.'};
  const shown = raw.presentation.jobs[0].rows;
  shown[1] = {...shown[1],status:'unknown',resume_quotes:[],question:'Уточните опыт.'};
  shown.forEach((row,index) => {row.evidence_check = {requirement_id:row.requirement_id,state:index ? 'no_evidence' : 'structure_ok',reasons:[]};});
  job.score.units = [{ids:ids.slice(0,1),state:'full'},{ids:ids.slice(1),state:'unknown'}];
  job.score.conflict_ids = [];
  job.score.disputed_ids = [];
  job.score.shares = {confirmed:50,disputed:0,unknown:50};
  job.score.breakdown = {full:ids.slice(0,1),partial:[],fail:[],unknown:ids.slice(1),disputed:[]};
  job.competency_axes = {policy_version:raw.policy_version,job_id:job.job_id,axes:[
    {axis:'stack',score:0,coverage:100,weight:50,requirement_ids:ids.slice(0,1)},
    {axis:'domain',score:null,coverage:0,weight:50,requirement_ids:ids.slice(1)}]};
  let brief = parseReport(JSON.stringify(raw)).jobs[0].brief;
  assert.deepEqual(brief.axes.map(axis=>axis.score),[0,null]);
  assert.equal(brief.strengths.length,1);
  job.competency_axes.axes[0].score = 100;
  job.competency_axes.axes[0].coverage = 0;
  assert.deepEqual(parseReport(JSON.stringify(raw)).jobs[0].brief.axes,[]);
  job.competency_axes.axes[0].coverage = 100;
  job.competency_axes.axes[0].score = 500;
  assert.deepEqual(parseReport(JSON.stringify(raw)).jobs[0].brief.axes,[]);
  job.score.breakdown.full = ids;
  job.score.breakdown.unknown = [];
  assert.equal(parseReport(JSON.stringify(raw)).jobs[0].brief.strengths.length,1);
  job.score.shares.confirmed = 200;
  assert.equal(parseReport(JSON.stringify(raw)).jobs[0].brief.shares,null);
});

test('radar distinguishes measured zero from absent data without inventing a vertex', () => {
  const { radarGeometry } = require('../static/report.js');
  const points = radarGeometry([{axis:'stack',score:100,coverage:100},{axis:'domain',score:null,coverage:0},
    {axis:'education',score:0,coverage:100},{axis:'language',score:50,coverage:20}]);
  assert.equal(points.length,4);
  assert.equal(points[1].point,null);
  assert.deepEqual(points[2].point,{x:160,y:130});
  assert.notDeepEqual(points[0].point,{x:160,y:130});
  assert.deepEqual(radarGeometry([{score:90}]),[]);
});
