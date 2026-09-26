"""Import hygiene: the deployed runtime must not import the ingest stack.

The container installs ``backend/requirements.txt`` only. If a module
reachable from the app imports yfinance / torch / transformers / ... at MODULE
level, the process dies at import time with ``ModuleNotFoundError`` before
FastAPI ever serves a request -- and it dies in production, not in the dev venv,
because the dev venv has all three requirement files installed.

The convention this enforces is "import inside the function that needs it".
That is not a workaround, it is the mechanism: ``services/market_data.py``
(yfinance), ``services/news_fetch.py`` (feedparser), ``services/sentiment.py``
(torch, transformers) and ``scheduler.py`` (apscheduler) all import their heavy
dependency inside the function that uses it, so the boot path stays clean.

Scope, and the blind spots this definition deliberately has:
  - ``app/scripts/`` is excluded. Those are operator-invoked CLIs the app never
    imports. The exclusion is load-bearing today for a different reason than
    expected: ``scripts/validate_sentiment.py`` imports scipy at module level,
    and scipy is also ingest-only but is not one of the banned packages here.
  - Only direct children of ``tree.body`` are inspected. A function-local import
    is therefore ignored -- that is the intent -- and so is an import nested in
    a top-level ``if TYPE_CHECKING:`` or ``try:``. Neither of those executes
    unconditionally so neither can crash the container, but a bare
    ``try: import torch / except ImportError`` would slip past this check.
"""
from __future__ import annotations

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"

#: Packages that exist only in requirements-ingest.txt, never in the image.
INGEST_ONLY = {
    "yfinance",
    "torch",
    "transformers",
    "apscheduler",
    "feedparser",
    "sentencepiece",
    "huggingface_hub",
}


def _root_package(name: str) -> str:
    """``torch.nn`` -> ``torch``. A dotted import of a banned root is banned too."""
    return name.split(".", 1)[0]


def _scanned_files() -> list[Path]:
    """Every .py under app/ except app/scripts/ and __pycache__."""
    return sorted(
        path
        for path in APP_DIR.rglob("*.py")
        if "__pycache__" not in path.parts
        and "scripts" not in path.relative_to(APP_DIR).parts
    )


def _module_level_imports(path: Path) -> list[tuple[int, str]]:
    """``(lineno, dotted_name)`` for imports at the top level of a module.

    Deliberately NOT ``ast.walk``: anything inside a function body is the lazy
    pattern and is allowed.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[tuple[int, str]] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            found.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                # Relative import (from . import x): always in-repo, never ingest.
                continue
            if node.module:
                found.append((node.lineno, node.module))
    return found


def test_scanner_actually_scans_the_app():
    """Guards against a vacuous pass.

    If APP_DIR were wrong or the exclusion filter over-matched, the hygiene
    test below would find zero files and pass while checking nothing.
    """
    files = _scanned_files()
    assert len(files) >= 30, f"scanner found only {len(files)} files -- path or filter is wrong"
    rel = {path.relative_to(APP_DIR).as_posix() for path in files}
    assert {"main.py", "scheduler.py", "services/sentiment.py"} <= rel
    assert not any("scripts" in path.relative_to(APP_DIR).parts for path in files)


def test_no_module_level_ingest_imports():
    """The main assertion: nothing on the boot path imports the ingest stack."""
    violations: list[str] = []
    for path in _scanned_files():
        for lineno, name in _module_level_imports(path):
            if _root_package(name) in INGEST_ONLY:
                rel = path.relative_to(APP_DIR.parent).as_posix()
                violations.append(f"{rel}:{lineno} imports {name!r} at module level")

    assert not violations, (
        "module-level ingest imports crash the deployed container "
        "(requirements.txt installs none of these):\n  "
        + "\n  ".join(violations)
        + "\n\nMove the import inside the function that needs it."
    )


def test_scheduler_imports_apscheduler_lazily():
    """The predicted failure, pinned to its own test.

    ``app/scheduler.py`` is the one module whose *job* is to use apscheduler,
    so it is the most likely place for a top-level import to creep in. A
    regression here should say "scheduler", not send someone grepping 35 files.
    """
    violations = [
        (lineno, name)
        for lineno, name in _module_level_imports(APP_DIR / "scheduler.py")
        if _root_package(name) in INGEST_ONLY
    ]
    assert not violations, (
        "app/scheduler.py must import apscheduler inside create_scheduler(), "
        f"not at module level: {violations}"
    )


def test_scripts_exclusion_is_load_bearing():
    """Confirms the app/scripts exclusion excludes something real.

    If the ingest CLIs ever stopped importing ingest-only packages, excluding
    them would be hiding nothing -- which would mean the exclusion should be
    revisited rather than left as a blanket pass.
    """
    script_roots = {
        _root_package(name)
        for path in sorted((APP_DIR / "scripts").glob("*.py"))
        for _, name in _module_level_imports(path)
    }
    assert "scipy" in script_roots, (
        "expected app/scripts/validate_sentiment.py to import scipy at module "
        f"level; saw {sorted(script_roots)} -- if the scripts no longer need the "
        "ingest stack, narrow or drop the exclusion in _scanned_files()"
    )
