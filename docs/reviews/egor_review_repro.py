"""Воспроизведение находок docs/reviews/egor-review.md.

Запуск из корня репозитория (venv прототипа активирован):
    python docs/reviews/egor_review_repro.py

Все входы — вручную написанные СИНТЕТИЧЕСКИЕ примеры: не ответы модели, не реальные резюме.
Сеть, ключи и модель не используются; отчёты пишутся только во временный каталог.
Скрипт показывает, что текущий код ПРОПУСКАЕТ такие входы. Как часто их выдаёт реальная
модель, он не измеряет. Код прототипа скрипт не меняет.

Каждая находка разбита на независимые подпроверки:
  ВОСПРОИЗВЕДЕНО      — все подпроверки показывают поведение из ревью;
  ЧАСТИЧНО            — часть поведения изменилась (вероятно, частично исправлено);
  НЕ ВОСПРОИЗВОДИТСЯ  — ни одна подпроверка не воспроизводится.
"""
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prototype.contracts import (Evaluation, Fact, Facts, Requirement,  # noqa: E402
                                 Requirements, Row, validate_pair)
from prototype.demo import ReplayModel, SyntheticPrivacy, demo_inputs  # noqa: E402
from prototype.pipeline import run_pipeline, write_report  # noqa: E402
from prototype.scoring import rank, score  # noqa: E402


def req(rid, text, quote, mandatory=None):
    return Requirement(id=rid, text=text, quote=quote, mandatory_quote=mandatory)


def row(rid, status, fact_ids, comment='синтетический комментарий'):
    return Row(requirement_id=rid, status=status, fact_ids=fact_ids, comment=comment,
               question=None if status == 'full' else 'Синтетический вопрос?')


def passes(fn):
    try:
        fn()
        return True
    except ValueError:
        return False


def job(jid, reqs, rows):
    return {'job_id': jid, 'score': score(Requirements(items=reqs), Evaluation(rows=rows))}


JOB = 'Python обязателен. SQL желателен.'
CV_FACTS = Facts(items=[Fact(id='f1', text='Python 3 года', quote='Разрабатывал на Python 3 года.'),
                        Fact(id='f2', text='SQL 1 год', quote='Использовал SQL 1 год.')])


def finding_1():
    """Обязательность приписана не тому требованию."""
    wrong = Requirements(items=[req('r1', 'Python', 'Python обязателен.'),
                                req('r2', 'SQL', 'SQL желателен.', 'Python обязателен.')])
    right = Requirements(items=[req('r1', 'Python', 'Python обязателен.', 'Python обязателен.'),
                                req('r2', 'SQL', 'SQL желателен.')])
    ev = Evaluation(rows=[row('r1', 'full', ['f1']), row('r2', 'fail', ['f2'])])
    accepted = passes(lambda: (wrong.validate_source(JOB), validate_pair(wrong, CV_FACTS, ev)))
    s_wrong, s_right = score(wrong, ev), score(right, ev)
    rec_wrong = rank([{'job_id': 'job-1', 'score': s_wrong}], 1)['recommendation']
    rec_right = rank([{'job_id': 'job-1', 'score': s_right}], 1)['recommendation']
    checks = {
        'чужая цитата обязательности принята': accepted,
        'ошибочная разметка даёт review_none_fit': accepted and rec_wrong == 'review_none_fit',
        'цитата обязательности из 1 символа принята':
            passes(lambda: Requirements(items=[req('r1', 'SQL', 'SQL желателен.', 'л')]).validate_source(JOB)),
    }
    detail = (f"ошибочная разметка: L={s_wrong['lower']}, {s_wrong['mandatory']}, {rec_wrong}; "
              f"правильная: L={s_right['lower']}, {s_right['mandatory']}, {rec_right}")
    return checks, detail


def finding_2():
    """Цитата подтверждает фрагмент, но не вывод: ложный full и ложный fail."""
    cv = 'Не работал с Python, планирую изучить.'
    facts = Facts(items=[Fact(id='f1', text='Python 3 года коммерческой разработки', quote='Python')])
    reqs = Requirements(items=[req('r1', 'Python', 'Python обязателен.', 'Python обязателен.')])
    ev = Evaluation(rows=[row('r1', 'full', ['f1'])])
    false_full = passes(lambda: (facts.validate_source(cv), validate_pair(reqs, facts, ev)))
    java = Requirements(items=[req('r1', 'Java', 'Java обязателен.', 'Java обязателен.')])
    ev_fail = Evaluation(rows=[row('r1', 'fail', ['f1'], 'Пишет на Python, а не на Java.')])
    false_fail = passes(lambda: validate_pair(java, CV_FACTS, ev_fail))
    s_full, s_fail = score(reqs, ev), score(java, ev_fail)
    checks = {
        'однословная цитата из отрицания → full принят': false_full and s_full['mandatory'] == 'confirmed',
        'fail по несвязанному факту принят': false_fail and s_fail['mandatory'] == 'violated',
    }
    detail = (f"резюме «{cv}» → Python full, L={s_full['lower']}, {s_full['mandatory']}; "
              f"Java fail по факту о Python → {s_fail['mandatory']} (верно: unknown, clarify)")
    return checks, detail


def finding_3():
    """Место по нижней границе L: нехватка данных стоит как несоответствие."""
    two = [req('r1', 'Go', 'Go желателен.'), req('r2', 'K8s', 'K8s желателен.')]
    a = job('job-A', two, [row('r1', 'unknown', []), row('r2', 'unknown', [])])
    b = job('job-B', two, [row('r1', 'fail', ['f1']), row('r2', 'fail', ['f1'])])
    tie = rank([a, b], 2)['jobs']
    short = job('job-short', [req('r1', 'Python', 'Python обязателен.', 'Python обязателен.')],
                [row('r1', 'full', ['f1'])])
    detailed = job('job-detailed',
                   [req('r1', 'Python', 'Python обязателен.', 'Python обязателен.'),
                    req('r2', 'SQL', 'SQL обязателен.', 'SQL обязателен.')]
                   + [req(f'n{i}', f'Желательный навык {i}', f'Навык {i}.') for i in range(6)],
                   [row('r1', 'full', ['f1']), row('r2', 'full', ['f1'])]
                   + [row(f'n{i}', 'unknown', []) for i in range(6)])
    order = rank([detailed, short], 2)['jobs']
    places = {j['job_id']: j['rank'] for j in order}
    checks = {
        'всё unknown и всё fail делят место': tie[0]['rank'] == tie[1]['rank'],
        'подробная вакансия ниже короткой при подтверждённых обязательных':
            places['job-short'] < places['job-detailed'],
    }
    detail = (f"unknown L/H {a['score']['lower']}/{a['score']['upper']} и fail "
              f"L/H {b['score']['lower']}/{b['score']['upper']} → места {tie[0]['rank']} и {tie[1]['rank']}; "
              f"короткая L={short['score']['lower']} место {places['job-short']}, "
              f"подробная L={detailed['score']['lower']} место {places['job-detailed']}")
    return checks, detail


def demo_report(model):
    resume, jobs = demo_inputs()
    report = asyncio.run(run_pipeline(resume, jobs, model, SyntheticPrivacy()))
    report['mode'] = 'synthetic_replay_NOT_model_output'
    with tempfile.TemporaryDirectory() as tmp:
        return report, (write_report(report, Path(tmp)) / 'report.md').read_text(encoding='utf-8')


class MandatoryByHeading(ReplayModel):
    """Обязательность задана отдельной фразой, цитата требования её не содержит."""
    async def ask(self, schema, task, payload):
        if task == 'requirements' and 'Python' in payload['text']:
            return Requirements(items=[req('r1', 'Python', 'Python', 'Python обязателен.'),
                                       req('r2', 'SQL', 'SQL желателен.')])
        return await super().ask(schema, task, payload)


def finding_4():
    """Отчёт: шаблонные блоки, нет итоговой рекомендации, обязательность не помечена."""
    _, md = demo_report(ReplayModel())
    _, md_heading = demo_report(MandatoryByHeading())
    header = md.split('\n## ')[0]
    checks = {
        'сильные стороны — один шаблон во всех вакансиях':
            md.count('Сильные стороны: строки full; частичное соответствие: partial') == 3,
        'лучшая вакансия не названа до таблиц': 'job-001' not in header,
        'mandatory_quote не выводится в report.md': 'Python обязателен.' not in md_heading,
    }
    return checks, 'демо-отчёт и вариант, где обязательность задана отдельной фразой'


class FailOnSecondEvaluation(ReplayModel):
    async def ask(self, schema, task, payload):
        if task == 'evaluation':
            self.evaluations = getattr(self, 'evaluations', 0) + 1
            if self.evaluations == 2:
                raise RuntimeError('синтетический сбой')
        return await super().ask(schema, task, payload)


class FabricatedFactQuote(ReplayModel):
    async def ask(self, schema, task, payload):
        if task == 'facts':
            return Facts(items=[Fact(id='f1', text='x', quote='этой цитаты нет в резюме')])
        return await super().ask(schema, task, payload)


def finding_5():
    """Неполный прогон: в report.md не названы пропущенные вакансии; сбой на фактах не даёт отчёта."""
    report, md = demo_report(FailOnSecondEvaluation())
    errors = report['errors']
    try:
        demo_report(FabricatedFactQuote())
        facts_no_report = False
    except ValueError:
        facts_no_report = True
    checks = {
        'report.md не называет job-002/job-003': 'job-002' not in md and 'job-003' not in md,
        'стадия ошибки не записана': bool(errors) and 'stage' not in errors[0],
        'сбой на этапе фактов → исключение без отчёта': facts_no_report,
    }
    detail = (f"report.json: {report['ranking']['recommendation']}, не обработаны {report['unprocessed_job_ids']}, "
              f"код ошибки {errors[0]['code'] if errors else '—'}; в report.md есть «Рекомендация: incomplete»: "
              f"{'incomplete' in md}")
    return checks, detail


def extra_duplicate():
    """Дубль требования удваивает вес."""
    dup = Requirements(items=[req('r1', 'Python', 'Python обязателен.', 'Python обязателен.'),
                              req('r2', 'Python', 'Python обязателен.', 'Python обязателен.')])
    accepted = passes(lambda: dup.validate_source(JOB))
    weight = sum(r.weight for r in dup.items)
    return {'дубль принят, вес 6 вместо 3': accepted and weight == 6}, f'суммарный вес Python {weight}'


def extra_mandatory_unknown_above_confirmed():
    """Спорное (по спецификации): вакансия с неизвестным обязательным выше подтверждённой."""
    x = job('job-X', [req('r1', 'Python', 'Python обязателен.', 'Python обязателен.')]
            + [req(f'd{i}', f'Навык {i}', f'Навык {i}.') for i in range(5)],
            [row('r1', 'unknown', [])] + [row(f'd{i}', 'full', ['f1']) for i in range(5)])
    y = job('job-Y', [req('r1', 'Python', 'Python обязателен.', 'Python обязателен.')]
            + [req(f'd{i}', f'Навык {i}', f'Навык {i}.') for i in range(3)],
            [row('r1', 'full', ['f1'])] + [row(f'd{i}', 'fail', ['f1']) for i in range(3)])
    out = rank([y, x], 2)
    top = out['jobs'][0]
    return ({'unknown-обязательное на первом месте': top['job_id'] == 'job-X'},
            f"job-X L={x['score']['lower']} ({x['score']['mandatory']}), "
            f"job-Y L={y['score']['lower']} ({y['score']['mandatory']}); рекомендация {out['recommendation']}")


CHECKS = [('1', finding_1), ('2', finding_2), ('3', finding_3), ('4', finding_4), ('5', finding_5),
          ('доп', extra_duplicate), ('спорное', extra_mandatory_unknown_above_confirmed)]


def main():
    full = 0
    for label, check in CHECKS:
        checks, detail = check()
        hits = sum(checks.values())
        status = ('ВОСПРОИЗВЕДЕНО' if hits == len(checks) else 'НЕ ВОСПРОИЗВОДИТСЯ' if hits == 0 else 'ЧАСТИЧНО')
        full += hits == len(checks)
        print(f"[{status}] {label}. {check.__doc__}")
        for name, ok in checks.items():
            print(f"    {'да ' if ok else 'нет'} — {name}")
        print(f"    {detail}")
    print(f"\nИтого: {full} из {len(CHECKS)} воспроизведено полностью. "
          "Синтетика; качество live-модели не измерялось.")


if __name__ == '__main__':
    main()
