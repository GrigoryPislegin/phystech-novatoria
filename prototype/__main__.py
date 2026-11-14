import argparse
import asyncio
import json
import sys
from pathlib import Path
from .demo import demo_inputs, ReplayModel, SyntheticPrivacy
from .documents import DocumentReadError, document_diagnostic, read_document
from .model import Model, RATES
from .pipeline import RunControl, preflight_output
from .application import InputDocumentError, analyze, analyze_protected, load_documents
from .errors import error_code
from .privacy import local_privacy, protect_dependency_logs


async def execute(args):
    protect_dependency_logs()
    if args.command == 'inspect':
        text = read_document(args.file)
        print(json.dumps({'status':'extracted_locally', 'characters':len(text)}, ensure_ascii=False))
        return 0
    control = RunControl(timeout_seconds=getattr(args, 'deadline', 300))
    preflight_output(args.out)
    async def process(resume, jobs, privacy, replay=False, manifest=None):
        result = await analyze(resume, jobs, privacy=privacy,
            model_factory=(ReplayModel if replay else lambda: Model(args.model, privacy, args.budget)),
            out=args.out, control=control, manifest=manifest,
            mode='synthetic_replay_NOT_model_output' if replay else ('live_synthetic' if args.command == 'demo' else 'live_local_privacy'),
            metadata={'demo_scenario':args.scenario} if args.command == 'demo' else None)
        print(f"Отчёт: {result.path.resolve()}")
        return result.exit_code
    if args.command == 'demo':
        return await process(*demo_inputs(args.scenario), SyntheticPrivacy(), replay=not args.live)
    resume, jobs, manifest = load_documents(args.resume, args.jobs, reader=read_document, control=control)
    result = await analyze_protected(resume, jobs, privacy_context=local_privacy,
        model_factory=lambda privacy:Model(args.model, privacy, args.budget),
        out=args.out, control=control, manifest=manifest)
    print(f"Отчёт: {result.path.resolve()}")
    return result.exit_code


def main():
    parser = argparse.ArgumentParser(description='Одно резюме → рейтинг вакансий. По умолчанию демо без сети.')
    sub = parser.add_subparsers(dest='command', required=True)
    inspect = sub.add_parser('inspect', help='Извлечь текст локально, вывести только число символов')
    inspect.add_argument('file', type=Path)
    web = sub.add_parser('serve', help='Локальный интерфейс, сохранённые запуски и решения HR')
    web.add_argument('--host', default='127.0.0.1')
    web.add_argument('--port', type=int, default=8765)
    web.add_argument('--state-dir', type=Path, default=Path('data/private/local-app'))
    web.add_argument('--allow-live', action='store_true', help='Явно разрешить платный внешний API для загруженных документов')
    for command in ['demo','run']:
        p = sub.add_parser(command)
        p.add_argument('--model', choices=list(RATES), default='gpt-6-luna')
        p.add_argument('--budget', type=float, default=1.0, help='Консервативный резерв USD на процесс, максимум 5')
        p.add_argument('--out', type=Path, default=Path('data/private/prototype-runs'))
        p.add_argument('--deadline', type=float, default=300, help='Предел асинхронных стадий в секундах, максимум 1800; синхронный парсер не прерывается')
        if command == 'demo':
            p.add_argument('--live', action='store_true', help='Платный вызов на встроенном синтетическом примере')
            p.add_argument('--scenario', choices=['success', 'disputed'], default='success')
        else:
            p.add_argument('--resume', required=True, type=Path)
            p.add_argument('--jobs', required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.command == 'serve':
            from .web_app import serve
            return serve(args)
        return asyncio.run(execute(args))
    except DocumentReadError as exc:
        item = {'status':'error', **document_diagnostic(exc)}
        if isinstance(exc, InputDocumentError):
            item.update(role='resume' if exc.position == 0 else 'vacancy', index=exc.position or 1)
        elif args.command == 'inspect':
            item['file'] = 1
        print(json.dumps(item, ensure_ascii=False), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"Запуск остановлен: {error_code(exc)}. Проверьте входные файлы, зависимости и настройки по prototype/README.md.")
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
