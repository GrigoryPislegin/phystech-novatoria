import argparse
import asyncio
import json
from pathlib import Path
from .demo import demo_inputs, ReplayModel, SyntheticPrivacy
from .documents import read_document
from .model import Model, RATES
from .pipeline import run_pipeline, write_report
from .privacy import certum_privacy


async def execute(args):
    if args.command == 'inspect':
        text = read_document(args.file)
        print(json.dumps({'status':'extracted_locally', 'characters':len(text)}, ensure_ascii=False))
        return 0
    async def process(resume, jobs, privacy, replay=False):
        model = ReplayModel() if replay else Model(args.model, privacy, args.budget)
        try:
            report = await run_pipeline(resume, jobs, model, privacy)
            report['mode'] = 'synthetic_replay_NOT_model_output' if replay else ('live_synthetic' if args.command == 'demo' else 'live_certum')
            report['model'] = None if replay else args.model
            if not replay:
                report['usage'] = model.usage
                report['reserved_usd_estimate'] = str(model.budget.reserved)
            out = write_report(report, args.out)
            print(f"Отчёт: {out.resolve()}")
            return 0 if report['ranking']['complete'] else 2
        finally:
            if not replay: await model.close()
    if args.command == 'demo':
        return await process(*demo_inputs(), SyntheticPrivacy(), replay=not args.live)
    resume = read_document(args.resume)
    files = sorted(p for p in args.jobs.iterdir() if p.is_file() and not p.name.startswith('.'))
    jobs = [(f'job-{i:03}', read_document(p)) for i,p in enumerate(files, 1)]
    async with certum_privacy() as privacy:
        return await process(resume, jobs, privacy)


def main():
    parser = argparse.ArgumentParser(description='Одно резюме → рейтинг вакансий. По умолчанию демо без сети.')
    sub = parser.add_subparsers(dest='command', required=True)
    inspect = sub.add_parser('inspect', help='Извлечь текст локально, вывести только число символов')
    inspect.add_argument('file', type=Path)
    for command in ['demo','run']:
        p = sub.add_parser(command)
        p.add_argument('--model', choices=list(RATES), default='gpt-6-luna')
        p.add_argument('--budget', type=float, default=1.0, help='Консервативный резерв USD на процесс, максимум 5')
        p.add_argument('--out', type=Path, default=Path('data/private/prototype-runs'))
        if command == 'demo': p.add_argument('--live', action='store_true', help='Платный вызов на встроенном синтетическом примере')
        else:
            p.add_argument('--resume', required=True, type=Path)
            p.add_argument('--jobs', required=True, type=Path)
    args = parser.parse_args()
    try:
        return asyncio.run(execute(args))
    except Exception as exc:
        print(f"Запуск остановлен ({type(exc).__name__}). Проверьте входные файлы, зависимости и настройки по prototype/README.md. Содержимое ошибки скрыто, чтобы не раскрыть данные.")
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
