# -*- coding: utf-8 -*-
"""
PyKuai Global Dependency Discovery & Package Manager (`pp` - Pull Packages)
Discovers runtime requirements across pyproject.toml, loaded engines' `requires`,
and third-party AST imports in active scripts, with clickable TUI & pip execution.
"""
from __future__ import annotations

import argparse
import ast
import importlib
import importlib.metadata as importlib_metadata
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pykuai.core.ui import print_error, print_info, print_step, print_success, print_warning

IMPORT_TO_PYPI: dict[str, str] = {
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML",
    "fitz": "PyMuPDF",
    "docx": "python-docx",
    "pptx": "python-pptx",
    "dotenv": "python-dotenv",
    "Crypto": "pycryptodome",
    "Cryptodome": "pycryptodomex",
    "dateutil": "python-dateutil",
    "sklearn": "scikit-learn",
    "win32api": "pywin32",
    "win32con": "pywin32",
    "win32gui": "pywin32",
    "win32com": "pywin32",
    "pythoncom": "pywin32",
    "yt_dlp": "yt-dlp",
    "PySide6": "PySide6",
}


@dataclass
class DependencyInfo:
    name: str
    spec: str
    group: str
    is_core: bool
    installed_version: str | None = None


def _normalize_name(name: str) -> str:
    """Normalize package name per PEP 503 for deduplication."""
    return re.sub(r"[-_.]+", "-", name).lower().strip()


def _parse_req_name(spec: str) -> str:
    """Extract base distribution name from a PEP 508 requirement spec."""
    base = spec.split(";")[0].strip()
    base = re.split(r"[<>=!~\[\s]", base, maxsplit=1)[0]
    return base.strip()


def _get_installed_version(pkg_name: str) -> str | None:
    """Query installed distribution version without importing the module."""
    candidates = [pkg_name, pkg_name.replace("-", "_"), pkg_name.replace("_", "-")]
    for cand in candidates:
        try:
            return importlib_metadata.version(cand)
        except importlib_metadata.PackageNotFoundError:
            continue
    norm = _normalize_name(pkg_name)
    try:
        for dist in importlib_metadata.distributions():
            dist_name = dist.metadata.get("Name", "")
            if dist_name and _normalize_name(dist_name) == norm:
                return dist.version
    except Exception:
        pass
    return None


def _read_pyproject_specs(project_root: Path) -> list[tuple[str, str, bool]]:
    """Parse dependencies and optional-dependencies from pyproject.toml."""
    toml_path = project_root / "pyproject.toml"
    if not toml_path.exists():
        return []

    specs: list[tuple[str, str, bool]] = []
    try:
        import tomllib

        with open(toml_path, "rb") as f:
            data = tomllib.load(f)
        proj = data.get("project", {})
        for req in proj.get("dependencies", []):
            specs.append((req, "core", True))
        for opt_group, opt_reqs in proj.get("optional-dependencies", {}).items():
            if opt_group == "all":
                continue
            for req in opt_reqs:
                specs.append((req, opt_group, False))
        return specs
    except Exception:
        # Lightweight regex fallback for Python < 3.11 environments
        text = toml_path.read_text(encoding="utf-8", errors="ignore")
        in_deps = False
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("dependencies = ["):
                in_deps = True
                continue
            if in_deps:
                if stripped.startswith("]"):
                    in_deps = False
                    continue
                m = re.search(r'"([^"]+)"', stripped)
                if m:
                    specs.append((m.group(1), "core", True))
        return specs


def _scan_ast_imports(package_dir: Path) -> set[str]:
    """Scan active core/engines Python modules for third-party import statements."""
    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    stdlib.update({"os", "sys", "re", "json", "time", "math", "shlex", "ctypes", "signal", "atexit"})
    discovered: set[str] = set()

    for folder in ("core", "engines"):
        target_dir = package_dir / folder
        if not target_dir.exists():
            continue
        for py_file in sorted(target_dir.glob("*.py")):
            try:
                tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"), filename=str(py_file))
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        top = alias.name.split(".")[0]
                        if top and top != "pykuai" and top not in stdlib:
                            discovered.add(IMPORT_TO_PYPI.get(top, top))
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    top = node.module.split(".")[0]
                    if top and top != "pykuai" and top not in stdlib:
                        discovered.add(IMPORT_TO_PYPI.get(top, top))
    return discovered


def discover_dependencies() -> list[DependencyInfo]:
    """Aggregate and inspect all runtime dependencies for PyKuai scripts."""
    package_dir = Path(__file__).resolve().parent.parent
    project_root = package_dir.parent

    seen: dict[str, DependencyInfo] = {}

    def _register(spec: str, group: str, is_core: bool) -> None:
        name = _parse_req_name(spec)
        if not name:
            return
        key = _normalize_name(name)
        if key not in seen:
            seen[key] = DependencyInfo(
                name=name,
                spec=spec.strip(),
                group=group,
                is_core=is_core,
                installed_version=_get_installed_version(name),
            )
        elif is_core and not seen[key].is_core:
            seen[key].is_core = True

    # 1. pyproject.toml requirements
    for spec, group, is_core in _read_pyproject_specs(project_root):
        _register(spec, group, is_core)

    # 2. Loaded engines' explicit `requires` declarations
    from pykuai.core.registry import load_all_engines

    for eng in load_all_engines().values():
        for req in getattr(eng, "requires", []):
            _register(req, f"engine:{eng.name}", False)

    # 3. Third-party imports discovered by scanning active scripts
    for pkg_name in sorted(_scan_ast_imports(package_dir)):
        _register(pkg_name, "auto-scan", False)

    # Keep missing dependencies prominently first, then core, then alphabetical
    return sorted(
        seen.values(),
        key=lambda d: (d.installed_version is not None, not d.is_core, d.name.lower()),
    )


def _format_pkg_chip(dep: DependencyInfo) -> str:
    """Format package name and installed/missing state cleanly for 35-col chip."""
    tag = f"v{dep.installed_version}" if dep.installed_version else "MISSING"
    if len(tag) > 10:
        tag = tag[:9] + "…"
    max_name = 28 - 1 - len(tag)
    short_name = dep.name if len(dep.name) <= max_name else dep.name[: max_name - 1] + "…"
    return f"{short_name:<{max_name}} {tag}"


def _build_pp_studio_app(deps: list[DependencyInfo]):
    """Construct the clickable Cyber-Dark Package Installer Studio (lazy-loaded)."""
    from textual.app import ComposeResult
    from textual.containers import Container, Horizontal, VerticalScroll
    from textual.widgets import Button, Static
    from pykuai.core.tui import ActionChip, CYBER_TUI_CSS, PyKuaiStudioApp, ToggleChip

    missing_names = {d.name for d in deps if d.installed_version is None}
    core_names = {d.name for d in deps if d.is_core}
    installed_count = sum(1 for d in deps if d.installed_version is not None)
    missing_count = len(deps) - installed_count

    extra_css = CYBER_TUI_CSS + """
    #studio-card {
        width: 80;
    }
    .pkg-chip {
        width: 35;
    }
    """

    class PullPackagesApp(PyKuaiStudioApp):
        CSS = extra_css

        def compose(self) -> ComposeResult:
            py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            if missing_count:
                summary_text = f"Python {py_ver} · {installed_count} ok · {missing_count} missing"
                summary_cls = "status-err"
            else:
                summary_text = f"Python {py_ver} · {installed_count} ready"
                summary_cls = "status-ok"

            default_selected = missing_names if missing_count else set()

            with Container(id="studio-card"):
                yield Static("📦 Packages", classes="studio-title")

                with Horizontal(classes="field-header"):
                    yield Static("Env:", classes="field-label")
                    yield Static(summary_text, classes=summary_cls)

                with Horizontal(classes="compact-row"):
                    yield Static("Pick:", classes="field-label")
                    yield ActionChip(f"Missing ({missing_count})", value="missing", variant_class="-preset", id="pre-missing")
                    yield ActionChip(f"Core ({len(core_names)})", value="core", variant_class="-preset", id="pre-core")
                    yield ActionChip(f"All ({len(deps)})", value="all", variant_class="-preset", id="pre-all")
                    yield ActionChip("Clear", value="clear", variant_class="-preset", id="pre-clear")

                with VerticalScroll(classes="pkg-scroll"):
                    for idx in range(0, len(deps), 2):
                        pair = deps[idx : idx + 2]
                        with Horizontal(classes="compact-tight"):
                            for offset, dep in enumerate(pair):
                                is_checked = dep.name in default_selected
                                yield ToggleChip(
                                    _format_pkg_chip(dep),
                                    value=dep,
                                    active=is_checked,
                                    id=f"pkg-{idx + offset}",
                                    classes="pkg-chip",
                                )

                with Horizontal(classes="compact-tight"):
                    yield Static("Opt:", classes="field-label")
                    yield ToggleChip("Upgrade", value="upgrade", active=False, id="opt-upgrade")

                yield Static("", id="form-error", classes="hidden-err")

                with Horizontal(classes="action-bar"):
                    yield ActionChip(
                        f"⚡ Install ({len(default_selected)})",
                        variant_class="-primary",
                        id="btn-run",
                    )
                    yield ActionChip("✕ Cancel", variant_class="-danger", id="btn-cancel")

        def _sync_run_button(self) -> list[DependencyInfo]:
            selected = [
                chip.value
                for chip in self.query(ToggleChip)
                if chip.id and chip.id.startswith("pkg-") and chip.active
            ]
            run_btn = self.query_one("#btn-run", ActionChip)
            run_btn.label = f"⚡ Install ({len(selected)})"
            return selected

        def _set_error(self, msg: str = "") -> None:
            err = self.query_one("#form-error", Static)
            err.update(msg)
            err.set_classes("shown-err" if msg else "hidden-err")

        def on_button_pressed(self, event: Button.Pressed) -> None:
            btn = event.button
            self._set_error("")

            if isinstance(btn, ToggleChip):
                btn.active = not btn.active
                if btn.id and btn.id.startswith("pkg-"):
                    self._sync_run_button()
            elif btn.id and btn.id.startswith("pre-"):
                mode = btn.value
                for chip in self.query(ToggleChip):
                    if chip.id and chip.id.startswith("pkg-"):
                        dep: DependencyInfo = chip.value
                        if mode == "missing":
                            chip.active = dep.installed_version is None
                        elif mode == "core":
                            chip.active = dep.is_core
                        elif mode == "all":
                            chip.active = True
                        else:
                            chip.active = False
                self._sync_run_button()
            elif btn.id == "btn-run":
                selected = self._sync_run_button()
                if not selected:
                    self._set_error("Select at least one package to install.")
                    return
                upgrade = self.query_one("#opt-upgrade", ToggleChip).active
                self.exit((selected, upgrade))
            elif btn.id == "btn-cancel":
                self.exit(None)

    return PullPackagesApp()


def print_dependency_table(deps: list[DependencyInfo], console: Console) -> None:
    """Render global dependency status matrix cleanly inside the terminal."""
    table = Table(
        box=box.SIMPLE_HEAD,
        header_style="bold #10b981",
        border_style="#333333",
        show_edge=False,
        pad_edge=False,
    )
    table.add_column("Package", style="bold #E0E0E0", width=18)
    table.add_column("Requirement", style="dim #38BDF8", width=22)
    table.add_column("Origin", style="#FF9800", width=14)
    table.add_column("Status", style="#E0E0E0")

    for dep in deps:
        status = (
            f"[bold #00FF00]✓ v{dep.installed_version}[/bold #00FF00]"
            if dep.installed_version
            else "[bold #FF5252]✗ MISSING[/bold #FF5252]"
        )
        table.add_row(dep.name, dep.spec, dep.group, status)

    console.print()
    console.print(table)
    console.print()


def install_dependencies(
    targets: list[DependencyInfo],
    console: Console,
    upgrade: bool = False,
) -> int:
    """Install selected dependencies via native python -m pip and show verification summary."""
    specs = [dep.spec for dep in targets]
    cmd = [sys.executable, "-m", "pip", "install"]
    if upgrade:
        cmd.append("--upgrade")
    cmd.extend(specs)

    print_step(f"Pulling [bold #00FF00]{len(specs)}[/bold #00FF00] package(s) via pip...")
    console.print(f"[dim]$ {' '.join(cmd)}[/dim]\n")

    try:
        proc = subprocess.run(cmd)
    except Exception as e:
        print_error(f"Failed to invoke pip: {e}")
        return 1

    importlib.invalidate_caches()

    lines = []
    ok_count = 0
    for dep in targets:
        ver = _get_installed_version(dep.name)
        if ver:
            ok_count += 1
            lines.append(f"  [dim]•[/dim] [bold #E0E0E0]{dep.name:<18}[/bold #E0E0E0] [bold #00FF00]✓ v{ver}[/bold #00FF00]")
        else:
            lines.append(f"  [dim]•[/dim] [bold #E0E0E0]{dep.name:<18}[/bold #E0E0E0] [bold #FF5252]✗ Install Failed[/bold #FF5252]")

    header_text = (
        "[bold #00FF00]✅ Global Dependencies Ready[/bold #00FF00]"
        if proc.returncode == 0 and ok_count == len(targets)
        else "[bold #FF9800]⚠️ Package Installation Finished with Warnings[/bold #FF9800]"
    )
    border = "#10b981" if proc.returncode == 0 else "#FF9800"
    card = header_text + "\n\n" + "\n".join(lines)

    console.print()
    console.print(Panel(card, border_style=border, box=box.ROUNDED, expand=False))
    return proc.returncode


def run_pull_packages(console: Console, cli_args: list[str] | None = None, interactive: bool = True) -> int:
    """Entrypoint for global `pp` command (interactive clickable Studio or CLI flags)."""
    deps = discover_dependencies()
    if not deps:
        print_info("No dependencies declared or discovered.")
        return 0

    if cli_args:
        parser = argparse.ArgumentParser(
            prog="pykuai pp",
            description="Inspect and install global PyKuai script dependencies.",
        )
        parser.add_argument("--check", action="store_true", help="Inspect status only without installing")
        parser.add_argument("--all", action="store_true", help="Target all dependencies (including installed)")
        parser.add_argument("-y", "--yes", action="store_true", help="Install missing dependencies non-interactively")
        parser.add_argument("-U", "--upgrade", action="store_true", help="Upgrade existing packages via pip")
        try:
            args = parser.parse_args(cli_args)
        except SystemExit:
            return 0

        print_dependency_table(deps, console)
        if args.check:
            return 0
        targets = deps if (args.all or args.upgrade) else [d for d in deps if d.installed_version is None]
        if not targets:
            print_success("All dependencies are already installed.")
            return 0
        return install_dependencies(targets, console, upgrade=args.upgrade)

    from pykuai.core.tui import is_interactive_tty

    if interactive and is_interactive_tty():
        app = _build_pp_studio_app(deps)
        result = app.run(mouse=True)
        sys.stdout.flush()
        if not result:
            console.print("[dim]› Cancelled.[/dim]")
            return 0
        targets, upgrade = result
        return install_dependencies(targets, console, upgrade=upgrade)

    # Non-TTY / piped fallback: display audit table
    print_dependency_table(deps, console)
    missing = [d for d in deps if d.installed_version is None]
    if not missing:
        print_success("All global dependencies are already installed.")
        return 0
    print_warning(
        f"{len(missing)} missing package(s) detected. "
        "Run `pykuai pp` in an interactive terminal or `pykuai pp -y` to install."
    )
    return 0
