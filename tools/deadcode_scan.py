"""Heuristic dead-code scanner for this repo.

Outputs Python modules inside first-party packages that appear to have zero
import references across the repo.

NOTE: This is heuristic. It may miss dynamic imports (Django settings strings,
Celery autodiscovery, import_string, etc.). Treat output as candidates only.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]

EXCLUDE_DIR_NAMES = {
    ".git",
    ".idea",
    ".pytest_cache",
    ".vscode",
    ".venv",
    ".venv_broken",
    "__pycache__",
    "build",
    "staticfiles",
    "media",
}

EXCLUDE_PATH_PARTS = {
    "migrations",
}

EXCLUDE_TOP_LEVEL_DIRS = {
    "tests",
    "tmp",
}

FIRST_PARTY_TOP_LEVEL = {
    "byteneko",
    "core",
    "surveys",
    "tools",
}


@dataclass(frozen=True)
class PyFile:
    path: Path
    module: str | None  # None if not a package module


def _is_excluded_path(p: Path) -> bool:
    if any(name in EXCLUDE_DIR_NAMES for name in p.parts):
        return True
    if any(part in EXCLUDE_PATH_PARTS for part in p.parts):
        return True
    if len(p.parts) >= 1 and p.parts[0] in EXCLUDE_TOP_LEVEL_DIRS:
        return True
    return False


def _is_package_dir(d: Path) -> bool:
    return (d / "__init__.py").exists()


def _module_name_for_file(py_path: Path) -> str | None:
    rel = py_path.relative_to(ROOT)
    if rel.parts[0] not in FIRST_PARTY_TOP_LEVEL:
        return None

    # Only consider proper package modules
    pkg_root = ROOT / rel.parts[0]
    if not _is_package_dir(pkg_root):
        return None

    # Ensure every intermediate dir is a package if we want a dotted module
    current = pkg_root
    dotted_parts: list[str] = [rel.parts[0]]
    for part in rel.parts[1:-1]:
        current = current / part
        if not _is_package_dir(current):
            return None
        dotted_parts.append(part)

    name = rel.name
    if name == "__init__.py":
        return ".".join(dotted_parts)

    if not name.endswith(".py"):
        return None
    dotted_parts.append(name[:-3])
    return ".".join(dotted_parts)


def iter_py_files() -> Iterable[PyFile]:
    for p in ROOT.rglob("*.py"):
        if _is_excluded_path(p.relative_to(ROOT)):
            continue
        yield PyFile(path=p, module=_module_name_for_file(p))


def _imports_in_file(py_path: Path) -> set[str]:
    try:
        src = py_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        src = py_path.read_text(encoding="latin-1")

    try:
        tree = ast.parse(src)
    except SyntaxError:
        return set()

    current_mod = _module_name_for_file(py_path)
    current_pkg = None
    if current_mod:
        # For a module file like pkg.mod, relative imports are resolved from pkg
        current_pkg = current_mod.rsplit(".", 1)[0]

    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    found.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                found.add(node.module)
                # Resolve relative `from .foo import bar` into first-party dotted refs
                if node.level and current_pkg:
                    # Level 1: from current_pkg import module
                    base_parts = current_pkg.split(".")
                    if node.level > 1:
                        base_parts = base_parts[: -(node.level - 1)]
                    if base_parts:
                        found.add(".".join(base_parts + [node.module]))
            else:
                # Handles `from . import x` where module is None.
                if node.level and current_pkg:
                    base_parts = current_pkg.split(".")
                    if node.level > 1:
                        base_parts = base_parts[: -(node.level - 1)]
                    base = ".".join(base_parts) if base_parts else None
                    if base:
                        for alias in node.names:
                            if alias.name:
                                found.add(f"{base}.{alias.name}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            s = node.value.strip()
            # Catch dynamic import strings common in Django (INSTALLED_APPS,
            # middleware, ROOT_URLCONF, WSGI_APPLICATION, etc.).
            if "." in s:
                head = s.split(".", 1)[0]
                if head in FIRST_PARTY_TOP_LEVEL:
                    found.add(s)
    return found


def main() -> int:
    py_files = list(iter_py_files())
    package_modules = sorted({pf.module for pf in py_files if pf.module})

    imported_modules: set[str] = set()
    for pf in py_files:
        imported_modules |= _imports_in_file(pf.path)

    # Consider a module "referenced" if any file imports it directly,
    # or imports a parent package that would likely touch it.
    referenced: set[str] = set()
    for mod in package_modules:
        # direct import or dynamic string reference
        if mod in imported_modules:
            referenced.add(mod)
            continue

        # dynamic dotted reference might include class/function, e.g. core.apps.CoreConfig
        if any(s.startswith(mod + ".") for s in imported_modules):
            referenced.add(mod)
            continue
        # parent package imports (e.g., from core.utils import helpers)
        parts = mod.split(".")
        for i in range(1, len(parts)):
            parent = ".".join(parts[:i])
            if parent in imported_modules:
                referenced.add(mod)
                break

    unreferenced = [m for m in package_modules if m not in referenced]

    print("Repo root:", ROOT)
    print("Package modules scanned:", len(package_modules))
    print("Import statements found:", len(imported_modules))
    print("Unreferenced package modules (candidates):", len(unreferenced))
    for m in unreferenced:
        print(" -", m)

    # Also flag top-level python files that are not entrypoints and not imported
    top_level_py = [pf for pf in py_files if pf.path.parent == ROOT]
    print("\nTop-level .py files:")
    for pf in sorted(top_level_py, key=lambda x: x.path.name):
        print(" -", pf.path.name)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
