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
  const analyzeMock = byId('analyze-mock-inputs');
  const liveDialog = byId('confirm-live');
  const uploadMock = 'synthetic-upload-mock';
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
    starting: 'Подготовка запуска', parsing: 'Чтение документов', validating_inputs: 'Проверка входных данных',
    privacy_startup: 'Подготовка локальной защиты', privacy: 'Локальная защита текста',
    facts: 'Извлечение фактов', requirements: 'Чтение требований',
    evaluation: 'Сопоставление требований', job_finished: 'Вакансия обработана',
    analysis_finished: 'Подготовка отчёта', export: 'Сохранение отчёта'
  };
  const runErrors = {
    privacy_models_missing_or_invalid: 'Проверьте установку локальных весов NER.',
    openai_key_missing: 'Внешний анализ требует настройки сервера.',
    budget_limit: 'Достигнут лимит бюджета.', deadline_exceeded: 'Время обработки истекло.',
    interrupted: 'Сервер перезапустился во время обработки.'
  };
  const dateFormat = new Intl.DateTimeFormat('ru', { dateStyle: 'medium', timeStyle: 'short' });

  let operations = new Set();
  let pendingStart = null;
  let inputLimits;
  let liveAvailable = false;
  let mockAvailable = false;
  let inspected = null;
  let inputBusy = false;
  let inputSequence = 0;
  let startBusy = false;
  let listSequence = 0;
  let activeTimer;
  let activeRunsSeen = false;
  let removalBusy = false;
  let toRemove = null;
  const rowMutations = new Set();
  const cancelPending = new Set();
  const deletedRuns = new Set();

  function addressRun(id) {
    const url = new URL(location.href);
    if (id) url.searchParams.set('run', id);
    else url.searchParams.delete('run');
    history.replaceState(null, '', url);
  }

  viewer.onOpen(context => addressRun(context?.id));

  function message(text, error = false, id = 'runs-message') {
    const node = byId(id);
    delete node.dataset.listStatus;
    node.classList.toggle('error', error);
    node.textContent = text;
  }

  function reportContext(next) {
    const context = { id: next.runId, revision: next.revision };
    if (operations.has('review')) {
      context.decide = (jobId, action, itemId) => saveDecision(context, jobId, action, itemId);
    }
    if (operations.has('compare')) context.compare = (a, b) => api.comparison(context.id, a, b);
    return context;
  }

  async function openRun(id, revealReport = true, reviewWarning = null) {
    if (deletedRuns.has(id)) return;
    const sequence = viewer.beginLoad();
    viewer.status('Читаем отчёт запуска…');
    try {
      const source = await api.report(id, MAX_REPORT_BYTES);
      const next = parseReport(source);
      if (next.runId !== id || !next.revision) throw new Error('Версия отчёта запуска недоступна.');
      if (deletedRuns.has(id) || !viewer.isLatest(sequence)) return;
      viewer.openServerReport(next, reportContext(next));
      message('Открыт отчёт запуска.');
      if (reviewWarning) message(reviewWarning, true, 'review-message');
      if (revealReport) {
        setRunCenterOpen(false);
        setInputCenterOpen(false);
        byId('file-status').focus();
      }
    } catch (error) {
      if (viewer.isLatest(sequence)) viewer.status(error.message, true);
    }
  }

  async function saveDecision(context, jobId, action, itemId) {
    if (viewer.getContext() !== context || context.pending || !Object.hasOwn(confirmation, action)) return;
    const sequence = viewer.loadVersion();
    const isCurrent = () => viewer.isLatest(sequence) && viewer.getContext() === context;
    const text = confirmation[action];
    context.pending = true;
    try {
      if ((text && !await confirmReview(text)) || !isCurrent()) return;
      message('Сохраняем решение…', false, 'review-message');
      const decision = { expected_revision: context.revision, job_id: jobId, action, item_id: itemId };
      const key = JSON.stringify(decision);
      if (context.retry?.key !== key) context.retry = { key, id: crypto.randomUUID() };
      const { report } = await api.review(context.id, { ...decision, idempotency_key: context.retry.id });
      const next = parseReport(JSON.stringify(report));
      if (next.runId !== context.id || !next.revision) throw new Error('Версия отчёта запуска недоступна.');
      if (isCurrent()) {
        viewer.openServerReport(next, reportContext(next));
        message('Решение сохранено.', false, 'review-message');
      }
      refreshRuns();
    } catch (error) {
      if (!isCurrent()) return;
      if (error.status === 409 && error.code === 'stale_revision') {
        const warning = 'Версия отчёта изменилась. Проверьте текущую запись и повторите действие.';
        await openRun(context.id, false, warning);
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
      run.mode === 'protected-live' ? 'Live · Защищённый анализ' : run.mode === uploadMock
        ? 'Mock SDK · Загруженная синтетика' : known(knownModes, run.mode, 'Режим не распознан'),
      known(knownScenarios, run.scenario, ''),
      Number.isFinite(created.getTime()) && run.created_at ? dateFormat.format(created) : ''
    ].filter(Boolean).join(' · ');
    const progress = Number.isSafeInteger(run.processed) && Number.isSafeInteger(run.total) && run.total > 0
      ? run.processed + ' из ' + run.total : '';
    const stage = isActive(run) ? known(stages, run.stage, '') : '';
    const state = known(states, run.state, 'Состояние недоступно');
    status.textContent = run.state === 'complete' && progress
      ? state + ' ' + progress
      : [run.cancel_requested && isActive(run) ? 'Ожидается отмена' : state, stage,
        progress && 'Обработано ' + progress, known(runErrors, run.error, '')].filter(Boolean).join(' · ');
    content.append(title, status);

    const actions = document.createElement('div');
    actions.className = 'run-actions';
    if (operations.has('read') && run.report_available === true) {
      actions.append(makeButton('Открыть отчёт', () => openRun(run.run_id)));
    }
    if (operations.has('cancel') && isActive(run)) {
      const cancellation = run.cancel_requested || cancelPending.has(run.run_id);
      const cancel = makeButton(cancellation ? 'Отмена запрошена' : 'Отменить запуск', async () => {
        if (rowMutations.has(run.run_id)) return;
        rowMutations.add(run.run_id);
        cancel.disabled = true;
        try {
          const updated = await api.cancel(run.run_id);
          if (!isActive(updated)) {
            message('Обработка уже завершилась. Проверьте состояние запуска.');
            return;
          }
          cancelPending.add(run.run_id);
          message(run.mode === 'protected-live'
            ? 'Отмена запрошена. Уже отправленный запрос может быть оплачен.' : 'Отмена запрошена.');
        } catch (error) {
          message(error.message, true);
        } finally {
          rowMutations.delete(run.run_id);
          refreshRuns();
        }
      }, cancellation || rowMutations.has(run.run_id));
      actions.append(cancel);
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
    const status = byId('runs-message');
    if (status.textContent === '' || status.dataset.listStatus === 'true') {
      message('Загружаем список запусков…');
      status.dataset.listStatus = 'true';
    }
    byId('saved-runs').setAttribute('aria-busy', 'true');
    try {
      const result = await api.list();
      if (sequence !== listSequence || center.hidden) return;
      if (!Array.isArray(result?.runs)) throw new Error('Список запусков недоступен.');
      const runs = result.runs.filter(run => isRunId(run?.run_id));
      byId('saved-runs').removeAttribute('aria-busy');
      for (const run of runs) if (!isActive(run)) cancelPending.delete(run.run_id);
      const list = byId('saved-runs');
      const focused = document.activeElement;
      const focusedId = focused.closest('li')?.dataset.runId;
      const focusText = focusedId ? focused.textContent : null;
      const existing = new Map(Array.from(list.children, row => [row.dataset.runId, row]));
      const rows = runs.map(run => {
        const signature = JSON.stringify([run, rowMutations.has(run.run_id), cancelPending.has(run.run_id)]);
        const prior = existing.get(run.run_id);
        if (prior?.dataset.signature === signature) return prior;
        const row = renderRun(run);
        row.dataset.signature = signature;
        return row;
      });
      for (const [index, row] of rows.entries()) {
        if (list.children[index] !== row) list.insertBefore(row, list.children[index] ?? null);
      }
      while (list.children.length > rows.length) list.lastElementChild.remove();
      if (focusedId) {
        const row = Array.from(list.children).find(item => item.dataset.runId === focusedId);
        const target = Array.from(row?.querySelectorAll('button') ?? []).find(button => button.textContent === focusText)
          ?? row?.querySelector('button') ?? reload;
        target.focus({ preventScroll: true });
      }
      if (runs.length === 0 && !startBusy && !rowMutations.size) {
        message('Сохранённых запусков пока нет.');
        status.dataset.listStatus = 'true';
      } else if (status.dataset.listStatus === 'true') {
        message('');
      }
      activeRunsSeen = runs.some(isActive);
      if (activeRunsSeen) activeTimer = setTimeout(refreshRuns, 1000);
    } catch (error) {
      if (sequence === listSequence && !center.hidden) {
        byId('saved-runs').removeAttribute('aria-busy');
        message(error.message, true);
        status.dataset.listStatus = 'true';
        if (activeRunsSeen) activeTimer = setTimeout(refreshRuns, 2000);
      }
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

  function setUploadBusy(busy) {
    inputBusy = busy;
    for (const input of [resumeInput, vacanciesInput, inspectInputs, analyzeInputs, analyzeMock]) input.disabled = busy;
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
      activeRunsSeen = true;
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
    analyzeMock.hidden = true;
    byId('inspected-files').replaceChildren();
    message('', false, 'inputs-message');
  }

  function displayInspection(result, files) {
    if (!Array.isArray(result?.files) || result.files.length !== files.length ||
        result.files.some((file, index) => file?.role !== (index === 0 ? 'resume' : 'vacancy') ||
          file.index !== Math.max(index, 1) || !['ok', 'error'].includes(file.status))) {
      throw new Error('Сервер вернул неполную проверку документов.');
    }
    const list = byId('inspected-files');
    list.replaceChildren(...result.files.map((file, index) => {
      const row = document.createElement('li');
      row.className = 'saved-run';
      const name = document.createElement('strong');
      name.textContent = (file.role === 'resume' ? 'Резюме' : 'Вакансия ' + file.index) + ' · ' + files[index].name;
      const details = document.createElement('span');
      details.className = file.status === 'error' ? 'support error' : 'support';
      const checked = Number.isSafeInteger(file.characters) && file.characters >= 0
        ? 'Текст извлечён · ' + file.characters + ' знаков' : 'Текст извлечён';
      const guidance = typeof file.action === 'string' && file.action.length <= 220 ? file.action : null;
      const reason = typeof file.reason === 'string' && file.reason.length <= 220 ? file.reason : null;
      const code = typeof file.error === 'string' && /^[a-z0-9_]{1,64}$/.test(file.error) ? ' (' + file.error + ')' : '';
      details.textContent = file.status === 'ok' ? checked
        : [reason || 'Файл не прошёл проверку' + code + '.', guidance].filter(Boolean).join(' ');
      row.append(name, details);
      return row;
    }));
    if (result.ready !== true || result.files.some(file => file.status !== 'ok')) {
      message('Исправьте отмеченные документы и повторите проверку.', true, 'inputs-message');
      return;
    }
    if (isRunId(result.input_id)) {
      const mock = mockAvailable && ['success', 'disputed'].includes(result.mock_scenario);
      inspected = { id: result.input_id, mock, pending: null };
      analyzeMock.hidden = !mock;
      analyzeInputs.hidden = !liveAvailable;
    }
    message(inspected?.mock ? 'Учебный набор проверен. Mock SDK работает без внешних запросов.' :
      inspected && liveAvailable ? 'Документы проверены локально.' :
        'Документы прочитаны. Для них доступна локальная проверка чтения. Внешний анализ выключен.',
      false, 'inputs-message');
  }

  async function sendInspection() {
    if (inputBusy || !inputLimits) return;
    if (inspected?.pending) {
      message('Проверьте список запусков или повторите отправку проверенного набора.', true, 'inputs-message');
      return;
    }
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

    setUploadBusy(true);
    message('Проверяем документы на локальном сервере…', false, 'inputs-message');
    try {
      const [cv, ...vacancies] = await Promise.all(files.map(readInputFile));
      if (sequence !== inputSequence) return;
      const result = await api.inspect({ resume: cv, jobs: vacancies });
      if (sequence === inputSequence) displayInspection(result, files);
    } catch (error) {
      if (sequence === inputSequence) message(error.message, true, 'inputs-message');
    } finally {
      setUploadBusy(false);
    }
  }

  async function startUploaded(mode) {
    if (!inspected || inputBusy || (mode === uploadMock ? !inspected.mock : !liveAvailable)) return;
    const input = inspected;
    if (input.pending && input.pending.mode !== mode) {
      message('Сначала повторите запрос в том же режиме или проверьте список запусков.', true, 'inputs-message');
      return;
    }
    input.pending ??= { mode, id: crypto.randomUUID() };
    setUploadBusy(true);
    message('Создаём защищённый запуск…', false, 'inputs-message');
    try {
      const data = { mode, input_id: input.id, idempotency_key: input.pending.id };
      if (mode === 'protected-live') data.budget = 1;
      const run = await api.start(data);
      if (!isRunId(run?.run_id)) throw new Error('Идентификатор созданного запуска недоступен.');
      if (inspected === input) {
        resumeInput.value = '';
        vacanciesInput.value = '';
        clearInspection();
        message('', false, 'inputs-message');
      }
      if (!show.hidden) {
        activeRunsSeen = true;
        setInputCenterOpen(false);
        message(mode === uploadMock ? 'Локальный запуск Mock SDK создан.' : 'Защищённый запуск Live создан.');
        setRunCenterOpen(true);
        reload.focus();
      }
    } catch (error) {
      if (inspected === input) {
        if (error.status >= 400 && error.status < 500 && error.status !== 408) input.pending = null;
        const hint = input.pending ? ' Повтор запроса в том же режиме использует тот же запуск.' : '';
        message(error.message + hint, true, 'inputs-message');
      }
    } finally {
      setUploadBusy(false);
    }
  }

  showInputs.addEventListener('click', () => {
    const open = inputCenter.hidden;
    setInputCenterOpen(open);
    if (open) resumeInput.focus();
  });
  resumeInput.addEventListener('change', clearInspection);
  vacanciesInput.addEventListener('change', clearInspection);
  inspectInputs.addEventListener('click', sendInspection);
  analyzeMock.addEventListener('click', () => startUploaded(uploadMock));
  analyzeInputs.addEventListener('click', () => {
    if (inspected && liveAvailable && !inputBusy) liveDialog.showModal();
  });
  byId('dismiss-live').addEventListener('click', () => liveDialog.close());
  byId('submit-live').addEventListener('click', () => {
    liveDialog.close();
    startUploaded('protected-live');
  });

  show.addEventListener('click', () => {
    const open = center.hidden;
    setRunCenterOpen(open);
    if (open) (reload.hidden ? type : reload).focus();
  });
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
      const closed = viewer.closeServerReport(id);
      message('Запуск удалён.');
      if (closed) {
        reload.focus();
      }
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
    const requested = new URL(location.href).searchParams.get('run');
    const initialView = viewer.beginLoad();
    const serviceStatus = byId('service-status');
    try {
      const capabilities = await api.session();
      if (!capabilities || !Array.isArray(capabilities.operations)) throw new Error('Локальный сервис недоступен.');
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
            file / 1e6 + ' МБ на файл и ' + new Intl.NumberFormat('ru').format(total / 1e6) + ' МБ суммарно.';
          showInputs.hidden = false;
          liveAvailable = operations.has('create') && capabilities.live === true &&
            Array.isArray(capabilities.modes) && capabilities.modes.includes('protected-live');
          mockAvailable = operations.has('create') && Array.isArray(capabilities.modes) &&
            capabilities.modes.includes(uploadMock);
          byId('welcome-title').textContent = 'Загрузите резюме и вакансии';
          byId('welcome-copy').textContent = 'Откройте «Документы» для проверки файлов или «Запуски» для просмотра сохранённых отчётов.';
        }
      }
      if (requested !== null && viewer.isLatest(initialView)) {
        if (isRunId(requested) && operations.has('read')) await openRun(requested);
        else viewer.status('Запуск по этой ссылке недоступен.', true);
      }
    } catch {
      serviceStatus.hidden = false;
      serviceStatus.textContent = 'Локальный сервис недоступен. Можно открыть сохранённый отчёт или демо.';
    }
  }

  initialize();
})();
