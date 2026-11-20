"""Run Build Bench in the caller's Windows console."""

import base64
import os
from pathlib import Path
import subprocess
import sys


# PowerShell loads these definitions once, then reads commands itself. User input
# is never interpolated into this script. PowerShell owns history, quoting and I/O.
_STARTUP = r"""
try {
    $utf8 = [System.Text.UTF8Encoding]::new($false)
    [Console]::InputEncoding = $utf8
    [Console]::OutputEncoding = $utf8
    $OutputEncoding = $utf8
} catch {}
function global:prompt {
    Write-Host 'bb ' -ForegroundColor Green -NoNewline
    Write-Host (Get-Location).Path -ForegroundColor Gray -NoNewline
    Write-Host ' ❯ ' -ForegroundColor Green -NoNewline
    return ' '
}
function global:edit {
    if ($args.Count -ne 1) {
        Write-Host 'Usage: edit <file.c>' -ForegroundColor Yellow
        return
    }
    $sourcePath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath([string]$args[0])
    & $env:PYKUAI_BB_PYTHON -m pykuai.bench.edit_entry $sourcePath
}
function global:gg { $Host.SetShouldExit(0) }
Write-Host 'Build Bench · C / Windows x64 · Clang · gg to return' -ForegroundColor Green
Write-Host 'edit <file.c>  ·  clang <file.c> -o <app.exe>  ·  .\<app.exe>' -ForegroundColor Gray
"""


def run_shell(clang_path: Path) -> int:
    """Open a native shell in this terminal, with a session-local toolchain."""
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    env = os.environ.copy()
    env["PATH"] = str(clang_path.parent) + os.pathsep + env.get("PATH", "")
    env["PYKUAI_BB_PYTHON"] = sys.executable
    startup = base64.b64encode(_STARTUP.encode("utf-16-le")).decode("ascii")
    cmd = [str(powershell), "-NoLogo", "-NoProfile", "-NoExit", "-EncodedCommand", startup]
    with subprocess.Popen(cmd, env=env) as shell:
        while True:
            try:
                return shell.wait()
            except KeyboardInterrupt:
                # Ctrl+C is delivered to the foreground program in this same
                # console. Keep the Python caller waiting for the shell's gg.
                continue
