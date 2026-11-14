(function (root) {
  'use strict';

  const commonJS = typeof module === 'object' && module.exports;
  const {
    describeRun, describeFit, scoreRange, assessments, mandatoryStates, evidenceLabel, evidenceNeedsReview,
    mandatoryLabel, mandatoryNeedsReview, requirementReviewLabel, createDisplayText, displayCopy
  } = commonJS ? require('./report.js') : root.NanimaiReport;

  const htmlEntities = {
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  };
  const briefTextLimit = 110;
  const escape = value => String(value).replace(/[&<>"']/g, character => htmlEntities[character]);

  function reference({ row, number }, includeStatus = false) {
    const status = includeStatus ? ' — ' + (row.scoreConflict ? 'Требует сверки' : assessments[row.status][0]) : '';
    return '<a href="#evidence-' + number + '">[' + number + '] ' + escape(shortText(row.label)) + '</a>' + status;
  }

  function shortText(text) {
    const label = text.replace(/\s+/g, ' ').trim();
    return label.length > briefTextLimit ? label.slice(0, briefTextLimit - 1) + '…' : label;
  }

  function summaryList(items, empty) {
    return items.length
      ? '<ul>' + items.map(item => '<li>' + item + '</li>').join('') + '</ul>'
      : '<p>' + empty + '</p>';
  }

  function riskText(item, showQuotes) {
    const { row } = item;
    const review = [
      mandatoryNeedsReview(row) ? mandatoryLabel(row) : null,
      evidenceNeedsReview(row) ? evidenceLabel(row) : null
    ].filter(Boolean).join('. ');
    const text = reference(item, true) + (review ? '. ' + review + '.' : '');
    if (!showQuotes || !row.resumeQuotes.length) return text;
    const quotes = row.resumeQuotes.map(quote => quote.replace(/\s+/g, ' ').trim());
    if (quotes.join(' ').length > 160) return text;
    return text + '<span class="fit-citation">Резюме ' +
      quotes.map(quote => '«' + escape(quote) + '»').join(' · ') + '</span>';
  }

  function profileSections(profile) {
    if (!profile.claims) {
      const message = profile.state === 'invalid' ? 'Не удалось проверить профиль.' : 'Профиль не извлечён.';
      return { brief: '<section id="candidate-profile" class="unavailable"><p><strong>Краткий профиль.</strong> ' +
        message + '</p></section>', sources: '' };
    }

    const claimPaths = Array.from(profile.claims.keys());
    const references = new Map();
    function cite(spans) {
      const snippets = spans.map(({ sentence, heading }) => heading ? heading + '\n' + sentence : sentence);
      const key = JSON.stringify(snippets);
      if (!references.has(key)) references.set(key, { number: references.size + 1, snippets });
      const number = references.get(key).number;
      const context = snippets.join(' / ').replace(/\s+/g, ' ').trim();
      const preview = context.length > briefTextLimit ? 'См. полный фрагмент' : '«' + escape(context) + '»';
      return preview + ' <a href="#profile-source-' + number + '" aria-label="Цитата ' +
        number + ' из резюме">[Р' + number + ']</a>';
    }

    const claimsIn = prefix => claimPaths.filter(path => path.startsWith(prefix))
      .sort((left, right) => left.localeCompare(right, 'ru', { numeric: true }));
    const summary = claimsIn('summary[').slice(0, 2).map(path => cite(profile.claims.get(path)));
    const stack = Array.from(new Set(claimsIn('stack[').slice(0, 6).map(path => cite(profile.claims.get(path)))));
    const position = profile.claims.get('last_position.role');
    const domain = profile.claims.get('last_position.domain');
    const period = profile.claims.get('last_position.period');
    const lastRole = position && period
      ? Array.from(new Set([cite(position), cite(period), domain ? cite(domain) : 'сфера не указана'])).join(' · ')
      : 'Не извлечена';
    const achievements = claimsIn('achievements[').filter(path => path.endsWith('.action')).slice(0, 2).map(path => {
      const result = profile.claims.get(path.replace(/\.action$/, '.result'));
      const action = cite(profile.claims.get(path));
      const outcome = result ? cite(result) : 'Результат не указан';
      return action === outcome ? action : action + ' · ' + outcome;
    });
    const fields = [
      ['Специализация и опыт', summary.join(' · ') || 'Не извлечены'],
      ['Стек в контексте резюме', stack.join(' · ') || 'Не извлечён'],
      ['Последняя роль, сфера и период', lastRole],
      ['Достижения и результаты', achievements.join('<br>') || 'Не извлечены']
    ];
    const note = profile.state === 'needs_review'
      ? '<p class="state">Часть сведений профиля требует сверки с резюме.</p>' : '';
    const details = fields.map(([title, value]) => '<div><dt>' + title + '</dt><dd>' + value + '</dd></div>').join('');
    const sources = Array.from(references.values(), ({ number, snippets }) =>
      '<div id="profile-source-' + number + '"><dt>Р' + number + '</dt><dd>' +
      snippets.map(text => '<blockquote>' + escape(text) + '</blockquote>').join('') + '</dd></div>').join('');
    return {
      brief: '<section id="candidate-profile"><h2>Краткий профиль</h2>' + note + '<dl>' + details + '</dl></section>',
      sources: sources ? '<section class="evidence"><h2>Цитаты к профилю</h2>' +
        '<dl class="profile-sources">' + sources + '</dl></section>' : ''
    };
  }

  const conditionStatus = {
    conflict: 'Возможный конфликт', compatible: 'Условия совпадают по отчёту',
    unknown: 'Нужно уточнить', invalid: 'Не удалось проверить'
  };

  function conditionsSection(conditions) {
    if (conditions.state === 'missing') return '<section id="conditions" class="unavailable">' +
      '<p><strong>Условия для HR.</strong> Условия не сравнивались.</p></section>';
    const heading = '<section id="conditions"><h2>Условия для HR</h2>';
    if (!conditions.items.length) {
      const message = conditions.state === 'invalid'
        ? 'Не удалось проверить условия.' : 'В отчёте нет условий для сравнения.';
      return heading + '<p>' + message + '</p></section>';
    }

    function quote(source, unresolved) {
      if (source) return '«' + escape(source.heading ? source.heading + ' · ' + source.sentence : source.sentence) + '»';
      return unresolved ? 'Не удалось привязать цитату' : 'Сведения не указаны';
    }
    const ordered = [...conditions.items.filter(item => item.state === 'conflict'),
      ...conditions.items.filter(item => item.state !== 'conflict')];
    const items = ordered.map(({ label, state, cv, vacancy, needsReview, cvUnresolved, vacancyUnresolved }) => {
      const flag = state === 'conflict' ? ' class="condition-conflict"' : '';
      const sources = state === 'invalid' ? '' : '<p><span>Резюме</span> ' + quote(cv, cvUnresolved) +
        '</p><p><span>Вакансия</span> ' + quote(vacancy, vacancyUnresolved) + '</p>';
      const status = conditionStatus[state] + (state === 'conflict' && needsReview ? ' · Нужна ручная сверка' : '');
      return '<div' + flag + '><h3>' + label + ' <span>· ' + status + '</span></h3>' + sources + '</div>';
    }).join('');
    const note = conditions.state === 'invalid'
      ? '<p class="state">Часть условий не удалось проверить.</p>' : '';
    return heading + '<p class="state">Решение по условиям принимает HR.</p>' + note +
      '<div class="condition-list">' + items + '</div></section>';
  }

  function quoteGroup(title, quotes, empty = '') {
    return '<h4>' + title + '</h4>' + (quotes.length
      ? quotes.map(quote => '<blockquote>' + escape(quote) + '</blockquote>').join('')
      : '<p>' + empty + '</p>');
  }

  function evidenceItem({ row, number }) {
    const mandatoryQuote = row.mandatoryQuote && row.mandatoryQuote !== row.requirementQuote
      ? quoteGroup('Фрагмент об обязательности', [row.mandatoryQuote]) : '';
    const title = row.label === row.requirementQuote ? 'Требование' : shortText(row.label);
    return '<article id="evidence-' + number + '"><h3>[' + number + '] ' + escape(title) + '</h3>' +
      '<p class="state"><strong>' + assessments[row.status][0] + '</strong> · ' + mandatoryLabel(row) +
      ' · ' + evidenceLabel(row) + '</p>' +
      quoteGroup('Фрагмент вакансии', [row.requirementQuote]) + mandatoryQuote +
      quoteGroup('Фрагменты резюме', row.resumeQuotes, 'В отчёте нет подтверждающей цитаты.') +
      '</article>';
  }

  function provenance(report, job, run) {
    const fields = [
      ['Источник', [run.mode, run.modeDetail, run.scenario].filter(Boolean).join(' · ')],
      ['Модель', report.model ?? (report.mode === 'synthetic_replay_NOT_model_output'
        ? 'Не вызывалась' : 'Не указана')],
      ['Методика оценки', job.score.policyVersion ?? 'Не указана'],
      ['SHA-256 резюме после обработки', report.resumeDigest],
      ['SHA-256 вакансии после обработки', job.sourceDigest],
      ['SHA-256 модели', report.modelDigest],
      ['SHA-256 методики', job.policyDigest]
    ];
    const rows = fields.filter(([, value]) => value != null).map(([label, value]) =>
      '<div><dt>' + label + '</dt><dd' + (label.startsWith('SHA-256') ? ' class="digest"' : '') +
      '>' + escape(value) + '</dd></div>');
    return '<section class="provenance"><h2>Источник и версии</h2><dl>' + rows.join('') + '</dl></section>';
  }

  const styles = `
    :root { color-scheme: light; font-family: "Inter", "Segoe UI", system-ui, sans-serif; color: #1d1d1d; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #fafafa; font-size: 15px; line-height: 1.52; }
    main { width: min(100% - 32px, 840px); margin: 28px auto; padding: clamp(20px, 5vw, 48px);
      background: #fff; border: 1px solid #dfdfe0; border-radius: 12px; overflow-wrap: anywhere; }
    h1, h2, h3, h4, p { margin: 0; }
    h1 { font-size: clamp(25px, 5vw, 38px); line-height: 1.1; letter-spacing: -.04em; }
    h2 { font-size: 1.13em; line-height: 1.3; }
    h3 { font-size: 1.04em; }
    h4 { font-size: .88em; margin-top: .7em; }
    p { margin-top: .35em; }
    a { color: #4d61f4; text-underline-offset: .16em; }
    a:focus-visible { outline: 2px solid #4d61f4; outline-offset: 3px; }
    article:target, .profile-sources > div:target { background: #eef0ff; }
    .eyebrow, .state, .provenance { color: #6b6b6b; font-size: .88em; }
    .eyebrow { margin: 0 0 8px; font-weight: 700; }
    .vacancy { font-size: 1.25em; margin-top: 13px; font-weight: 680; }
    .run-state { padding: 8px 12px; border-left: 3px solid #4d61f4; background: #eef0ff;
      margin: 0 0 14px; font-weight: 650; }
    .incomplete { border-color: #805000; background: #fff3da; color: #634000; }
    .print-toolbar { display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
      flex-wrap: wrap; margin-bottom: 16px; }
    .print-toolbar p { margin: 0; color: #6b6b6b; font-size: .88em; }
    .print-toolbar button { font: inherit; color: #394cce; background: #fff; cursor: pointer;
      border: 1px solid #d7dbfc; border-radius: 7px; padding: 6px 12px; }
    .print-toolbar button:focus-visible { outline: 2px solid #4d61f4; outline-offset: 3px; }
    .print-toolbar button:hover { background: #eef3ff; }
    .recommendation { padding-block: 13px; border-block: 1px solid #dfdfe0; }
    .recommendation h3 { margin-top: .6em; }
    .fit-verdict { font-size: 1.15em; font-weight: 720; }
    .fit-notes { margin-top: .45em; }
    .fit-citation { display: block; color: #6b6b6b; font-size: .9em; }
    .unavailable { margin-top: 8px; color: #6b6b6b; font-size: .88em; }
    .condition-list > div { margin-top: 8px; padding: 6px 10px; border-left: 2px solid #dfdfe0; }
    .condition-list .condition-conflict { border-color: #805000; background: #fff3da; }
    .condition-conflict h3 { color: #634000; }
    .condition-list p { margin-top: .15em; white-space: pre-wrap; }
    .condition-list p span { font-weight: 650; }
    section { margin-top: 19px; }
    ul, ol { padding-left: 1.35em; margin: .38em 0 0; }
    li + li { margin-top: .35em; }
    .evidence, .provenance { border-top: 1px solid #dfdfe0; padding-top: 12px; }
    article { padding-block: 10px; }
    article + article { border-top: 1px solid #dfdfe0; }
    blockquote { margin: .3em 0 0; padding-left: .75em; border-left: 2px solid #c8cffc;
      white-space: pre-wrap; overflow-wrap: anywhere; }
    dl { display: grid; gap: 5px; margin: .45em 0 0; }
    dl div { display: grid; grid-template-columns: minmax(8em, 1fr) minmax(0, 2fr); gap: 8px; }
    .profile-sources > div { grid-template-columns: 2em minmax(0, 1fr); }
    .profile-sources blockquote:first-child { margin-top: 0; }
    dt { font-weight: 650; }
    dd { margin: 0; }
    .digest { font: .91em "IBM Plex Mono", ui-monospace, monospace; overflow-wrap: anywhere; }
    @page { size: A4; margin: 12mm 15mm; }
    @media print {
      body { margin: 0; background: #fff; font-size: 10.5pt; line-height: 1.35; }
      main { width: auto; margin: 0; padding: 0; border: 0; border-radius: 0; }
      .print-toolbar { display: none; }
      h1 { font-size: 22pt; letter-spacing: normal; }
      .run-state { padding: 5px 9px; margin-bottom: 9px; }
      .eyebrow { margin-bottom: 5px; }
      .vacancy { margin-top: 8px; }
      section { margin-top: 12px; }
      .unavailable { margin-top: 5px; }
      .recommendation { padding-block: 8px; }
      .evidence, .provenance { padding-top: 8px; }
      .condition-list > div { break-inside: auto; }
      article { padding-block: 6px; }
      dl { gap: 2px; }
      dl div { grid-template-columns: minmax(0, 155pt) minmax(0, 1fr); break-inside: avoid; }
      .profile-sources > div { break-inside: auto; }
      h2, h3, h4, .run-state { break-after: avoid; }
      p, blockquote { orphans: 2; widows: 2; }
      a { color: inherit; }
    }
  `;

  // The standalone file has a single fixed script. Document data never enters script or CSS.
  const printScript = "document.getElementById('print-report').addEventListener('click', () => window.print());";
  const printScriptDigest = 'Ly5N7hfg2ILqQD8qjfrNRGdeV9zTxlJEU/jhMitXdoU=';

  function renderManagerReport(report, jobId, trustedContext = null, displayText = createDisplayText()) {
    report = displayCopy(report, displayText);
    const job = report.jobs.find(item => item.id === jobId);
    if (!job) throw new Error('Выберите оценённую вакансию.');

    const run = describeRun(report);
    const trustedRevision = report.runId && report.revision && trustedContext?.runId === report.runId &&
      trustedContext.revision === report.revision ? report.revision : null;
    const reviewed = trustedRevision && report.complete
      ? report.handoff.find(item => item.job_id === job.id && item.state === 'reviewed_for_handoff') : null;
    const reviewStatus = reviewed ? 'Проверено рекрутером для передачи' : 'Черновик для проверки';
    const reviewRevision = trustedRevision ? ' · Ревизия ' + trustedRevision : '';
    const exceptions = reviewed?.accepted_exceptions.length ?? 0;
    const fit = describeFit(report, job);
    const profile = profileSections(report.profile);
    const risks = fit.risks.slice(0, 3);
    if (fit.priority && !risks.includes(fit.priority)) risks.splice(2, 1, fit.priority);
    const questions = fit.risks.filter(({ row }) => row.status !== 'full' && !row.scoreConflict).slice(0, 5);
    const showQuestions = questions.length
      ? '<section><h2>Вопросы кандидату</h2><ol>' + questions.map(item =>
        '<li class="manager-question">' + reference(item) +
        ' — что вы можете уточнить по этому требованию?</li>').join('') + '</ol></section>' : '';
    const recommendation = run.recommendation?.[1] ?? 'Рекомендация в отчёте не указана.';
    const count = 'Обработано ' + report.processed + ' из ' + report.total + ' вакансий.';
    const progress = report.complete ? count : 'Неполный результат. ' + count + ' Место предварительное.';
    const sharedPlace = report.jobs.some(other => other.id !== job.id && other.rank === job.rank);
    const place = (report.complete ? 'Место ' : 'Предварительное место ') + job.rank +
      (sharedPlace ? ' · Делит место' : '');

    return `<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'sha256-${printScriptDigest}'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
  <title>AI-рекрутер — Отчёт для менеджера</title>
  <style>${styles}</style>
</head>
<body>
<main>
  <div class="print-toolbar">
    <button id="print-report" type="button">Печать / PDF</button>
    <p>Для PDF без адреса файла отключите колонтитулы браузера.</p>
  </div>
  <header>
    <p class="run-state${report.complete ? '' : ' incomplete'}">${progress}</p>
    <p class="eyebrow">AI-рекрутер · ${run.mode} · ${reviewStatus}${reviewRevision} · Версия отчёта ${escape(report.schemaVersion)}</p>
    <h1>Отчёт для менеджера</h1>
    <p class="vacancy">Вакансия ${escape(job.title)}</p>
    <p>${place} · Диапазон L–H ${scoreRange(job.score)}</p>
    <p class="state">${requirementReviewLabel(job.requirementsReview)} · ${mandatoryStates[job.score.mandatory][0]}</p>
    ${exceptions ? '<p class="state">Принятые исключения по условиям · ' + exceptions + '</p>' : ''}
  </header>
  <section id="vacancy-fit" class="recommendation">
    <h2>Предварительный вывод по вакансии</h2>
    <p class="fit-verdict">${fit.label}</p>
    ${fit.notes.length ? '<p class="fit-notes state">' + fit.notes.join(' ') + '</p>' : ''}
    <h3>Основания по вакансии</h3>
    ${summaryList(fit.grounds.slice(0, 3).map(item => reference(item)),
      'Нет оценок полного соответствия со структурно сверенными цитатами.')}
    <h3>Риски и пробелы</h3>
    ${summaryList(risks.map(item => riskText(item, item === fit.priority)),
      'По оценённым требованиям пробелы не отмечены.')}
    ${fit.risks.length > risks.length ? '<p>Остальные пробелы перечислены в <a href="#evidence">цитатах и оценках</a>.</p>' : ''}
  </section>
  ${profile.brief}
  ${conditionsSection(job.conditions)}
  ${report.privacyWarning ? '<p>Защита могла скрыть часть профессиональных сведений. Сверьте их с локальным оригиналом.</p>' : ''}
  ${showQuestions}
  <p class="state">Предварительная рекомендация по запуску. ${recommendation}</p>
  <section class="evidence" id="evidence">
    <h2>Цитаты и оценки по требованиям</h2>
    <p class="state">Смысл цитат и оценки соответствия проверяет рекрутер.</p>
    ${fit.rows.map(evidenceItem).join('\n    ')}
  </section>
  ${profile.sources}
  ${provenance(report, job, run)}
</main>
<script>${printScript}</script>
</body>
</html>`;
  }

  if (commonJS) module.exports = { renderManagerReport };
  else root.NanimaiManagerReport = { renderManagerReport };
})(globalThis);
