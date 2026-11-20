"""Child process used by the Build Bench PowerShell edit command."""

from pathlib import Path
import sys


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: edit <file.c>", file=sys.stderr)
        return 2
    from .editor import edit_file

    try:
        edit_file(Path(sys.argv[1]))
    except (OSError, UnicodeError, ValueError) as error:
        print(f"edit: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
