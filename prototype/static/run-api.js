(function (root) {
  'use strict';

  const errorMessages = {
    400: 'Сервер отклонил параметры запроса.',
    403: 'Локальная сессия изменилась. Обновите страницу.',
    404: 'Запуск недоступен. Обновите список запусков.',
    408: 'Локальный сервер не получил запрос вовремя.',
    409: 'Состояние запуска изменилось. Обновите список запусков.',
    413: 'Данные превышают допустимый объём.',
    429: 'Слишком много запросов. Попробуйте позже.'
  };
  const messagesByCode = new Map([
    ['input_not_found', 'Проверка документов устарела. Проверьте файлы ещё раз.'],
    ['live_disabled', 'Внешний анализ отключён на сервере.'],
    ['busy', 'Другой анализ ещё выполняется.'],
    ['report_unavailable', 'Отчёт по этому запуску ещё недоступен.'],
    ['run_active', 'Запуск ещё выполняется. Дождитесь окончания или отмены.'],
    ['action_not_allowed', 'Для этой вакансии действие недоступно. Проверьте открытые замечания.'],
    ['comparison_unavailable', 'Сервер не смог восстановить сравнение для этой пары.']
  ]);

  function pathFor(id) {
    if (typeof id !== 'string' || !/^[0-9a-f]{32}$/.test(id)) {
      throw new Error('Недопустимый идентификатор запуска.');
    }
    return '/api/runs/' + id;
  }

  function createRunApi(request, timeoutMs = 45_000) {
    let csrfToken;
    async function response(path, { method = 'GET', data, allowMissing = false, maxBytes } = {}) {
      const headers = { Accept: 'application/json' };
      const signal = AbortSignal.timeout(timeoutMs);
      const options = { method, headers, signal, credentials: 'same-origin', cache: 'no-store', redirect: 'error' };
      if (method !== 'GET') {
        if (!csrfToken) throw new Error('Локальная сессия недоступна.');
        headers['X-CSRF-Token'] = csrfToken;
        headers['Content-Type'] = 'application/json';
        options.body = JSON.stringify(data ?? {});
      }

      let result;
      try {
        result = await request(path, options);
      } catch {
        throw new Error(signal.aborted ? 'Локальный сервер не ответил вовремя.' : 'Локальный сервер не отвечает.');
      }
      if (allowMissing && result.status === 404) return null;
      if (!result.ok) {
        const error = new Error(errorMessages[result.status] ?? 'Локальный сервер не выполнил запрос.');
        error.status = result.status;
        try {
          const body = await result.json();
          if (typeof body?.error === 'string' && /^[a-z0-9_]{1,64}$/.test(body.error)) error.code = body.error;
        } catch {
          // The client always displays a fixed message for unexpected response bodies.
        }
        error.message = messagesByCode.get(error.code) ?? error.message;
        throw error;
      }
      if (maxBytes != null) {
        if (Number(result.headers.get('Content-Length')) > maxBytes) throw new Error('Отчёт слишком большой.');
        let source;
        try {
          source = await result.text();
        } catch {
          throw new Error(signal.aborted ? 'Отчёт не получен вовремя.' : 'Не удалось прочитать отчёт запуска.');
        }
        if (new Blob([source]).size > maxBytes) throw new Error('Отчёт слишком большой.');
        return source;
      }
      return result;
    }

    async function json(path, options) {
      const result = await response(path, options);
      if (!result || result.status === 204) return null;
      try {
        return await result.json();
      } catch {
        throw new Error('Локальный сервер вернул некорректный ответ.');
      }
    }

    return {
      async session() {
        const session = await json('/api/session', { allowMissing: true });
        if (typeof session?.csrf_token !== 'string' || !session.csrf_token ||
            !session.capabilities || typeof session.capabilities !== 'object') return null;
        csrfToken = session.csrf_token;
        return session.capabilities;
      },
      inspect: data => json('/api/inputs/inspect', { method: 'POST', data }),
      list: () => json('/api/runs'),
      start: data => json('/api/runs', { method: 'POST', data }),
      async get(id) { return json(pathFor(id)); },
      async report(id, maxBytes = 25_000_000) { return response(pathFor(id) + '/report', { maxBytes }); },
      async comparison(id, a, b) {
        return json(pathFor(id) + '/report?' + new URLSearchParams({ a, b }));
      },
      async cancel(id) { return json(pathFor(id) + '/cancel', { method: 'POST' }); },
      async review(id, data) { return json(pathFor(id) + '/review', { method: 'POST', data }); },
      async remove(id) { await response(pathFor(id), { method: 'DELETE' }); }
    };
  }

  if (typeof module === 'object' && module.exports) module.exports = { createRunApi };
  else root.RecruiterRunApi = { createRunApi };
})(globalThis);
