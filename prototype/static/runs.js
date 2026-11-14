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
  const inputCenter = byId('input-center');
  const showInputs = byId('show-inputs');
  const resumeInput = byId('resume-input');
  const vacanciesInput = byId('vacancies-input');
  const inspectInputs = byId('inspect-inputs');
  const analyzeInputs = byId('analyze-inputs');
  const liveDialog = byId('confirm-live');
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
  let inputLimits;
  let liveAvailable = false;
  let inspected = null;
  let inputBusy = false;
  let inputSequence = 0;
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

  async function openRun(id, revealReport = true) {
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
      if (revealReport) {
        setRunCenterOpen(false);
        setInputCenterOpen(false);
        byId('file-status').focus();
      }
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
        await openRun(context.id, false);
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
      run.mode === 'protected-live' ? 'Live · Защищённый анализ' : known(knownModes, run.mode, 'Локальный запуск'),
      known(knownScenarios, run.scenario, ''),
      Number.isFinite(created.getTime()) && run.created_at ? dateFormat.format(created) : ''
    ].filter(Boolean).join(' · ');
    const progress = Number.isSafeInteger(run.processed) && Number.isSafeInteger(run.total) && run.total > 0
      ? run.processed + ' из ' + run.total : '';
    const stage = isActive(run) ? known(stages, run.stage, '') : '';
    const state = known(states, run.state, 'Состояние недоступно');
    status.textContent = run.state === 'complete' && progress
      ? state + ' ' + progress
      : [state, stage, progress && 'Обработано ' + progress].filter(Boolean).join(' · ');
    content.append(title, status);
    if (run.error) {
      const failure = document.createElement('p');
      failure.className = 'support error';
      failure.textContent = window.NanimaiReport.describeFailure({code:run.error, stage:run.stage});
      content.append(failure);
    }

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

  function setRunCenterOpen(open) {
    center.hidden = !open;
    show.setAttribute('aria-expanded', String(open));
    if (open) {
      refreshRuns();
    } else {
      ++listSequence;
      clearTimeout(activeTimer);
    }
  }

  function setInputCenterOpen(open) {
    inputCenter.hidden = !open;
    showInputs.setAttribute('aria-expanded', String(open));
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

  function readInputFile(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.addEventListener('load', () => {
        const base64 = reader.result.slice(reader.result.indexOf(',') + 1);
        resolve({ name: file.name, content_base64: base64 });
      });
      reader.addEventListener('error', () => reject(new Error('Не удалось прочитать выбранный файл.')));
      reader.readAsDataURL(file);
    });
  }

  function clearInspection() {
    ++inputSequence;
    inspected = null;
    analyzeInputs.hidden = true;
    byId('inspected-files').replaceChildren();
    message('', false, 'inputs-message');
  }

  function displayInspection(result, count) {
    if (!Array.isArray(result?.files) || result.files.length !== count ||
        result.files.some(file => !['resume', 'vacancy'].includes(file?.role) ||
          !['ok', 'error'].includes(file.status) || !Number.isSafeInteger(file.index) || file.index <= 0)) {
      throw new Error('Сервер вернул неполную проверку документов.');
    }
    const list = byId('inspected-files');
    list.replaceChildren(...result.files.map(file => {
      const row = document.createElement('li');
      row.className = 'saved-run';
      const name = document.createElement('strong');
      name.textContent = file.role === 'resume' ? 'Резюме' : 'Вакансия ' + file.index;
      const details = document.createElement('span');
      details.className = file.status === 'error' ? 'support error' : 'support';
      const checked = Number.isSafeInteger(file.characters) && file.characters >= 0
        ? 'Текст извлечён · ' + file.characters + ' знаков' : 'Текст извлечён';
      const guidance = typeof file.action === 'string' && file.action.length <= 220 ? file.action : null;
      const code = typeof file.error === 'string' && /^[a-z0-9_]{1,64}$/.test(file.error) ? ' (' + file.error + ')' : '';
      details.textContent = file.status === 'ok' ? checked
        : guidance || 'Файл не прошёл проверку. Проверьте формат и содержимое.' + code;
      row.append(name, details);
      return row;
    }));
    if (result.ready === true && isRunId(result.input_id) && result.files.every(file => file.status === 'ok')) {
      inspected = { id: result.input_id, key: crypto.randomUUID() };
      analyzeInputs.hidden = !liveAvailable;
      const text = liveAvailable ? 'Документы проверены локально.' : 'Проверено локально. Внешний анализ выключен.';
      message(text, false, 'inputs-message');
    } else {
      message('Исправьте отмеченные документы и повторите проверку.', true, 'inputs-message');
    }
  }

  async function sendInspection() {
    if (inputBusy || !inputLimits) return;
    clearInspection();
    const sequence = inputSequence;
    const [resume] = resumeInput.files;
    const jobs = Array.from(vacanciesInput.files);
    if (!resume || !jobs.length || jobs.length + 1 > inputLimits.count) {
      message('Выберите одно резюме и от 1 до ' + (inputLimits.count - 1) + ' вакансий.', true, 'inputs-message');
      return;
    }
    const files = [resume, ...jobs];
    if (files.some(file => file.size > inputLimits.file) || files.reduce((sum, file) => sum + file.size, 0) > inputLimits.total) {
      message('Объём файлов превышает лимит. Уменьшите размер документов или их число.', true, 'inputs-message');
      return;
    }

    inputBusy = true;
    inspectInputs.disabled = true;
    message('Проверяем документы на локальном сервере…', false, 'inputs-message');
    try {
      const [cv, ...vacancies] = await Promise.all(files.map(readInputFile));
      if (sequence !== inputSequence) return;
      const result = await api.inspect({ resume: cv, jobs: vacancies });
      if (sequence === inputSequence) displayInspection(result, files.length);
    } catch (error) {
      if (sequence === inputSequence) message(error.message, true, 'inputs-message');
    } finally {
      inputBusy = false;
      inspectInputs.disabled = false;
    }
  }

  async function startProtected() {
    liveDialog.close();
    if (!liveAvailable || !inspected || inputBusy) return;
    const input = inspected;
    inputBusy = true;
    analyzeInputs.disabled = true;
    inspectInputs.disabled = true;
    message('Создаём защищённый запуск…', false, 'inputs-message');
    try {
      const run = await api.start({ mode: 'protected-live', input_id: input.id, budget: 1, idempotency_key: input.key });
      if (!isRunId(run?.run_id)) throw new Error('Идентификатор созданного запуска недоступен.');
      if (inspected === input) {
        resumeInput.value = '';
        vacanciesInput.value = '';
        clearInspection();
        message('Защищённый запуск создан.', false, 'inputs-message');
      }
      if (!show.hidden) setRunCenterOpen(true);
    } catch (error) {
      if (inspected === input) message(error.message, true, 'inputs-message');
    } finally {
      inputBusy = false;
      analyzeInputs.disabled = false;
      inspectInputs.disabled = false;
    }
  }

  showInputs.addEventListener('click', () => setInputCenterOpen(inputCenter.hidden));
  resumeInput.addEventListener('change', clearInspection);
  vacanciesInput.addEventListener('change', clearInspection);
  inspectInputs.addEventListener('click', sendInspection);
  analyzeInputs.addEventListener('click', () => {
    if (inspected && liveAvailable && !inputBusy) liveDialog.showModal();
  });
  byId('dismiss-live').addEventListener('click', () => liveDialog.close());
  byId('submit-live').addEventListener('click', startProtected);

  show.addEventListener('click', () => setRunCenterOpen(center.hidden));
  reload.addEventListener('click', refreshRuns);
  start.addEventListener('click', startRun);
  for (const button of document.querySelectorAll('[data-dismiss-dialog]')) {
    button.addEventListener('click', () => button.closest('dialog').close());
  }
  byId('save-review').addEventListener('click', () => reviewDialog.close('confirm'));
  removal.addEventListener('close', () => { toRemove = null; });
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
      if (operations.has('inspect')) {
        const count = capabilities.max_files;
        const file = capabilities.max_file_bytes;
        const total = capabilities.max_total_bytes;
        if ([count, file, total].every(Number.isSafeInteger) && count >= 2 && file > 0 && total >= file) {
          inputLimits = { count, file, total };
          byId('input-limits').textContent = 'Одно резюме и до ' + (count - 1) + ' вакансий. До ' +
            file / 1e6 + ' МБ на файл и ' + total / 1e6 + ' МБ суммарно.';
          showInputs.hidden = false;
          liveAvailable = operations.has('create') && capabilities.live === true &&
            Array.isArray(capabilities.modes) && capabilities.modes.includes('protected-live');
        }
      }
    } catch {
      // The offline viewer remains available when the service is absent or unreachable.
    }
  }

  initialize();
})();
