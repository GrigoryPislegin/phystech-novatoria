(function (root) {
  'use strict';

  const MAX_REPORT_BYTES = 25_000_000;
  const MAX_REQUIREMENTS = 80;
  const statuses = ['full', 'partial', 'unknown', 'fail'];

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
      mandatory: value.mandatory, policyVersion: isText(value.policy_version) ? value.policy_version : null
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
    return Array.from(ids, id => ({ id, reason: reasons.get(id)?.reason || null }));
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

    const jobs = Array.from(rankedJobs.values(), job => {
      requireShape(Number.isInteger(job.rank) && job.rank > 0);
      const prepared = presentation?.get(job.job_id);
      requireShape(!presentation || (prepared && prepared.rank === job.rank));
      const excluded = job.score_review?.excluded_mandatory_ids ?? [];
      requireShape(Array.isArray(excluded) && excluded.every(isText) && new Set(excluded).size === excluded.length);
      const rows = rowsFrom(job, facts, prepared, excluded);
      requireShape(rows.length > 0);
      // Report 0.1 keeps file labels in a separate private manifest. Display the stable report ID.
      return { id: job.job_id, title: job.job_id, rank: job.rank, score: scoreFrom(job.score), rows, excluded };
    });

    return {
      jobs, unprocessed, processed: jobs.length, total,
      complete: report.ranking.complete, recommendation: report.ranking.recommendation,
      requirementsConfirmed: false, finalAllowed: false,
      mode: report.mode, model: report.model || null, scenario: report.demo_scenario || null,
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

  const api = { MAX_REPORT_BYTES, parseReport, filterRows, statusCounts };
  if (typeof module === 'object' && module.exports) {
    module.exports = api;
  } else {
    root.NanimaiReport = api;
  }
})(globalThis);
