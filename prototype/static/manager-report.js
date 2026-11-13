(function (root) {
  'use strict';

  const commonJS = typeof module === 'object' && module.exports;
  const {
    describeRun, scoreRange, assessments, mandatoryStates, evidenceLabel, mandatoryLabel,
    mandatoryNeedsReview, requirementReviewLabel
  } = commonJS ? require('./report.js') : root.NanimaiReport;

  const htmlEntities = {
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  };
  const escape = value => String(value).replace(/[&<>"']/g, character => htmlEntities[character]);

  function reference({ row, number }, includeStatus = false) {
    const status = includeStatus ? ' — ' + assessments[row.status][0] : '';
    return '<a href="#evidence-' + number + '">[' + number + '] ' + escape(shortLabel(row)) + '</a>' + status;
  }

  function shortLabel(row) {
    const label = row.label.replace(/\s+/g, ' ').trim();
    return label.length > 110 ? label.slice(0, 109) + '…' : label;
  }

  function summaryList(title, items, empty) {
    const content = items.length
      ? '<ul>' + items.map(item => '<li>' + item + '</li>').join('') + '</ul>'
      : '<p>' + empty + '</p>';
    return '<section><h2>' + title + '</h2>' + content + '</section>';
  }

  function riskText(item) {
    const { row } = item;
    const review = [
      mandatoryNeedsReview(row) ? mandatoryLabel(row) : null,
      evidenceNeedsReview(row) ? evidenceLabel(row) : null
    ].filter(Boolean).join('. ');
    return reference(item, true) + (review ? '. ' + review + '.' : '');
  }

  function evidenceNeedsReview(row) {
    if (row.status === 'unknown') {
      return ['needs_review', 'invalid'].includes(row.evidence?.state);
    }
    return row.evidence?.state !== 'structure_ok';
  }

  function quoteGroup(title, quotes, empty = '') {
    return '<h4>' + title + '</h4>' + (quotes.length
      ? quotes.map(quote => '<blockquote>' + escape(quote) + '</blockquote>').join('')
      : '<p>' + empty + '</p>');
  }

  function evidenceItem({ row, number }) {
    const mandatoryQuote = row.mandatoryQuote && row.mandatoryQuote !== row.requirementQuote
      ? quoteGroup('Фрагмент об обязательности', [row.mandatoryQuote]) : '';
    const title = row.label === row.requirementQuote ? 'Требование' : shortLabel(row);
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
    :root { color-scheme: light; font-family: "Inter", "Segoe UI", system-ui, sans-serif; color: #17233c; }
    * { box-sizing: border-box; }
    body { margin: 0; background: #edf1f7; font-size: 15px; line-height: 1.52; }
    main { width: min(100% - 32px, 840px); margin: 28px auto; padding: clamp(20px, 5vw, 48px);
      background: #fff; border: 1px solid #dce2ec; border-radius: 12px; overflow-wrap: anywhere; }
    h1, h2, h3, h4, p { margin: 0; }
    h1 { font-size: clamp(25px, 5vw, 38px); line-height: 1.1; letter-spacing: -.04em; }
    h2 { font-size: 1.13em; line-height: 1.3; }
    h3 { font-size: 1.04em; }
    h4 { font-size: .88em; margin-top: .7em; }
    p { margin-top: .35em; }
    a { color: #214bbe; text-underline-offset: .16em; }
    a:focus-visible { outline: 2px solid #214bbe; outline-offset: 3px; }
    article:target { background: #f1f5ff; }
    .eyebrow, .state, .provenance { color: #4d5c76; font-size: .88em; }
    .eyebrow { margin: 0 0 8px; font-weight: 700; }
    .vacancy { font-size: 1.25em; margin-top: 13px; font-weight: 680; }
    .run-state { padding: 8px 12px; border-left: 3px solid #214bbe; background: #edf3ff;
      margin: 0 0 14px; font-weight: 650; }
    .incomplete { border-color: #805000; background: #fff3da; color: #634000; }
    .print-toolbar { display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
      flex-wrap: wrap; margin-bottom: 16px; }
    .print-toolbar p { margin: 0; color: #4d5c76; font-size: .88em; }
    .print-toolbar button { font: inherit; color: #183c9e; background: #fff; cursor: pointer;
      border: 1px solid #bbcdfb; border-radius: 7px; padding: 6px 12px; }
    .print-toolbar button:focus-visible { outline: 2px solid #214bbe; outline-offset: 3px; }
    .print-toolbar button:hover { background: #eef3ff; }
    .recommendation { padding-block: 13px; border-block: 1px solid #dce2ec; }
    section { margin-top: 19px; }
    ul, ol { padding-left: 1.35em; margin: .38em 0 0; }
    li + li { margin-top: .35em; }
    .evidence, .provenance { border-top: 1px solid #dce2ec; padding-top: 12px; }
    .profile { margin-top: 14px; }
    article { padding-block: 10px; }
    article + article { border-top: 1px solid #dce2ec; }
    blockquote { margin: .3em 0 0; padding-left: .75em; border-left: 2px solid #a9b9df;
      white-space: pre-wrap; overflow-wrap: anywhere; }
    dl { display: grid; gap: 5px; margin: .45em 0 0; }
    dl div { display: grid; grid-template-columns: minmax(8em, 1fr) minmax(0, 2fr); gap: 8px; }
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
      .recommendation { padding-block: 8px; }
      .evidence, .provenance { padding-top: 8px; }
      .profile { margin-top: 8px; }
      article { padding-block: 6px; }
      dl { gap: 2px; }
      dl div { grid-template-columns: minmax(0, 155pt) minmax(0, 1fr); break-inside: avoid; }
      h2, h3, h4, .run-state { break-after: avoid; }
      p, blockquote { orphans: 2; widows: 2; }
      a { color: inherit; }
    }
  `;

  // The standalone file has a single fixed script. Document data never enters script or CSS.
  const printScript = "document.getElementById('print-report').addEventListener('click', () => window.print());";
  const printScriptDigest = 'Ly5N7hfg2ILqQD8qjfrNRGdeV9zTxlJEU/jhMitXdoU=';

  function renderManagerReport(report, jobId) {
    const job = report.jobs.find(item => item.id === jobId);
    if (!job) throw new Error('Выберите оценённую вакансию.');

    const run = describeRun(report);
    const rows = job.rows.map((row, index) => ({ row, number: index + 1 }));
    const grounds = rows.filter(({ row }) => row.status === 'full' && row.evidence?.state === 'structure_ok');
    const risks = rows.filter(({ row }) =>
      row.status !== 'full' || mandatoryNeedsReview(row) || evidenceNeedsReview(row));
    const prioritizedRisks = [
      ...risks.filter(({ row }) => row.mandatoryQuote),
      ...risks.filter(({ row }) => !row.mandatoryQuote)
    ];
    const questions = prioritizedRisks.filter(({ row }) => row.status !== 'full').slice(0, 5);
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
  <title>Nanimai — Отчёт для менеджера</title>
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
    <p class="eyebrow">Nanimai · ${run.mode} · Черновик для проверки · Версия отчёта ${escape(report.schemaVersion)}</p>
    <h1>Отчёт для менеджера</h1>
    <p class="vacancy">Вакансия ${escape(job.title)}</p>
    <p>${place} · Диапазон L–H ${scoreRange(job.score)}</p>
    <p class="state">${requirementReviewLabel(job.requirementsReview)} · ${mandatoryStates[job.score.mandatory][0]}</p>
  </header>
  <section class="recommendation">
    <h2>Предварительная рекомендация по запуску</h2>
    <p>${recommendation}</p>
  </section>
  ${summaryList('Основания по вакансии', grounds.slice(0, 3).map(item => reference(item)),
    'Нет оценок полного соответствия со структурно сверенными цитатами.')}
  ${summaryList('Риски и пробелы', prioritizedRisks.slice(0, 3).map(riskText), 'По оценённым требованиям пробелы не отмечены.')}
  ${risks.length > 3 ? '<p>Остальные пробелы перечислены в <a href="#evidence">цитатах и оценках</a>.</p>' : ''}
  ${report.privacyWarning ? '<p>Защита могла скрыть часть профессиональных сведений. Сверьте их с локальным оригиналом.</p>' : ''}
  ${showQuestions}
  <p class="profile state">Профессиональный профиль (выжимка, стек, последняя роль, сфера, период, достижения) не извлечён.</p>
  <section class="evidence" id="evidence">
    <h2>Цитаты и оценки по требованиям</h2>
    <p class="state">Смысл цитат и оценки соответствия проверяет рекрутер.</p>
    ${rows.map(evidenceItem).join('\n    ')}
  </section>
  ${provenance(report, job, run)}
</main>
<script>${printScript}</script>
</body>
</html>`;
  }

  if (commonJS) module.exports = { renderManagerReport };
  else root.NanimaiManagerReport = { renderManagerReport };
})(globalThis);
