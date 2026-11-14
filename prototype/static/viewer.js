(() => {
  'use strict';

  const {
    MAX_REPORT_BYTES, parseReport, filterRows, describeDashboard, describeRun, describeFit, scoreRange,
    assessments, mandatoryStates, evidenceLabel, mandatoryLabel, requirementReviewLabel, assessmentLabel, summarizeJob,
    createDisplay, rowSourceHidden, trustedRequirements
  } = window.NanimaiReport;
  const { renderManagerReport } = window.NanimaiManagerReport;
  const byId = id => document.getElementById(id);
  const input = byId('report-file');
  const search = byId('requirement-search');
  const managerButton = byId('manager-report');
  const views = Array.from(byId('report-views').querySelectorAll('button'));
  const filterButtons = Array.from(byId('row-filters').querySelectorAll('button'));
  const numberFormat = new Intl.NumberFormat('ru', { maximumFractionDigits: 1 });

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
  let runContext = null;
  let display = createDisplay({});
  let rowButtons = new Map();
  const reviewContext = () => runContext ? { runId: runContext.id, revision: runContext.revision } : null;
  const isInsufficient = job => summarizeJob(job, display).insufficient;

  function setText(id, value) {
    byId(id).textContent = display.text(value);
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = display.text(text);
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
    setText('run-progress', report.processed === 0 ? 'Анализ не выполнен' :
      report.complete ? 'Все вакансии оценены' : 'Часть вакансий не оценена');
    setText('run-review', runContext && report.requirementsConfirmed ? 'Состав подтверждён' : 'Состав не подтверждён');
    setText('run-review-detail', report.finalAllowed ? 'Подтверждение записано в отчёте' : 'Оценки и цитаты требуют проверки');
    byId('privacy-note').hidden = !report.privacyWarning;

    const note = report.complete && report.jobs.every(isInsufficient)
      ? ['Недостаточно данных для оценки', 'Откройте вакансию и проверьте спорные основания.'] : recommendation;
    byId('run-note').hidden = !note;
    byId('run-note').dataset.tone = report.complete ? 'info' : 'warning';
    setText('run-note-title', note?.[0] || '');
    setText('run-note-text', note?.[1] || '');
    const skipped = byId('skipped-jobs');
    skipped.hidden = report.unprocessed.length === 0;
    skipped.replaceChildren(...report.unprocessed.map(job => {
      const reason = Object.hasOwn(skipReasons, job.reason) ? skipReasons[job.reason] : 'Вакансия не оценена';
      return element('li', null, job.title + ' — ' + (job.diagnostic || reason));
    }));
  }

  function renderRanking() {
    setText('ranking-count', report.jobs.length);
    byId('empty-ranking').hidden = report.jobs.length > 0;
    byId('score-help').hidden = report.jobs.length === 0;
    const policy = report.jobs[0]?.score.policyVersion;
    const knownPolicy = ['draft-2026-11-12-v1', 'draft-2026-11-13-v2', 'draft-2026-11-14-v3'].includes(policy) &&
      report.jobs.every(job => job.score.policyVersion === policy);
    setText('ranking-method', knownPolicy
      ? 'Сначала идут вакансии без выявленного нарушения обязательных требований. Внутри группы порядок определяется нижней границей L. При равном балле вакансии делят место.'
      : 'Места и порядок взяты из отчёта.');
    byId('score-policy').hidden = !knownPolicy;
    setText('score-policy', policy === 'draft-2026-11-14-v3'
      ? 'В этой версии обязательная группа получает 75 баллов шкалы, прочая — 25. Если группа одна, ей отводятся все 100. Это выбранные командой правила, не вероятность найма.'
      : 'В этой версии вес применённого обязательного требования — 3, прочего — 1. Это выбранные командой правила, не вероятность найма.');
    const list = byId('job-list');
    list.replaceChildren();
    list.toggleAttribute('data-many', report.jobs.length > 8);
    if (report.jobs.length > 8) list.tabIndex = 0;
    else list.removeAttribute('tabindex');
    report.jobs.forEach(job => {
      const item = element('li', 'job-card');
      const rank = element('p', 'eyeline numeric', (report.complete ? 'Место ' : 'Предварительное место ') + job.rank);
      const heading = element('h2', 'job-option-name', job.title);
      const { matches, gaps, clarify, insufficient } = summarizeJob(job, display);
      const score = element('p', 'job-option-summary', insufficient ? 'Недостаточно данных для оценки' :
        matches.length + ' совпадений · ' + gaps.length + ' пробелов · ' + clarify.length + ' на уточнение');
      const button = element('button', 'job-option button button-secondary', 'Открыть');
      button.type = 'button';
      button.setAttribute('aria-label', 'Открыть вакансию ' + job.title);
      button.setAttribute('aria-controls', 'job-detail');
      button.addEventListener('click', () => {
        selectJob(job);
        byId('job-title').focus();
      });
      item.append(rank, heading, score, tag(...mandatoryStates[job.score.mandatory]), button);
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
    setText('job-coverage', 'Покрытие засчитанными доказательствами ' + numberFormat.format(job.score.coverage) + '%');
    setText('job-requirements-review', requirementReviewLabel(trustedRequirements(report, job, reviewContext())));
    const scoreReview = byId('job-score-review');
    scoreReview.hidden = job.excluded.length === 0;
    scoreReview.textContent = 'Для ' + job.excluded.length +
      ' требований привязка обязательности требует проверки. Балл приведён по отчёту.';
    const fit = describeFit(report, job, display, reviewContext());
    setText('job-fit', fit.label);
    setText('job-fit-notes', fit.notes.join(' '));
    byId('job-fit-notes').hidden = !fit.notes.length;
    setText('job-range', 'Диагностический диапазон L–H · ' + scoreRange(job.score));
    byId('job-range').hidden = isInsufficient(job);
    const conditions = byId('job-conditions');
    const conflicts = job.conditions.items.filter(item => item.state === 'conflict');
    conditions.hidden = !conflicts.length;
    conditions.textContent = conflicts.length
      ? 'Возможный конфликт для HR · ' + conflicts.map(item => item.label).join(', ')
      : '';
    renderConditions(job.conditions);
    renderRows();
    renderFindings(job);
    renderCompetencies(job);
    renderReview(job);
    renderComparison(job);
  }

  function renderCompetencies(job) {
    const panel = byId('job-competencies');
    panel.replaceChildren(element('h4', null, 'Профиль компетенций'));
    if (!job.competencies || isInsufficient(job)) {
      panel.append(element('p', 'support', 'Недостаточно данных для диаграммы компетенций.'));
      return;
    }
    const axes = job.competencies;
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 232 232');
    svg.setAttribute('aria-hidden', 'true');
    const point = (index, length) => {
      const angle = index * 2 * Math.PI / axes.length - Math.PI / 2;
      return [116 + 93 * length * Math.cos(angle), 116 + 93 * length * Math.sin(angle)];
    };
    const shape = (tag, className, attributes) => {
      const node = document.createElementNS(ns, tag);
      node.setAttribute('class', className);
      for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, value);
      svg.append(node);
      return node;
    };
    for (const scale of [.25, .5, .75, 1]) {
      shape('polygon', 'radar-grid', { points: axes.map((_, i) => point(i, scale).join(',')).join(' ') });
    }
    for (const [index, item] of axes.entries()) {
      const [x2, y2] = point(index, 1);
      shape('line', 'radar-grid', { x1: 116, y1: 116, x2, y2 });
      const [x, y] = point(index, 1.13);
      shape('text', 'radar-label', { x, y }).textContent = index + 1;
      const next = (index + 1) % axes.length;
      if (item.score === null) continue;
      const [cx, cy] = point(index, item.score / 100);
      if (axes[next].score !== null) {
        const [x2, y2] = point(next, axes[next].score / 100);
        shape('line', 'radar-value', { x1: cx, y1: cy, x2, y2 });
      }
      shape('circle', 'radar-point', { cx, cy, r: 4 });
    }
    const list = element('ol', 'radar-legend');
    for (const item of axes) {
      const value = item.score === null ? 'Недостаточно данных' :
        numberFormat.format(item.score) + '% · покрытие ' + numberFormat.format(item.coverage) + '%';
      list.append(element('li', null, item.title + ' · ' + value));
    }
    const figure = element('figure', 'competency-figure');
    figure.append(svg, list);
    panel.append(figure);
  }

  function openEvidence(row) {
    byId('job-evidence').open = true;
    if (!rowButtons.has(row.id)) {
      filter = 'all';
      search.value = '';
      updateFilters();
      renderRows();
    }
    const button = rowButtons.get(row.id);
    if (button.getAttribute('aria-expanded') === 'false') button.click();
    button.focus();
  }

  function renderFindings(job) {
    const { matches, gaps, clarify, stops } = summarizeJob(job, display);
    const decisive = (report.leader?.canChange ?? []).filter(ref => ref.jobId === job.id).map(ref => ref.row);
    const questions = [...new Set([...decisive, ...clarify])];
    const groups = [
      ['Что подходит', matches, 'Засчитанных совпадений пока нет.'],
      ['Подтверждённые пробелы', gaps, 'По пригодным цитатам пробелы не выявлены.'],
      ['Что уточнить', questions, 'Открытых вопросов по требованиям нет.'],
      ['Обязательные ограничения', stops, 'Подтверждённых обязательных несоответствий нет.']
    ];
    byId('job-findings').replaceChildren(...groups.map(([title, rows, empty]) => {
      const section = element('section');
      section.append(element('h4', null, title));
      if (!rows.length) section.append(element('p', 'support', empty));
      else {
        const list = element('ul');
        for (const row of rows.slice(0, 3)) {
          const item = element('li');
          const defaultText = title === 'Что уточнить' ? 'Что можно уточнить по требованию «' + row.label + '»?' : row.label;
          const button = element('button', 'text-action', defaultText);
          button.type = 'button';
          button.addEventListener('click', () => openEvidence(row));
          item.append(button);
          list.append(item);
        }
        section.append(list);
      }
      return section;
    }));
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

  const handoffStates = {
    draft: 'Черновик', reviewed_for_handoff: 'Проверено для передачи', blocked: 'Передача заблокирована',
    stale: 'Проверка устарела', invalid: 'Проверка недействительна'
  };
  const queueActions = {
    complete_run: 'Завершите обработку', fix_source: 'Сверьте исходный документ',
    read_context: 'Проверьте контекст', check_list: 'Проверьте список требований',
    ask_candidate: 'Уточните у кандидата', decide_condition: 'Согласуйте условия',
    compare_with_original: 'Сверьте с оригиналом'
  };

  function reviewButton(label, action, itemId, jobId) {
    const button = element('button', 'button button-secondary compact', label);
    button.type = 'button';
    button.addEventListener('click', () => runContext?.decide(jobId, action, itemId));
    return button;
  }

  function renderReview(job) {
    const jobItems = report.reviewItems.filter(item => item.job_id == null || item.job_id === job.id);
    const handoff = runContext ? report.handoff.find(item => item.job_id === job.id) : null;
    const panel = byId('review-panel');
    panel.hidden = !jobItems.length && !handoff;
    const list = byId('review-list');
    const controls = byId('review-controls');
    list.replaceChildren();
    controls.replaceChildren();
    setText('review-message', '');
    if (panel.hidden) return;

    const serverState = runContext ? handoff?.state : null;
    const base = Object.hasOwn(handoffStates, serverState) ? handoffStates[serverState] : 'Черновик';
    const state = handoff?.requirements_confirmed === true ? base + ' · Состав подтверждён' : base;
    setText('review-state', runContext?.decide ? state : state + ' · Просмотр без изменений');
    if (runContext?.decide && handoff?.can_confirm_requirements === true) {
      controls.append(reviewButton('Подтвердить состав', 'confirm_requirements', null, job.id));
    }
    if (runContext?.decide && handoff?.can_mark_for_handoff === true) {
      controls.append(reviewButton('Отметить для передачи', 'mark_for_handoff', null, job.id));
    }

    for (const item of jobItems) {
      const details = element('details', 'source-disclosure');
      const summary = element('summary', 'source-heading');
      const blocked = handoff?.blockers?.includes(item.id);
      const closed = handoff?.acknowledged?.includes(item.id);
      const accepted = handoff?.accepted_exceptions?.includes(item.id);
      const instruction = Object.hasOwn(queueActions, item.action) ? queueActions[item.action] : 'Проверьте замечание';
      summary.append(element('span', null, instruction));
      if (item.decisive) summary.append(tag('Может изменить первое место', 'warning'));
      if (blocked) summary.append(tag('Блокирует передачу', 'danger'));
      if (closed) summary.append(tag('Ознакомились', 'neutral'));
      if (accepted) summary.append(tag('Исключение принято', 'warning'));
      details.append(summary, element('p', 'source-note', item.explanation));
      if (item.refs.length) {
        const quotes = element('div', 'evidence-grid source-body');
        for (const source of ['vacancy', 'cv']) {
          const refs = item.refs.filter(ref => ref.source === source);
          if (!refs.length) continue;
          quotes.append(quoteCard(source === 'cv' ? 'Фрагменты резюме' : 'Фрагменты вакансии',
            refs.map(ref => ref.heading ? ref.heading + '\n' + (ref.sentence || ref.quote) : ref.sentence || ref.quote)));
        }
        details.append(quotes);
      }
      if (item.contexts.length) details.append(quoteCard('Возможные контексты', item.contexts));
      if (runContext?.decide && handoff?.allowed_actions && Object.hasOwn(handoff.allowed_actions, item.id)) {
        const action = handoff.allowed_actions[item.id];
        if (['read_context', 'accept_condition'].includes(action)) {
          const label = action === 'read_context' ? 'Отметить ознакомление' : 'Принять исключение';
          const area = element('div', 'review-controls source-body');
          area.append(reviewButton(label, action, item.id, job.id));
          details.append(area);
        }
      }
      list.append(details);
    }
  }

  const comparisonCaveats = {
    different_requirement_lists: 'У вакансий разные требования или веса. Нижняя граница рассчитана по требованиям каждой вакансии.',
    incomplete_run: 'Обработаны не все вакансии.',
    evidence_not_applied: 'Спорные цитаты отмечены для проверки. При расчёте балла они не учитывались отдельно.',
    close_margin: 'Разница меньше одного шага оценки: превосходство по проценту не установлено. Сравните вакансии по существу.'
  };
  const swingOutcomes = {
    reversed: 'порядок может поменяться', tie: 'вакансии могут разделить место', breaks_tie: 'места могут разойтись'
  };

  function renderComparison(job) {
    const matches = report.comparisons.filter(item => item.a === job || item.b === job);
    const section = byId('comparison-section');
    const picker = byId('comparison-job');
    section.hidden = report.jobs.length < 2;
    byId('comparison-picker').hidden = matches.length < 2;
    picker.replaceChildren(...matches.map((item, index) => {
      const option = element('option', null, (item.a === job ? item.b : item.a).title);
      option.value = index;
      return option;
    }));
    renderComparisonDetail(matches[0]);
  }

  function renderComparisonDetail(item) {
    const detail = byId('comparison-detail');
    detail.replaceChildren();
    if (!item) {
      setText('comparison-summary', 'В отчёте нет сравнения для этой вакансии.');
      return;
    }
    if ((isInsufficient(item.a) || isInsufficient(item.b)) && item.reason !== 'mandatory_violation') {
      setText('comparison-summary', 'Недостаточно данных для сравнения. По одной или обеим вакансиям нет засчитанных доказательств.');
      return;
    }
    const { a, b, outcome, reason } = item;
    const [higher, lower] = outcome === 'b_higher' ? [b, a] : [a, b];
    const low = job => numberFormat.format(job.score.lower) + '%';
    let summary = a.title + ' и ' + b.title + ' делят место ' + a.rank + ' · L ' + low(a) + ' и ' + low(b) + '.';
    if (reason === 'mandatory_violation') {
      summary = higher.title + ' выше ' + lower.title + ' по правилу обязательных требований. ' +
        'У ' + lower.title + ' отмечено обязательное несоответствие.';
    } else if (reason === 'lower_bound') {
      summary = higher.title + ' выше ' + lower.title + ' по нижней границе L. ' +
        (low(higher) === low(lower) ? 'Разница меньше точности отображения.' : low(higher) + ' и ' + low(lower) + '.');
    }
    setText('comparison-summary', summary);

    for (const ref of item.deciding) detail.append(comparisonFactor(ref));
    if (item.swings.length) {
      const finding = element('details', 'source-disclosure');
      finding.append(element('summary', 'source-heading', 'Что уточнить, чтобы проверить порядок'));
      const body = element('div', 'source-list source-body');
      for (const ref of item.swings) {
        const hypothetical = 'Если оценка станет «' + assessments[ref.assumedStatus][0].toLocaleLowerCase('ru') +
          '», ' + swingOutcomes[ref.result] + '.';
        body.append(comparisonFactor(ref, hypothetical));
      }
      finding.append(body);
      detail.append(finding);
    }
    if (item.caveats.length) {
      const notes = element('ul', 'comparison-caveats');
      for (const caveat of item.caveats) notes.append(element('li', null, comparisonCaveats[caveat]));
      detail.append(notes);
    }
  }

  function comparisonFactor(ref, hypothetical) {
    const job = report.jobs.find(candidate => candidate.id === ref.jobId);
    const details = element('details', 'source-disclosure');
    const title = element('summary', 'source-heading');
    title.append(element('span', null, job.title + ' · ' + ref.row.label), tag(...assessmentLabel(ref.row, display)));
    details.append(title);
    const quotes = element('div', 'evidence-grid source-body');
    quotes.append(quoteCard('Фрагмент вакансии', [ref.row.requirementQuote]),
      quoteCard('Фрагменты резюме', ref.row.resumeQuotes, 'Цитата в отчёте не указана.'));
    details.append(quotes);
    if (ref.row.scoreConflict) details.append(element('p', 'source-note support',
      'Повторы одного требования получили разные оценки. Их общий вклад спорный; исходные статусы сохранены.'));
    if (hypothetical) details.append(element('p', 'source-note support', hypothetical));
    return details;
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
      const hidden = [item.cv, item.vacancy].some(source => source && display.unresolved(sourceText(source)));
      const status = hidden && item.state === 'compatible'
        ? ['Источник нужно сверить', 'warning'] : conditionStates[item.state];
      summary.append(element('span', null, item.label), tag(...status));
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
      if (hidden) details.append(element('p', 'source-note support', 'Часть условия скрыта. Сверьте с оригиналами.'));
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
      if (Array.from(quotes).some(display.unresolved)) {
        details.append(element('p', 'source-note support', 'Часть цитаты скрыта. Сверьте с оригиналом резюме.'));
      }
      list.append(details);
    }
    if (list.firstElementChild) list.firstElementChild.open = true;
  }

  function renderLeader() {
    const leader = report.leader;
    byId('leader-analysis').hidden = !leader;
    const body = byId('leader-evidence');
    body.replaceChildren();
    if (!leader) return;
    const states = {
      stable: 'Первое место сохраняется в проверенных сценариях уточнения.',
      tie: 'Несколько вакансий делят первое место.',
      close: 'Оценки близки. Одного процента недостаточно, чтобы выбрать вакансию.',
      open: 'Первое место предварительное: основания требуют уточнения.',
      none_fit: 'В каждой вакансии отмечен обязательный пробел. Решение принимает HR.'
    };
    const names = jobs => jobs.map(job => job.title).join(', ');
    setText('leader-title', report.complete ? 'Что определяет первое место' : 'Предварительный выбор среди обработанных');
    const insufficient = !leader.comparable || leader.jobs.every(isInsufficient);
    setText('leader-summary', insufficient ? 'Недостаточно данных для сравнения вакансий.' :
      names(leader.jobs) + ' · ' + (report.complete ? states[leader.state] :
      'Предварительный выбор среди обработанных вакансий. Сравнение со всем набором не завершено.'));
    setText('leader-scope', (report.complete ? '' : 'Обработаны не все вакансии. ') +
      'Проверка по правилам отчёта охватывает спорные основания и не более двух ответов кандидата. Смысл цитат проверяет рекрутер.');
    const groups = [
      ['Основания выбора', leader.factors], ['Ограничения', leader.limits],
      ['Что может изменить выбор', leader.canChange]
    ];
    for (const [heading, refs] of groups) {
      if (!refs.length) continue;
      const section = element('details', 'source-disclosure');
      section.append(element('summary', 'source-heading', heading));
      const rows = element('div', 'source-list source-body');
      for (const ref of refs) rows.append(comparisonFactor(ref));
      section.append(rows);
      body.append(section);
    }
    if (leader.closeTo.length) body.append(element('p', 'support', 'Близкие вакансии: ' + names(leader.closeTo) + '.'));
    if (leader.unassessed.length) body.append(element('p', 'support',
      'Без подтверждённых совпадений: ' + names(leader.unassessed) + '. Сведений недостаточно; это не отказ.'));
  }

  function renderOverview() {
    renderLeader();
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

      const grouped = summarizeJob(report.jobs[index], display);
      const bounds = element('div', 'overview-metric');
      bounds.append(element('p', null, 'Диагностический диапазон L–H'),
        element('strong', 'numeric', !grouped.insufficient ? scoreRange(job) : 'Недостаточно данных'));
      // Native meters take numeric values under the offline page's strict CSP.
      // The two meters share a baseline and the upper bound has the lighter fill.
      const interval = element('div', 'interval');
      interval.setAttribute('aria-hidden', 'true');
      interval.append(meter(job.upper, 'high'), meter(job.lower, 'low'));
      if (!grouped.insufficient) bounds.append(interval);

      const coverage = element('div', 'overview-metric');
      coverage.append(element('p', null, 'Покрытие засчитанными доказательствами'),
        element('strong', 'numeric', percent(job.coverage)));
      const coverageTrack = meter(job.coverage, 'coverage');
      coverageTrack.setAttribute('aria-hidden', 'true');
      coverage.append(coverageTrack);

      const counts = element('ul', 'status-counts');
      for (const [label, count] of [['Совпадения', grouped.matches.length], ['Пробелы', grouped.gaps.length],
        ['К уточнению', grouped.clarify.length]]) counts.append(element('li', null, label + ' · ' + count));
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
    assessment.colSpan = 2;
    assessment.append(tag(...assessmentLabel(row, display)),
      element('span', 'row-subtitle', evidenceLabel(row)));
    if (rowSourceHidden(row, display)) {
      assessment.append(element('span', 'row-subtitle', 'Фрагмент скрыт · откройте доказательства для сверки'));
    }
    main.append(heading, assessment);
    rowButtons.set(row.id, toggle);

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
    if (rowSourceHidden(row, display)) {
      addNote(notes, 'Часть источника скрыта', 'Сверьте требование и цитату с локальными оригиналами перед решением.');
    }
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
    rowButtons = new Map();
    if (!activeJob) return;
    const rows = filterRows(activeJob.rows, filter, search.value, display);
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
    const html = renderManagerReport(report, activeJob.id, reviewContext(), display);
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

  function openReport(next, label, context = null, selectedJob = null, view = 'ranking') {
    runContext = context;
    display = createDisplay(next, context?.displayData);
    report = next;
    renderSummary();
    renderRanking();
    selectJob(report.jobs.find(job => job.id === selectedJob) || report.jobs[0] || null);
    renderOverview();
    renderProfile();
    selectView(view);
    byId('welcome').hidden = true;
    byId('report-workspace').hidden = false;
    setFileStatus(label);
  }

  window.RecruiterViewer = {
    beginLoad: () => ++loadSequence,
    loadVersion: () => loadSequence,
    isLatest: sequence => sequence === loadSequence,
    getContext: () => runContext,
    openServerReport(next, context) {
      const staysOpen = runContext?.id === context.id;
      if (staysOpen && context.revision < runContext.revision) return;
      const view = staysOpen ? views.find(button => button.getAttribute('aria-pressed') === 'true').dataset.view : 'ranking';
      openReport(next, 'Открыт отчёт локального запуска', context, staysOpen ? activeJob?.id : null, view);
    },
    closeServerReport(id) {
      if (runContext?.id !== id) return;
      ++loadSequence;
      runContext = null;
      display = createDisplay({});
      report = null;
      activeJob = null;
      byId('report-workspace').hidden = true;
      byId('welcome').hidden = false;
      for (const container of ['job-list', 'requirement-rows', 'profile-list', 'overview-list',
        'condition-list', 'comparison-detail', 'comparison-job', 'leader-evidence', 'job-findings', 'job-competencies',
        'review-list', 'review-controls', 'skipped-jobs']) byId(container).replaceChildren();
      for (const name of ['comparison-summary', 'leader-summary', 'leader-scope', 'job-fit-notes']) setText(name, '');
      setFileStatus('Локальный запуск удалён.');
    }
  };

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
  byId('comparison-job').addEventListener('change', event => {
    if (!activeJob) return;
    const matches = report.comparisons.filter(item => item.a === activeJob || item.b === activeJob);
    renderComparisonDetail(matches[Number(event.target.value)]);
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
