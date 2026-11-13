(() => {
  'use strict';

  const {
    MAX_REPORT_BYTES, parseReport, filterRows, statusCounts, describeRun, describeFit, scoreRange,
    assessments, mandatoryStates, evidenceLabel, mandatoryLabel, mandatoryNeedsReview, requirementReviewLabel
  } = window.NanimaiReport;
  const { renderManagerReport } = window.NanimaiManagerReport;
  const byId = id => document.getElementById(id);
  const input = byId('report-file');
  const search = byId('requirement-search');
  const managerButton = byId('manager-report');
  const filterButtons = Array.from(byId('row-filters').querySelectorAll('button'));
  const numberFormat = new Intl.NumberFormat('ru', { maximumFractionDigits: 4 });

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
    return element('span', 'tag tag-' + tone, label);
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
    setText('run-count', report.processed + ' / ' + report.total);
    setText('run-progress', report.complete ? 'Все вакансии оценены' : 'Обработка завершилась досрочно');
    setText('run-review', report.requirementsConfirmed ? 'Состав подтверждён' : 'Состав не подтверждён');
    setText('run-review-detail', report.finalAllowed ? 'Подтверждение записано в отчёте' : 'Оценки и цитаты требуют проверки');
    byId('privacy-note').hidden = !report.privacyWarning;

    const note = recommendation;
    byId('run-note').hidden = !note;
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
    const knownPolicy = report.jobs.length > 0 &&
      report.jobs.every(job => job.score.policyVersion === 'draft-2026-11-12-v1');
    setText('ranking-method', knownPolicy
      ? 'Сначала идут вакансии без выявленного нарушения обязательных требований. Внутри группы порядок определяется нижней границей L. При равном балле вакансии делят место.'
      : 'Места и порядок взяты из отчёта.');
    const list = byId('job-list');
    list.replaceChildren();
    for (const job of report.jobs) {
      const counts = statusCounts(job.rows);
      const item = element('li');
      const button = element('button', 'job-option');
      button.type = 'button';
      button.dataset.jobId = job.id;
      button.setAttribute('aria-controls', 'job-detail');
      const rank = element('span', 'job-rank numeric', job.rank);
      rank.setAttribute('aria-label', 'Место ' + job.rank);
      const content = element('span', 'job-option-content');
      const top = element('span', 'job-option-top');
      top.append(element('span', 'job-option-name', job.title),
        element('span', 'job-option-score numeric', scoreRange(job.score)));
      content.append(top, element('span', 'job-option-meta', mandatoryStates[job.score.mandatory][0]),
        element('span', 'job-option-review',
          'Спорных: ' + job.rows.filter(row => ['partial', 'fail'].includes(row.status) ||
            ['needs_review', 'invalid'].includes(row.evidence?.state) || mandatoryNeedsReview(row)).length +
          ' · Не указано: ' + counts.unknown));
      button.append(rank, content);
      button.addEventListener('click', () => selectJob(job));
      item.append(button);
      list.append(item);
    }
  }

  function selectJob(job) {
    activeJob = job;
    managerButton.hidden = !job;
    managerButton.disabled = !job;
    filter = 'all';
    search.value = '';
    updateFilters();

    for (const button of byId('job-list').querySelectorAll('button')) {
      if (button.dataset.jobId === job?.id) button.setAttribute('aria-current', 'true');
      else button.removeAttribute('aria-current');
    }
    byId('job-detail').hidden = !job;
    byId('empty-detail').hidden = Boolean(job);
    if (!job) {
      byId('requirement-rows').replaceChildren();
      return;
    }

    const sharedPlace = report.jobs.some(other => other !== job && other.rank === job.rank);
    const place = report.complete ? 'Место ' : 'Предварительное место ';
    setText('job-place', place + job.rank + (sharedPlace ? ' · Делит место' : ''));
    setText('job-title', job.title);
    setText('job-score-range', scoreRange(job.score));
    const [mandatory, tone] = mandatoryStates[job.score.mandatory];
    const mandatoryLabel = byId('job-mandatory');
    mandatoryLabel.textContent = mandatory;
    mandatoryLabel.className = 'tag tag-' + tone;
    setText('job-coverage', 'Доля известных данных ' + numberFormat.format(job.score.coverage) + '%');
    setText('job-requirements-review', requirementReviewLabel(job.requirementsReview));
    setText('job-policy', job.score.policyVersion ? 'Методика ' + job.score.policyVersion : '');
    const scoreReview = byId('job-score-review');
    scoreReview.hidden = job.excluded.length === 0;
    scoreReview.textContent = 'Для ' + job.excluded.length +
      ' требований привязка обязательности требует проверки. Их учли с обычным весом 1.';
    const fit = describeFit(report, job);
    setText('job-fit', 'Предварительный вывод · ' + fit.label);
    const conditions = byId('job-conditions');
    const conflicts = job.conditions.items.filter(item => item.state === 'conflict');
    conditions.hidden = !conflicts.length;
    conditions.textContent = conflicts.length
      ? 'Возможный конфликт для HR · ' + conflicts.map(item => item.label).join(', ') + '. Цитаты в отчёте для менеджера.'
      : '';
    renderRows();
  }

  function quoteCard(title, quotes, emptyText) {
    const card = element('div', 'evidence-card');
    card.append(element('h4', null, title));
    if (!quotes.length) card.append(element('p', null, emptyText));
    for (const quote of quotes) card.append(element('blockquote', null, quote));
    return card;
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
    link.download = 'nanimai-manager-report.html';
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
    report = next;
    renderSummary();
    renderRanking();
    selectJob(report.jobs[0] || null);
    byId('welcome').hidden = true;
    byId('report-workspace').hidden = false;
    setFileStatus('Открыт ' + file.name);
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
