(() => {
  'use strict';

  if (!['http:', 'https:'].includes(location.protocol)) return;
  const { createRunApi } = window.RecruiterRunApi;
  const { MAX_REPORT_BYTES, parseReport } = window.NanimaiReport;
  const viewer = window.RecruiterViewer;
  const api = createRunApi(window.fetch.bind(window));
  const byId = id => document.getElementById(id);
  const center = byId('run-center');
  const show = byId('show-runs');
  const reload = byId('reload-runs');
  const type = byId('run-type');
  const scenario = byId('run-scenario');
  const start = byId('start-run');
  const removal = byId('confirm-run-removal');
  const reviewDialog = byId('confirm-review');
  const knownModes = {
    'synthetic-replay': 'Синтетический replay',
    'synthetic-protected-mock': 'Защищённый Mock SDK'
  };
  const knownScenarios = {
    success: 'Подходящая вакансия', disputed: 'Спорный случай', incomplete: 'Неполный запуск'
  };
  const states = {
    queued: 'В очереди', running: 'Обрабатывается', complete: 'Обработано', partial: 'Обработано частично',
    failed: 'Сбой обработки', cancelled: 'Отменён', interrupted: 'Прерван'
  };
  const confirmation = {
    confirm_requirements: 'Подтвердить состав требований выбранной вакансии?',
    read_context: null,
    accept_condition: 'Принять это исключение по условиям для передачи? Конфликт останется в отчёте.',
    mark_for_handoff: 'Отметить вакансию для передачи? Оценки соответствия сохранятся.'
  };
  const isRunId = value => typeof value === 'string' && /^[0-9a-f]{32}$/.test(value);
  const isActive = run => run.state === 'queued' || run.state === 'running';
  const known = (options, value, fallback) => typeof value === 'string' && Object.hasOwn(options, value)
    ? options[value] : fallback;
  const stages = {
    parsing: 'Чтение документов', validating_inputs: 'Проверка входных данных',
    facts: 'Извлечение фактов', requirements: 'Чтение требований',
    evaluation: 'Сопоставление требований', analysis_finished: 'Подготовка отчёта', export: 'Сохранение отчёта'
  };
  const dateFormat = new Intl.DateTimeFormat('ru', { dateStyle: 'medium', timeStyle: 'short' });

  let operations = new Set();
  let pendingStart = null;
  let startBusy = false;
  let listSequence = 0;
  let activeTimer;
  let removalBusy = false;
  let toRemove = null;
  const rowMutations = new Set();
  const deletedRuns = new Set();

  function message(text, error = false, id = 'runs-message') {
    const node = byId(id);
    node.classList.toggle('error', error);
    node.textContent = text;
  }

  function reportContext(next) {
    const context = { id: next.runId, revision: next.revision };
    if (operations.has('review')) {
      context.decide = (jobId, action, itemId) => saveDecision(context, jobId, action, itemId);
    }
    return context;
  }

  async function openRun(id) {
    if (deletedRuns.has(id)) return;
    const sequence = viewer.beginLoad();
    message('Читаем отчёт запуска…');
    try {
      const response = await api.report(id);
      if (Number(response.headers.get('Content-Length')) > MAX_REPORT_BYTES) throw new Error('Отчёт слишком большой.');
      const source = await response.text();
      if (new Blob([source]).size > MAX_REPORT_BYTES) throw new Error('Отчёт слишком большой.');
      const next = parseReport(source);
      if (next.runId !== id || !next.revision) throw new Error('Версия отчёта запуска недоступна.');
      if (deletedRuns.has(id) || !viewer.isLatest(sequence)) return;
      viewer.openServerReport(next, reportContext(next));
      message('Открыт отчёт запуска.');
    } catch (error) {
      if (viewer.isLatest(sequence)) message(error.message, true);
    }
  }

  async function saveDecision(context, jobId, action, itemId) {
    if (viewer.getContext() !== context || context.pending || !Object.hasOwn(confirmation, action)) return;
    const text = confirmation[action];
    context.pending = true;
    if (text && !await confirmReview(text)) {
      context.pending = false;
      return;
    }
    if (viewer.getContext() !== context) return;
    message('Сохраняем решение…', false, 'review-message');
    try {
      const decision = { expected_revision: context.revision, job_id: jobId, action, item_id: itemId };
      const key = JSON.stringify(decision);
      if (context.retry?.key !== key) context.retry = { key, id: crypto.randomUUID() };
      const { report } = await api.review(context.id, { ...decision, idempotency_key: context.retry.id });
      const next = parseReport(JSON.stringify(report));
      if (next.runId !== context.id || !next.revision) throw new Error('Версия отчёта запуска недоступна.');
      if (viewer.getContext() === context) {
        viewer.openServerReport(next, reportContext(next));
        message('Решение сохранено.', false, 'review-message');
      }
      refreshRuns();
    } catch (error) {
      if (viewer.getContext() !== context) return;
      if (error.status === 409 && error.code === 'stale_revision') {
        await openRun(context.id);
        if (viewer.getContext()?.id === context.id) {
          message('Версия отчёта изменилась. Проверьте текущую запись и повторите действие.', true, 'review-message');
        }
      } else {
        message(error.message, true, 'review-message');
      }
    } finally {
      context.pending = false;
    }
  }

  function confirmReview(text) {
    byId('review-dialog-copy').textContent = text;
    reviewDialog.returnValue = '';
    reviewDialog.showModal();
    return new Promise(resolve => {
      reviewDialog.addEventListener('close', () => resolve(reviewDialog.returnValue === 'confirm'), { once: true });
    });
  }

  function makeButton(text, action, disabled = false) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'button button-secondary compact';
    button.textContent = text;
    button.disabled = disabled;
    button.addEventListener('click', action);
    return button;
  }

  function renderRun(run) {
    const item = document.createElement('li');
    item.dataset.runId = run.run_id;
    item.className = 'saved-run';
    const content = document.createElement('div');
    const title = document.createElement('strong');
    const status = document.createElement('p');
    status.className = 'support';
    const created = new Date(run.created_at);
    title.textContent = [
      known(knownModes, run.mode, 'Локальный запуск'),
      known(knownScenarios, run.scenario, ''),
      Number.isFinite(created.getTime()) && run.created_at ? dateFormat.format(created) : ''
    ].filter(Boolean).join(' · ');
    const progress = Number.isSafeInteger(run.processed) && Number.isSafeInteger(run.total) && run.total > 0
      ? ' · Обработано ' + run.processed + ' из ' + run.total : '';
    const stage = isActive(run) ? known(stages, run.stage, '') : '';
    status.textContent = known(states, run.state, 'Состояние недоступно') + (stage ? ' · ' + stage : '') + progress;
    content.append(title, status);

    const actions = document.createElement('div');
    actions.className = 'run-actions';
    if (operations.has('read') && run.report_available === true) {
      actions.append(makeButton('Открыть отчёт', () => openRun(run.run_id)));
    }
    if (operations.has('cancel') && isActive(run)) {
      actions.append(makeButton('Отменить запуск', async () => {
        if (rowMutations.has(run.run_id)) return;
        rowMutations.add(run.run_id);
        try {
          await api.cancel(run.run_id);
          message('Запрос на отмену отправлен.');
        } catch (error) {
          message(error.message, true);
        } finally {
          rowMutations.delete(run.run_id);
          refreshRuns();
        }
      }, rowMutations.has(run.run_id)));
    }
    if (operations.has('delete') && Object.hasOwn(states, run.state) && !isActive(run)) {
      actions.append(makeButton('Удалить', () => {
        toRemove = run.run_id;
        removal.showModal();
      }));
    }
    item.append(content, actions);
    return item;
  }

  async function refreshRuns() {
    if (!operations.has('list') || center.hidden) return;
    const sequence = ++listSequence;
    clearTimeout(activeTimer);
    try {
      const result = await api.list();
      if (sequence !== listSequence || center.hidden) return;
      if (!Array.isArray(result?.runs)) throw new Error('Список запусков недоступен.');
      const runs = result.runs.filter(run => isRunId(run?.run_id));
      const list = byId('saved-runs');
      const focused = document.activeElement;
      const focusedId = focused.closest('li')?.dataset.runId;
      const focusText = focusedId ? focused.textContent : null;
      list.replaceChildren(...runs.map(renderRun));
      if (focusedId) {
        const row = Array.from(list.children).find(item => item.dataset.runId === focusedId);
        const target = Array.from(row?.querySelectorAll('button') ?? []).find(button => button.textContent === focusText)
          ?? row?.querySelector('button') ?? reload;
        target.focus({ preventScroll: true });
      }
      if (runs.length === 0 && !startBusy && !rowMutations.size) message('Сохранённых запусков пока нет.');
      if (runs.some(isActive)) activeTimer = setTimeout(refreshRuns, 1000);
    } catch (error) {
      if (sequence === listSequence && !center.hidden) message(error.message, true);
    }
  }

  async function startRun() {
    if (startBusy) return;
    const mode = type.value;
    const selected = scenario.value;
    const key = mode + '/' + selected;
    if (!pendingStart || pendingStart.key !== key) pendingStart = { key, id: crypto.randomUUID() };
    startBusy = true;
    start.disabled = true;
    message('Создаём запуск…');
    try {
      const run = await api.start({ mode, scenario: selected, idempotency_key: pendingStart.id });
      if (!isRunId(run?.run_id)) throw new Error('Идентификатор созданного запуска недоступен.');
      pendingStart = null;
      message('Запуск создан.');
      refreshRuns();
    } catch (error) {
      message(error.message, true);
    } finally {
      startBusy = false;
      start.disabled = false;
    }
  }

  function setupOptions(select, available, labels) {
    for (const value of Array.isArray(available) ? available : []) {
      const label = known(labels, value);
      if (!label) continue;
      const option = document.createElement('option');
      option.value = value;
      option.textContent = label;
      select.append(option);
    }
  }

  show.addEventListener('click', () => {
    center.hidden = !center.hidden;
    show.setAttribute('aria-expanded', String(!center.hidden));
    if (center.hidden) {
      ++listSequence;
      clearTimeout(activeTimer);
    } else {
      refreshRuns();
    }
  });
  reload.addEventListener('click', refreshRuns);
  start.addEventListener('click', startRun);
  byId('dismiss-review').addEventListener('click', () => reviewDialog.close());
  byId('save-review').addEventListener('click', () => reviewDialog.close('confirm'));
  removal.addEventListener('close', () => { toRemove = null; });
  byId('dismiss-run-removal').addEventListener('click', () => removal.close());
  byId('remove-run').addEventListener('click', async event => {
    const id = toRemove;
    if (!id || removalBusy) return;
    removalBusy = true;
    event.target.disabled = true;
    try {
      await api.remove(id);
      deletedRuns.add(id);
      viewer.closeServerReport(id);
      message('Запуск удалён.');
    } catch (error) {
      message(error.message, true);
    } finally {
      removalBusy = false;
      event.target.disabled = false;
      removal.close();
      refreshRuns();
    }
  });

  async function initialize() {
    try {
      const capabilities = await api.session();
      if (!capabilities || !Array.isArray(capabilities.operations)) return;
      operations = new Set(capabilities.operations);
      setupOptions(type, capabilities.modes, knownModes);
      setupOptions(scenario, capabilities.scenarios, knownScenarios);
      const canCreate = operations.has('create') && type.options.length && scenario.options.length;
      byId('start-run-form').hidden = !canCreate;
      reload.hidden = !operations.has('list');
      show.hidden = !canCreate && reload.hidden;
    } catch {
      // The offline viewer remains available when the service is absent or unreachable.
    }
  }

  initialize();
})();
