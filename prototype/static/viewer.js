(() => {
  'use strict';

  const {
    MAX_REPORT_BYTES, interviewPlan, parseReport, createDisplayText, radarGeometry, filterRows, describeDashboard, describeRun, describeFit, scoreLabel,
    assessments, mandatoryStates, evidenceLabel, mandatoryLabel, requirementReviewLabel
  } = window.NanimaiReport;
  const { renderManagerReport } = window.NanimaiManagerReport;
  const byId = id => document.getElementById(id);
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
  let displayText = createDisplayText();
  const boundTextNodes = new Set();

  function setText(id, value) {
    const node = byId(id);
    node.textContent = displayText(value);
    boundTextNodes.add(node);
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = displayText(text);
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
    report.jobs.forEach(job => {
      const item = element('li', 'job-card');
      const rank = element('p', 'eyeline numeric', (report.complete ? 'Место ' : 'Предварительное место ') + job.rank);
      const heading = element('h2', 'job-option-name', job.title);
      const score = element('p', 'job-option-score numeric');
      score.append(element('strong', null, scoreLabel(job.score)), element('span', null, 'Подтверждённый балл'));
      const coverage = element('p', 'support', 'Покрытие требований · ' + numberFormat.format(job.score.coverage) + '%');
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
    setText('job-coverage', 'Покрытие требований ' + numberFormat.format(job.score.coverage) + '%');
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
    renderReview(job);
    renderComparison(job);
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
    const handoff = report.handoff.find(item => item.job_id === job.id);
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
    const { a, b, outcome, reason } = item;
    const [higher, lower] = outcome === 'b_higher' ? [b, a] : [a, b];
    const low = job => scoreLabel(job.score);
    let summary = a.title + ' и ' + b.title + ' делят место ' + a.rank + ' · L ' + low(a) + ' и ' + low(b) + '.';
    if (reason === 'mandatory_violation') {
      summary = higher.title + ' выше ' + lower.title + ' по правилу обязательных требований. ' +
        'У ' + lower.title + ' отмечено обязательное несоответствие.';
    } else if (reason === 'lower_bound') {
      summary = higher.title + ' выше ' + lower.title + ' по подтверждённому баллу · ' + low(higher) + ' и ' + low(lower) + '.';
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
    title.append(element('span', null, job.title + ' · ' + ref.row.label), tag(...assessments[ref.row.status]));
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
    setText('leader-summary', names(leader.jobs) + ' · ' + (report.complete ? states[leader.state] :
      'Предварительный выбор среди обработанных вакансий. Сравнение со всем набором не завершено.'));
    setText('leader-scope', (report.complete ? '' : 'Обработаны не все вакансии. ') +
      'Проверка по правилам отчёта охватывает спорные основания и не более двух ответов кандидата. Смысл цитат проверяет рекрутер.');
    const questions = interviewPlan(report);
    if (questions.length) {
      const plan = element('section', 'source-list');
      plan.append(element('h3', null, 'Сначала спросите об этом'),
        element('p', 'support', 'Три приоритетных уточнения для короткого интервью.'));
      questions.forEach((ref, index) => {
        const card = element('article', 'source-disclosure source-body');
        card.append(element('strong', null, (index + 1) + '. ' + ref.row.question),
          element('p', 'support', ref.title + ' · ' + (ref.changesOrder ?
            'Ответ может изменить порядок вакансий.' :
            ref.row.mandatoryQuote && !ref.row.mandatoryExcluded ? 'Уточните обязательное требование.' : 'Уточните недостающий опыт.')));
        card.append(comparisonFactor(ref));
        plan.append(card);
      });
      body.append(plan);
    }
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
    const currentPolicy = report.jobs.length > 0 && report.jobs.every(job =>
      job.score.policyVersion === 'draft-2026-11-14-v3');
    byId('overview-method').hidden = !currentPolicy;
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
      heading.append(tag(...mandatoryStates[report.jobs[index].score.mandatory]));

      const bounds = element('div', 'overview-metric');
      bounds.append(element('p', null, 'Подтверждённый балл'),
        element('strong', 'numeric', numberFormat.format(job.lower) + ' / 100'));
      // Native meters take numeric values under the offline page's strict CSP.
      // Show only confirmed credit; unknown requirements are not assumed matches.
      const interval = element('div', 'interval');
      interval.setAttribute('aria-hidden', 'true');
      interval.append(meter(job.lower, 'low'));
      bounds.append(interval);

      const coverage = element('div', 'overview-metric');
      coverage.append(element('p', null, 'Покрытие требований'),
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
      const statusDetails = element('details', 'overview-statuses');
      statusDetails.append(element('summary', null, 'Все статусы · ' + job.total), counts,
        element('p', 'support', 'Подтверждённый балл: ' + scoreLabel(job)));
      row.append(heading, bounds, coverage, statusDetails);
      if (job.brief?.shares) {
        const brief = element('div', 'compact-brief');
        const strengths = element('section');
        strengths.append(element('h4', null, 'Что подходит'));
        const matches = element('ul');
        for (const item of job.brief.strengths) matches.append(element('li', null,
          item.text + (item.status === 'partial' ? ' — частично подтверждено' : ' — подтверждено')));
        if (!matches.childElementCount) matches.append(element('li', null, 'Основания требуют проверки.'));
        strengths.append(matches);
        const questions = element('ul');
        for (const question of job.brief.questions) questions.append(element('li', null, question));
        if (questions.childElementCount) strengths.append(element('h4', null, 'Что уточнить'), questions);
        const skills = element('section');
        skills.append(element('h4', null, 'Соответствие по группам'));
        if (job.brief.radarReady) skills.append(radar(job.brief.axes));
        for (const axis of job.brief.axes) {
          const axisRow = element('div', 'competency-axis');
          axisRow.append(element('span', null, axis.label + ' · вес ' + numberFormat.format(axis.weight) +
            '% · ' + numberFormat.format(axis.coverage) + '% данных'));
          if (axis.score === null) axisRow.append(element('span', 'support', 'Нет данных'));
          else axisRow.append(meter(axis.score, 'coverage'), element('strong', 'numeric', numberFormat.format(axis.score)));
          skills.append(axisRow);
        }
        if (!job.brief.axes.length) skills.append(element('p', 'support', 'Группировка недоступна.'));
        const shares = job.brief.shares;
        skills.append(element('p', 'support', 'Основания: ' + percent(shares.confirmed) +
          ' · Сверка: ' + percent(shares.disputed) + ' · Нет сведений: ' + percent(shares.unknown)));
        brief.append(strengths, skills);
        if (index < 3) row.append(brief);
        else {
          const detail = element('details', 'overview-brief');
          detail.append(element('summary', null, 'Навыки и основания'), brief);
          row.append(detail);
        }
      }
      list.append(row);
    });
  }

  function radar(axes) {
    const points = radarGeometry(axes);
    const svg = (name, attrs = {}) => {
      const node = document.createElementNS('http://www.w3.org/2000/svg', name);
      for (const [key,value] of Object.entries(attrs)) node.setAttribute(key, String(value));
      return node;
    };
    const chart = svg('svg', {viewBox:'0 0 320 260',class:'skills-radar',role:'img',
      'aria-label':'Соответствие по группам требований. Отсутствующие данные не показаны точкой.'});
    for (const radius of [20.5,41,61.5,82]) chart.append(svg('circle',{cx:160,cy:130,r:radius,class:'radar-grid'}));
    for (const axis of points) {
      chart.append(svg('line',{x1:160,y1:130,x2:axis.outer.x,y2:axis.outer.y,class:'radar-grid'}));
      const label = svg('text',{x:axis.labelPoint.x,y:axis.labelPoint.y,'text-anchor':'middle','dominant-baseline':'middle'});
      label.textContent = axis.label;
      chart.append(label);
    }
    if (points.every(axis=>axis.point)) chart.append(svg('polygon',{
      points:points.map(axis=>axis.point.x+','+axis.point.y).join(' '),class:'radar-area'}));
    for (let index=0; index<points.length; index++) {
      const axis = points[index], next = points[(index+1)%points.length];
      if (!axis.point) continue;
      if (next.point) chart.append(svg('line',{x1:axis.point.x,y1:axis.point.y,x2:next.point.x,y2:next.point.y,class:'radar-line'}));
      const dot = svg('circle',{cx:axis.point.x,cy:axis.point.y,r:3.5,class:'radar-dot'});
      const title = svg('title');
      title.textContent = axis.label + ': ' + numberFormat.format(axis.score) + '/100; данные ' + numberFormat.format(axis.coverage) + '%';
      dot.append(title);chart.append(dot);
    }
    return chart;
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
    const rows = filterRows(activeJob.rows, filter, search.value, displayText);
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
    const trustedContext = runContext ? { runId: runContext.id, revision: runContext.revision } : null;
    const html = renderManagerReport(report, activeJob.id, trustedContext, displayText);
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }));
    const link = element('a');
    link.href = url;
    link.download = 'manager-report.html';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function clearReportData() {
    displayText = createDisplayText();
    search.value = '';
    for (const node of boundTextNodes) node.textContent = '';
    boundTextNodes.clear();
    for (const container of ['job-list', 'requirement-rows', 'profile-list', 'overview-list',
      'condition-list', 'comparison-detail', 'comparison-job', 'review-list', 'review-controls', 'skipped-jobs',
      'leader-evidence', 'job-conditions']) byId(container).replaceChildren();
  }

  function openReport(next, label, context = null, selectedJob = null, view = 'overview') {
    clearReportData();
    runContext = context;
    displayText = context?.displayText || createDisplayText();
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
    beginAnalysis() {
      ++loadSequence;
      runContext = null;
      report = null;
      activeJob = null;
      clearReportData();
      byId('report-workspace').hidden = true;
      byId('welcome').hidden = true;
      setFileStatus('');
    },
    beginLoad: () => ++loadSequence,
    isLatest: sequence => sequence === loadSequence,
    getContext: () => runContext,
    openServerReport(next, context) {
      const staysOpen = runContext?.id === context.id;
      const view = staysOpen ? views.find(button => button.getAttribute('aria-pressed') === 'true').dataset.view : 'overview';
      openReport(next, 'Результат анализа', context, staysOpen ? activeJob?.id : null, view);
    },
    closeServerReport(id) {
      if (runContext?.id !== id) return;
      ++loadSequence;
      runContext = null;
      report = null;
      activeJob = null;
      clearReportData();
      byId('report-workspace').hidden = true;
      byId('welcome').hidden = false;
      setFileStatus('Анализ удалён из истории.');
    }
  };

  for (const button of views) {
    button.addEventListener('click', () => selectView(button.dataset.view));
  }
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
