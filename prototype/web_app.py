"""Loopback-first HTTP transport. No filesystem browsing, implicit live, or CORS."""
import hashlib
import hmac
from ipaddress import IPv4Address, IPv6Address
import json
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .local_service import LocalService
from .run_store import StoreError

MAX_BODY = 28_000_000
MAX_REPORT = 16_000_000
STATIC = Path(__file__).with_name('static')
RUN = re.compile(r'/api/runs/([0-9a-f]{32})(?:/(report|display-data|cancel|review))?\Z')
HTTPS_ORIGIN = re.compile(r'https://(\[[a-fA-F0-9:.]+\]|[a-zA-Z0-9.-]+)(?::([0-9]{1,5}))?')
DNS_LABEL = re.compile(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?')
CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; frame-src 'self' blob:; "
       "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


def _pairs(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('duplicate_key')
        obj[key] = value
    return obj


def _public_authority(origin):
    """Validate config before binding and return its exact HTTP authority."""
    match = HTTPS_ORIGIN.fullmatch(origin) if isinstance(origin, str) else None
    if not match:
        raise StoreError('invalid_public_origin')
    host, port = match.groups()
    if port is not None and (not 1 <= int(port) <= 65535 or port != str(int(port))):
        raise StoreError('invalid_public_origin')
    try:
        if host.startswith('['):
            IPv6Address(host[1:-1])
        elif host.rsplit('.', 1)[-1].isdigit():
            IPv4Address(host)
        elif len(host) > 253 or not all(DNS_LABEL.fullmatch(label) for label in host.split('.')):
            raise ValueError()
    except ValueError:
        raise StoreError('invalid_public_origin') from None
    return origin.removeprefix('https://')


class LocalHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    request_queue_size = 8

    def handle_error(self, request, client_address):
        # HTTP/library exception strings may contain document content or credentials.
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = 'LocalRecruiter'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    def log_message(self, *args):
        pass

    def _send(self, status, content, mime='application/json; charset=utf-8'):
        raw = (json.dumps(content, ensure_ascii=False, allow_nan=False).encode()
               if not isinstance(content, bytes) else content)
        if len(raw) > MAX_REPORT:
            status, raw, mime = 413, b'{"error":"response_too_large"}', 'application/json'
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', CSP)
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Connection', 'close')
        self.end_headers()
        self.wfile.write(raw)
        self.close_connection = True

    def _guard(self, mutate):
        hosts = self.headers.get_all('Host', [])
        if len(hosts) != 1:
            raise StoreError('origin_rejected')
        host = hosts[0]
        expected_origin = self.server.public_origin
        if expected_origin is not None:
            if host != self.server.public_authority:
                raise StoreError('origin_rejected')
        else:
            expected_origin = 'http://' + host
            try:
                parsed = urlsplit(expected_origin)
                port = parsed.port
                if (parsed.hostname not in {'localhost','127.0.0.1','::1'} or parsed.username is not None
                        or parsed.path or parsed.query or parsed.fragment or (port is not None and not 0 < port < 65536)):
                    raise ValueError()
            except ValueError:
                raise StoreError('origin_rejected') from None
        origins = self.headers.get_all('Origin', [])
        if origins and origins != [expected_origin]:
            raise StoreError('origin_rejected')
        if ('cross-site' in self.headers.get_all('Sec-Fetch-Site', [])
                and (self.server.public_origin is not None or self.path.startswith('/api/'))):
            raise StoreError('origin_rejected')
        if mutate:
            tokens = self.headers.get_all('X-CSRF-Token', [])
            if len(tokens) != 1 or not hmac.compare_digest(tokens[0], self.server.session_token):
                raise StoreError('csrf_rejected')

    def _body(self):
        lengths = self.headers.get_all('Content-Length', [])
        if self.headers.get_all('Transfer-Encoding') or len(lengths) != 1:
            raise StoreError('invalid_request')
        if self.headers.get_content_type() != 'application/json':
            raise StoreError('invalid_content_type')
        try:
            size = int(lengths[0])
        except ValueError:
            raise StoreError('invalid_request') from None
        if not 0 <= size <= MAX_BODY:
            raise StoreError('input_too_large')
        raw = self.rfile.read(size)
        if len(raw) != size:
            raise StoreError('invalid_request')
        try:
            def invalid_constant(_):
                raise ValueError('non_finite')
            body = json.loads(raw, object_pairs_hook=_pairs, parse_constant=invalid_constant)
            if not isinstance(body, dict):
                raise ValueError()
            return body
        except (ValueError, UnicodeError):
            raise StoreError('invalid_request') from None

    def _dispatch(self, mutate=False):
        try:
            self._guard(mutate)
            path = urlsplit(self.path).path
            service = self.server.service
            if self.command == 'GET':
                if path == '/api/session':
                    return self._send(200, {'csrf_token':self.server.session_token,'capabilities':service.capabilities})
                if path == '/api/runs':
                    return self._send(200, {'runs':service.store.list()})
                match = RUN.fullmatch(path)
                if match:
                    rid, operation = match.groups()
                    if operation == 'report':
                        return self._send(200, service.store.report(rid))
                    if operation == 'display-data':
                        return self._send(200, service.store.display_data(rid))
                    if operation is None:
                        return self._send(200, service.store.get(rid))
                name = 'index.html' if path == '/' else path.removeprefix('/')
                if '/' not in name and name in self.server.static_files:
                    file = STATIC / name
                    if file.is_symlink():
                        raise StoreError('not_found')
                    mime = {'.html':'text/html','.css':'text/css','.js':'text/javascript'}[file.suffix]
                    return self._send(200, file.read_bytes(), mime + '; charset=utf-8')
                raise StoreError('not_found')
            body = self._body()
            if self.command == 'POST' and path == '/api/runs':
                return self._send(202, service.create(body))
            if self.command == 'POST' and path == '/api/inputs/inspect':
                return self._send(200, service.inspect(body))
            match = RUN.fullmatch(path)
            if match:
                rid, operation = match.groups()
                if self.command == 'POST' and operation == 'review':
                    return self._send(200, service.store.review(rid, body))
                if self.command == 'POST' and operation == 'cancel' and body == {}:
                    return self._send(200, service.cancel(rid))
                if self.command == 'DELETE' and operation is None and body == {}:
                    service.store.delete(rid)
                    return self._send(200, {'deleted':rid})
            raise StoreError('not_found')
        except StoreError as exc:
            code = str(exc)
            status = 404 if code in {'not_found','unknown_job','input_not_found'} else (
                403 if code in {'origin_rejected','csrf_rejected','live_disabled'} else (
                413 if code in {'input_too_large','record_too_large'} else (
                409 if code in {'busy','stale_revision','idempotency_conflict','action_not_allowed','run_active',
                                'report_unavailable','invalid_transition'} else 400)))
            self._send(status, {'error':code})
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            self._send(500, {'error':'operation_failed'})

    def do_GET(self):
        self._dispatch()

    def do_POST(self):
        self._dispatch(mutate=True)

    def do_DELETE(self):
        self._dispatch(mutate=True)


def create_server(service, host='127.0.0.1', port=8765, *, public_origin=None):
    # Native app is loopback-only. Container networking requires an internal
    # wildcard bind; publish it on 127.0.0.1 using the documented Docker command.
    if host not in {'127.0.0.1', 'localhost'} and not (host == '0.0.0.0' and Path('/.dockerenv').is_file()):
        raise StoreError('loopback_required')
    public_authority = _public_authority(public_origin) if public_origin is not None else None
    server = LocalHTTPServer((host, port), Handler)
    server.service = service
    server.public_origin = public_origin
    server.public_authority = public_authority
    server.session_token = secrets.token_urlsafe(32)
    server.static_files = {p.name for p in STATIC.iterdir() if p.is_file() and p.suffix in {'.js','.css','.html'}}
    return server


def serve(args):
    service = LocalService(args.state_dir, allow_live=args.allow_live)
    server = None
    try:
        server = create_server(service, args.host, args.port, public_origin=args.public_origin)
        address = server.public_origin or f'http://127.0.0.1:{server.server_port}'
        print(f'Откройте {address}', flush=True)
        print('Внешний API включён явно.' if args.allow_live else 'Локальный режим. Платные запросы выключены.', flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        if server is not None:
            server.server_close()
        service.close()
