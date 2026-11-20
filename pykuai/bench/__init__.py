"""Build Bench: a same-window C workbench for Windows x64."""

import argparse
import os
from pathlib import Path
import signal
import subprocess


def run_bench(console, arguments):
    parser = argparse.ArgumentParser(
        prog="pykuai bb",
        description="Open Build Bench, or compile a C source file to a Windows executable.",
    )
    parser.add_argument("source", nargs="?", type=Path, help="C file to compile without running it")
    parser.add_argument("-o", "--output", type=Path, default=None, help="Output .exe path (default: <source>.exe)")
    try:
        args = parser.parse_args(arguments)
    except SystemExit as exc:
        return exc.code

    source = args.source
    if source is not None and (source.suffix.lower() != ".c" or not source.is_file()):
        console.print(f"Expected an existing .c file: {source}", style="red", markup=False)
        return 2
    if source is None and args.output is not None:
        console.print("-o/--output requires a .c source file.", style="red", markup=False)
        return 2

    # The home console normally exits on Ctrl+C. Cancelling this tool returns there.
    previous_sigint = signal.signal(signal.SIGINT, signal.default_int_handler)
    try:
        from .toolchain import ensure_toolchain

        clang = ensure_toolchain(console)
        if source is None:
            from .shell import run_shell
            return run_shell(clang)

        output = args.output if args.output is not None else source.with_suffix(".exe")
        if output.suffix.lower() != ".exe":
            output = output.with_suffix(".exe")
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [str(clang), str(source.resolve()), "-o", str(output.resolve())]
        console.print(subprocess.list2cmdline(["clang", str(source), "-o", str(output)]),
                      style="green", markup=False)
        env = os.environ.copy()
        env["PATH"] = str(clang.parent) + os.pathsep + env.get("PATH", "")
        result = subprocess.run(command, env=env)
        if result.returncode == 0:
            console.print(f"Built {output}", style="green", markup=False)
        return result.returncode
    except KeyboardInterrupt:
        console.print("Build Bench cancelled.", style="yellow")
        return 130
    except (OSError, RuntimeError) as exc:
        console.print(f"Build Bench: {exc}", style="red", markup=False)
        return 1
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
