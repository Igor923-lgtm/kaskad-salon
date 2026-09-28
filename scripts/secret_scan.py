"""secret_scan.py — анти-утечка секретов в git.

Ищет в отслеживаемых файлах: SSH-пароли, BOT_TOKEN, CRM-пароли/секреты.
Запуск:  python3 scripts/secret_scan.py            # аудит всего index+worktree
         python3 scripts/secret_scan.py --staged   # только staged (для pre-commit)

Выход 0 = чисто, 1 = найдены утечки (печатает file:line).
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (имя, regex). Ищем и в рабочем дереве, и в index.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ("SSH password", re.compile(r"""password\s*=\s*["'][A-Za-z0-9+/]{10,}["']""")),
    ("SSH PASS assign", re.compile(r"""^\s*(PASS|SERVER_PASS|PASSWORD)\s*=\s*["'][A-Za-z0-9+/]{8,}["']""", re.M)),
    ("BOT_TOKEN", re.compile(r"\b\d{8,10}:AAH[A-Za-z0-9_-]{30,}")),
    ("CRM_PASSWORD", re.compile(r"CRM_PASSWORD\s*=\s*[\"']?(?!your_)[A-Za-z0-9@#!$%^&*_-]{6,}")),
    ("CRM_SECRET", re.compile(r"CRM_SECRET\s*=\s*[\"']?(?!your_)[A-Za-z0-9@#!$%^&*_-]{12,}")),
    # curl/shell-контекст: password=<литерал>. Код-ссылки (deploy_secrets.X, SERVER_PASS,
    # _load_pass(), os.environ[…]) — не утечка, отфильтрованы негативным lookahead.
    (
        "shell password=",
        re.compile(
            r"""password=(?!["']?(?:deploy_secrets|SERVER_PASS|PASSWORD|_load_pass|os\.|form\.|"""
            r"""getenv|environ|\$\{|\{|your_|<|YOUR_|config\.|\$))[A-Za-z0-9@#!$%^&*_-]{6,}"""
        ),
    ),
]

# Файлы, которые ДОЛЖНЫ содержать плейсхолдеры/секреты и не сканируются как утечка.
ALLOW_SUBSTRINGS = (
    "deploy_secrets.py",       # само хранилище (gitignored, но на диске)
    "deploy_settings.py",      # gitignored
    ".env.example",            # плейсхолдеры
    "scripts/secret_scan.py",  # сам сканер (содержит regex)
    "tests/",                  # тестовые фикстуры
    "node_modules/",
)


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-c", "--exclude-standard"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [f for f in out.split() if f]


def _staged_files() -> list[str]:
    out = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout
    return [f for f in out.split() if f]


def scan(files: list[str]) -> list[str]:
    hits: list[str] = []
    for rel in files:
        if any(s in rel for s in ALLOW_SUBSTRINGS):
            continue
        p = ROOT / rel
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, rx in PATTERNS:
            for m in rx.finditer(text):
                line = text.count("\n", 0, m.start()) + 1
                hits.append(f"{rel}:{line}  [{name}]  {m.group(0)[:60]}")
    return hits


def main() -> int:
    staged = "--staged" in sys.argv
    files = _staged_files() if staged else _tracked_files()
    hits = scan(files)
    if hits:
        mode = "STAGED" if staged else "TRACKED"
        print(f"secret_scan: {len(hits)} утечек в {mode} файлах:")
        for h in hits:
            print("  " + h)
        print("\nЗначения должны жить в gitignored deploy_secrets.py / .env, не в коде.")
        return 1
    print(f"secret_scan: чисто ({len(files)} файлов)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
