(() => {
  'use strict';

  const {
    MAX_REPORT_BYTES, parseReport, filterRows, describeDashboard, describeRun, describeFit, scoreRange,
    assessments, mandatoryStates, evidenceLabel, mandatoryLabel, requirementReviewLabel, readComparison,
    reviewFor, handoffLabel, acceptedConditionKinds
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
  let runContext = null;
  let reportOrigin = null;
  let reportLoading = false;
  let compareSequence = 0;
  const rowToggles = new Map();
  let openListener;

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
    setText('run-progress', report.complete ? 'Все вакансии оценены' : 'Часть вакансий не оценена');
    const confirmed = runContext && report.jobs.filter(job => reviewFor(report, job, runContext).requirements === 'confirmed').length;
    const source = runContext ? 'Локальный запуск · Ревизия ' + runContext.revision
      : reportOrigin === 'file' ? 'Внешний непроверенный файл' : 'Встроенный пример';
    setText('run-review', source);
    const policy = report.policyVersion || report.jobs[0]?.score.policyVersion;
    const review = confirmed ? 'Состав подтверждён для ' + confirmed + ' из ' + report.total
      : runContext ? 'Состав не подтверждён' : 'Решения HR не проверены';
    setText('run-review-detail', [policy ? 'Политика ' + policy : 'Версия политики не указана', review].join(' · '));
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
    const unranked = !report.jobs.length ? (report.reviewItems ?? []) : [];
    byId('unranked-review').hidden = !unranked.length;
    const skippedTitles = new Map(report.unprocessed.map(job => [job.id, job.title]));
    byId('unranked-review-list').replaceChildren(...unranked.map(item =>
      reviewDisclosure(item, queueScope(item, skippedTitles), null)));
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
    ++compareSequence;
    activeJob = job;
    managerButton.hidden = !job;
    updateReportActions();
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
    setText('job-requirements-review', requirementReviewLabel(reviewFor(report, job, runContext).requirements));
    const scoreReview = byId('job-score-review');
    scoreReview.hidden = job.excluded.length === 0;
    scoreReview.textContent = 'Для ' + job.excluded.length +
      ' требований привязка обязательности требует проверки. Балл приведён по отчёту.';
    const fit = describeFit(report, job, runContext);
    setText('job-fit', fit.label);
    setText('job-fit-notes', fit.notes.join(' '));
    byId('job-fit-notes').hidden = !fit.notes.length;
    const conditions = byId('job-conditions');
    const conflicts = job.conditions.items.filter(item => item.state === 'conflict');
    conditions.hidden = !conflicts.length;
    conditions.textContent = conflicts.length
      ? 'Возможный конфликт для HR · ' + conflicts.map(item => item.label).join(', ')
      : '';
    renderConditions(job, reviewFor(report, job, runContext).handoff);
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
    const sentence = source.sentence || source.quote;
    return source.heading ? source.heading + '\n' + sentence : sentence;
  }

  const queueActions = {
    complete_run: 'Завершите обработку', fix_source: 'Сверьте исходный документ',
    read_context: 'Проверьте контекст', check_list: 'Проверьте список требований',
    ask_candidate: 'Уточните у кандидата', decide_condition: 'Согласуйте условия',
    compare_with_original: 'Сверьте с оригиналом'
  };

  function updateReportActions() {
    const pending = Boolean(runContext?.pending);
    const busy = reportLoading || pending || Boolean(runContext?.stale);
    managerButton.disabled = !activeJob || busy;
    for (const button of byId('review-panel').querySelectorAll('[data-review-action]')) {
      button.disabled = busy;
    }
    input.disabled = pending;
    byId('open-demo').disabled = pending;
    for (const button of byId('saved-runs').querySelectorAll('[data-report-navigation]')) button.disabled = pending;
  }

  function reviewButton(label, action, itemId, jobId) {
    const button = reviewLink(label, () => runContext?.decide(jobId, action, itemId));
    button.dataset.reviewAction = action;
    return button;
  }

  function renderRequirementsDraft(job, handoff) {
    const disclosure = byId('requirements-draft');
    const content = byId('requirements-draft-content');
    const draft = job.requirementsDraft;
    disclosure.open = false;
    setText('requirements-draft-title', 'Состав требований · ' + job.rows.length);
    content.replaceChildren();
    if (runContext) content.append(element('p', 'support', 'Ревизия ' + runContext.revision + ' · Вакансия ' + job.title));
    const list = element('ol', 'composition-list');
    const byRequirement = new Map(job.rows.map(row => [row.id, row]));
    const entries = draft?.requirements ?? job.rows.map(row => ({ id: row.id, text: row.label }));
    for (const item of entries) {
      const row = byRequirement.get(item.id);
      const line = element('li');
      line.append(element('strong', null, item.text), element('p', 'support',
        (draft ? 'Формулировка из отчёта · ' : '') + mandatoryLabel(row)),
        element('p', 'support', 'Цитата из вакансии'), element('blockquote', null, row.requirementQuote));
      if (row.mandatoryQuote && row.mandatoryQuote !== row.requirementQuote) {
        line.append(element('p', 'support', 'Основание обязательности'),
          element('blockquote', null, row.mandatoryQuote));
      }
      list.append(line);
    }
    content.append(list, quoteCard('Фрагменты вакансии вне списка', draft?.uncovered ?? [],
      draft ? 'Отчёт не выделил таких фрагментов.' : 'Данные о пропущенных фрагментах недоступны.'));
    if (runContext?.decide && handoff?.can_confirm_requirements) {
      const action = element('div', 'review-controls source-body');
      if (draft) action.append(reviewButton('Подтвердить состав · ревизия ' + runContext.revision,
        'confirm_requirements', null, job.id));
      else action.append(element('p', 'support', 'Подтверждение недоступно. Сервер не передал сверяемый состав этой ревизии.'));
      content.append(action);
    }
  }

  function showDisclosure(disclosure) {
    disclosure.open = true;
    disclosure.querySelector('summary').focus();
  }

  function showRequirement(id) {
    if (!rowToggles.has(id)) {
      filter = 'all';
      search.value = '';
      updateFilters();
      renderRows();
    }
    const toggle = rowToggles.get(id);
    if (toggle.getAttribute('aria-expanded') === 'false') toggle.click();
    toggle.focus();
  }

  function reviewLink(label, action) {
    const button = element('button', 'button button-secondary compact', label);
    button.type = 'button';
    button.addEventListener('click', action);
    return button;
  }

  function queueScope(item, titles) {
    return titles.has(item.job_id) ? 'Вакансия ' + titles.get(item.job_id) : 'Весь запуск';
  }

  function reviewDisclosure(item, scope, subject) {
    const details = element('details', 'source-disclosure');
    const summary = element('summary', 'source-heading');
    const instruction = Object.hasOwn(queueActions, item.action) ? queueActions[item.action] : 'Проверьте замечание';
    summary.append(element('span', null, [scope, subject, instruction].filter(Boolean).join(' · ')));
    if (item.priority) summary.append(tag('Приоритет ' + item.priority, item.priority <= 2 ? 'warning' : 'neutral'));
    details.append(summary, element('p', 'source-note', item.explanation));
    return details;
  }

  function renderReview(job) {
    const skipped = new Map(report.unprocessed.map(item => [item.id, item.title]));
    const jobItems = (report.reviewItems ?? []).filter(item => item.job_id == null || item.job_id === job.id || skipped.has(item.job_id));
    const { handoff } = reviewFor(report, job, runContext);
    const list = byId('review-list');
    const controls = byId('review-controls');
    list.replaceChildren();
    controls.replaceChildren();
    if (!runContext?.stale) {
      setText('review-message', runContext?.reviewWarning || '');
      byId('review-message').classList.toggle('error', Boolean(runContext?.reviewWarning));
    }
    setText('review-state', handoff ? handoffLabel(handoff) + (runContext.decide ? '' : ' · Только просмотр')
      : runContext ? 'Серверная проверка недоступна' : 'Только просмотр · Подтверждение состава и решения HR доступны в локальном запуске.');
    renderRequirementsDraft(job, handoff);
    const empty = byId('review-empty');
    empty.hidden = jobItems.length > 0;
    empty.textContent = report.reviewItems ? 'В очереди этой вакансии нет замечаний.' : 'В этом отчёте нет очереди проверки.';
    if (runContext?.decide && handoff?.can_mark_for_handoff === true) {
      controls.append(reviewButton('Отметить для передачи', 'mark_for_handoff', null, job.id));
    }

    for (const item of jobItems) {
      const blocked = handoff?.blockers?.includes(item.id);
      const closed = handoff?.acknowledged?.includes(item.id);
      const accepted = handoff?.accepted_exceptions?.includes(item.id);
      const row = job.rows.find(entry => entry.id === item.requirementId && item.job_id === job.id);
      const condition = job.conditions.items.find(entry => entry.kind === item.conditionKind && item.job_id === job.id);
      const scope = item.job_id === job.id ? 'Вакансия ' + job.title : queueScope(item, skipped);
      const subject = row?.label || condition?.label || (item.conditionKind ? 'Условия' : null);
      const details = reviewDisclosure(item, scope, subject);
      const summary = details.firstElementChild;
      if (item.decisive) summary.append(tag('Может изменить первое место', 'warning'));
      if (blocked) summary.append(tag('Блокирует передачу', 'danger'));
      if (closed) summary.append(tag('Ознакомились', 'neutral'));
      if (accepted) summary.append(tag('Исключение принято', 'warning'));
      if (row || condition || item.refs.length) {
        const quotes = element('div', 'evidence-grid source-body');
        for (const source of ['vacancy', 'cv']) {
          const refs = item.refs.filter(ref => ref.source === source);
          const fallback = condition?.[source];
          const texts = refs.map(sourceText);
          if (!texts.length) {
            if (fallback) texts.push(sourceText(fallback));
            else if (row) texts.push(...(source === 'cv' ? row.resumeQuotes : [row.requirementQuote]));
          }
          quotes.append(quoteCard(source === 'cv' ? 'Фрагменты резюме' : 'Фрагменты вакансии',
            texts, 'Фрагмент не указан.'));
        }
        details.append(quotes);
      }
      if (item.contexts.length) details.append(quoteCard(
        item.action === 'check_list' ? 'Дополнительные фрагменты вакансии' : 'Возможные контексты', item.contexts));
      const area = element('div', 'review-controls source-body');
      if (row) area.append(reviewLink('К оценке требования', () => showRequirement(row.id)));
      if (item.action === 'check_list') {
        area.append(reviewLink('К составу требований', () => showDisclosure(byId('requirements-draft'))));
      }
      if (condition) {
        const index = job.conditions.items.indexOf(condition);
        area.append(reviewLink('К условию', () => showDisclosure(byId('condition-list').children[index])));
      } else if (item.conditionKind) {
        area.append(reviewLink('К условиям', () => byId('conditions-title').focus()));
      }
      if (runContext?.decide && handoff?.allowed_actions && Object.hasOwn(handoff.allowed_actions, item.id)) {
        const action = handoff.allowed_actions[item.id];
        if (['read_context', 'accept_condition'].includes(action)) {
          const label = action === 'read_context' ? 'Отметить ознакомление' : 'Принять исключение';
          area.append(reviewButton(label, action, item.id, job.id));
        }
      }
      if (area.children.length) details.append(area);
      list.append(details);
    }
    updateReportActions();
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
    const section = byId('comparison-section');
    const picker = byId('comparison-job');
    const others = report.jobs.filter(other => other !== job);
    section.hidden = !others.length;
    byId('comparison-picker').hidden = others.length < 2;
    picker.replaceChildren(...others.map((other, index) => {
      const option = element('option', null, other.title);
      option.value = index;
      return option;
    }));
    if (others.length) chooseComparison(job, others[0]);
  }

  function comparisonCard(job, kinds) {
    const card = element('section', 'comparison-card');
    card.append(element('h4', null, 'Вакансия ' + job.title),
      element('p', 'support', (report.complete ? 'Место ' : 'Предварительное место ') + job.rank +
        ' · L–H ' + scoreRange(job.score) + ' · Известно ' + numberFormat.format(job.score.coverage) + '%'),
      tag(...mandatoryStates[job.score.mandatory]));
    const terms = new Map(job.conditions.items.map(item => [item.label, item]));
    for (const label of kinds) {
      const item = terms.get(label);
      const details = element('details', 'source-disclosure');
      const summary = element('summary', 'source-heading', label);
      summary.append(tag(...(item ? conditionStates[item.state] : ['Сравнение отсутствует', 'neutral'])));
      details.append(summary);
      if (item) {
        for (const [title, fragment, unresolved] of [['Вакансия', item.vacancy, item.vacancyUnresolved],
          ['Резюме', item.cv, item.cvUnresolved]]) {
          details.append(quoteCard(title, fragment ? [sourceText(fragment)] : [],
            item.state === 'invalid' || unresolved ? 'Цитату не удалось привязать.' : 'Цитата не указана.'));
        }
      } else {
        details.append(element('p', 'support', 'В отчёте нет результата проверки этого условия.'));
      }
      card.append(details);
    }
    return card;
  }

  async function chooseComparison(left, right) {
    const sequence = ++compareSequence;
    const context = runContext;
    const summary = byId('comparison-summary');
    const detail = byId('comparison-detail');
    const terms = job => new Map(job.conditions.items.map(item => [item.label, item]));
    const a = terms(left), b = terms(right);
    const different = [...new Set([...a.keys(), ...b.keys()])].filter(label => {
      const x = a.get(label), y = b.get(label);
      return x?.state !== y?.state || x?.vacancy?.quote !== y?.vacancy?.quote || x?.cv?.quote !== y?.cv?.quote;
    });
    byId('comparison-pair').replaceChildren(comparisonCard(left, different), comparisonCard(right, different));
    detail.replaceChildren();
    summary.classList.remove('error');
    const stored = report.comparisons.find(item => (item.a === left && item.b === right) || (item.a === right && item.b === left));
    if (stored) return renderComparisonDetail(stored);
    if (!context?.compare) {
      summary.textContent = 'Разбор порядка этой пары отсутствует в сохранённом отчёте.';
      return;
    }

    summary.textContent = 'Запрашиваем сравнение по сохранённому отчёту…';
    try {
      const result = await context.compare(left.id, right.id);
      if (sequence !== compareSequence) return;
      const item = readComparison(result?.comparison, report.jobs, report.policyVersion);
      if (result?.run_id !== context.runId || result.revision !== context.revision || item?.a !== left || item?.b !== right) {
        throw new Error('Сравнение недоступно для открытой версии отчёта. Откройте запуск снова.');
      }
      renderComparisonDetail(item);
    } catch (error) {
      if (sequence !== compareSequence) return;
      summary.classList.add('error');
      summary.textContent = error.message;
    }
  }

  function renderComparisonDetail(item) {
    const detail = byId('comparison-detail');
    detail.replaceChildren();
    const { a, b, outcome, reason } = item;
    const [higher, lower] = outcome === 'b_higher' ? [b, a] : [a, b];
    const low = job => numberFormat.format(job.score.lower) + '%';
    let summary = a.title + ' и ' + b.title + ' делят место ' + a.rank + ' · L ' + low(a) + ' и ' + low(b) + '.';
    if (reason === 'mandatory_violation') {
      summary = higher.title + ' выше ' + lower.title + ' по правилу обязательных требований. ' +
        'У ' + lower.title + ' отмечено обязательное несоответствие.';
    } else if (reason === 'lower_bound') {
      summary = higher.title + ' выше ' + lower.title + ' по нижней границе L · ' + low(higher) + ' и ' + low(lower) + '.';
    }
    setText('comparison-summary', summary);
    if ([a, b].every(job => job.conditions.items.length === 0)) {
      detail.append(element('p', 'support', 'В отчёте нет условий, которые можно сопоставить для этой пары.'));
    }

    for (const ref of item.deciding) detail.append(comparisonFactor(ref));
    if (item.swings.length) {
      detail.append(whatIf(item));
    } else {
      detail.append(element('p', 'support', 'В этом сравнении нет допущения по одному требованию, меняющего порядок пары.'));
    }
    if (item.caveats.length) {
      const notes = element('ul', 'comparison-caveats');
      for (const caveat of item.caveats) notes.append(element('li', null, comparisonCaveats[caveat]));
      detail.append(notes);
    }
  }

  function whatIf(item) {
    const section = element('section', 'what-if');
    section.append(element('h4', null, 'Что изменится после уточнения'));
    const controls = element('div', 'run-actions');
    const label = element('label', 'comparison-picker', 'Допущение');
    const select = element('select');
    const empty = element('option', null, 'Выберите допущение');
    empty.value = '';
    select.append(empty);
    item.swings.forEach((ref, index) => {
      const job = ref.jobId === item.a.id ? item.a : item.b;
      const option = element('option', null, 'Вакансия ' + job.title + ' · ' + ref.row.label.slice(0, 70) +
        ' · ' + assessments[ref.assumedStatus][0]);
      option.value = index;
      select.append(option);
    });
    label.append(select);
    const reset = element('button', 'button button-secondary compact', 'Сбросить');
    reset.type = 'button';
    reset.disabled = true;
    controls.append(label, reset);
    const output = element('div', 'source-list');
    output.setAttribute('aria-live', 'polite');
    section.append(controls, output);
    const update = () => {
      output.replaceChildren();
      reset.disabled = select.value === '';
      if (!select.value) return;
      const ref = item.swings[Number(select.value)];
      const job = ref.jobId === item.a.id ? item.a : item.b;
      output.append(element('p', 'support', 'Гипотетически, если по требованию «' + ref.row.label + '» оценка станет «' +
        assessments[ref.assumedStatus][0].toLocaleLowerCase('ru') + '», ' + swingOutcomes[ref.result] + '. Допущение не меняет рейтинг и решения HR.'));
      if (ref.alternative) output.append(element('p', 'support', 'Вакансия ' + job.title + ' · L–H ' +
        scoreRange(job.score) + ' → ' + scoreRange(ref.alternative.score) + '. Место в этой паре после уточнения: ' +
        ref.alternative.rank + '.'));
      output.append(comparisonFactor(ref));
    };
    select.addEventListener('change', update);
    reset.addEventListener('click', () => { select.value = ''; update(); select.focus(); });
    return section;
  }

  function comparisonFactor(ref) {
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
    return details;
  }

  function renderConditions(job, handoff) {
    const { conditions } = job;
    const accepted = acceptedConditionKinds(report, job, handoff);
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
      if (accepted.has(item.kind)) summary.append(tag('Исключение принято', 'warning'));
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
    setText('leader-summary', names(leader.jobs) + ' · ' + states[leader.state]);
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
    rowToggles.set(row.id, toggle);
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
    rowToggles.clear();
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
    if (managerButton.disabled) return;
    const html = renderManagerReport(report, activeJob.id, runContext, reportOrigin);
    const url = URL.createObjectURL(new Blob([html], { type: 'text/html;charset=utf-8' }));
    const link = element('a');
    link.href = url;
    link.download = 'manager-report.html';
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  async function loadFile(file) {
    if (runContext?.pending) return;
    const sequence = beginLoad();
    const prefix = report ? 'Сейчас открыт предыдущий отчёт. ' : '';
    setFileStatus('Читаем отчёт…');
    try {
      if (file.size > MAX_REPORT_BYTES) {
        setFileStatus(prefix + 'Отчёт больше 25 МБ. Выберите файл меньшего размера.', true);
        return;
      }
      const source = await file.text().catch(() => {
        throw new Error('Файл недоступен. Выберите его ещё раз.');
      });
      if (sequence !== loadSequence) return;
      openReport(parseReport(source), 'Открыт внешний файл ' + file.name, 'file');
    } catch (error) {
      if (sequence === loadSequence) setFileStatus(prefix + error.message, true);
    } finally {
      finishLoad(sequence);
    }
  }

  function beginLoad() {
    reportLoading = true;
    updateReportActions();
    return ++loadSequence;
  }

  function finishLoad(sequence) {
    if (sequence !== loadSequence) return;
    reportLoading = false;
    updateReportActions();
  }

  function openReport(next, label, origin, context = null, selectedJob = null, view = 'ranking') {
    reportLoading = false;
    runContext = context;
    reportOrigin = origin;
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
    openListener?.(context);
    if (!context) byId('file-status').focus();
  }

  window.RecruiterViewer = {
    beginLoad,
    finishLoad,
    loadVersion: () => loadSequence,
    isLatest: sequence => sequence === loadSequence,
    getContext: () => runContext,
    canReview: context => runContext === context && !reportLoading && !context.pending && !context.stale,
    updateReportActions,
    status: setFileStatus,
    onOpen: listener => { openListener = listener; },
    openServerReport(next, context) {
      const staysOpen = runContext?.runId === context.runId;
      const view = staysOpen ? views.find(button => button.getAttribute('aria-pressed') === 'true').dataset.view : 'ranking';
      const focusReview = staysOpen && byId('review-panel').contains(document.activeElement);
      const draftOpen = staysOpen && byId('requirements-draft').open;
      openReport(next, 'Открыт отчёт локального запуска', 'server', context, staysOpen ? activeJob?.id : null, view);
      byId('requirements-draft').open = draftOpen;
      if (focusReview) byId('review-title').focus();
    },
    closeServerReport(id) {
      if (runContext?.runId !== id) return false;
      ++compareSequence;
      runContext = null;
      report = null;
      activeJob = null;
      rowToggles.clear();
      byId('report-workspace').hidden = true;
      byId('welcome').hidden = false;
      for (const container of ['job-list', 'requirement-rows', 'profile-list', 'overview-list',
        'condition-list', 'comparison-pair', 'comparison-detail', 'comparison-job', 'review-list', 'review-controls',
        'requirements-draft-content', 'unranked-review-list', 'skipped-jobs']) byId(container).replaceChildren();
      updateReportActions();
      setFileStatus('Локальный запуск удалён.');
      openListener?.(null);
      return true;
    }
  };

  byId('open-demo').addEventListener('click', () => {
    if (runContext?.pending) return;
    const sequence = beginLoad();
    try {
      openReport(parseReport(window.RecruiterDemoReport), 'Открыт синтетический пример', 'example');
    } catch (error) {
      setFileStatus(error.message, true);
    } finally {
      finishLoad(sequence);
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
    const other = report?.jobs.filter(job => job !== activeJob)[Number(event.target.value)];
    if (activeJob && other) chooseComparison(activeJob, other);
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
