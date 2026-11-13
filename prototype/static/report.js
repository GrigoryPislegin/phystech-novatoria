(function (root) {
  'use strict';

  const MAX_REPORT_BYTES = 25_000_000;
  const MAX_REQUIREMENTS = 80;
  const statuses = ['full', 'partial', 'unknown', 'fail'];
  const modes = {
    synthetic_replay_NOT_model_output: ['Синтетический replay', 'Заранее подготовленные ответы'],
    live_synthetic: ['Анализ на синтетике', 'Ответы модели'],
    live_local_privacy: ['Защищённый анализ', 'Ответы модели'],
    live_certum: ['Защищённый анализ', 'Ответы модели']
  };
  const scenarios = { success: 'Подходящая вакансия', disputed: 'Спорный случай' };
  const recommendations = {
    review_top: ['С чего начать', 'Проверьте цитаты по вакансиям на первом месте.'],
    clarify: ['Нужны уточнения', 'Перед выбором вакансии уточните спорные условия у кандидата.'],
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
  const numberFormat = new Intl.NumberFormat('ru', { maximumFractionDigits: 4 });

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
    return row.mandatoryExcluded || ['needs_review', 'invalid'].includes(row.mandatoryCheck?.state);
  }

  function mandatoryLabel(row) {
    if (mandatoryNeedsReview(row)) {
      return 'Обязательность требует проверки';
    }
    return row.mandatoryQuote ? 'Обязательное по отчёту' : 'Обязательность не указана';
  }

  function evidenceLabel(row) {
    return evidenceLabels[row.evidence?.state] || 'Доказательство требует проверки';
  }

  function requireShape(condition) {
    if (!condition) throw new Error('В файле нет корректной структуры отчёта Nanimai.');
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
      mandatory: value.mandatory, policyVersion: versionLabel(value.policy_version)
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
    if (report.presentation != null) {
      requireShape(isRecord(report.presentation) && report.presentation.version === '0.1');
      presentation = uniqueIndex(report.presentation.jobs, 'job_id');
      requireShape(presentation.size === rankedJobs.size);
    }

    const jobs = Array.from(rankedJobs.values(), (job, index) => {
      requireShape(Number.isInteger(job.rank) && job.rank > 0);
      const prepared = presentation?.get(job.job_id);
      requireShape(!presentation || (prepared && prepared.rank === job.rank));
      const excluded = job.score_review?.excluded_mandatory_ids ?? [];
      requireShape(Array.isArray(excluded) && excluded.every(isText) && new Set(excluded).size === excluded.length);
      const rows = rowsFrom(job, facts, prepared, excluded);
      requireShape(rows.length > 0);
      return {
        id: job.job_id, title: vacancyTitle(job.job_id, index), rank: job.rank,
        score: scoreFrom(job.score), rows, excluded,
        requirementsReview: requirementReviewFrom(job),
        sourceDigest: digest(job.safe_source_sha256), policyDigest: digest(job.score.policy_sha256)
      };
    });

    return {
      jobs, unprocessed, processed: jobs.length, total,
      complete: report.ranking.complete, recommendation: report.ranking.recommendation,
      requirementsConfirmed: report.ranking.complete && jobs.every(job => job.requirementsReview === 'confirmed'),
      finalAllowed: false,
      schemaVersion: report.schema_version,
      mode: report.mode, model: versionLabel(report.model), scenario: report.demo_scenario || null,
      resumeDigest: digest(report.safe_resume_sha256), modelDigest: digest(report.model_sha256),
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

  const api = {
    MAX_REPORT_BYTES, parseReport, filterRows, statusCounts, describeRun, scoreRange, assessments,
    mandatoryStates, evidenceLabel, mandatoryLabel, mandatoryNeedsReview, requirementReviewLabel
  };
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.NanimaiReport = api;
  }
})(globalThis);
