#!/usr/bin/env python3
"""Read-only local toolchain check; --write-report updates only READY.md."""
import argparse
from datetime import datetime
from pathlib import Path
import shutil
import subprocess
import tomllib
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent


def run(args):
    try:
        result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=10)
        lines = result.stdout.strip().splitlines()
        return result.returncode == 0, lines[-1] if lines else "Нет вывода"
    except (OSError, subprocess.TimeoutExpired):
        return False, "Проверка не выполнена"


def report():
    rows = []
    for title, command in [
        ("Node.js", ["node", "--version"]), ("npm", ["npm", "--version"]),
        ("pnpm", ["pnpm", "--version"]), ("Python", ["python3", "--version"]),
        ("Git", ["git", "--version"]), ("GitHub CLI", ["gh", "--version"]),
        ("Codex CLI", ["codex", "--version"]), ("Docker CLI", ["docker", "--version"]),
    ]:
        if not shutil.which(command[0]):
            rows.append((title, "Не найден"))
            continue
        ok, value = run(command)
        if title == "GitHub CLI" and ok:
            value = subprocess.run(command, capture_output=True, text=True, timeout=10).stdout.splitlines()[0]
        rows.append((title, value if ok else "Команда найдена, проверка версии не прошла"))

    if shutil.which("docker"):
        ok, _ = run(["docker", "info", "--format", "{{.ServerVersion}}"])
        rows.append(("Docker engine", "Доступен" if ok else "Не доступен в текущем окружении; для подготовки не обязателен"))
    rows.append(("Chrome", "Установлен" if Path("/Applications/Google Chrome.app").exists() else "Не найден в /Applications"))
    rows.append(("Safari", "Установлен" if Path("/Applications/Safari.app").exists() else "Не найден в /Applications"))

    for name in ["economy_explorer", "economy_reviewer"]:
        config_path = Path.home() / ".codex" / "agents" / f"{name}.toml"
        try:
            data = tomllib.loads(config_path.read_text())
            value = f"{data.get('model', 'модель не указана')} / {data.get('model_reasoning_effort', 'reasoning не указан')}"
        except (OSError, tomllib.TOMLDecodeError):
            value = "Конфигурация не прочитана"
        rows.append((name, value))

    stamp = datetime.now(ZoneInfo("Europe/Moscow")).strftime("%d.%m.%Y %H:%M МСК")
    text = ["# Проверка готовности окружения", "", f"Проверено локально: {stamp}.", "", "| Компонент | Наблюдение |", "|---|---|"]
    text.extend(f"| {name} | {value.replace('|', '/')} |" for name, value in rows)
    text.extend([
        "", "## Что подтверждено", "",
        "Проверены доступность локальных команд, браузеров и названия моделей в существующих экономных ролях. Во время подготовки исследователь economy_explorer успешно выполнил аудит и исследование GitHub. Ревьюер в этом чате не запускался.",
        "", "## Что ещё не проверено", "",
        "Авторизация GitHub/Codex CLI, доступы команды, окружения остальных участников, внешний деплой и реальные интеграции. Проверка версии CLI не подтверждает авторизацию. Текущая сессия Codex с субагентом работает через приложение.",
        "", "## Состояние подготовки", "",
        "Условие ещё не выдано. Стек не выбран, приложение не создаётся. В рабочей папке остаются инструкции, шаблоны, сравнение мультиагентных систем и эта диагностическая утилита. Внешние фреймворки оркестрации не установлены.",
        "", "Следующий шаг: выбрать подход к оркестрации по MULTIAGENT_OPTIONS.md, затем получить кейс и заполнить docs/01-brief.md.", "",
    ])
    return "\n".join(text)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-report", action="store_true")
    args = parser.parse_args()
    content = report()
    if args.write_report:
        (ROOT / "READY.md").write_text(content, encoding="utf-8")
        print(f"Сохранён отчёт: {ROOT / 'READY.md'}")
    else:
        print(content)
