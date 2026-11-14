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
  const removal = byId('confirm-run-removal');
  const reviewDialog = byId('confirm-review');
  const inputCenter = byId('input-center');
  const showInputs = byId('show-inputs');
  const resumeInput = byId('resume-input');
  const vacanciesInput = byId('vacancies-input');
  const inspectInputs = byId('inspect-inputs');
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
  let inputLimits;
  let liveAvailable = false;
  let inspected = null;
  let inputBusy = false;
  let inputSequence = 0;
  let listSequence = 0;
  let activeTimer;
  let removalBusy = false;
  let toRemove = null;
  let activeRun = null;
  let trackedRunId = null;
  let openingResult = false;
  let autoOpenedId = null;
  let reportRetryAt = 0;
  let reportLoadError = '';
  let pendingRequest = null;
  try { const saved = sessionStorage.getItem('nanimai-analysis'); if (isRunId(saved)) trackedRunId = saved; } catch {}
  try {
    const saved = JSON.parse(sessionStorage.getItem('nanimai-pending-start'));
    if (isRunId(saved?.id) && typeof saved.key === 'string' && /^[a-f0-9-]{36}$/.test(saved.key)) pendingRequest = saved;
  } catch {}

  function rememberPending(value) {
    pendingRequest = value;
    try { if (value) sessionStorage.setItem('nanimai-pending-start', JSON.stringify(value)); else sessionStorage.removeItem('nanimai-pending-start'); } catch {}
  }

  async function acknowledgeStart() {
    const input = pendingRequest;
    try {
      const run = await api.start({mode:'protected-live',input_id:input.id,budget:1,idempotency_key:input.key});
      if (!isRunId(run?.run_id)) throw new Error('Не удалось подтвердить запуск. Нажмите «Проверить состояние».');
      rememberRun(run.run_id);
      rememberPending(null);
      inspected = null;
      autoOpenedId = null;
      reportRetryAt = 0;
      reportLoadError = '';
      message('', false, 'inputs-message');
      if (isActive(run)) watchRun(run);
      return run;
    } catch (error) {
      // These explicit rejections prove this key did not create a run.
      if (['busy','input_not_found','invalid_budget','invalid_request','live_disabled'].includes(error.code)) rememberPending(null);
      if (error.code === 'input_not_found') inspected = null;
      throw error;
    }
  }

  function rememberRun(id) {
    trackedRunId = id;
    try { if (id) sessionStorage.setItem('nanimai-analysis', id); else sessionStorage.removeItem('nanimai-analysis'); } catch {}
  }

  function updateInputControls() {
    const busy = inputBusy || !!activeRun;
    inspectInputs.disabled = busy || !liveAvailable;
    resumeInput.disabled = busy || !!pendingRequest;
    vacanciesInput.disabled = busy || !!pendingRequest;
    inspectInputs.textContent = inputBusy ? 'Запускаем…' : pendingRequest ? 'Проверить состояние' : 'Запустить анализ';
    showInputs.hidden = !inputLimits || !inputCenter.hidden || busy;
  }

  function watchRun(run) {
    if (trackedRunId !== run.run_id || !activeRun) viewer.beginAnalysis();
    rememberRun(run.run_id);
    activeRun = run;
    byId('active-analysis').hidden = !center.hidden;
    byId('active-analysis-title').textContent = 'Анализируем документы';
    message(known(stages, run.stage, 'Готовим анализ'), false, 'active-analysis-stage');
    const progress = byId('analysis-progress');
    progress.hidden = false;
    progress.max = run.total || 1;
    if (run.processed > 0) progress.value = run.processed;
    else progress.removeAttribute('value');
    const seconds = Math.max(0, Math.floor((Date.now() - new Date(run.created_at).getTime()) / 1000));
    const elapsed = Number.isFinite(seconds) ? ' · ' + Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2,'0') : '';
    byId('active-analysis-detail').textContent = 'Обработано ' + run.processed + ' из ' + run.total + elapsed + '. Отчёт откроется автоматически.';
    byId('cancel-analysis').hidden = false;
    byId('cancel-analysis').disabled = rowMutations.has(run.run_id);
    setInputCenterOpen(false);
    updateInputControls();
  }

  function showFailure(run) {
    activeRun = null;
    rememberRun(null);
    byId('active-analysis').hidden = false;
    byId('active-analysis-title').textContent = run.state === 'cancelled' ? 'Анализ отменён' : 'Анализ не завершён';
    byId('active-analysis-stage').textContent = window.NanimaiReport.describeFailure({code:run.error,stage:run.stage});
    byId('active-analysis-detail').textContent = resumeInput.files.length ? 'Файлы остались в форме. Можно повторить запуск.' : 'Выберите документы для нового анализа.';
    byId('analysis-progress').hidden = true;
    byId('cancel-analysis').hidden = true;
    setInputCenterOpen(true);
    updateInputControls();
  }

  async function cancelRun(id) {
    if (rowMutations.has(id)) return;
    rowMutations.add(id);
    if (activeRun?.run_id === id) byId('cancel-analysis').disabled = true;
    try { await api.cancel(id); message('Отменяем анализ…', false, 'active-analysis-stage'); }
    catch (error) { message(error.message, true, 'active-analysis-stage'); }
    finally { rowMutations.delete(id); refreshRuns(true); }
  }
  const rowMutations = new Set();
  const deletedRuns = new Set();

  function message(text, error = false, id = 'runs-message') {
    const node = byId(id);
    node.classList.toggle('error', error);
    node.textContent = text;
  }

  function contextFor(next, display) {
    const displayText = window.NanimaiReport.bindDisplayData(next, display);
    const context = { id: next.runId, revision: next.revision, displayText };
    if (operations.has('review')) {
      context.decide = (jobId, action, itemId) => saveDecision(context, jobId, action, itemId);
    }
    return context;
  }

  async function reportContext(next) {
    return contextFor(next, await api.displayData(next.runId));
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
      const context = await reportContext(next);
      if (deletedRuns.has(id) || !viewer.isLatest(sequence)) return false;
      viewer.openServerReport(next, context);
      autoOpenedId = id;
      reportLoadError = '';
      message('');
      if (trackedRunId === id) { rememberRun(null); activeRun = null; }
      byId('active-analysis').hidden = true;
      updateInputControls();
      if (revealReport) {
        setRunCenterOpen(false);
        setInputCenterOpen(false);
        byId('file-status').focus();
      }
      return true;
    } catch (error) {
      if (viewer.isLatest(sequence)) {
        reportLoadError = error.message;
        reportRetryAt = Date.now() + 10000;
        if (trackedRunId === id) setRunCenterOpen(true);
        message(reportLoadError, true);
      }
      return false;
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
      let updatedContext, savedMessage = 'Решение сохранено.';
      try { updatedContext = await reportContext(next); }
      catch {
        // The write already succeeded. Missing/stale decoration cannot undo
        // it or leave the old revision looking as if nothing was saved.
        updatedContext = contextFor(next, null);
        savedMessage = 'Решение сохранено. Обновите запуск для актуальной расшифровки.';
      }
      if (viewer.getContext() === context) {
        viewer.openServerReport(next, updatedContext);
        message(savedMessage, false, 'review-message');
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
    title.textContent = 'Анализ резюме' + (Number.isFinite(created.getTime()) && run.created_at ? ' · ' + dateFormat.format(created) : '');
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
      actions.append(makeButton('Отменить', () => cancelRun(run.run_id), rowMutations.has(run.run_id)));
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

  async function refreshRuns(force = false) {
    if (!operations.has('list') || (!force && center.hidden && !trackedRunId && !activeRun)) return;
    const sequence = ++listSequence;
    clearTimeout(activeTimer);
    try {
      const result = await api.list();
      if (sequence !== listSequence) return;
      if (!Array.isArray(result?.runs)) throw new Error('История анализов недоступна.');
      const runs = result.runs.filter(run => isRunId(run?.run_id) && run.mode === 'protected-live');
      const list = byId('saved-runs');
      const focused = document.activeElement;
      const focusedId = focused.closest('li')?.dataset.runId;
      const focusText = focusedId ? focused.textContent : null;
      list.replaceChildren(...runs.map(renderRun));
      if (focusedId && !center.hidden) {
        const row = Array.from(list.children).find(item => item.dataset.runId === focusedId);
        const target = Array.from(row?.querySelectorAll('button') ?? []).find(button => button.textContent === focusText) ?? reload;
        target.focus({ preventScroll: true });
      }
      const pending = !pendingRequest && (runs.find(run => run.run_id === trackedRunId && isActive(run)) || runs.find(isActive));
      if (pending) watchRun(pending);
      else {
        activeRun = null;
        updateInputControls();
        const completed = runs.find(run => run.run_id === trackedRunId);
        if (completed && !openingResult) {
          if (completed.report_available && completed.processed > 0 && autoOpenedId !== completed.run_id && Date.now() >= reportRetryAt) {
            openingResult = true;
            try { await openRun(completed.run_id); } finally { openingResult = false; }
          } else if (!completed.processed) showFailure(completed);
        } else if (trackedRunId && !completed) rememberRun(null);
      }
      if (sequence !== listSequence) return;
      if (!center.hidden) message(reportLoadError || (runs.length ? '' : 'Здесь появятся ваши анализы.'), !!reportLoadError);
      if (pending || trackedRunId) activeTimer = setTimeout(() => refreshRuns(true), 1500);
    } catch (error) {
      if (sequence === listSequence) {
        message(error.message, true, trackedRunId ? 'active-analysis-stage' : 'runs-message');
        if (trackedRunId || !center.hidden) activeTimer = setTimeout(() => refreshRuns(true), 3000);
      }
    }
  }

  function setRunCenterOpen(open) {
    center.hidden = !open;
    show.setAttribute('aria-expanded', String(open));
    if (open) {
      viewer.beginAnalysis();
      setInputCenterOpen(false);
      byId('active-analysis').hidden = true;
      refreshRuns();
    } else {
      if (!trackedRunId && !activeRun) { ++listSequence; clearTimeout(activeTimer); }
      if (activeRun) byId('active-analysis').hidden = false;
      else if (byId('report-workspace').hidden) setInputCenterOpen(true);
    }
  }

  function setInputCenterOpen(open) {
    inputCenter.hidden = !open;
    showInputs.setAttribute('aria-expanded', String(open));
    showInputs.hidden = open || !!activeRun || !inputLimits;
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
    list.replaceChildren(...result.files.filter(file => file.status === 'error').map(file => {
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
      message('Документы прочитаны. Запускаем анализ…', false, 'inputs-message');
    } else {
      message('Исправьте отмеченные документы и повторите проверку.', true, 'inputs-message');
    }
  }

  async function submitAnalysis() {
    if (inputBusy || activeRun || !inputLimits || !liveAvailable) return;
    if (pendingRequest) {
      inputBusy = true;
      updateInputControls();
      try { await acknowledgeStart(); }
      catch (error) { message(error.message, true, 'inputs-message'); }
      finally { inputBusy = false; updateInputControls(); await refreshRuns(true); }
      return;
    }
    const [resume] = resumeInput.files;
    const jobs = Array.from(vacanciesInput.files);
    if (!resume || !jobs.length || jobs.length + 1 > inputLimits.count) {
      message('Выберите одно резюме и от 1 до ' + (inputLimits.count - 1) + ' вакансий.', true, 'inputs-message');
      return;
    }
    const files = [resume, ...jobs];
    if (files.some(file => file.size > inputLimits.file) || files.reduce((sum,file) => sum + file.size,0) > inputLimits.total) {
      message('Объём файлов превышает лимит. Уменьшите размер документов или их число.', true, 'inputs-message');
      return;
    }
    inputBusy = true;
    updateInputControls();
    viewer.beginAnalysis();
    byId('active-analysis').hidden = true;
    setRunCenterOpen(false);
    const sequence = inputSequence;
    try {
      if (!inspected) {
        message('Читаем и проверяем документы…', false, 'inputs-message');
        const [cv, ...vacancies] = await Promise.all(files.map(readInputFile));
        if (sequence !== inputSequence) return;
        displayInspection(await api.inspect({resume:cv,jobs:vacancies}), files.length);
      }
      if (!inspected || sequence !== inputSequence) return;
      rememberPending({id:inspected.id,key:inspected.key});
      message('Запускаем анализ…', false, 'inputs-message');
      await acknowledgeStart();
      await refreshRuns(true);
    } catch (error) {
      if (error.code === 'input_not_found') inspected = null;
      message(error.message, true, 'inputs-message');
      // The opaque pending key survives network failure and reload. A list
      // entry alone cannot prove that this particular request was accepted.
      await refreshRuns(true);
    } finally {
      inputBusy = false;
      updateInputControls();
    }
  }

  showInputs.addEventListener('click', () => {
    if (activeRun) { byId('active-analysis').scrollIntoView({behavior:'smooth'}); return; }
    viewer.beginAnalysis();
    byId('active-analysis').hidden = true;
    setRunCenterOpen(false);
    setInputCenterOpen(true);
  });
  resumeInput.addEventListener('change', clearInspection);
  vacanciesInput.addEventListener('change', clearInspection);
  inspectInputs.addEventListener('click', submitAnalysis);
  byId('cancel-analysis').addEventListener('click', () => { if (activeRun) cancelRun(activeRun.run_id); });

  show.addEventListener('click', () => setRunCenterOpen(center.hidden));
  reload.addEventListener('click', refreshRuns);
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
      reload.hidden = !operations.has('list');
      show.hidden = reload.hidden;
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
          setInputCenterOpen(true);
          updateInputControls();
          if (!liveAvailable) message('Анализ временно недоступен. Проверьте подключение модели на сервере.', true, 'inputs-message');
        }
      }
      if (pendingRequest && liveAvailable) {
        inputBusy = true;
        updateInputControls();
        try { await acknowledgeStart(); }
        catch (error) { message(error.message, true, 'inputs-message'); }
        finally { inputBusy = false; updateInputControls(); }
      }
      await refreshRuns(true);
    } catch {
      setInputCenterOpen(true);
      inspectInputs.disabled = true;
      message('Не удалось соединиться с сервером. Обновите страницу.', true, 'inputs-message');
    }
  }

  initialize();
})();
