(function (root) {
  'use strict';

  const errorMessages = {
    400: 'Сервер отклонил параметры запроса.',
    403: 'Локальная сессия изменилась. Обновите страницу.',
    404: 'Запуск недоступен. Обновите список запусков.',
    409: 'Состояние запуска изменилось. Обновите список запусков.',
    413: 'Данные превышают допустимый объём.',
    429: 'Слишком много запросов. Попробуйте позже.'
  };

  function pathFor(id) {
    if (typeof id !== 'string' || !/^[0-9a-f]{32}$/.test(id)) {
      throw new Error('Недопустимый идентификатор запуска.');
    }
    return '/api/runs/' + id;
  }

  function createRunApi(request) {
    let csrfToken;
    async function response(path, { method = 'GET', data, allowMissing = false } = {}) {
      const headers = { Accept: 'application/json' };
      const options = { method, headers, credentials: 'same-origin', cache: 'no-store', redirect: 'error' };
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
        throw new Error('Локальный сервер не отвечает.');
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
        throw error;
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
      async report(id) { return response(pathFor(id) + '/report'); },
      async displayData(id) { return json(pathFor(id) + '/display-data', { allowMissing: true }); },
      async cancel(id) { return json(pathFor(id) + '/cancel', { method: 'POST' }); },
      async review(id, data) { return json(pathFor(id) + '/review', { method: 'POST', data }); },
      async remove(id) { await response(pathFor(id), { method: 'DELETE' }); }
    };
  }

  if (typeof module === 'object' && module.exports) module.exports = { createRunApi };
  else root.RecruiterRunApi = { createRunApi };
})(globalThis);
