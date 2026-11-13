(() => {
  'use strict';

  const {
    MAX_REPORT_BYTES, parseReport, filterRows, describeDashboard, describeRun, describeFit, scoreRange,
    assessments, mandatoryStates, evidenceLabel, mandatoryLabel, requirementReviewLabel
  } = window.NanimaiReport;
  const { renderManagerReport } = window.NanimaiManagerReport;
  const byId = id => document.getElementById(id);
  const input = byId('report-file');
  const search = byId('requirement-search');
  const managerButton = byId('manager-report');
  const views = Array.from(byId('report-views').querySelectorAll('button'));
  const filterButtons = Array.from(byId('row-filters').querySelectorAll('button'));
  const numberFormat = new Intl.NumberFormat('ru', { maximumFractionDigits: 4 });

  const indicators = { ok: '✓', warning: '◐', neutral: '–', danger: '×' };
  const conditionStates = {
    conflict: ['Возможный конфликт', 'warning'], compatible: ['Совпадают по отчёту', 'ok'],
    unknown: ['Нужно уточнить', 'neutral'], invalid: ['Не удалось проверить', 'danger']
  };
  const skipReasons = {
    evaluation_failed: 'Сбой оценки', requirements_failed: 'Сбой извлечения требований',
    facts_failed: 'Сбой извлечения фактов', model_invalid: 'Некорректный ответ модели',
    stopped_after_error: 'Обработка остановлена после сбоя', cancelled: 'Запуск отменён',
    deadline_exceeded: 'Истекло время запуска', budget_limit: 'Достигнут лимит бюджета',
    privacy_residual_findings: 'Обработка остановлена проверкой данных'
  };

  let report = null;
  let activeJob = null;
  let filter = 'all';
  let loadSequence = 0;

  function setText(id, value) {
    byId(id).textContent = value;
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function tag(label, tone) {
    const badge = element('span', 'tag tag-' + tone);
    const icon = element('span', 'status-icon', indicators[tone]);
    icon.setAttribute('aria-hidden', 'true');
    badge.append(icon, element('span', null, label));
    return badge;
  }

  function setFileStatus(text, error = false) {
    const node = byId('file-status');
    node.hidden = !text;
    node.classList.toggle('error', error);
    node.textContent = text;
  }

  function renderSummary() {
    const { mode, modeDetail, scenario, recommendation } = describeRun(report);
    setText('run-mode', mode);
    setText('run-mode-detail', [modeDetail, scenario, report.model].filter(Boolean).join(' · '));
    setText('run-count', report.processed + ' из ' + report.total);
    setText('run-progress', report.complete ? 'Все вакансии оценены' : 'Обработка завершилась досрочно');
    setText('run-review', report.requirementsConfirmed ? 'Состав подтверждён' : 'Состав не подтверждён');
    setText('run-review-detail', report.finalAllowed ? 'Подтверждение записано в отчёте' : 'Оценки и цитаты требуют проверки');
    byId('privacy-note').hidden = !report.privacyWarning;

    const note = recommendation;
    byId('run-note').hidden = !note;
    byId('run-note').dataset.tone = report.complete ? 'info' : 'warning';
    setText('run-note-title', note?.[0] || '');
    setText('run-note-text', note?.[1] || '');
    const skipped = byId('skipped-jobs');
    skipped.hidden = report.unprocessed.length === 0;
    skipped.replaceChildren(...report.unprocessed.map(job => {
      const reason = Object.hasOwn(skipReasons, job.reason) ? skipReasons[job.reason] : 'Вакансия не оценена';
      return element('li', null, job.title + ' — ' + reason);
    }));
  }

  function renderRanking() {
    setText('ranking-count', report.jobs.length);
    byId('empty-ranking').hidden = report.jobs.length > 0;
    byId('score-help').hidden = report.jobs.length === 0;
    const knownPolicy = report.jobs.length > 0 &&
      report.jobs.every(job => job.score.policyVersion === 'draft-2026-11-12-v1');
    setText('ranking-method', knownPolicy
      ? 'Сначала идут вакансии без выявленного нарушения обязательных требований. Внутри группы порядок определяется нижней границей L. При равном балле вакансии делят место.'
      : 'Места и порядок взяты из отчёта.');
    const list = byId('job-list');
    list.replaceChildren();
    report.jobs.forEach(job => {
      const item = element('li', 'job-card');
      const rank = element('p', 'eyeline numeric', (report.complete ? 'Место ' : 'Предварительное место ') + job.rank);
      const heading = element('h2', 'job-option-name', job.title);
      const score = element('p', 'job-option-score numeric');
      score.append(element('strong', null, scoreRange(job.score)), element('span', null, 'Диапазон L–H'));
      const coverage = element('p', 'support', 'Известные данные · ' + numberFormat.format(job.score.coverage) + '%');
      const button = element('button', 'job-option button button-secondary', 'Открыть');
      button.type = 'button';
      button.setAttribute('aria-label', 'Открыть вакансию ' + job.title);
      button.setAttribute('aria-controls', 'job-detail');
      button.addEventListener('click', () => {
        selectJob(job);
        byId('job-title').focus();
      });
      item.append(rank, heading, tag(...mandatoryStates[job.score.mandatory]), score, coverage, button);
      list.append(item);
    });
  }

  function selectJob(job) {
    activeJob = job;
    managerButton.hidden = !job;
    managerButton.disabled = !job;
    filter = 'all';
    search.value = '';
    updateFilters();

    const buttons = Array.from(byId('job-list').querySelectorAll('button'));
    buttons.forEach((button, index) => {
      const current = report.jobs[index] === job;
      button.parentElement.toggleAttribute('data-current', current);
      if (current) button.setAttribute('aria-current', 'true');
      else button.removeAttribute('aria-current');
    });
    byId('job-detail').hidden = !job;
    if (!job) {
      byId('requirement-rows').replaceChildren();
      return;
    }

    const sharedPlace = report.jobs.some(other => other !== job && other.rank === job.rank);
    const place = report.complete ? 'Место ' : 'Предварительное место ';
    setText('job-place', place + job.rank + (sharedPlace ? ' · Делит место' : ''));
    setText('job-title', 'Вакансия ' + job.title);
    const mandatory = tag(...mandatoryStates[job.score.mandatory]);
    const mandatoryNode = byId('job-mandatory');
    mandatoryNode.className = mandatory.className;
    mandatoryNode.replaceChildren(...mandatory.childNodes);
    setText('job-coverage', 'Доля известных данных ' + numberFormat.format(job.score.coverage) + '%');
    setText('job-requirements-review', requirementReviewLabel(job.requirementsReview));
    const scoreReview = byId('job-score-review');
    scoreReview.hidden = job.excluded.length === 0;
    scoreReview.textContent = 'Для ' + job.excluded.length +
      ' требований привязка обязательности требует проверки. Балл приведён по отчёту.';
    const fit = describeFit(report, job);
    setText('job-fit', fit.label);
    setText('job-fit-notes', fit.notes.join(' '));
    byId('job-fit-notes').hidden = !fit.notes.length;
    const conditions = byId('job-conditions');
    const conflicts = job.conditions.items.filter(item => item.state === 'conflict');
    conditions.hidden = !conflicts.length;
    conditions.textContent = conflicts.length
      ? 'Возможный конфликт для HR · ' + conflicts.map(item => item.label).join(', ')
      : '';
    renderConditions(job.conditions);
    renderRows();
  }

  function quoteCard(title, quotes, emptyText) {
    const card = element('div', 'evidence-card');
    card.append(element('h4', null, title));
    if (!quotes.length) card.append(element('p', null, emptyText));
    for (const quote of quotes) card.append(element('blockquote', null, quote));
    return card;
  }

  function sourceText(source) {
    return source.heading ? source.heading + '\n' + source.sentence : source.sentence;
  }

  function renderConditions(conditions) {
    const messages = {
      missing: 'Условия не сравнивались.',
      invalid: 'Часть условий не удалось проверить.',
      available: conditions.items.length ? 'Решение по условиям принимает HR.' : 'В отчёте нет условий для сравнения.'
    };
    setText('conditions-summary', messages[conditions.state]);
    byId('condition-list').replaceChildren(...conditions.items.map(item => {
      const details = element('details', 'source-disclosure');
      const summary = element('summary', 'source-heading');
      summary.append(element('span', null, item.label), tag(...conditionStates[item.state]));
      details.append(summary);
      const quotes = element('div', 'evidence-grid source-body');
      for (const [label, source, unresolved] of [
        ['Фрагмент вакансии', item.vacancy, item.vacancyUnresolved],
        ['Фрагмент резюме', item.cv, item.cvUnresolved]
      ]) {
        const missing = item.state === 'invalid' || unresolved ? 'Цитату не удалось привязать.' : 'Сведения не указаны.';
        quotes.append(quoteCard(label, source ? [sourceText(source)] : [], missing));
      }
      details.append(quotes);
      if (item.needsReview) details.append(element('p', 'source-note support', 'Нужна ручная сверка.'));
      return details;
    }));
  }

  function renderProfile() {
    const { profile } = report;
    const list = byId('profile-list');
    list.replaceChildren();
    const messages = {
      missing: 'Профиль не извлечён.',
      invalid: 'Не удалось проверить профиль.',
      needs_review: 'Часть сведений профиля требует сверки с резюме.',
      structure_ok: 'Фрагменты резюме, на которых основан профиль.'
    };
    setText('profile-summary', messages[profile.state]);
    if (!profile.claims) return;
    const groupings = [
      ['Специализация и опыт', 'summary['],
      ['Последняя роль, сфера и период', 'last_position.'],
      ['Стек в контексте резюме', 'stack['],
      ['Достижения и результаты', 'achievements[']
    ];
    for (const [title, prefix] of groupings) {
      const quotes = new Set();
      for (const [path, sources] of profile.claims) {
        if (path.startsWith(prefix)) sources.forEach(source => quotes.add(sourceText(source)));
      }
      if (!quotes.size) continue;
      const details = element('details', 'source-disclosure');
      details.append(element('summary', 'source-heading', title),
        quoteCard('Фрагменты резюме', Array.from(quotes)));
      list.append(details);
    }
    list.firstElementChild.open = true;
  }

  function renderOverview() {
    const list = byId('overview-list');
    const entries = describeDashboard(report);
    const percent = value => numberFormat.format(value) + '%';
    list.replaceChildren();
    if (!entries.length) {
      list.append(element('p', 'empty-panel', 'В этом запуске нет оценённых вакансий.'));
      return;
    }
    entries.forEach((job, index) => {
      const row = element('article', 'overview-row');
      const heading = element('header', 'overview-heading');
      const button = element('button', 'button button-secondary', 'Открыть');
      button.type = 'button';
      button.setAttribute('aria-label', 'Открыть вакансию ' + job.title);
      button.addEventListener('click', () => {
        selectView('ranking');
        selectJob(report.jobs[index]);
        byId('job-title').focus();
      });
      const place = report.complete ? 'Место ' : 'Предварительное место ';
      heading.append(element('h3', null, job.title), element('span', 'support', place + job.rank), button);

      const bounds = element('div', 'overview-metric');
      bounds.append(element('p', null, 'Диапазон L–H'),
        element('strong', 'numeric', scoreRange(job)));
      // Native meters take numeric values under the offline page's strict CSP.
      // The two meters share a baseline and the upper bound has the lighter fill.
      const interval = element('div', 'interval');
      interval.setAttribute('aria-hidden', 'true');
      interval.append(meter(job.upper, 'high'), meter(job.lower, 'low'));
      bounds.append(interval);

      const coverage = element('div', 'overview-metric');
      coverage.append(element('p', null, 'Доля известных данных'),
        element('strong', 'numeric', percent(job.coverage)));
      const coverageTrack = meter(job.coverage, 'coverage');
      coverageTrack.setAttribute('aria-hidden', 'true');
      coverage.append(coverageTrack);

      const counts = element('ul', 'status-counts');
      for (const [status, count] of Object.entries(job.counts)) {
        const item = element('li');
        item.append(tag(...assessments[status]), element('strong', 'numeric', count));
        counts.append(item);
      }
      row.append(heading, bounds, coverage, counts);
      list.append(row);
    });
  }

  function meter(value, variant) {
    const elementMeter = element('meter', 'chart-track ' + variant);
    elementMeter.min = 0;
    elementMeter.max = 100;
    elementMeter.value = value;
    return elementMeter;
  }

  function selectView(name) {
    for (const button of views) {
      const selected = button.dataset.view === name;
      byId(button.getAttribute('aria-controls')).hidden = !selected;
      button.setAttribute('aria-pressed', String(selected));
    }
  }

  function addNote(list, title, text) {
    if (!text) return;
    const note = element('div');
    note.append(element('dt', null, title), element('dd', null, text));
    list.append(note);
  }

  function makeRow(row, index) {
    const main = element('tr', 'requirement-row');
    const heading = element('th');
    heading.scope = 'row';
    const toggle = element('button', 'row-toggle');
    toggle.type = 'button';
    toggle.setAttribute('aria-expanded', 'false');
    const arrow = element('span', 'chevron', '›');
    arrow.setAttribute('aria-hidden', 'true');
    toggle.append(arrow, element('span', 'row-name', row.label));
    heading.append(toggle, element('span', 'row-subtitle', mandatoryLabel(row)));

    const assessment = element('td');
    assessment.append(tag(...assessments[row.status]),
      element('span', 'row-subtitle', evidenceLabel(row)));
    const resume = element('td');
    resume.append(element('span', 'quote-preview', row.resumeQuotes[0] || 'Цитата не приведена'));
    main.append(heading, assessment, resume);

    const detail = element('tr', 'evidence-row');
    detail.id = 'evidence-' + index;
    detail.hidden = true;
    toggle.setAttribute('aria-controls', detail.id);
    const cell = element('td');
    cell.colSpan = 3;
    const quotes = element('div', 'evidence-grid');
    quotes.append(quoteCard('Фрагмент вакансии', [row.requirementQuote]),
      quoteCard('Фрагменты резюме', row.resumeQuotes, 'Подтверждающий фрагмент в отчёте отсутствует.'));
    const notes = element('dl', 'row-notes');
    if (row.mandatoryQuote && row.mandatoryQuote !== row.requirementQuote) {
      addNote(notes, 'Основание обязательности · требует проверки', row.mandatoryQuote);
    }
    for (const check of [row.evidence, row.mandatoryCheck]) {
      for (const reason of check?.reasons || []) {
        addNote(notes, 'Замечание из отчёта', [reason.message, reason.context].filter(Boolean).join('\n'));
      }
    }
    addNote(notes, row.commentFromModel ? 'Комментарий модели · не проверен' : 'Пояснение к оценке', row.comment);
    addNote(notes, row.commentFromModel ? 'Вопрос модели · не проверен' : 'Вопрос кандидату · черновик', row.question);
    cell.append(quotes);
    if (notes.childElementCount) cell.append(notes);
    detail.append(cell);

    toggle.addEventListener('click', () => {
      const open = detail.hidden;
      detail.hidden = !open;
      main.toggleAttribute('data-open', open);
      toggle.setAttribute('aria-expanded', String(open));
      arrow.textContent = open ? '⌄' : '›';
    });
    return [main, detail];
  }

  function renderRows() {
    if (!activeJob) return;
    const rows = filterRows(activeJob.rows, filter, search.value);
    byId('requirement-rows').replaceChildren(...rows.flatMap(makeRow));
    byId('empty-rows').hidden = rows.length > 0;
    setText('result-count', 'Показано требований: ' + rows.length + ' из ' + activeJob.rows.length);
  }

  function updateFilters() {
    for (const button of filterButtons) {
      button.setAttribute('aria-pressed', String(button.dataset.filter === filter));
    }
  }

  function downloadManagerReport() {
    if (!activeJob) return;
    const html = renderManagerReport(report, activeJob.id);
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }));
    const link = element('a');
    link.href = url;
    link.download = 'manager-report.html';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function loadFile(file) {
    const sequence = ++loadSequence;
    const prefix = report ? 'Сейчас открыт предыдущий отчёт. ' : '';
    setFileStatus('Читаем отчёт…');
    if (file.size > MAX_REPORT_BYTES) {
      setFileStatus(prefix + 'Отчёт больше 25 МБ. Выберите файл меньшего размера.', true);
      return;
    }
    let source;
    try {
      source = await file.text();
    } catch {
      if (sequence === loadSequence) setFileStatus(prefix + 'Файл недоступен. Выберите его ещё раз.', true);
      return;
    }
    if (sequence !== loadSequence) return;

    let next;
    try {
      next = parseReport(source);
    } catch (error) {
      setFileStatus(prefix + error.message, true);
      return;
    }
    openReport(next, 'Открыт ' + file.name);
  }

  function openReport(next, label) {
    report = next;
    renderSummary();
    renderRanking();
    selectJob(report.jobs[0] || null);
    renderOverview();
    renderProfile();
    selectView('ranking');
    byId('welcome').hidden = true;
    byId('report-workspace').hidden = false;
    setFileStatus(label);
  }

  byId('open-demo').addEventListener('click', () => {
    ++loadSequence;
    try {
      openReport(parseReport(window.RecruiterDemoReport), 'Открыт синтетический пример');
    } catch (error) {
      setFileStatus(error.message, true);
    }
  });
  for (const button of views) {
    button.addEventListener('click', () => selectView(button.dataset.view));
  }
  input.addEventListener('change', () => {
    const [file] = input.files;
    input.value = '';
    if (file) loadFile(file);
  });
  managerButton.addEventListener('click', downloadManagerReport);
  search.addEventListener('input', renderRows);
  for (const button of filterButtons) {
    button.addEventListener('click', () => {
      filter = button.dataset.filter;
      updateFilters();
      renderRows();
    });
  }
})();
