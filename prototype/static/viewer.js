(() => {
  'use strict';

  const { MAX_REPORT_BYTES, parseReport, filterRows, statusCounts } = window.NanimaiReport;
  const byId = id => document.getElementById(id);
  const input = byId('report-file');
  const search = byId('requirement-search');
  const filterButtons = Array.from(byId('row-filters').querySelectorAll('button'));
  const numberFormat = new Intl.NumberFormat('ru', { maximumFractionDigits: 4 });

  const assessments = {
    full: ['Полное соответствие', 'ok'],
    partial: ['Частичное соответствие', 'warning'],
    unknown: ['Не указано', 'neutral'],
    fail: ['Несоответствие', 'danger']
  };
  const mandatoryStates = {
    confirmed: ['Обязательные условия покрыты по оценке', 'ok'],
    clarify: ['Обязательные условия требуют уточнения', 'warning'],
    violated: ['Выявлено обязательное несоответствие', 'danger'],
    not_set: ['Обязательные условия не выделены', 'neutral']
  };
  const modes = {
    synthetic_replay_NOT_model_output: ['Синтетический replay', 'Заранее подготовленные ответы'],
    live_synthetic: ['Анализ на синтетике', 'Ответы модели'],
    live_certum: ['Защищённый анализ', 'Ответы модели']
  };
  const scenarioLabels = { success: 'Подходящая вакансия', disputed: 'Спорный случай' };
  const recommendations = {
    review_top: ['С чего начать', 'Проверьте цитаты по вакансиям на первом месте.'],
    clarify: ['Нужны уточнения', 'Перед выбором вакансии уточните спорные условия у кандидата.'],
    review_none_fit: ['Нужна проверка несоответствий', 'Проверьте обязательность требований и основания по каждой вакансии.']
  };
  const skipReasons = {
    evaluation_failed: 'Сбой оценки', requirements_failed: 'Сбой извлечения требований',
    facts_failed: 'Сбой извлечения фактов', model_invalid: 'Некорректный ответ модели',
    stopped_after_error: 'Обработка остановлена после сбоя', cancelled: 'Запуск отменён',
    deadline_exceeded: 'Истекло время запуска', budget_limit: 'Достигнут лимит бюджета',
    privacy_residual_findings: 'Обработка остановлена проверкой данных'
  };
  const evidenceLabels = {
    structure_ok: 'Структура сверена · смысл требует проверки',
    no_evidence: 'Цитата в резюме не указана',
    needs_review: 'Доказательство требует проверки',
    invalid: 'Отчёт отмечает ошибку в доказательстве'
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

  function scoreRange(score) {
    const low = numberFormat.format(score.lower);
    const high = numberFormat.format(score.upper);
    return (score.lower === score.upper ? low : low + '–' + high) + '%';
  }

  function setFileStatus(text, error = false) {
    const node = byId('file-status');
    node.hidden = !text;
    node.classList.toggle('error', error);
    node.textContent = text;
  }

  function renderSummary() {
    const [mode, detail] = Object.hasOwn(modes, report.mode)
      ? modes[report.mode] : ['Неизвестный режим', 'Тип запуска не распознан'];
    setText('run-mode', mode);
    const scenario = Object.hasOwn(scenarioLabels, report.scenario) ? scenarioLabels[report.scenario] : null;
    setText('run-mode-detail', [detail, scenario, report.model].filter(Boolean).join(' · '));
    setText('run-count', report.processed + ' / ' + report.total);
    setText('run-progress', report.complete ? 'Все вакансии оценены' : 'Обработка завершилась досрочно');
    setText('run-review', report.requirementsConfirmed ? 'Состав подтверждён' : 'Состав не подтверждён');
    setText('run-review-detail', report.finalAllowed ? 'Подтверждение записано в отчёте' : 'Оценки и цитаты требуют проверки');
    byId('privacy-note').hidden = !report.privacyWarning;

    const note = report.complete
      ? (Object.hasOwn(recommendations, report.recommendation) ? recommendations[report.recommendation] : null)
      : ['Неполный рейтинг', 'Места предварительные. Ниже показаны только оценённые вакансии.'];
    byId('run-note').hidden = !note;
    setText('run-note-title', note?.[0] || '');
    setText('run-note-text', note?.[1] || '');
    const skipped = byId('skipped-jobs');
    skipped.hidden = report.unprocessed.length === 0;
    skipped.replaceChildren(...report.unprocessed.map(job => {
      const reason = Object.hasOwn(skipReasons, job.reason) ? skipReasons[job.reason] : 'Вакансия не оценена';
      return element('li', null, job.id + ' — ' + reason);
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
            row.evidence?.state === 'needs_review' || row.mandatoryExcluded).length +
          ' · Не указано: ' + counts.unknown));
      button.append(rank, content);
      button.addEventListener('click', () => selectJob(job));
      item.append(button);
      list.append(item);
    }
  }

  function selectJob(job) {
    activeJob = job;
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
    setText('job-policy', job.score.policyVersion ? 'Методика ' + job.score.policyVersion : '');
    const scoreReview = byId('job-score-review');
    scoreReview.hidden = job.excluded.length === 0;
    scoreReview.textContent = 'Для ' + job.excluded.length +
      ' требований привязка обязательности требует проверки. Их учли с обычным весом 1.';
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
    heading.append(toggle, element('span', 'row-subtitle',
      row.mandatoryExcluded ? 'Обязательность требует проверки'
        : row.mandatoryQuote ? 'Обязательное по отчёту' : 'Обязательность не указана'));

    const assessment = element('td');
    const evidence = Object.hasOwn(evidenceLabels, row.evidence?.state)
      ? evidenceLabels[row.evidence.state] : 'Требует проверки';
    assessment.append(tag(...assessments[row.status]),
      element('span', 'row-subtitle', evidence));
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
  search.addEventListener('input', renderRows);
  for (const button of filterButtons) {
    button.addEventListener('click', () => {
      filter = button.dataset.filter;
      updateFilters();
      renderRows();
    });
  }
})();
