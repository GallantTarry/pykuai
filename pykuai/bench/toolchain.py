"""Install and cache Build Bench's complete, pinned Windows C toolchain."""
from __future__ import annotations

import os
import platform
import stat
import subprocess
import tempfile
import time
import zipfile
from contextlib import contextmanager
from pathlib import Path, PureWindowsPath

from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn

from pykuai.core.tools import USER_TOOLS_DIR, _download_to_file, _file_sha256


VERSION = "20261117"
PACKAGE = f"llvm-mingw-{VERSION}-ucrt-x86_64"
URL = f"https://github.com/mstorsjo/llvm-mingw/releases/download/{VERSION}/{PACKAGE}.zip"
# Digest and byte count of this exact asset in the upstream release manifest.
SHA256 = "4d002e330a0f703625aa5ccbc37e96f8f824413e163bfc7336774aabd2c3a412"
ARCHIVE_SIZE = 191082415
_READY = ".pykuai-ready"
_COMPONENTS = ("bin/clang.exe", "bin/ld.lld.exe", "include/stdio.h",
               "x86_64-w64-mingw32/lib/crt2.o", "x86_64-w64-mingw32/lib/libkernel32.a")


def _is_ready(root: Path) -> bool:
    try:
        return ((root / _READY).read_bytes() == SHA256.encode("ascii")
                and all((root / name).is_file() for name in _COMPONENTS))
    except OSError:
        return False


@contextmanager
def _install_lock(cache: Path, console):
    """Windows releases the byte-range lock if an installer exits or crashes."""
    import errno
    import msvcrt

    with (cache / f"{PACKAGE}.lock").open("a+b") as handle:
        handle.seek(0)
        waiting = False
        while True:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EDEADLK):
                    raise
                if not waiting:
                    console.print("Another Build Bench is preparing the C toolchain. Waiting…")
                    waiting = True
                time.sleep(0.5)
        try:
            yield
        finally:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def _extract(archive: Path, stage: Path) -> Path:
    with zipfile.ZipFile(archive) as bundle:
        for entry in bundle.infolist():
            member = PureWindowsPath(entry.filename)
            if (member.anchor or not member.parts or member.parts[0] != PACKAGE
                    or ".." in member.parts or ":" in entry.filename
                    or stat.S_ISLNK(entry.external_attr >> 16)):
                raise RuntimeError(f"Unexpected toolchain archive member: {entry.filename}")
        bundle.extractall(stage)
    return stage / PACKAGE


def _probe(root: Path, stage: Path) -> None:
    """Verify headers, linker, runtime and a runnable target before publishing."""
    source = stage / "check.c"
    executable = stage / "check.exe"
    source.write_text('#include <stdio.h>\nint main(void) { puts("bb-ready"); return 0; }\n',
                      encoding="ascii")
    compiler = root / "bin" / "clang.exe"
    env = os.environ.copy()
    env["PATH"] = str(compiler.parent) + os.pathsep + env.get("PATH", "")
    try:
        subprocess.run([str(compiler), source.name, "-o", executable.name],
                       cwd=stage, env=env, capture_output=True, check=True, timeout=90)
        result = subprocess.run([str(executable)], cwd=stage, env=env, capture_output=True,
                                check=True, timeout=15)
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or exc.stdout or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(f"C toolchain self-test failed ({exc.returncode}): {details}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("C toolchain self-test timed out.") from exc
    if result.stdout.strip() != b"bb-ready":
        raise RuntimeError("C toolchain self-test produced unexpected output.")


def ensure_toolchain(console) -> Path:
    machine = os.environ.get("PROCESSOR_ARCHITEW6432") or platform.machine()
    if os.name != "nt" or machine.lower() not in ("amd64", "x86_64"):
        raise RuntimeError("Build Bench currently supports Windows x64.")
    cache = USER_TOOLS_DIR / "bb"
    installed = cache / PACKAGE
    compiler = installed / "bin" / "clang.exe"
    if _is_ready(installed):
        return compiler

    cache.mkdir(parents=True, exist_ok=True)
    with _install_lock(cache, console):
        if _is_ready(installed):
            return compiler
        console.print(f"Preparing LLVM-MinGW {VERSION} for Windows x64 ({ARCHIVE_SIZE / 2**20:.0f} MiB)")
        console.print(URL, markup=False, highlight=False)
        with tempfile.TemporaryDirectory(prefix="install-", dir=cache) as tmp:
            stage = Path(tmp)
            archive = stage / "toolchain.zip"
            with Progress(TextColumn("{task.description}"), BarColumn(), DownloadColumn(),
                          console=console) as progress:
                task = progress.add_task("Downloading toolchain", total=ARCHIVE_SIZE)

                def update(done, total):
                    progress.update(task, completed=done, total=total or ARCHIVE_SIZE)

                _download_to_file(URL, archive, timeout=120, progress_cb=update)
            if archive.stat().st_size != ARCHIVE_SIZE or _file_sha256(archive) != SHA256:
                raise RuntimeError("LLVM-MinGW integrity check failed. Run bb again to retry.")
            console.print("Extracting compiler, headers, linker and libraries…")
            try:
                staged = _extract(archive, stage)
            except zipfile.BadZipFile as exc:
                raise RuntimeError("Invalid LLVM-MinGW archive.") from exc
            console.print("Compiling and running the C self-test…")
            _probe(staged, stage)
            (staged / _READY).write_bytes(SHA256.encode("ascii"))
            # The ready marker travels with the directory in one same-volume rename.
            if installed.exists():
                installed.rename(stage / "incomplete-install")
            staged.rename(installed)
        console.print("Build Bench toolchain ready.")
    return compiler
