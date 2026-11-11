# 🐍 PyKuai (Cyber Script Workbench)

> **Modular Cyber-Dark CLI Script Workbench & Plug-in Automation Toolkit**  
> *"The Lord is my shepherd."* — Author: **TuKuai** | Username: **GallantTarry**

---

## 🌟 Core Philosophy & Architecture

`pykuai` is a minimalist, high-extensibility CLI script workbench powered by `rich`. Built on a microkernel + plug-in engine architecture, it lets you add new command-line utilities simply by dropping a Python module into `pykuai/engines/`—no boilerplate registration or GUI clutter required.

```text
pykuai/
├── pyproject.toml              # Package metadata & global CLI entrypoint (pykuai)
├── pykuai/
│   ├── cli.py                  # Master console: Interactive REPL vs Direct CLI execution
│   ├── core/
│   │   ├── base.py             # BaseEngine contract (name, description, usage, requires, args, direct, interactive)
│   │   ├── deps.py             # Global Pull Packages (`pp`) dependency scanner & installer
│   │   ├── registry.py         # Dynamic engine auto-discovery & registration
│   │   ├── intro.py            # High-DPI desktop pixel snake intro animation
│   │   ├── ui.py               # Cyber-dark Rich theme, banner, progress bars & identity hooks
│   │   ├── tui.py              # Mouse-clickable interactive terminal UI widgets (Textual)
│   │   ├── watchdog.py         # Background Windows Terminal settings.json lifecycle guard
│   │   └── tools.py            # Bundled & system binary locator (FFmpeg, UnRAR, yt-dlp)
│   ├── engines/                # Plug-and-play script engines
│   │   └── ico_maker.py        # ico: PNG to multi-resolution Windows ICO container
│   └── assets/                 # Multi-res High-DPI icon assets
```

---

## 🚀 Dual-Mode Execution

### 1. Interactive Console Mode (`pykuai`)
Run `pykuai` in any terminal to enter the Cyber-Dark REPL console:

```bash
pykuai
# Skip intro animation:
pykuai --fast
```

Built-in console commands (strictly 1-to-1 unique):
* `hh` — Help Hub (show all registered engines, syntax, and usage examples)
* `cc` — Clear console and refresh banner
* `pp` — Pull Packages (inspect and install global dependencies visually)
* `gg` — Exit safely (automatically restores terminal title & icon)
* Drag and drop an image file directly into the console to invoke the `ico` engine automatically

### 2. Direct CLI Mode (`pykuai <command>`)
Execute engines directly from the shell without entering the REPL—ideal for scripts and pipelines:

```bash
# Convert a PNG to a multi-resolution Windows .ico file
pykuai ico logo.png

# Specify custom layer sizes and output path
pykuai ico logo.png -s 16,32,48,256 -o app.ico

# Inspect or install global script dependencies
pykuai pp --check
pykuai pp -y

# Show CLI help or version
pykuai hh
pykuai --version
```

---

## 🛠️ Installation & Local Development

Install in editable mode from the repository root:

```bash
pip install -e .
```

Once installed, the `pykuai` command is available globally from any terminal directory.

---

## 🧩 Writing New Script Engines (Plug-and-Play)

Create a new `.py` file inside `pykuai/engines/` (for example, `doc_pdf.py`) and subclass `BaseEngine`:

```python
# -*- coding: utf-8 -*-
import argparse
from rich.console import Console
from pykuai.core.base import BaseEngine


class MyToolEngine(BaseEngine):
    name = "pdf"
    description = "Merge or split PDF documents"
    usage = "pdf <files> [-o output]"
    category = "Document"
    requires = ["pypdf>=3.0.0"]

    def register_args(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("files", nargs="*", help="Input PDF file paths")
        parser.add_argument("-o", "--output", default="merged.pdf", help="Output file path")

    def run_direct(self, args: argparse.Namespace, console: Console) -> int:
        if not args.files:
            return self.run_interactive(console)
        console.print(f"[#00FF00]Processing {len(args.files)} file(s)...[/#00FF00]")
        return 0

    def run_interactive(self, console: Console) -> int:
        from pykuai.core.tui import pick_one
        mode = pick_one("Select PDF Action", [("Merge PDFs", "merge"), ("Split PDF", "split")])
        if mode:
            console.print(f"[#00FF00]Selected mode: {mode}[/#00FF00]")
        return 0
```

Save the file and launch `pykuai`. Auto-discovery picks it up immediately and lists it in `hh`, and `pp` detects its `requires` / imports automatically without modifying any core files.
