(function (root) {
  'use strict';

  const MAX_REPORT_BYTES = 25_000_000;
  const MAX_REQUIREMENTS = 80;
  const statuses = ['full', 'partial', 'unknown', 'fail'];
  const modes = {
    synthetic_replay_NOT_model_output: ['Синтетический replay', 'Заранее подготовленные ответы'],
    synthetic_sdk_mock_NOT_model_output: ['Mock SDK', 'Локальный тест без запросов к модели'],
    live_synthetic: ['Live · Синтетические данные', 'Ответы модели'],
    live_local_privacy: ['Live · Защищённый анализ', 'Ответы модели'],
    live_certum: ['Live · Защищённый анализ', 'Ответы модели']
  };
  const scenarios = { success: 'Подходящая вакансия', disputed: 'Спорный случай', incomplete: 'Неполный запуск' };
  const recommendations = {
    review_top: ['С чего начать', 'Проверьте цитаты по вакансиям на первом месте.'],
    clarify: ['Нужны уточнения', 'Перед выбором вакансии проверьте основания порядка и открытые вопросы в очереди проверки.'],
    review_none_fit: ['Нужна проверка несоответствий', 'Проверьте обязательность требований и основания по каждой вакансии.']
  };
  const assessments = {
    full: ['Полное соответствие', 'ok'],
    partial: ['Частичное соответствие', 'warning'],
    unknown: ['Сведения не указаны', 'neutral'],
    fail: ['Несоответствие', 'danger']
  };
  const mandatoryStates = {
    confirmed: ['Обязательные условия покрыты по оценке', 'ok'],
    clarify: ['Обязательные условия требуют уточнения', 'warning'],
    violated: ['Выявлено обязательное несоответствие', 'danger'],
    not_set: ['Обязательные условия не выделены', 'neutral']
  };
  const evidenceLabels = {
    structure_ok: 'Структура сверена · смысл требует проверки',
    no_evidence: 'Цитата в резюме не указана',
    needs_review: 'Доказательство требует проверки',
    invalid: 'Отчёт отмечает ошибку в доказательстве'
  };
  const requirementReviews = {
    confirmed: 'Состав подтверждён в отчёте',
    stale: 'Подтверждение состава устарело',
    invalid: 'Подтверждение состава недействительно',
    unconfirmed: 'Состав не подтверждён'
  };
  const checkStates = ['structure_ok', 'needs_review', 'invalid'];
  const conditionLabels = {
    work_mode: 'Формат работы', location: 'Место работы', schedule: 'График',
    relocation: 'Переезд', salary: 'Зарплата'
  };
  const profilePath = /^(?:summary\[[0-2]\]|stack\[(?:[0-9]|[12][0-9])\]|last_position\.(?:role|domain|period)|achievements\[[0-4]\]\.(?:action|result))$/;
  const numberFormat = new Intl.NumberFormat('ru', { maximumFractionDigits: 4 });
  const verdictLabels = {
    mismatch: 'Есть несоответствие требованиям',
    partial: 'Соответствие частичное',
    unknown: 'Недостаточно сведений о соответствии',
    review: 'Нужна проверка',
    match: 'По оценённым требованиям соответствует'
  };

  function scoreRange(score) {
    const low = numberFormat.format(score.lower);
    const high = numberFormat.format(score.upper);
    return (score.lower === score.upper ? low : low + '–' + high) + '%';
  }

  function describeRun(report) {
    const [mode, modeDetail] = Object.hasOwn(modes, report.mode)
      ? modes[report.mode] : ['Неизвестный режим', 'Тип запуска не распознан'];
    const scenario = Object.hasOwn(scenarios, report.scenario) ? scenarios[report.scenario] : null;
    const recommendation = !report.complete
      ? ['Неполный рейтинг', 'Места предварительные. Ниже показаны только оценённые вакансии.']
      : Object.hasOwn(recommendations, report.recommendation)
        ? recommendations[report.recommendation] : null;
    return { mode, modeDetail, scenario, recommendation };
  }

  function requirementReviewLabel(state) {
    return requirementReviews[state] || requirementReviews.unconfirmed;
  }

  function mandatoryNeedsReview(row) {
    return row.mandatoryExcluded || (Boolean(row.mandatoryQuote) && row.mandatoryCheck?.state !== 'structure_ok');
  }

  function mandatoryLabel(row) {
    if (mandatoryNeedsReview(row)) {
      return 'Обязательность требует проверки';
    }
    return row.mandatoryQuote ? 'Обязательное по отчёту' : 'Обязательность не указана';
  }

  function evidenceLabel(row) {
    if (row.scoreConflict) return 'Оценки одного требования противоречат друг другу';
    return evidenceLabels[row.evidence?.state] || 'Доказательство требует проверки';
  }

  function evidenceNeedsReview(row) {
    if (row.scoreConflict) return true;
    if (row.status === 'unknown') {
      return ['needs_review', 'invalid'].includes(row.evidence?.state);
    }
    return row.evidence?.state !== 'structure_ok';
  }

  function describeFit(report, job) {
    const rows = job.rows.map((row, index) => ({ row, number: index + 1 }));
    const groups = { mismatch: [], partial: [], unknown: [], review: [] };
    const grounds = [];
    for (const item of rows) {
      const { row } = item;
      if (row.scoreConflict) { groups.review.push(item); continue; }
      const evidenceChecked = row.evidence?.state === 'structure_ok';
      if (row.status === 'full' && evidenceChecked) grounds.push(item);

      if (row.status === 'fail' && evidenceChecked) groups.mismatch.push(item);
      else if (row.status === 'partial') groups.partial.push(item);
      else if (row.status === 'unknown') groups.unknown.push(item);
      else if (mandatoryNeedsReview(row) || evidenceNeedsReview(row)) groups.review.push(item);
    }

    const gap = ['mismatch', 'partial', 'unknown', 'review'].find(state => groups[state].length);
    const listConfirmed = job.requirementsReview === 'confirmed';
    const state = gap ?? (report.complete && listConfirmed ? 'match' : 'review');
    const notes = [];
    if (state === 'review' && !report.complete) notes.push('Обработана часть вакансий.');
    if (state === 'review' && !gap && grounds.length === rows.length) {
      notes.push('По всем оценённым требованиям есть признаки соответствия.');
    }
    if (!gap && !listConfirmed) notes.push(requirementReviewLabel(job.requirementsReview) + '.');

    const risks = Object.values(groups).flat();
    risks.sort((left, right) => Number(Boolean(right.row.mandatoryQuote)) - Number(Boolean(left.row.mandatoryQuote)));
    const priority = groups[gap]?.find(({ row }) => row.mandatoryQuote) ?? groups[gap]?.[0];
    return { rows, grounds, risks, label: verdictLabels[state], notes, priority };
  }

  function requireShape(condition) {
    if (!condition) throw new Error('В файле нет корректной структуры отчёта.');
  }

  function isRecord(value) {
    return value !== null && typeof value === 'object' && !Array.isArray(value);
  }

  function isText(value) {
    return typeof value === 'string' && value.trim().length > 0;
  }

  function isOptionalText(value) {
    return value == null || typeof value === 'string';
  }

  function digest(value) {
    return typeof value === 'string' && /^[0-9a-f]{64}$/i.test(value) ? value : null;
  }

  function versionLabel(value) {
    return typeof value === 'string' && /^[a-z0-9][a-z0-9._:-]{0,127}$/i.test(value)
      ? value : null;
  }

  function sourceSpan(span, id, hash) {
    if (!hash || !isRecord(span) || span.source_id !== id ||
        digest(span.source_sha256)?.toLowerCase() !== hash.toLowerCase() ||
        !isText(span.quote) || !Number.isInteger(span.start) || !Number.isInteger(span.end) ||
        span.start < 0 || span.end > 60_000 || span.end - span.start !== Array.from(span.quote).length) {
      return null;
    }
    // Evidence sentences omit list markers and terminal punctuation.
    const core = span.quote.trim().replace(/^(?:[-*•–]|\d+[.)])\s+/, '').replace(/[.!?;]+$/, '').trim();
    const sentence = core && isText(span.sentence) && span.sentence.includes(core) &&
      span.sentence !== core ? span.sentence : span.quote;
    const heading = isText(span.heading) ? span.heading : null;
    return { quote: span.quote, sentence, heading };
  }

  function profileFrom(profile, factQuotes, resumeHash) {
    if (profile == null) return { state: 'missing' };
    if (!isRecord(profile) || profile.schema_version !== 'candidate-profile-0.1' ||
        !checkStates.includes(profile.state) || profile.state === 'invalid' ||
        !isRecord(profile.spans) || !isRecord(profile.display) || !resumeHash) {
      return { state: 'invalid' };
    }
    const claims = new Map();
    let state = profile.state;
    for (const [path, spans] of Object.entries(profile.spans)) {
      if (!profilePath.test(path)) continue;
      if (!Array.isArray(spans) || !spans.length || spans.length > 5) {
        state = 'needs_review';
        continue;
      }
      const sources = spans.map(span => sourceSpan(span, 'cv', resumeHash));
      if (!sources.every(span => span && factQuotes.some(quote => quote.includes(span.quote)))) {
        state = 'needs_review';
        continue;
      }
      claims.set(path, sources);
    }
    for (const path of Object.keys(profile.display)) {
      if (profilePath.test(path) && !claims.has(path)) state = 'needs_review';
    }
    if (!claims.size) return { state: state === 'needs_review' ? 'invalid' : 'missing' };
    return { state, claims };
  }

  function conditionsFrom(conditions, jobId, resumeHash, vacancyHash, factQuotes) {
    if (conditions == null) return { state: 'missing', items: [] };
    if (!isRecord(conditions) || !Array.isArray(conditions.items) || conditions.items.length > 10 ||
        !Array.isArray(conditions.findings) || !resumeHash || !vacancyHash) {
      return { state: 'invalid', items: [] };
    }
    const items = new Map();
    let invalid = conditions.has_invalid === true || conditions.findings.some(finding => finding?.severity === 'invalid');
    for (const [index, item] of conditions.items.entries()) {
      if (!isRecord(item) || typeof item.kind !== 'string' || !Object.hasOwn(conditionLabels, item.kind)) {
        invalid = true;
        continue;
      }
      const label = conditionLabels[item.kind];
      if (items.has(item.kind)) {
        items.set(item.kind, { label, state: 'invalid' });
        invalid = true;
        continue;
      }
      const cv = item.cv_span == null ? null : sourceSpan(item.cv_span, 'cv', resumeHash);
      const vacancy = item.vacancy_span == null ? null : sourceSpan(item.vacancy_span, jobId, vacancyHash);
      const valid = ['compatible', 'conflict', 'unknown'].includes(item.state) &&
        checkStates.includes(item.check) && item.check !== 'invalid' &&
        Array.isArray(item.findings) && !item.findings.some(finding => finding?.severity === 'invalid') &&
        (item.cv_span == null || (cv && factQuotes.some(quote => quote.includes(cv.quote)))) &&
        (item.vacancy_span == null || vacancy) &&
        (item.state === 'unknown' || (cv && vacancy));
      if (!valid) {
        items.set(item.kind, { label, state: 'invalid' });
        invalid = true;
        continue;
      }
      const needsReview = item.kind === 'salary' || item.check !== 'structure_ok' || item.findings.length > 0;
      const state = item.state === 'compatible' && needsReview ? 'unknown' : item.state;
      const where = 'conditions[' + index + ']';
      const unresolved = field => item.findings.some(finding => finding?.where === where + '.' + field);
      items.set(item.kind, {
        label, state, cv, vacancy, needsReview,
        cvUnresolved: !cv && unresolved('cv'), vacancyUnresolved: !vacancy && unresolved('vacancy_quote')
      });
    }
    return { state: invalid ? 'invalid' : 'available', items: Array.from(items.values()) };
  }

  function uniqueIndex(items, key) {
    requireShape(Array.isArray(items));
    const index = new Map();
    for (const item of items) {
      requireShape(isRecord(item) && isText(item[key]) && !index.has(item[key]));
      index.set(item[key], item);
    }
    return index;
  }

  function scoreFrom(value) {
    const inRange = n => Number.isFinite(n) && n >= 0 && n <= 100;
    requireShape(isRecord(value) && inRange(value.lower) && inRange(value.upper) &&
      inRange(value.coverage) && value.lower <= value.upper &&
      ['confirmed', 'clarify', 'violated', 'not_set'].includes(value.mandatory));
    return {
      lower: value.lower, upper: value.upper, coverage: value.coverage,
      mandatory: value.mandatory, policyVersion: versionLabel(value.policy_version),
      resolution: Number.isFinite(value.resolution) && value.resolution > 0 && value.resolution <= 50
        ? value.resolution : null
    };
  }

  function rowFrom(id, requirementQuote, values) {
    requireShape(isText(id) && isText(requirementQuote) && statuses.includes(values.status) &&
      isOptionalText(values.mandatoryQuote) && isOptionalText(values.comment) &&
      isOptionalText(values.question) && Array.isArray(values.resumeQuotes) &&
      values.resumeQuotes.every(isText));
    return {
      id, requirementQuote,
      label: isText(values.label) && requirementQuote.includes(values.label) ? values.label : requirementQuote,
      mandatoryQuote: values.mandatoryQuote || null,
      status: values.status,
      resumeQuotes: values.resumeQuotes.slice(),
      comment: values.comment || null,
      question: values.question || null,
      commentFromModel: values.fromModel,
      verified: false
    };
  }

  function checkFrom(check, id) {
    if (check == null) return null;
    requireShape(isRecord(check) && check.requirement_id === id &&
      ['structure_ok', 'no_evidence', 'not_mandatory', 'needs_review', 'invalid'].includes(check.state) &&
      Array.isArray(check.reasons) && check.reasons.every(reason =>
        isRecord(reason) && isText(reason.message) && isOptionalText(reason.context)));
    return { state: check.state, reasons: check.reasons.map(({ message, context }) => ({ message, context })) };
  }

  function rowsFrom(job, facts, prepared, excluded) {
    requireShape(isRecord(job.requirements) && isRecord(job.evaluation));
    requireShape(Array.isArray(job.requirements.items) && job.requirements.items.length <= MAX_REQUIREMENTS &&
      Array.isArray(job.evaluation.rows) && job.evaluation.rows.length === job.requirements.items.length);
    const requirements = uniqueIndex(job.requirements.items, 'id');
    const rows = uniqueIndex(job.evaluation.rows, 'requirement_id');
    requireShape(rows.size === requirements.size);
    requireShape(excluded.every(id => requirements.has(id) && isText(requirements.get(id).mandatory_quote)));
    let displayed;
    if (prepared) {
      requireShape(Array.isArray(prepared.rows) && prepared.rows.length === rows.size);
      displayed = uniqueIndex(prepared.rows, 'requirement_id');
    }
    return Array.from(rows.values(), row => {
      const requirement = requirements.get(row.requirement_id);
      requireShape(requirement && Array.isArray(row.fact_ids));
      requireShape(new Set(row.fact_ids).size === row.fact_ids.length &&
        (row.status === 'unknown' ? row.fact_ids.length === 0 : row.fact_ids.length > 0));
      const quotes = row.fact_ids.map(id => {
        requireShape(facts.has(id) && isText(facts.get(id).quote));
        return facts.get(id).quote;
      });
      const view = displayed?.get(row.requirement_id);
      if (displayed) {
        requireShape(view && view.status === row.status && view.requirement_quote === requirement.quote &&
          (view.mandatory_quote ?? null) === (requirement.mandatory_quote ?? null) &&
          Array.isArray(view.resume_quotes) && view.resume_quotes.length === quotes.length &&
          view.resume_quotes.every((quote, index) => quote === quotes[index]));
      }
      const result = rowFrom(requirement.id, requirement.quote, {
        label: view ? view.label : requirement.text,
        status: row.status, mandatoryQuote: requirement.mandatory_quote, resumeQuotes: quotes,
        comment: view ? view.explanation : row.comment,
        question: view ? view.question : row.question, fromModel: !view
      });
      return {
        ...result,
        evidence: checkFrom(view?.evidence_check, result.id),
        mandatoryCheck: checkFrom(view?.mandatory_check, result.id),
        mandatoryExcluded: excluded.includes(result.id)
      };
    });
  }

  function unprocessedFrom(report, jobs) {
    requireShape(Array.isArray(report.unprocessed_job_ids) &&
      report.unprocessed_job_ids.every(id => isText(id) && !jobs.has(id)));
    const ids = new Set(report.unprocessed_job_ids);
    requireShape(ids.size === report.unprocessed_job_ids.length);
    const reasons = report.unprocessed == null ? new Map() : uniqueIndex(report.unprocessed, 'job_id');
    requireShape(Array.from(reasons.values()).every(entry => ids.has(entry.job_id) && isText(entry.reason)));
    return Array.from(ids, (id, index) => ({
      id, title: vacancyTitle(id, jobs.size + index), reason: reasons.get(id)?.reason || null
    }));
  }

  function requirementReviewFrom(job) {
    const review = job.requirements_review;
    return isRecord(review) && review.vacancy_id === job.job_id && isText(review.state) &&
      Object.hasOwn(requirementReviews, review.state)
      ? review.state : 'unconfirmed';
  }

  function vacancyTitle(id, index) {
    // Live job IDs include a digest of the original source. Keep them out of display and print.
    return /^job-\d{3}$/.test(id) ? id : '№' + (index + 1);
  }

  function readReviewItems(queue, jobs, leader) {
    if (queue?.schema_version !== 'review-queue-0.1' || !Array.isArray(queue.items)) return [];
    return queue.items.slice(0, 2000).filter(item => isRecord(item) && isText(item.id) &&
      (item.job_id === null || jobs.has(item.job_id)) && isText(item.explanation)).map(item => ({
        id: item.id, job_id: item.job_id, action: isText(item.action) ? item.action : null, explanation: item.explanation,
        decisive: queue.policy_version === 'draft-2026-11-14-v3' && item.decisive === true &&
          !!leader?.canChange.some(ref => ref.jobId === item.job_id && ref.unitIds.includes(item.requirement_id)),
        refs: Array.isArray(item.refs) ? item.refs.filter(ref => isRecord(ref) && isText(ref.quote) &&
          ['cv', 'vacancy'].includes(ref.source) && isOptionalText(ref.sentence) && isOptionalText(ref.heading)) : [],
        contexts: Array.isArray(item.contexts) ? item.contexts.filter(isText) : []
      }));
  }

  function readHandoff(input, jobs) {
    if (!Array.isArray(input)) return [];
    return input.slice(0, 20).filter(item => isRecord(item) && jobs.has(item.job_id)).map(item => ({
      job_id: item.job_id, state: isText(item.state) ? item.state : null, requirements_confirmed: item.requirements_confirmed === true,
      blockers: Array.isArray(item.blockers) ? item.blockers.filter(isText) : [],
      acknowledged: Array.isArray(item.acknowledged) ? item.acknowledged.filter(isText) : [],
      accepted_exceptions: Array.isArray(item.accepted_exceptions) ? item.accepted_exceptions.filter(isText) : [],
      allowed_actions: isRecord(item.allowed_actions) ? item.allowed_actions : null,
      can_confirm_requirements: item.can_confirm_requirements === true,
      can_mark_for_handoff: item.can_mark_for_handoff === true
    }));
  }

  function factorReference(ref, jobs) {
    if (!isRecord(ref)) return null;
    const job = jobs.find(item => item.id === ref.job_id);
    const row = job?.rows.find(item => item.id === ref.requirement_id);
    if (!row || row.status !== ref.status || row.requirementQuote !== ref.requirement_quote ||
        !Array.isArray(ref.cv_quotes) || row.resumeQuotes.length !== ref.cv_quotes.length ||
        !row.resumeQuotes.every((quote, index) => quote === ref.cv_quotes[index]) ||
        !Number.isFinite(ref.effect) || Math.abs(ref.effect) > 100) return null;
    return { jobId: job.id, row, effect: ref.effect,
      unitIds: job.units.find(unit => unit.includes(row.id)) || [row.id] };
  }

  function readComparison(item, jobs, policy) {
    if (!isRecord(item)) return null;
    const byId = new Map(jobs.map(job => [job.id, job]));
    const a = byId.get(item.job_a);
    const b = byId.get(item.job_b);
    if (!a || !b || a === b || (item.policy_version && item.policy_version !== policy)) return null;
    const outcome = a.rank === b.rank ? 'tie' : a.rank < b.rank ? 'a_higher' : 'b_higher';
    if (item.outcome !== outcome || !(outcome === 'tie' ? item.reason === 'tie' :
      ['mandatory_violation', 'lower_bound'].includes(item.reason))) return null;
    const deciding = Array.isArray(item.deciding) ? item.deciding.slice(0, 3)
      .map(ref => factorReference(ref, [a, b])).filter(Boolean) : [];
    const swings = Array.isArray(item.swings) ? item.swings.slice(0, 8).flatMap(swing => {
      const ref = factorReference(swing?.row, [a, b]);
      return ref && ['full', 'fail'].includes(swing.assumed_status) &&
        ['reversed', 'tie', 'breaks_tie'].includes(swing.result)
        ? [{ ...ref, assumedStatus: swing.assumed_status, result: swing.result,
          alternative: readAlternative(swing.hypothetical_score, ref.jobId === a.id ? a : b, ref.effect) }] : [];
    }) : [];
    const v3 = policy === 'draft-2026-11-14-v3' && jobs.every(job => job.score.policyVersion === policy);
    const close = v3 && item.close === true && item.reason === 'lower_bound' && outcome !== 'tie' &&
      [a, b].every(job => job.score.lower > 0 || job.excluded.length || job.disputed.length || job.conflicts.length) &&
      a.score.resolution !== null && b.score.resolution !== null && Number.isFinite(item.margin) && item.margin >= 0 &&
      item.margin <= Math.max(a.score.resolution, b.score.resolution) + 0.0001 &&
      Math.abs(item.margin - Math.abs(a.score.lower - b.score.lower)) < 0.00011;
    const caveats = Array.isArray(item.caveats) ? item.caveats.filter(value =>
      ['different_requirement_lists', 'incomplete_run', 'evidence_not_applied'].includes(value) ||
      (value === 'close_margin' && close)) : [];
    return { a, b, outcome, reason: item.reason, deciding, swings, caveats: Array.from(new Set(caveats)) };
  }

  function readAlternative(value, job, effect) {
    if (!isRecord(value) || ![1, 2].includes(value.rank)) return null;
    try {
      const score = scoreFrom(value);
      return Math.abs(score.lower - job.score.lower - effect) < 0.0002 ? { rank: value.rank, score } : null;
    } catch {
      return null;
    }
  }

  function readLeader(input, jobs, policy, ranking) {
    // Optional v3 projection. Imported prose never becomes an authoritative conclusion.
    // Invalid explanation data must not hide an otherwise readable legacy report.
    if (!isRecord(input) || policy !== 'draft-2026-11-14-v3' || input.policy_version !== policy ||
        !jobs.length || jobs.some(job => job.score.policyVersion !== policy || !job.unitMetadataValid) ||
        !['stable', 'tie', 'close', 'open', 'none_fit'].includes(input.state)) return null;
    const jobList = ids => Array.isArray(ids) && ids.length <= jobs.length &&
      new Set(ids).size === ids.length && ids.every(id => jobs.some(job => job.id === id))
      ? ids.map(id => jobs.find(job => job.id === id)) : null;
    const top = jobList(input.job_ids);
    const rankedTop = jobs.filter(job => job.rank === 1);
    if (!top?.length || top.length !== rankedTop.length || top.some(job => job.rank !== 1)) return null;
    if ((input.state === 'none_fit') !== jobs.every(job => job.score.mandatory === 'violated') ||
        (input.state === 'tie' && top.length < 2) || (input.state === 'stable' && top.length !== 1)) return null;
    if (['stable', 'tie'].includes(input.state) &&
        ((ranking.complete && ranking.recommendation !== 'review_top') || top.some(job =>
          job.score.mandatory === 'clarify' || job.score.lower === 0 || job.excluded.length ||
          job.disputed.length || job.conflicts.length || job.rows.some(row => row.evidence?.state === 'needs_review')))) return null;
    const refs = values => Array.isArray(values) && values.length <= 3
      ? values.map(ref => factorReference(ref, top)) : null;
    const factors = refs(input.factors);
    const limits = refs(input.limits);
    const canChange = Array.isArray(input.can_change) && input.can_change.length <= 3
      ? input.can_change.map(change => {
        const ref = factorReference(change?.row, jobs);
        const matchesKind = ref && ({unknown:ref.row.status === 'unknown', partial:ref.row.status === 'partial',
          disputed:ref.row.evidence?.state === 'needs_review' || ref.row.scoreConflict, marker:ref.row.mandatoryExcluded})[change.kind] === true;
        return matchesKind &&
          change.role === (top.some(job => job.id === ref.jobId) ? 'leader' : 'challenger')
          ? { ...ref, kind: change.kind, role: change.role } : null;
      }) : null;
    const closeTo = jobList(input.close_to);
    const challengers = jobList(input.challengers);
    const unassessed = jobList(input.unassessed);
    if ([factors, limits, canChange, closeTo, challengers, unassessed].some(values =>
      values === null || values.some(value => value === null))) return null;
    if (unassessed.some(job => job.rank === 1 || job.score.lower !== 0 || job.excluded.length || job.disputed.length || job.conflicts.length) ||
        [...challengers, ...closeTo].some(job => job.rank === 1 ||
          (job.score.lower <= 0 && !job.excluded.length && !job.disputed.length && !job.conflicts.length)) ||
        factors.some(ref => ['unknown', 'fail'].includes(ref.row.status) || (ref.row.evidence?.state === 'needs_review' || ref.row.scoreConflict)) ||
        (input.state === 'stable' && (canChange.length || closeTo.length || challengers.length))) return null;
    return {state:input.state, jobs:top, factors, limits, canChange, closeTo, challengers, unassessed};
  }

  function parseReport(source) {
    let report;
    try {
      report = JSON.parse(source.replace(/^\uFEFF/, ''));
    } catch {
      throw new Error('Не удалось прочитать JSON. Выберите report.json из папки запуска.');
    }
    requireShape(isRecord(report) && isText(report.schema_version));
    if (report.schema_version !== '0.1') {
      throw new Error('Эта версия отчёта не поддерживается. Ожидается версия 0.1.');
    }
    requireShape(isRecord(report.ranking) && typeof report.ranking.complete === 'boolean' &&
      isText(report.ranking.recommendation) && isText(report.mode) &&
      isOptionalText(report.model) && isOptionalText(report.demo_scenario));

    const rankedJobs = uniqueIndex(report.ranking.jobs, 'job_id');
    const unprocessed = unprocessedFrom(report, rankedJobs);
    const total = rankedJobs.size + unprocessed.length;
    requireShape(report.ranking.complete === (unprocessed.length === 0) &&
      total > 0 && total <= 20);

    let presentation;
    requireShape(isRecord(report.facts));
    const facts = uniqueIndex(report.facts.items, 'id');
    const factQuotes = Array.from(facts.values(), fact => fact.quote).filter(isText);
    if (report.presentation != null) {
      requireShape(isRecord(report.presentation) && report.presentation.version === '0.1');
      presentation = uniqueIndex(report.presentation.jobs, 'job_id');
      requireShape(presentation.size === rankedJobs.size);
    }
    const resumeDigest = digest(report.safe_resume_sha256);
    const profile = profileFrom(report.profile, factQuotes, resumeDigest);

    const coherentV3 = report.policy_version === 'draft-2026-11-14-v3' &&
      Array.from(rankedJobs.values()).every(job => job.score?.policy_version === report.policy_version);
    const jobs = Array.from(rankedJobs.values(), (job, index) => {
      requireShape(Number.isInteger(job.rank) && job.rank > 0);
      const prepared = presentation?.get(job.job_id);
      requireShape(!presentation || (prepared && prepared.rank === job.rank));
      const excluded = job.score?.excluded_mandatory_ids ?? job.score_review?.excluded_mandatory_ids ?? [];
      requireShape(Array.isArray(excluded) && excluded.every(isText) && new Set(excluded).size === excluded.length);
      const rows = rowsFrom(job, facts, prepared, excluded);
      requireShape(rows.length > 0);
      const disputed = job.score?.disputed_ids ?? [];
      requireShape(Array.isArray(disputed) && new Set(disputed).size === disputed.length &&
        disputed.every(id => rows.some(row => row.id === id)));
      // V3 metadata is optional: it cannot reinterpret a legacy report or make it unreadable.
      const sourceUnits = coherentV3 ? job.score?.units : null;
      const normalizeUnitText = text => typeof text === 'string'
        ? text.toLowerCase().replace(/\s+/gu, ' ').replace(/^[ .;,:—–•*\-]+|[ .;,:—–•*\-]+$/gu, '') : null;
      const signature = id => {
        const req = job.requirements.items.find(item => item.id === id);
        return JSON.stringify([normalizeUnitText(req?.text), normalizeUnitText(req?.quote),
          Boolean(req?.mandatory_quote) && !excluded.includes(id), excluded.includes(id)]);
      };
      let units = [], conflicts = [], unitMetadataValid = false;
      if (Array.isArray(sourceUnits) && sourceUnits.length <= rows.length && sourceUnits.every(unit => {
          if (!Array.isArray(unit?.ids) || !unit.ids.length ||
              !unit.ids.every(id => rows.some(row => row.id === id))) return false;
          if (unit.ids.some(id => signature(id) !== signature(unit.ids[0]))) return false;
          const states = new Set(unit.ids.map(id => disputed.includes(id) ? 'disputed' : rows.find(row => row.id === id).status));
          states.delete('unknown');
          const state = !states.size ? 'unknown' : states.size === 1 ? Array.from(states)[0] : 'conflict';
          return unit.state === state;
        })) {
        const ids = sourceUnits.flatMap(unit => unit.ids);
        if (ids.length === rows.length && new Set(ids).size === ids.length) {
          units = sourceUnits.map(unit => unit.ids.slice());
          const expected = sourceUnits.filter(unit => unit.state === 'conflict').flatMap(unit => unit.ids);
          const declared = job.score.conflict_ids;
          if (Array.isArray(declared) && new Set(declared).size === declared.length &&
              declared.length === expected.length && declared.every(id => expected.includes(id))) {
            conflicts = expected; unitMetadataValid = true;
          }
        }
      }
      for (const row of rows) row.scoreConflict = conflicts.includes(row.id);
      const sourceDigest = digest(job.safe_source_sha256);
      return {
        id: job.job_id, title: vacancyTitle(job.job_id, index), rank: job.rank,
        score: scoreFrom(job.score), rows, excluded, disputed, conflicts, units, unitMetadataValid,
        requirementsReview: requirementReviewFrom(job),
        sourceDigest, policyDigest: digest(job.score.policy_sha256),
        conditions: conditionsFrom(job.conditions, job.job_id, resumeDigest, sourceDigest, factQuotes)
      };
    });

    const leader = readLeader(report.leader, jobs, report.policy_version, report.ranking);
    return {
      jobs, comparisons: Array.isArray(report.comparisons)
        ? report.comparisons.slice(0, 19).map(item => readComparison(item, jobs, report.policy_version)).filter(Boolean) : [],
      policyVersion: report.policy_version, unprocessed, processed: jobs.length, total,
      leader,
      complete: report.ranking.complete, recommendation: report.ranking.recommendation,
      requirementsConfirmed: report.ranking.complete && jobs.every(job => job.requirementsReview === 'confirmed'),
      runId: typeof report.run_id === 'string' && /^[0-9a-f]{32}$/.test(report.run_id) ? report.run_id : null,
      revision: Number.isSafeInteger(report.revision) && report.revision > 0 ? report.revision : null,
      finalAllowed: false,
      schemaVersion: report.schema_version,
      mode: report.mode, model: versionLabel(report.model), scenario: report.demo_scenario || null,
      resumeDigest, modelDigest: digest(report.model_sha256),
      profile, reviewItems: readReviewItems(report.review_queue, rankedJobs, leader), handoff: readHandoff(report.handoff, rankedJobs),
      privacyWarning: report.privacy?.professional_information_may_be_hidden === true
    };
  }

  function filterRows(rows, filter, query) {
    const search = query.trim().toLocaleLowerCase('ru');
    return rows.filter(row => {
      const matchesFilter = filter === 'all' || row.status === filter || (filter === 'review' && !row.verified);
      return matchesFilter && row.label.toLocaleLowerCase('ru').includes(search);
    });
  }

  function statusCounts(rows) {
    const counts = { full: 0, partial: 0, unknown: 0, fail: 0 };
    for (const row of rows) counts[row.status]++;
    return counts;
  }

  function describeDashboard(report) {
    return report.jobs.map(job => ({
      title: job.title,
      rank: job.rank,
      lower: job.score.lower,
      upper: job.score.upper,
      coverage: job.score.coverage,
      counts: statusCounts(job.rows),
      total: job.rows.length
    }));
  }

  const api = {
    MAX_REPORT_BYTES, parseReport, filterRows, statusCounts, describeDashboard, describeRun, describeFit, scoreRange, assessments,
    mandatoryStates, evidenceLabel, evidenceNeedsReview, mandatoryLabel, mandatoryNeedsReview, requirementReviewLabel,
    readComparison
  };
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.NanimaiReport = api;
  }
})(globalThis);
